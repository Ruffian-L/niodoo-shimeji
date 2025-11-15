"""PySide6 overlay for speech bubbles and interactive chat."""

from __future__ import annotations

from modules.chat_database import ChatDatabase

import html
import json
import logging
import os
import queue
import threading
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Tuple

LOGGER = logging.getLogger(__name__)


def _send_notification(author: str, text: str) -> None:
    """Send a desktop notification using notify-send as a fallback."""
    import subprocess
    try:
        subprocess.run(
            ["notify-send", "-t", "5000", "-u", "normal", author, text],
            check=False,
            timeout=2,
        )
    except Exception as exc:
        LOGGER.debug("Failed to send notification: %s", exc)


@dataclass
class DialogueEntry:
    text: str
    duration: int
    author: str = "Shimeji"


class SpeechBubbleOverlay:
    """Threaded Qt overlay that displays queued dialogue snippets AND a persistent chat panel."""

    def __init__(self) -> None:
        self._queue: "queue.Queue[DialogueEntry]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._started = threading.Event()
        self._shutdown = threading.Event()
        self._chat_queue: "queue.Queue[Tuple[str, Optional[str], Optional[str]]]" = queue.Queue()
        self._prompt_sender: Optional[Callable[[str], None]] = None
        self._anchor_lock = threading.Lock()
        self._anchor: Optional[Tuple[float, float]] = None
        self._state_machine: Optional[Any] = None  # MascotStateMachine instance

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="SpeechBubbleOverlay", daemon=True)
        self._thread.start()
        self._started.wait(timeout=10)

    def stop(self) -> None:
        self._shutdown.set()
        if self._thread and self._thread.is_alive():
            self._queue.put(DialogueEntry("", 0))
            self._thread.join(timeout=5)

    def enqueue(self, messages: Iterable[Dict[str, str]]) -> None:
        for message in messages:
            text = message.get("text", "").strip()
            if not text:
                continue
            try:
                duration = int(message.get("duration", 6))
            except (TypeError, ValueError):
                duration = 6
            author = message.get("author", "Shimeji")
            LOGGER.debug("Enqueuing bubble: %s - %s (duration %d)", author, text, duration)
            self._queue.put(
                DialogueEntry(text=text, duration=max(2, min(duration, 30)), author=author)
            )

    def set_prompt_sender(self, sender: Callable[[str], None]) -> None:
        self._prompt_sender = sender

    def show_chat_message(self, author: str, text: str) -> None:
        """Add message to persistent chat panel only."""
        self._chat_queue.put(("message", author, text))

    def open_chat_panel(self) -> None:
        self._chat_queue.put(("open", None, None))

    def show_bubble_message(self, author: str, text: str, duration: int = 6) -> None:
        """Show a temporary bubble above the Shimeji."""
        LOGGER.debug("Queueing bubble: %s - %s", author, text)
        self._queue.put(DialogueEntry(text=text, duration=duration, author=author))

    def update_anchor(self, x: Optional[float], y: Optional[float]) -> None:
        with self._anchor_lock:
            if x is None or y is None:
                self._anchor = None
            else:
                self._anchor = (float(x), float(y))

    def _get_anchor(self) -> Optional[Tuple[float, float]]:
        with self._anchor_lock:
            return self._anchor

    # ------------------------------------------------------------------
    # Qt Event Loop (executed in background thread)
    # ------------------------------------------------------------------
    def _run(self) -> None:  # pragma: no cover - requires GUI environment
        try:
            from PySide6.QtCore import Qt, QTimer, Signal, QUrl
            from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QPainter, QPalette, QKeyEvent
            from PySide6.QtWidgets import (
                QApplication,
                QCheckBox,
                QComboBox,
                QFrame,
                QHBoxLayout,
                QLabel,
                QLineEdit,
                QMenu,
                QPushButton,
                QTextEdit,
                QVBoxLayout,
                QWidget,
            )
        except ImportError as exc:  # pragma: no cover - import guard
            LOGGER.error("PySide6 is required for the speech bubble overlay: %s", exc)
            return

        app = QApplication.instance() or QApplication([])
        self._started.set()
        overlay_ref = self
        
        # Initialize mascot state machine
        try:
            from modules.mascot_state_machine import MascotStateMachine
            overlay_ref._state_machine = MascotStateMachine()
            if overlay_ref._state_machine.is_available():
                LOGGER.info("Mascot state machine initialized in Qt thread")
        except Exception as exc:
            LOGGER.warning("Failed to initialize state machine: %s", exc)
            overlay_ref._state_machine = None
        
        # Create shared chat database instance
        chat_db = ChatDatabase()

        def current_anchor() -> Optional[Tuple[int, int]]:
            anchor = overlay_ref._get_anchor()
            if anchor is None:
                return None
            return int(anchor[0]), int(anchor[1])

        # ============================================================
        # CHAT WINDOW #1: Persistent panel (left side, for typing)
        # ============================================================
        class ChatWindow(QWidget):
            user_submitted = Signal(str)

            def __init__(self, chat_db: Optional[ChatDatabase] = None) -> None:
                super().__init__()
                self.setWindowTitle("Shimeji Chat Log")
                self.setWindowFlag(Qt.Window, True)
                self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
                # Make it movable - keep title bar
                # self.setWindowFlag(Qt.FramelessWindowHint, True)
                
                # Set explicit dark background to prevent white box flash
                self.setStyleSheet("QWidget { background-color: #1a1a1a; }")
                
                # Size based on screen - 35% of screen width, wider and shorter
                screen = QApplication.primaryScreen()
                if screen:
                    screen_geometry = screen.availableGeometry()
                    # 35% of screen width, height is 40% of width (wider and shorter)
                    width = int(screen_geometry.width() * 0.35)
                    height = int(width * 0.4)  # Make it wider (width is 2.5x height)
                    # Minimum and maximum constraints
                    width = max(500, min(width, 1000))  # Between 500-1000px wide
                    height = max(300, min(height, 600))  # Between 300-600px tall
                    self.resize(width, height)
                else:
                    # Fallback if screen detection fails
                    self.resize(700, 280)  # Wide and short default
                
                # Enable drag-and-drop for file analysis
                self.setAcceptDrops(True)

                self._history = QTextEdit(self)
                self._history.setReadOnly(True)
                self._history.setStyleSheet(
                    "QTextEdit { background-color: #1a1a1a; color: #00ff00; font-size: 11pt; border: 2px solid #00ff00; }"
                )

                # Initialize chat database
                self._chat_db = chat_db or ChatDatabase()
                # Create a new session for this run
                self._session_id = self._chat_db.create_new_session()
                LOGGER.info("Created new chat session %d", self._session_id)
                
                # Load messages from current session
                self._chat_history: List[Dict[str, str]] = self._chat_db.get_messages(self._session_id)
                for msg in self._chat_history:
                    self.append_message(msg["author"], msg["text"], persist=False)

                self._input = QLineEdit(self)
                self._input.setPlaceholderText("Type a message...")
                self._input.setStyleSheet("QLineEdit { background-color: #2a2a2a; color: white; }")
                self._input.returnPressed.connect(self._on_submit)

                self._send = QPushButton("Send", self)
                self._send.clicked.connect(self._on_submit)

                self._close = QPushButton("×", self)
                self._close.setFixedSize(24, 24)
                self._close.clicked.connect(self.hide)

                # Typing indicator
                self._typing_indicator = QLabel("Shimeji is thinking...", self)
                self._typing_indicator.setStyleSheet("QLabel { color: #888; font-style: italic; }")
                self._typing_indicator.hide()
                self._typing_timer: Optional[QTimer] = None
                self._typing_dots = 0
                
                # Search box
                self._search_box = QLineEdit(self)
                self._search_box.setPlaceholderText("Search history...")
                self._search_box.setStyleSheet("QLineEdit { background-color: #2a2a2a; color: white; }")
                self._search_box.textChanged.connect(self._filter_history)
                
                # Export button
                self._export_button = QPushButton("Export", self)
                self._export_button.clicked.connect(self.export_to_markdown)
                self._export_button.setStyleSheet("QPushButton { background-color: #3a3a3a; color: white; }")
                
                # Import button
                self._import_button = QPushButton("Import", self)
                self._import_button.clicked.connect(self.import_from_file)
                self._import_button.setStyleSheet("QPushButton { background-color: #3a3a3a; color: white; }")
                
                # Open folder button (opens exports directory)
                self._open_folder_button = QPushButton("📁", self)
                self._open_folder_button.setToolTip("Open exports folder")
                self._open_folder_button.clicked.connect(self.open_exports_folder)
                self._open_folder_button.setStyleSheet("QPushButton { background-color: #3a3a3a; color: white; font-size: 14pt; }")
                self._open_folder_button.setFixedWidth(40)
                
                # Clipboard button - ask Gemini about clipboard
                self._clipboard_button = QPushButton("📋", self)
                self._clipboard_button.setToolTip("Ask Gemini about your clipboard")
                self._clipboard_button.clicked.connect(self._on_clipboard_clicked)
                self._clipboard_button.setStyleSheet("QPushButton { background-color: #3a3a3a; color: white; font-size: 14pt; }")
                self._clipboard_button.setFixedWidth(40)
                
                # Monitoring alerts menu button
                self._alerts_menu_button = QPushButton("🔔", self)
                self._alerts_menu_button.setToolTip("Configure monitoring alerts")
                self._alerts_menu_button.setStyleSheet("QPushButton { background-color: #3a3a3a; color: white; font-size: 14pt; }")
                self._alerts_menu_button.setFixedWidth(40)
                self._alerts_menu = QMenu(self)
                self._alerts_menu_button.setMenu(self._alerts_menu)
                self._setup_alerts_menu()

                controls = QHBoxLayout()
                controls.addWidget(self._input)
                controls.addWidget(self._close)
                controls.addWidget(self._send)

                layout = QVBoxLayout(self)
                layout.setContentsMargins(8, 8, 8, 8)
                layout.addWidget(self._history)
                layout.addWidget(self._typing_indicator)
                search_layout = QHBoxLayout()
                search_layout.addWidget(self._search_box)
                search_layout.addWidget(self._clipboard_button)
                search_layout.addWidget(self._alerts_menu_button)
                search_layout.addWidget(self._open_folder_button)
                search_layout.addWidget(self._import_button)
                search_layout.addWidget(self._export_button)
                layout.addLayout(search_layout)
                layout.addLayout(controls)

                self.dock()
                self.show()
                self.raise_()
                self.activateWindow()
                LOGGER.info("Chat panel initialized at %s", self.pos())

            def dock(self) -> None:
                """Position chat window in bottom-right corner of screen."""
                screen = QApplication.primaryScreen()
                if not screen:
                    return
                geometry = screen.availableGeometry()
                # Position in bottom-right with some margin
                x = geometry.right() - self.width() - 20
                y = geometry.bottom() - self.height() - 20
                self.move(x, y)

            def show_panel(self) -> None:
                self.dock()
                self.show()
                self.raise_()
                self.activateWindow()

            def append_message(self, author: str, text: str, persist: bool = True) -> None:
                author = author or "Shimeji"
                text = text or ""
                escaped_text = html.escape(text)
                self._history.append(f"<b style='color:#00ffff'>{html.escape(author)}:</b> {escaped_text}")
                bar = self._history.verticalScrollBar()
                bar.setValue(bar.maximum())
                if persist:
                    # Save to database
                    self._chat_db.add_message(author, text, self._session_id)
                    # Also update local cache for filtering
                    self._chat_history.append({"author": author, "text": text})

            def _on_submit(self) -> None:
                text = self._input.text().strip()
                if not text:
                    return
                self._input.clear()
                self.append_message("You", text)
                if overlay_ref._prompt_sender:
                    try:
                        overlay_ref._prompt_sender(text)
                    except Exception as exc:  # pragma: no cover - callback errors
                        LOGGER.exception("Prompt sender raised: %s", exc)
            
            def _setup_alerts_menu(self) -> None:
                """Set up the monitoring alerts dropdown menu with checkboxes."""
                try:
                    from modules.memory_manager import MemoryManager
                    self._memory_manager = MemoryManager()
                except Exception as exc:
                    LOGGER.error("Failed to initialize memory manager for alerts menu: %s", exc)
                    return
                
                # Alert types with their preference keys and display names
                alert_types = [
                    ("ram", "RAM Alerts"),
                    ("gpu", "GPU Alerts"),
                    ("disk", "Disk Alerts"),
                    ("zombie", "Zombie Process Alerts"),
                    ("network", "Network Alerts"),
                    ("log", "Log Alerts"),
                ]
                
                self._alert_checkboxes = {}
                
                for alert_type, display_name in alert_types:
                    # Get current state (default: enabled)
                    enabled = self._memory_manager.get_pref(f"alert_enabled_{alert_type}", True)
                    
                    # Create checkbox action
                    action = self._alerts_menu.addAction(display_name)
                    action.setCheckable(True)
                    action.setChecked(enabled)
                    
                    # Connect to toggle handler (capture both variables properly)
                    def make_toggle_handler(atype: str, dname: str):
                        def toggle_handler(checked: bool) -> None:
                            self._memory_manager.set_pref(f"alert_enabled_{atype}", checked)
                            status = "enabled" if checked else "disabled"
                            self.append_message("System", f"{dname} {status}")
                            LOGGER.info("Alert type %s %s", atype, status)
                        return toggle_handler
                    
                    action.triggered.connect(make_toggle_handler(alert_type, display_name))
                    self._alert_checkboxes[alert_type] = action
            
            def _on_clipboard_clicked(self) -> None:
                """Read clipboard and ask Gemini about it."""
                try:
                    from modules.productivity_tools import ProductivityTools
                    clipboard_content = ProductivityTools.read_clipboard()
                    if clipboard_content:
                        # Show what was copied
                        preview = clipboard_content[:200] + "..." if len(clipboard_content) > 200 else clipboard_content
                        self.append_message("You", f"[Clipboard] {preview}")
                        # Ask Gemini about it
                        prompt = f"Here's what I copied to my clipboard:\n\n{clipboard_content[:5000]}\n\nCan you help me with this?"
                        if overlay_ref._prompt_sender:
                            try:
                                overlay_ref._prompt_sender(prompt)
                            except Exception as exc:
                                LOGGER.exception("Prompt sender raised: %s", exc)
                    else:
                        self.append_message("System", "Clipboard is empty!")
                except Exception as exc:
                    LOGGER.exception("Failed to read clipboard: %s", exc)
                    self.append_message("System", f"Failed to read clipboard: {exc}")
            
            def dragEnterEvent(self, event: QDragEnterEvent) -> None:
                """Handle drag enter event for file drops."""
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()
                else:
                    event.ignore()
            
            def dropEvent(self, event: QDropEvent) -> None:
                """Handle file drop event."""
                files = [url.toLocalFile() for url in event.mimeData().urls()]
                for file_path in files:
                    self._handle_dropped_file(file_path)
                event.acceptProposedAction()
            
            def _handle_dropped_file(self, file_path: str) -> None:
                """Analyze a dropped file with Gemini."""
                from pathlib import Path
                import mimetypes
                
                # Publish FILE_DROPPED event to event bus (P2.4)
                try:
                    # Try to get agent reference from overlay
                    if hasattr(overlay_ref, '_agent_ref'):
                        agent = overlay_ref._agent_ref
                        if agent and hasattr(agent, '_event_bus'):
                            from modules.event_bus import EventType
                            agent._event_bus.publish(
                                EventType.FILE_DROPPED,
                                {"file_path": file_path, "source": "chat_window"}
                            )
                except Exception as exc:
                    LOGGER.debug("Failed to publish FILE_DROPPED event: %s", exc)
                
                file_path_obj = Path(file_path)
                if not file_path_obj.exists():
                    self.append_message("System", f"File not found: {file_path}")
                    return
                
                file_name = file_path_obj.name
                file_ext = file_path_obj.suffix.lower()
                mime_type, _ = mimetypes.guess_type(str(file_path))
                
                # Show that we're processing the file
                self.append_message("You", f"📎 Dropped: {file_name}")
                
                # Determine file type and handle accordingly
                if mime_type and mime_type.startswith('image/'):
                    # Image file - use vision API
                    self._analyze_image_file(file_path)
                elif file_ext == '.pdf':
                    # PDF file - extract text
                    self._analyze_pdf_file(file_path)
                elif file_ext in ['.md', '.txt', '.py', '.js', '.ts', '.html', '.css', '.json', '.yaml', '.yml', '.xml', '.csv', '.sh', '.bash', '.zsh']:
                    # Text-based file - read and analyze
                    self._analyze_text_file(file_path)
                else:
                    # Unknown file type - try to read as text
                    self.append_message("System", f"Unknown file type: {file_ext}. Trying to read as text...")
                    self._analyze_text_file(file_path)
            
            def _analyze_image_file(self, image_path: str) -> None:
                """Analyze an image file using Gemini Vision API."""
                if not overlay_ref._prompt_sender:
                    self.append_message("System", "Error: Cannot analyze image - agent not available")
                    return
                
                # Use the agent's vision analysis method
                # We'll need to call it via the prompt sender with a special format
                prompt = f"[IMAGE_ANALYZE:{image_path}] What do you see in this image? Describe it in detail and help me understand what's in it."
                try:
                    overlay_ref._prompt_sender(prompt)
                except Exception as exc:
                    LOGGER.exception("Failed to analyze image: %s", exc)
                    self.append_message("System", f"Failed to analyze image: {exc}")
            
            def _analyze_pdf_file(self, pdf_path: str) -> None:
                """Extract text from PDF and analyze with Gemini."""
                from pathlib import Path
                try:
                    # Try PyPDF2 first
                    try:
                        import PyPDF2
                        with open(pdf_path, 'rb') as f:
                            pdf_reader = PyPDF2.PdfReader(f)
                            text_content = ""
                            for page_num, page in enumerate(pdf_reader.pages):
                                text_content += f"\n--- Page {page_num + 1} ---\n"
                                text_content += page.extract_text()
                    except ImportError:
                        # Fallback: try pdfplumber
                        try:
                            import pdfplumber
                            with pdfplumber.open(pdf_path) as pdf:
                                text_content = ""
                                for page_num, page in enumerate(pdf.pages):
                                    text_content += f"\n--- Page {page_num + 1} ---\n"
                                    text_content += page.extract_text() or ""
                        except ImportError:
                            self.append_message("System", "PDF parsing requires PyPDF2 or pdfplumber. Install with: pip install PyPDF2")
                            return
                    
                    if not text_content.strip():
                        self.append_message("System", "Could not extract text from PDF (might be image-based)")
                        return
                    
                    # Send to Gemini for analysis (increased limit for long documents)
                    # Truncate to 100k chars to allow for very long documents while staying within API limits
                    truncated_text = text_content[:100000] if len(text_content) > 100000 else text_content
                    if len(text_content) > 100000:
                        truncated_text += f"\n\n[Note: Document truncated from {len(text_content)} to 100,000 characters]"
                    prompt = f"I dropped a PDF file ({Path(pdf_path).name}). Here's the extracted text:\n\n{truncated_text}\n\nCan you analyze this document thoroughly and help me understand it? Please provide a comprehensive analysis."
                    if overlay_ref._prompt_sender:
                        try:
                            overlay_ref._prompt_sender(prompt)
                        except Exception as exc:
                            LOGGER.exception("Failed to analyze PDF: %s", exc)
                            self.append_message("System", f"Failed to analyze PDF: {exc}")
                except Exception as exc:
                    LOGGER.exception("Failed to read PDF: %s", exc)
                    self.append_message("System", f"Failed to read PDF: {exc}")
            
            def _analyze_text_file(self, file_path: str) -> None:
                """Read text file and analyze with Gemini."""
                from pathlib import Path
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    if not content.strip():
                        self.append_message("System", "File is empty")
                        return
                    
                    file_name = Path(file_path).name
                    # Send to Gemini for analysis (increased limit for long documents)
                    # Truncate to 100k chars to allow for very long documents while staying within API limits
                    truncated_content = content[:100000] if len(content) > 100000 else content
                    if len(content) > 100000:
                        truncated_content += f"\n\n[Note: File truncated from {len(content)} to 100,000 characters]"
                    prompt = f"I dropped a file ({file_name}). Here's its content:\n\n{truncated_content}\n\nCan you analyze this thoroughly and help me understand it? Please provide a comprehensive analysis."
                    if overlay_ref._prompt_sender:
                        try:
                            overlay_ref._prompt_sender(prompt)
                        except Exception as exc:
                            LOGGER.exception("Failed to analyze text file: %s", exc)
                            self.append_message("System", f"Failed to analyze file: {exc}")
                except Exception as exc:
                    LOGGER.exception("Failed to read file: %s", exc)
                    self.append_message("System", f"Failed to read file: {exc}")

            
            def keyPressEvent(self, event: QKeyEvent) -> None:
                """Handle keyboard shortcuts."""
                if event.key() == Qt.Key_Escape:
                    self.hide()
                elif event.key() == Qt.Key_Return and event.modifiers() & Qt.ControlModifier:
                    self._on_submit()
                elif event.key() == Qt.Key_Tab:
                    self._input.setFocus()
                else:
                    super().keyPressEvent(event)
            
            def show_typing(self) -> None:
                """Show typing indicator with animated dots."""
                self._typing_indicator.show()
                self._typing_dots = 0
                if self._typing_timer:
                    self._typing_timer.stop()
                self._typing_timer = QTimer(self)
                self._typing_timer.timeout.connect(self._animate_typing)
                self._typing_timer.start(500)
            
            def hide_typing(self) -> None:
                """Hide typing indicator."""
                self._typing_indicator.hide()
                if self._typing_timer:
                    self._typing_timer.stop()
                    self._typing_timer = None
            
            def _animate_typing(self) -> None:
                """Animate typing dots."""
                self._typing_dots = (self._typing_dots + 1) % 4
                dots = "." * self._typing_dots
                self._typing_indicator.setText(f"Shimeji is thinking{dots}")
            
            def _filter_history(self, query: str) -> None:
                """Filter displayed messages by search query."""
                if not query:
                    # Show all messages
                    self._history.clear()
                    for msg in self._chat_history:
                        self.append_message(msg["author"], msg["text"], persist=False)
                    return
                
                # Filter messages
                query_lower = query.lower()
                self._history.clear()
                for msg in self._chat_history:
                    if query_lower in msg.get("author", "").lower() or query_lower in msg.get("text", "").lower():
                        self.append_message(msg["author"], msg["text"], persist=False)
            
            def export_to_markdown(self, path: Optional[str] = None) -> None:
                """Export current chat session as markdown or JSON."""
                try:
                    from pathlib import Path
                    from PySide6.QtWidgets import QFileDialog
                    
                    # Default export directory
                    export_dir = Path.cwd()
                    default_filename = f"chat_export_{self._session_id}.md"
                    default_path = str(export_dir / default_filename)
                    
                    if path is None:
                        file_path, selected_filter = QFileDialog.getSaveFileName(
                            self,
                            "Export Chat Session",
                            default_path,
                            "Markdown (*.md);;JSON (*.json);;All Files (*)"
                        )
                        if not file_path or not isinstance(file_path, str):
                            return
                        path = file_path
                    
                    # Determine format from extension
                    if isinstance(path, str):
                        format_type = "json" if path.lower().endswith(".json") else "markdown"
                    else:
                        format_type = "markdown"
                    
                    # Export using database
                    exported_path = self._chat_db.export_session_to_file(
                        session_id=self._session_id,
                        file_path=path,
                        format=format_type
                    )
                    
                    LOGGER.info("Chat session exported to %s", exported_path)
                    self.append_message("System", f"Exported to {exported_path}", persist=False)
                except Exception as exc:
                    LOGGER.error("Failed to export chat session: %s", exc)
                    self.append_message("System", f"Export failed: {exc}", persist=False)
            
            def open_exports_folder(self) -> None:
                """Open the exports folder in the file manager."""
                try:
                    import subprocess
                    from pathlib import Path
                    
                    export_dir = Path.cwd()
                    
                    # Try to open folder in default file manager
                    import platform
                    system = platform.system()
                    
                    if system == "Linux":
                        # Try xdg-open first (works on most Linux)
                        subprocess.Popen(["xdg-open", str(export_dir)], 
                                       stdout=subprocess.DEVNULL, 
                                       stderr=subprocess.DEVNULL)
                    elif system == "Darwin":  # macOS
                        subprocess.Popen(["open", str(export_dir)],
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
                    elif system == "Windows":
                        subprocess.Popen(["explorer", str(export_dir)],
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
                    
                    self.append_message("System", f"Opened folder: {export_dir}", persist=False)
                except Exception as exc:
                    LOGGER.error("Failed to open exports folder: %s", exc)
                    self.append_message("System", f"Failed to open folder: {exc}", persist=False)
            
            def import_from_file(self) -> None:
                """Import a chat session from a JSON file."""
                try:
                    from pathlib import Path
                    from PySide6.QtWidgets import QFileDialog, QMessageBox
                    
                    # Default to current directory (where exports are typically saved)
                    import_dir = str(Path.cwd().absolute())
                    
                    file_path, _ = QFileDialog.getOpenFileName(
                        self,
                        "Import Chat Session",
                        import_dir,  # Start in current directory (where exports are saved)
                        "JSON Files (*.json);;Markdown Files (*.md);;All Files (*)"
                    )
                    
                    if not file_path:
                        return
                    
                    # Ask user if they want to create new session or append to current
                    reply = QMessageBox.question(
                        self,
                        "Import Chat",
                        "Create a new session with imported messages?\n\n"
                        "Yes = New session\nNo = Append to current session",
                        QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
                    )
                    
                    if reply == QMessageBox.Cancel:
                        return
                    
                    create_new = reply == QMessageBox.Yes
                    
                    # Import using database
                    imported_session_id = self._chat_db.import_session(file_path, create_new=create_new)
                    
                    if create_new:
                        # Switch to new session
                        self._session_id = imported_session_id
                        self._chat_history = self._chat_db.get_messages(self._session_id)
                        # Reload UI
                        self._history.clear()
                        for msg in self._chat_history:
                            self.append_message(msg["author"], msg["text"], persist=False)
                    
                    LOGGER.info("Chat session imported into session %d", imported_session_id)
                    self.append_message(
                        "System",
                        f"Imported into session {imported_session_id}",
                        persist=False
                    )
                except Exception as exc:
                    LOGGER.error("Failed to import chat session: %s", exc)
                    self.append_message("System", f"Import failed: {exc}", persist=False)

        # ============================================================
        # CHAT WINDOW #2: Bubble box (follows Shimeji, read-only)
        # ============================================================
        class BubbleBox(QWidget):
            """A chat bubble that follows the Shimeji and shows the most recent message."""
            def __init__(self) -> None:
                super().__init__()
                self.setWindowTitle("Shimeji Speech")
                self.setWindowFlag(Qt.Window, True)
                self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
                self.setWindowFlag(Qt.FramelessWindowHint, True)
                self.setAttribute(Qt.WA_TranslucentBackground, True)
                # Ensure widget background is transparent
                self.setStyleSheet("QWidget { background-color: transparent; }")
                
                self._current_text = QTextEdit(self)
                self._current_text.setReadOnly(True)
                self._current_text.setFrameStyle(QFrame.NoFrame)
                self._current_text.setStyleSheet(
                    "QTextEdit { background-color: rgba(255, 255, 255, 220); color: #000000; font-size: 13pt; "
                    "border-radius: 12px; padding: 10px; }"
                )
                self._current_text.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                self._current_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                self._current_text.setLineWrapMode(QTextEdit.WidgetWidth)

                layout = QVBoxLayout(self)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.addWidget(self._current_text)

                self.setMinimumWidth(250)
                self.setMaximumWidth(500)
                self.setMinimumHeight(80)
                self.setMaximumHeight(400)

                # Hide immediately before any timers start to prevent flash
                self.hide()
                self.setVisible(False)
                
                # Track if we have content to show
                self._has_content = False

                self._reposition_timer = QTimer(self)
                self._reposition_timer.timeout.connect(self._update_position)
                # Only start timer if we have content and anchor
                # Timer will be started when message is added

                self._fade_timer: Optional[QTimer] = None
                self._current_opacity = 1.0
                
                # Enable drag-and-drop on mascot bubble (P2.4)
                self.setAcceptDrops(True)

                LOGGER.info("Bubble box initialized (hidden)")
            
            def dragEnterEvent(self, event: QDragEnterEvent) -> None:
                """Handle drag enter event for file/text drops on mascot."""
                if event.mimeData().hasUrls() or event.mimeData().hasText():
                    event.acceptProposedAction()
                else:
                    event.ignore()
            
            def dropEvent(self, event: QDropEvent) -> None:
                """Handle drop event on mascot - publish to event bus."""
                # Publish FILE_DROPPED event (P2.4)
                try:
                    if hasattr(overlay_ref, '_agent_ref'):
                        agent = overlay_ref._agent_ref
                        if agent and hasattr(agent, '_event_bus'):
                            from modules.event_bus import EventType
                            
                            if event.mimeData().hasUrls():
                                # File drop
                                files = [url.toLocalFile() for url in event.mimeData().urls()]
                                for file_path in files:
                                    agent._event_bus.publish(
                                        EventType.FILE_DROPPED,
                                        {"file_path": file_path, "source": "mascot"}
                                    )
                            elif event.mimeData().hasText():
                                # Text drop
                                text = event.mimeData().text()
                                agent._event_bus.publish(
                                    EventType.FILE_DROPPED,
                                    {"text": text, "source": "mascot"}
                                )
                except Exception as exc:
                    LOGGER.debug("Failed to publish FILE_DROPPED event: %s", exc)
                
                event.acceptProposedAction()

            def cleanup(self) -> None:
                """Clean up Qt timers."""
                if self._fade_timer:
                    self._fade_timer.stop()
                    self._fade_timer = None
                if self._reposition_timer:
                    self._reposition_timer.stop()
                    self._reposition_timer = None

            def add_message(self, author: str, text: str, duration: int = 6) -> None:
                """Show a new message, replacing the previous one."""
                # Don't show empty messages
                if not text or not text.strip():
                    self._has_content = False
                    self.hide()
                    if self._reposition_timer and self._reposition_timer.isActive():
                        self._reposition_timer.stop()
                    return
                
                # Don't show if there's no anchor (Shimeji position)
                anchor = current_anchor()
                if not anchor:
                    LOGGER.debug("BubbleBox: No anchor available, not showing message")
                    self._has_content = False
                    self.hide()
                    if self._reposition_timer and self._reposition_timer.isActive():
                        self._reposition_timer.stop()
                    return
                
                # Set content flag before showing
                self._has_content = True
                
                escaped_text = html.escape(text)
                display = f"<b style='color:#333'>{html.escape(author)}:</b><br>{escaped_text}"
                self._current_text.setHtml(display)
                
                # Adjust size based on content with proper word wrapping
                self._current_text.document().setTextWidth(450)  # Force wrap at this width
                doc_size = self._current_text.document().size()
                new_width = min(500, max(250, int(doc_size.width()) + 60))
                new_height = min(400, max(80, int(doc_size.height()) + 50))
                self.setFixedSize(new_width, new_height)
                
                # Position first, then show
                self._update_position()
                
                # Show and reset opacity
                self._current_opacity = 1.0
                self.setWindowOpacity(self._current_opacity)
                self.show()
                self.raise_()
                
                # Start reposition timer now that we have content
                if not self._reposition_timer.isActive():
                    self._reposition_timer.start(100)
                
                # Cancel any existing fade timer
                if self._fade_timer:
                    self._fade_timer.stop()
                    self._fade_timer = None
                
                # Start fade-out after duration
                QTimer.singleShot(duration * 1000, self._start_fadeout)

            def _start_fadeout(self) -> None:
                self._fade_timer = QTimer(self)
                self._fade_timer.timeout.connect(self._fade_out)
                self._fade_timer.start(50)

            def _fade_out(self) -> None:
                self._current_opacity -= 0.05
                if self._current_opacity <= 0:
                    if self._fade_timer:
                        self._fade_timer.stop()
                    self._has_content = False
                    self.hide()
                    # Stop reposition timer when hidden
                    if self._reposition_timer and self._reposition_timer.isActive():
                        self._reposition_timer.stop()
                else:
                    self.setWindowOpacity(self._current_opacity)

            def _update_position(self) -> None:
                # Don't update position if we don't have content or aren't visible
                if not self._has_content or not self.isVisible():
                    return
                    
                screen = QApplication.primaryScreen()
                if not screen:
                    return
                geometry = screen.availableGeometry()
                anchor = current_anchor()
                if anchor:
                    x = int(anchor[0] + 20)
                    y = int(anchor[1] - self.height() - 60)
                else:
                    # If no anchor, hide the bubble instead of showing in middle of screen
                    if self.isVisible():
                        self.hide()
                        self._has_content = False
                        if self._reposition_timer and self._reposition_timer.isActive():
                            self._reposition_timer.stop()
                    return
                x = max(geometry.left() + 20, min(x, geometry.right() - self.width() - 20))
                y = max(geometry.top() + 20, min(y, geometry.bottom() - self.height() - 20))
                self.move(x, y)

        chat_window = ChatWindow(chat_db=chat_db)
        self._chat_window = chat_window  # Store reference for external access
        bubble_box = BubbleBox()

        def process_bubble_queue() -> None:
            while not overlay_ref._queue.empty():
                entry = overlay_ref._queue.get()
                if overlay_ref._shutdown.is_set():
                    app.quit()
                    return
                if not entry.text:
                    continue
                LOGGER.debug("Processing bubble: %s - %s", entry.author, entry.text)
                # Add to BOTH windows
                chat_window.append_message(entry.author, entry.text, persist=False)
                bubble_box.add_message(entry.author, entry.text, duration=entry.duration)

        def process_chat_queue() -> None:
            while not overlay_ref._chat_queue.empty():
                kind, author, text = overlay_ref._chat_queue.get()
                if overlay_ref._shutdown.is_set():
                    app.quit()
                    return
                if kind == "open":
                    chat_window.show_panel()
                    LOGGER.debug("Opened chat panel")
                elif kind == "message" and author and text:
                    chat_window.append_message(author, text)

        timer = QTimer()
        timer.timeout.connect(process_bubble_queue)
        timer.timeout.connect(process_chat_queue)
        timer.start(200)

        try:
            app.exec()
        finally:
            # Cleanup timers
            try:
                bubble_box.cleanup()
            except Exception:
                pass
            overlay_ref._shutdown.set()
            overlay_ref._queue.queue.clear()
            overlay_ref._chat_queue.queue.clear()
