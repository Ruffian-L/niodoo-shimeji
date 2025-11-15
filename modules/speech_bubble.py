"""PySide6 overlay for speech bubbles and interactive chat."""

from __future__ import annotations

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
            from PySide6.QtCore import Qt, QTimer, Signal
            from PySide6.QtGui import QColor, QPainter, QPalette
            from PySide6.QtWidgets import (
                QApplication,
                QFrame,
                QHBoxLayout,
                QLabel,
                QLineEdit,
                QPushButton,
                QTextEdit,
                QVBoxLayout,
                QWidget,
            )
            from PySide6.QtGui import QKeyEvent
        except ImportError as exc:  # pragma: no cover - import guard
            LOGGER.error("PySide6 is required for the speech bubble overlay: %s", exc)
            return

        app = QApplication.instance() or QApplication([])
        self._started.set()
        overlay_ref = self

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

            def __init__(self) -> None:
                super().__init__()
                self.setWindowTitle("Shimeji Chat Log")
                self.setWindowFlag(Qt.Window, True)
                self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
                # Make it movable - keep title bar
                # self.setWindowFlag(Qt.FramelessWindowHint, True)
                self.resize(320, 640)

                self._history = QTextEdit(self)
                self._history.setReadOnly(True)
                self._history.setStyleSheet(
                    "QTextEdit { background-color: #1a1a1a; color: #00ff00; font-size: 11pt; border: 2px solid #00ff00; }"
                )

                self._chat_history: List[Dict[str, str]] = self._load_history()
                for msg in self._chat_history:
                    self.append_message(msg["author"], msg["text"], persist=False)

                self._save_timer = QTimer(self)
                self._save_timer.setSingleShot(True)
                self._save_timer.timeout.connect(self._do_save)

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
                search_layout.addWidget(self._export_button)
                layout.addLayout(search_layout)
                layout.addLayout(controls)

                self.dock()
                self.show()
                self.raise_()
                self.activateWindow()
                LOGGER.info("Chat panel initialized at %s", self.pos())

            def dock(self) -> None:
                screen = QApplication.primaryScreen()
                if not screen:
                    return
                geometry = screen.availableGeometry()
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
                    self._chat_history.append({"author": author, "text": text})
                    self._save_history()

            def _save_history(self) -> None:
                """Debounced save to avoid excessive I/O."""
                self._save_timer.stop()
                self._save_timer.start(2000)  # Save after 2s idle

            def _do_save(self) -> None:
                """Actually save the history."""
                try:
                    with open("chat_history.json", "w", encoding="utf-8") as handle:
                        json.dump(self._chat_history, handle)
                except Exception as exc:
                    LOGGER.warning("Failed to persist chat history: %s", exc)

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

            def _load_history(self) -> List[Dict[str, str]]:
                try:
                    with open("chat_history.json", "r", encoding="utf-8") as handle:
                        return json.load(handle)
                except (FileNotFoundError, json.JSONDecodeError):
                    return []
            
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
                """Export chat history as markdown."""
                from pathlib import Path
                from datetime import datetime
                
                if path is None:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    path = f"chat_history_{timestamp}.md"
                
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write("# Chat History\n\n")
                        for entry in self._chat_history:
                            author = entry.get("author", "Unknown")
                            text = entry.get("text", "")
                            f.write(f"## {author}\n\n{text}\n\n")
                    LOGGER.info("Chat history exported to %s", path)
                    # Show confirmation
                    self.append_message("System", f"Exported to {path}", persist=False)
                except Exception as exc:
                    LOGGER.error("Failed to export chat history: %s", exc)
                    self.append_message("System", f"Export failed: {exc}", persist=False)

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

                self._reposition_timer = QTimer(self)
                self._reposition_timer.timeout.connect(self._update_position)
                self._reposition_timer.start(100)

                self._fade_timer: Optional[QTimer] = None
                self._current_opacity = 1.0

                self._update_position()
                self.hide()  # Start hidden, show when message arrives
                LOGGER.info("Bubble box initialized")

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
                escaped_text = html.escape(text)
                display = f"<b style='color:#333'>{html.escape(author)}:</b><br>{escaped_text}"
                self._current_text.setHtml(display)
                
                # Adjust size based on content with proper word wrapping
                self._current_text.document().setTextWidth(450)  # Force wrap at this width
                doc_size = self._current_text.document().size()
                new_width = min(500, max(250, int(doc_size.width()) + 60))
                new_height = min(400, max(80, int(doc_size.height()) + 50))
                self.setFixedSize(new_width, new_height)
                
                # Show and reset opacity
                self._current_opacity = 1.0
                self.setWindowOpacity(self._current_opacity)
                self.show()
                self.raise_()
                self._update_position()
                
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
                    self.hide()
                else:
                    self.setWindowOpacity(self._current_opacity)

            def _update_position(self) -> None:
                screen = QApplication.primaryScreen()
                if not screen:
                    return
                geometry = screen.availableGeometry()
                anchor = current_anchor()
                if anchor:
                    x = int(anchor[0] + 20)
                    y = int(anchor[1] - self.height() - 60)
                else:
                    x = geometry.right() - self.width() - 50
                    y = geometry.bottom() - self.height() - 150
                x = max(geometry.left() + 20, min(x, geometry.right() - self.width() - 20))
                y = max(geometry.top() + 20, min(y, geometry.bottom() - self.height() - 20))
                self.move(x, y)

        chat_window = ChatWindow()
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
