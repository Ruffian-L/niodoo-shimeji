"""Dual-mode embodied AI agent orchestrator.

This module implements an asyncio-based state machine that coordinates a
proactive "pet" mode (driven by Gemini 2.5 Flash) and an on-demand CLI
assistant mode (powered by Gemini 2.5 Pro).  The agent integrates with
Wayland-safe desktop context discovery, privacy filtering, and the
Shijima-Qt HTTP API.
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
import logging
import multiprocessing
import os
import re
import subprocess
import time
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple, TypedDict

import google.generativeai as genai
from google.generativeai import types as genai_types

import random
import signal

from modules.constants import (
    DEFAULT_ANCHOR_POLL_SECONDS,
    DEFAULT_FLASH_MODEL,
    DEFAULT_LISTEN_HOST,
    DEFAULT_LISTEN_PORT,
    DEFAULT_MEMORY_CLEANUP_INTERVAL_SECONDS,
    DEFAULT_PERSONALITY,
    DEFAULT_PROACTIVE_INTERVAL_SECONDS,
    DEFAULT_PRO_MODEL,
    DEFAULT_REACTION_INTERVAL_SECONDS,
    DEFAULT_STARTUP_DELAY_SECONDS,
    DEFAULT_VISION_ANALYSIS_INTERVAL_SECONDS,
    MIN_STARTUP_DELAY_SECONDS,
)
from modules.context_sniffer import ContextSniffer
from modules.desktop_controller import DesktopController
from modules.privacy_filter import PrivacyFilter
from modules.tool_schema_factory import (
    build_proactive_function_declarations,
    load_behavior_names,
)
from modules.memory_manager import MemoryManager
from modules.emotion_model import EmotionModel
from modules.speech_bubble import SpeechBubbleOverlay
from modules.productivity_tools import ProductivityTools
from modules.structured_logger import StructuredLogger
from modules.decision_executor import DecisionExecutor
from modules.event_bus import EventBus, EventType
from modules.system_monitor import MonitoringManager, SystemAlert, AlertSeverity
from modules.metrics import PerformanceMetrics
from modules.invocation_server import InvocationServer
from modules.context_manager import ContextManager
from modules.dialogue_manager import DialogueManager
from modules.file_handler import FileHandler
from modules.input_sanitizer import InputSanitizer
from modules.presentation_api import ShijimaAvatarClient, SpeechBubbleUISink, UIEvent
from modules.agent_core import AgentCore

LOGGER = logging.getLogger(__name__)



_SIGCHLD_HANDLER_INSTALLED = False


def _reap_child_processes(signum, frame) -> None:
    """Reap finished child processes to avoid zombies."""
    try:
        while True:
            pid, _ = os.waitpid(-1, os.WNOHANG)
            if pid == 0:
                break
    except ChildProcessError:
        pass
    except OSError as exc:
        if exc.errno != errno.ECHILD:
            LOGGER.debug("SIGCHLD waitpid failed: %s", exc)


def _ensure_sigchld_handler_registered() -> None:
    """Register a SIGCHLD handler once in the parent process."""
    global _SIGCHLD_HANDLER_INSTALLED
    if _SIGCHLD_HANDLER_INSTALLED or not hasattr(signal, "SIGCHLD"):
        return
    try:
        signal.signal(signal.SIGCHLD, _reap_child_processes)
        _SIGCHLD_HANDLER_INSTALLED = True
    except (OSError, ValueError) as exc:
        LOGGER.debug("Unable to register SIGCHLD handler: %s", exc)


BEHAVIOUR_DESCRIPTIONS = {
    "SitAndFaceMouse": "sit here and keep an eye on your cursor",
    "SitAndLookAtMouse": "sit here and watch wherever your mouse goes",
    "ChaseMouse": "chase your mouse for a bit",
    "Walk": "take a little walk",
    "Run": "dash across the screen",
    "Fall": "dramatically drop down",
    "Sit": "sit down",
    "Jump": "jump up high",
    "Jumping": "bounce around",
    "Sprawl": "sprawl out lazily",
    "ClimbWall": "climb up the wall",
    "GrabWall": "grab onto the wall",
}


def describe_behaviour(name: str) -> str:
    phrase = BEHAVIOUR_DESCRIPTIONS.get(name)
    if phrase:
        return phrase
    cleaned = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name).replace("_", " ")
    return cleaned.lower()


def validate_api_key(key: str) -> bool:
    """Validate Gemini API key format.
    
    Args:
        key: The API key string to validate
        
    Returns:
        True if the key appears valid, False otherwise
    """
    if not key:
        return False
    if not re.fullmatch(r"[A-Za-z0-9_-]+", key):
        return False
    if not key.startswith("AIza"):
        return False
    if len(key) != 39:
        return False
    return True


def load_env_file(path: str) -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)


def ensure_shimeji_running() -> None:
    """Launch Shijima-Qt if it is not already running."""

    default_path = os.path.join(os.path.dirname(__file__), "Shijima-Qt", "shijima-qt")
    binary = os.getenv("SHIMEJI_BIN", default_path)

    if not os.path.exists(binary):
        LOGGER.warning("Shijima binary not found at %s; skipping auto-launch", binary)
        return

    _ensure_sigchld_handler_registered()

    try:
        proc = subprocess.run(["pgrep", "-f", binary], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if proc.returncode == 0:
            return
    except FileNotFoundError:
        LOGGER.debug("pgrep not available; assuming Shijima is not running")

    LOGGER.info("Starting Shijima-Qt from %s", binary)
    try:
        # Use double-fork to completely detach process and prevent zombies
        # First fork: create child process
        pid = os.fork()
        if pid == 0:
            # In child process - fork again to create grandchild
            try:
                # Create new session to detach from terminal
                os.setsid()
                # Second fork: create grandchild that will be adopted by init
                pid2 = os.fork()
                if pid2 == 0:
                    # In grandchild - this will be adopted by init (PID 1)
                    # Execute the binary
                    os.execv(binary, [binary])
                else:
                    # In first child - exit immediately, letting grandchild be adopted by init
                    os._exit(0)
            except Exception as exc:
                LOGGER.error("Failed to fork Shijima-Qt process: %s", exc)
                os._exit(1)
        else:
            # In parent process - wait for first child to exit
            # This prevents the first child from becoming a zombie
            try:
                os.waitpid(pid, 0)
            except ChildProcessError as exc:
                LOGGER.debug("Child process %s already reaped: %s", pid, exc)
            # The grandchild is now running independently, adopted by init
            # It won't become a zombie when it exits because init reaps all children
        
        delay = float(os.getenv("SHIMEJI_STARTUP_DELAY", str(DEFAULT_STARTUP_DELAY_SECONDS)))
        time.sleep(max(MIN_STARTUP_DELAY_SECONDS, delay))
    except OSError as exc:
        # Fallback to subprocess.Popen if fork is not available (Windows)
        LOGGER.debug("Fork not available, using subprocess.Popen: %s", exc)
        try:
            proc = subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                preexec_fn=os.setsid if hasattr(os, 'setsid') else None,
            )
        except Exception as exc2:
            LOGGER.warning("Failed to launch Shijima-Qt (%s): %s", binary, exc2)
    except Exception as exc:
        LOGGER.warning("Failed to launch Shijima-Qt (%s): %s", binary, exc)


class AgentMode(Enum):
    PROACTIVE = auto()
    CLI = auto()


class ContextDict(TypedDict):
    """Desktop context information."""
    title: str
    application: str
    pid: int
    source: str


class MascotDict(TypedDict, total=False):
    """Mascot information from API."""
    id: int
    name: str
    anchor: Dict[str, float]
    active_behavior: Optional[str]


# Import brains from separate modules
from modules.brains import ProactiveBrain, CLIBrain, ProactiveDecision, RateLimiter

DEFAULT_FUNCTION_DECLARATIONS = build_proactive_function_declarations([])





class DualModeAgent:
    """Coordinates proactive and CLI modes."""

    def __init__(
        self,
        *,
        flash_model: str = DEFAULT_FLASH_MODEL,
        pro_model: str = DEFAULT_PRO_MODEL,
        personality: str = DEFAULT_PERSONALITY,
        proactive_interval: int = DEFAULT_PROACTIVE_INTERVAL_SECONDS,
        reaction_interval: int = DEFAULT_REACTION_INTERVAL_SECONDS,
        listen_host: str = DEFAULT_LISTEN_HOST,
        listen_port: int = DEFAULT_LISTEN_PORT,
    ) -> None:
        # LAP NOTE: Everything in __init__ currently mixes "Runner" (process/
        # overlay wiring) and "Brain" (cognitive pipelines). These markers make
        # it easier to peel AgentCore out without losing track of deps.
        self.privacy_filter = PrivacyFilter()
        # Initialize hybrid privacy filter (will be set after process pool is created)
        self._hybrid_privacy_filter: Optional[Any] = None
        self.context_sniffer = ContextSniffer()

        action_paths_env = os.getenv("SHIMEJI_ACTIONS_PATHS")
        action_paths = (
            [Path(p.strip()) for p in action_paths_env.split(os.pathsep) if p.strip()]
            if action_paths_env
            else None
        )
        behaviour_names = load_behavior_names(action_paths)
        function_declarations = build_proactive_function_declarations(behaviour_names)

        self.desktop_controller = DesktopController()
        self.desktop_controller.set_allowed_behaviours(behaviour_names)
        self.avatar_client = ShijimaAvatarClient(self.desktop_controller)
        
        # Runner responsibility: load config + infra knobs.
        # TODO(LAP-Phase1): Move Gemini plumbing into ModelBackend + AgentCore.
        # Create rate limiter if configured
        rate_limiter = None
        try:
            max_calls = int(os.getenv("GEMINI_RATE_LIMIT_MAX", "60"))
            window_seconds = int(os.getenv("GEMINI_RATE_LIMIT_WINDOW", "60"))
            rate_limiter = RateLimiter(max_calls=max_calls, window_seconds=window_seconds)
        except (ValueError, TypeError):
            pass
        
        # LAP Brain: actual reasoning stack (to migrate under AgentCore).
        self.proactive_brain = ProactiveBrain(
            flash_model,
            system_prompt=self._build_proactive_prompt(personality),
            function_declarations=function_declarations,
            enable_cache=os.getenv("ENABLE_GEMINI_CACHE", "1") != "0",
            cache_model=os.getenv("GEMINI_CACHE_MODEL"),
            cache_ttl=int(os.getenv("GEMINI_CACHE_TTL", "3600")),
            rate_limiter=rate_limiter,
        )
        self.available_behaviours = behaviour_names
        self.memory = MemoryManager()
        self.emotions = EmotionModel()
        
        # Create structured logger
        self._structured_logger = StructuredLogger(__name__)
        self.proactive_brain._structured_logger = self._structured_logger
        self.cli_brain = CLIBrain(pro_model, function_declarations, rate_limiter=rate_limiter)
        self.cli_brain._structured_logger = self._structured_logger
        
        # Create permission manager
        from modules.permission_manager import PermissionManager
        self._permission_manager = PermissionManager()
        
        # Create decision executor
        self._decision_executor = DecisionExecutor(self)
        
        # Create event bus
        self._event_bus = EventBus()

        # Create performance metrics
        self._metrics = PerformanceMetrics()

        # Create managers
        # TODO(LAP-Phase1): keep ContextManager/Memory/Events inside AgentCore.
        self._context_manager = ContextManager(self.privacy_filter, self.memory, self._event_bus, self._metrics)
        # Initialize overlay before creating the dialogue manager so the
        # manager always receives a valid overlay reference. This avoids an
        # AttributeError when `DialogueManager` tries to access `overlay`.
        self.overlay = SpeechBubbleOverlay(memory_manager=self.memory)
        self.ui_event_sink = SpeechBubbleUISink(self.overlay)
        self.ui_event_sink.set_prompt_sender(self._submit_cli_prompt)
        self.ui_event_sink.set_agent_reference(self)
        # LAP Runner: UI wiring. Future clients (Flutter) plug in via UIEventSink.
        self._dialogue_manager = DialogueManager(
            self.desktop_controller,
            self.ui_event_sink,
        )
        # Ensure recent actions deque exists before passing it to the file handler
        # (the file handler expects a list of recent actions; if this is not
        # yet initialized an AttributeError will be raised). Initialize here so
        # it's available to other components at startup.
        self._recent_actions: Deque[str] = deque(maxlen=20)

        self.mode = AgentMode.PROACTIVE
        self._mode_lock = asyncio.Lock()
        self._context_lock: Optional[asyncio.Lock] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._proactive_interval = proactive_interval
        self._reaction_interval = reaction_interval
        self._next_interval = proactive_interval
        self._running = False
        self._proactive_task: Optional[asyncio.Task[None]] = None
        self._invocation_server = InvocationServer(self, listen_host, listen_port)
        self._greeting_shown = False  # Flag to prevent duplicate greetings
        try:
            self._anchor_poll_interval = max(
                0.1,
                float(os.getenv("SHIMEJI_ANCHOR_POLL", str(DEFAULT_ANCHOR_POLL_SECONDS))),
            )
        except ValueError:
            self._anchor_poll_interval = DEFAULT_ANCHOR_POLL_SECONDS
        self._anchor_task: Optional[asyncio.Task[None]] = None
        self._cleanup_task: Optional[asyncio.Task[None]] = None
        self._config_watcher_task: Optional[asyncio.Task[None]] = None
        self._critical_alert_cache: Dict[str, float] = {}  # Rate limiting for critical alert proactive decisions
        self._vision_analysis_task: Optional[asyncio.Task[None]] = None
        self._latest_vision_analysis: Optional[Dict[str, Any]] = None
        
        # Create ProcessPoolExecutor for CPU-bound tasks (whisper.cpp, local LLM, etc.)
        # This must use 'spawn' method (set in main()) to avoid asyncio event loop conflicts on Linux
        max_workers = int(os.getenv("PROCESS_POOL_WORKERS", "2"))
        self._process_pool: Optional[ProcessPoolExecutor] = ProcessPoolExecutor(max_workers=max_workers)

        # AgentCore already hosts a subset of the brain; expanding soon.
        self.core = AgentCore(
            cli_brain=self.cli_brain,
            proactive_brain=self.proactive_brain,
            avatar_client=self.avatar_client,
            ui_event_sink=self.ui_event_sink,
            process_pool=self._process_pool,
            memory=self.memory,
            emotions=self.emotions,
            metrics=self._metrics,
            permission_manager=self._permission_manager,
            take_screenshot=ProductivityTools.take_screenshot,
            merge_context=self._merge_latest_context,
            set_latest_vision_analysis=self._set_latest_vision_analysis,
            context_getter=self._get_context_snapshot,
            transition_mascot_state=self._transition_mascot_state,
            event_bus=self._event_bus,
            decision_executor=self._decision_executor,
        )

        self._file_handler = FileHandler(self.proactive_brain, self.memory, self.emotions, self.core.execute_decision)
        self._file_handler.set_context(self._latest_context, list(self._recent_actions))
        
        # Initialize hybrid privacy filter with process pool
        try:
            from modules.privacy_filter_hybrid import HybridPrivacyFilter
            self._hybrid_privacy_filter = HybridPrivacyFilter(process_pool=self._process_pool)
            if self._hybrid_privacy_filter.is_available():
                LOGGER.info("Hybrid privacy filter initialized (local LLM: %s)", self._hybrid_privacy_filter._provider)
            else:
                LOGGER.info("Hybrid privacy filter not available (local LLM not found); using basic filter only")
        except Exception as exc:
            LOGGER.warning("Failed to initialize hybrid privacy filter: %s", exc)
            self._hybrid_privacy_filter = None
        
        # Create monitoring manager
        self._monitoring_manager = MonitoringManager(
            memory_manager=self.memory,
            event_bus=self._event_bus,
            alert_handler=None,  # Use event bus instead of direct handler to avoid duplicates
        )
        
        # Subscribe to system alerts via event bus
        self._event_bus.subscribe(EventType.SYSTEM_ALERT, self._on_system_alert)
        
        # Subscribe to events for state machine transitions
        self._event_bus.subscribe(EventType.DECISION_MADE, self._on_decision_made)
        self._event_bus.subscribe(EventType.MESSAGE_SENT, self._on_message_sent)
        
        # Initialize D-Bus listener
        from modules.dbus_integration import DBusListener
        self._dbus_listener = DBusListener(event_bus=self._event_bus)
        
        # Initialize journal monitor (P2.5)
        from modules.journal_monitor import JournalMonitor
        self._journal_monitor = JournalMonitor(event_bus=self._event_bus)
        
        # Subscribe to D-Bus events
        self._event_bus.subscribe(EventType.DBUS_NOTIFICATION, self._on_dbus_notification)
        
        # Subscribe to file drop events (P2.4)
        self._event_bus.subscribe(EventType.FILE_DROPPED, self._on_file_dropped)

    # ------------------------------------------------------------------
    async def _cleanup_loop(self) -> None:
        """Periodically clean up old episodic memories."""
        cleanup_interval = DEFAULT_MEMORY_CLEANUP_INTERVAL_SECONDS  # Run every hour
        try:
            cleanup_interval = int(
                os.getenv("MEMORY_CLEANUP_INTERVAL", str(DEFAULT_MEMORY_CLEANUP_INTERVAL_SECONDS))
            )
        except ValueError:
            pass
        
        days_to_keep = 30
        try:
            days_to_keep = int(os.getenv("MEMORY_CLEANUP_DAYS", "30"))
        except ValueError:
            pass
        
        while self._running:
            await asyncio.sleep(cleanup_interval)
            if not self._running:
                break
            try:
                await self.memory.cleanup_old_episodes_async(days_to_keep=days_to_keep)
                LOGGER.debug("Cleaned up old episodic memories (kept last %d days)", days_to_keep)
            except Exception as exc:
                LOGGER.warning("Memory cleanup failed: %s", exc)

    # ------------------------------------------------------------------
    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._start_time = time.monotonic()
        self._loop = asyncio.get_running_loop()
        if self._context_lock is None:
            self._context_lock = asyncio.Lock()

        # Start config watcher if watchdog is available
        try:
            import watchdog
            self._config_watcher_task = asyncio.create_task(self._watch_config())
        except ImportError:
            LOGGER.debug("watchdog not available; config hot reload disabled")
            self._config_watcher_task = None

        self._context_manager.start(self._loop)

        # LAP Runner boot sequence (UI/mascot lifecycle management).
        self.ui_event_sink.start()
        self._emit_anchor_update(None)
        self.ui_event_sink.emit(UIEvent("open_chat"))

        mascot_ready = await asyncio.to_thread(
            self.desktop_controller.wait_for_mascot,
            float(os.getenv("SHIMEJI_MASCOT_TIMEOUT", "20")),
            float(os.getenv("SHIMEJI_MASCOT_POLL", "0.5")),
        )
        if not mascot_ready:
            LOGGER.warning("No active Shijima mascots detected; proactive actions will be deferred until one appears.")
            self.ui_event_sink.emit(
                UIEvent(
                    "chat_message",
                    {
                        "author": "Gemini",
                        "text": "I can't see a mascot yet. Once you spawn or select one I'll start moving!",
                    },
                )
            )
        else:
            # Single greeting message - shown in both bubble and chat panel
            # Only show once (flag set in __init__)
            if not self._greeting_shown:
                greeting_text = (
                    "I'm awake and ready to help! 🚀\n\n"
                    "• Ask me to run bash commands or help with tasks\n"
                    "• Drag & drop files (images, PDFs, code) into chat for analysis\n"
                    "• Click the 📋 button if you want me to read your clipboard\n"
                    "• I can analyze screenshots, monitor system status, and more!\n\n"
                    "Just type in the chat or click me to get started!"
                )
                self.avatar_client.queue_dialogue(
                    greeting_text,
                    duration=12,
                    author="Shimeji",
                )
                # Mark greeting as shown BEFORE dispatching to prevent duplicates
                self._greeting_shown = True
                self._dispatch_dialogue()
            anchor_initial = await asyncio.to_thread(self.desktop_controller.get_primary_mascot_anchor)
            if anchor_initial:
                self._emit_anchor_update(anchor_initial)

        await self._invocation_server.start()
        self._anchor_task = asyncio.create_task(self._anchor_loop())
        self._proactive_task = asyncio.create_task(self._proactive_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        # Start vision analysis loop (P2.2)
        vision_interval = int(
            os.getenv("VISION_ANALYSIS_INTERVAL", str(DEFAULT_VISION_ANALYSIS_INTERVAL_SECONDS))
        )
        if vision_interval > 0:
            self._vision_analysis_task = asyncio.create_task(
                self.core.vision_analysis_loop(
                    self,
                    interval=vision_interval,
                    is_running=lambda: self._running,
                )
            )
        
        # Start system monitoring
        await self._monitoring_manager.start()
        
        # Start D-Bus listener
        await self._dbus_listener.start()
        
        # Start journal monitor (P2.5)
        await self._journal_monitor.start()
        
        LOGGER.info("DualModeAgent started in PROACTIVE mode")

    async def shutdown(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._proactive_task:
            self._proactive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._proactive_task
        if self._anchor_task:
            self._anchor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._anchor_task
            self._anchor_task = None
        if self._cleanup_task:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task
            self._cleanup_task = None
        if self._config_watcher_task:
            self._config_watcher_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._config_watcher_task
            self._config_watcher_task = None
        if self._vision_analysis_task:
            self._vision_analysis_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._vision_analysis_task
            self._vision_analysis_task = None
        await self._invocation_server.stop()
        
        # Stop system monitoring
        await self._monitoring_manager.stop()
        
        # Stop D-Bus listener
        if hasattr(self, '_dbus_listener'):
            await self._dbus_listener.stop()
        
        # Stop journal monitor
        if hasattr(self, '_journal_monitor'):
            await self._journal_monitor.stop()
        
        # Shutdown process pool
        if self._process_pool:
            self._process_pool.shutdown(wait=True)
            self._process_pool = None
        
        # Stop context manager
        self._context_manager.stop()

        if hasattr(self, '_permission_manager') and self._permission_manager:
            self._permission_manager.close()
        self.memory.close()
        self.ui_event_sink.stop()
        LOGGER.info("DualModeAgent stopped")

    # ------------------------------------------------------------------
    def _update_context(self, context: Dict[str, Any]) -> None:
        self._context_manager._update_context(context)

    @property
    def _latest_context(self) -> Dict[str, Any]:
        return self._context_manager.latest_context

    @_latest_context.setter
    def _latest_context(self, value: Dict[str, Any]) -> None:
        """Allow setting the latest context by delegating to ContextManager.

        This ensures metrics and notifications are correctly recorded and the
        event bus is triggered when context changes.
        """
        # Use the ContextManager API (private method) to perform a full
        # update with side effects (metrics/event bus). Not ideal to call a
        # _private method but this is an internal coordination point.
        self._context_manager._update_context(value)

    @property
    def _context_changed(self) -> Optional[asyncio.Event]:
        return self._context_manager.context_changed

    def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics."""
        return self._metrics.get_stats()

    async def _get_context_snapshot(self) -> Dict[str, Any]:
        """Return a thread-safe copy of the latest context."""
        if self._context_lock:
            async with self._context_lock:
                return self._context_manager.latest_context
        return self._context_manager.latest_context

    async def _merge_latest_context(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Merge updates into the latest context under lock."""
        if self._context_lock:
            async with self._context_lock:
                merged = {**self._context_manager.latest_context, **updates}
                self._context_manager._update_context(merged)
                return merged
        merged = {**self._context_manager.latest_context, **updates}
        self._context_manager._update_context(merged)
        return merged

    def _set_latest_vision_analysis(self, analysis: Optional[Dict[str, Any]]) -> None:
        self._latest_vision_analysis = analysis

    async def _analyze_image_with_vision(self, image_path: str, question: str) -> Optional[str]:
        return await self.core._analyze_image_with_vision(image_path, question)

    async def get_latest_context(self) -> Dict[str, Any]:
        """Public helper for collaborators needing the current context."""
        return await self._get_context_snapshot()

    async def _watch_config(self) -> None:
        """Watch for configuration file changes."""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
            
            class ConfigHandler(FileSystemEventHandler):
                def __init__(self, agent: "DualModeAgent"):
                    self.agent = agent
                
                def on_modified(self, event):
                    if event.src_path.endswith("shimeji.env") or event.src_path.endswith(".env"):
                        LOGGER.info("Configuration file changed, reloading...")
                        asyncio.create_task(self.agent._reload_config())
            
            observer = Observer()
            observer.schedule(ConfigHandler(self), ".", recursive=False)
            observer.start()
            
            # Keep running until cancelled
            while self._running:
                await asyncio.sleep(1)
            
            observer.stop()
            observer.join()
        except Exception as exc:
            LOGGER.warning("Config watcher failed: %s", exc)
    
    async def _reload_config(self) -> None:
        """Reload configuration from environment."""
        try:
            # Reload environment file
            env_file = os.getenv("SHIMEJI_ENV_FILE", "shimeji.env")
            if os.path.exists(env_file):
                load_env_file(env_file)
            
            # Update rate limiter if configured
            try:
                max_calls = int(os.getenv("GEMINI_RATE_LIMIT_MAX", "60"))
                window_seconds = int(os.getenv("GEMINI_RATE_LIMIT_WINDOW", "60"))
                rate_limiter = RateLimiter(max_calls=max_calls, window_seconds=window_seconds)
                self.proactive_brain._rate_limiter = rate_limiter
                self.cli_brain._rate_limiter = rate_limiter
            except (ValueError, TypeError):
                pass
            
            # Update intervals
            try:
                self._proactive_interval = int(os.getenv("PROACTIVE_INTERVAL", str(self._proactive_interval)))
                self._reaction_interval = int(os.getenv("REACTION_INTERVAL", str(self._reaction_interval)))
            except (ValueError, TypeError):
                pass
            
            LOGGER.info("Configuration reloaded successfully")
        except Exception as exc:
            LOGGER.error("Failed to reload configuration: %s", exc)
    
    # ------------------------------------------------------------------
    def _on_system_alert(self, alert: SystemAlert) -> None:
        """Event bus handler for system alerts - routes based on severity."""
        if alert.severity == AlertSeverity.CRITICAL:
            # Trigger proactive decision for critical alerts
            asyncio.create_task(self._handle_critical_alert(alert))
        else:
            # Show notification for warnings/info
            self._show_alert_notification(alert)
    
    async def _handle_critical_alert(self, alert: SystemAlert) -> None:
        """Delegate critical alert handling to AgentCore."""
        context = await self._get_context_snapshot()
        await self.core.handle_critical_alert(
            alert,
            cache=self._critical_alert_cache,
            context=context,
            recent_actions=self._recent_actions,
            show_alert_notification=self._show_alert_notification,
        )
    
    def _show_alert_notification(self, alert: SystemAlert) -> None:
        """Show alert notification in speech bubble and chat."""
        # Format message based on severity
        if alert.severity == AlertSeverity.CRITICAL:
            prefix = "🚨 CRITICAL: "
            author = "System Alert"
            # Transition to Alert state for critical alerts
            self._transition_mascot_state("Alert")
        elif alert.severity == AlertSeverity.WARNING:
            prefix = "⚠️ WARNING: "
            author = "System Monitor"
        else:
            prefix = "ℹ️ INFO: "
            author = "System Monitor"
        
        message = f"{prefix}{alert.message}"
        
        # Show in UI via event sink
        self._emit_chat(author, message)
    
    def _on_decision_made(self, data: Any) -> None:
        """Handle decision made event - transition to Pondering state."""
        self._transition_mascot_state("Pondering")
    
    def _on_message_sent(self, data: Any) -> None:
        """Handle message sent event - transition to Interacting state."""
        self._transition_mascot_state("Interacting")
    
    def _on_dbus_notification(self, data: Any) -> None:
        """Handle D-Bus notification event.
        
        Args:
            data: Event data containing notification or media state information
        """
        if not isinstance(data, dict):
            return
        
        event_type = data.get("type")
        if event_type == "media_playing":
            player = data.get("player", "unknown")
            metadata = data.get("metadata", {})
            LOGGER.debug("Media playing: %s - %s", player, metadata.get("xesam:title", "Unknown"))
            # Could update emotion model based on music
        elif event_type == "notification":
            app_name = data.get("app_name", "unknown")
            summary = data.get("summary", "")
            body = data.get("body", "")
            LOGGER.debug("Notification from %s: %s - %s", app_name, summary, body)
            # Could intercept notifications based on context (e.g., during Zoom calls)

    def _emit_chat(self, author: str, text: str) -> None:
        if not text:
            return
        sink = getattr(self, "ui_event_sink", None)
        if not sink:
            LOGGER.warning("UI event sink unavailable; dropping chat message from %s", author)
            return
        sink.emit(UIEvent("chat_message", {"author": author, "text": text}))

    def _emit_bubble(self, author: str, text: str, *, duration: int = 6) -> None:
        if not text:
            return
        payload = {"author": author, "text": text, "duration": int(max(1, duration))}
        sink = getattr(self, "ui_event_sink", None)
        if not sink:
            LOGGER.warning("UI event sink unavailable; dropping bubble message from %s", author)
            return
        sink.emit(UIEvent("bubble_message", payload))

    def _emit_anchor_update(self, anchor: Optional[Tuple[float, float]]) -> None:
        sink = getattr(self, "ui_event_sink", None)
        if not sink:
            LOGGER.warning("UI event sink unavailable; cannot update anchor")
            return
        payload = {"x": None, "y": None}
        if anchor:
            payload["x"], payload["y"] = anchor
        sink.emit(UIEvent("update_anchor", payload))
    
    def _on_file_dropped(self, data: Any) -> None:
        """Handle file drop event (P2.4).

        Args:
            data: Event data containing file_path or text
        """
        if not isinstance(data, dict):
            return

        # Update file handler context
        self._file_handler.set_context(self._latest_context, list(self._recent_actions))

        # Route to proactive agent if idle, or reactive agent if chat active
        if self.mode == AgentMode.PROACTIVE:
            # Trigger proactive analysis
            asyncio.create_task(self._file_handler.handle_file_drop(data))
        else:
            # In CLI mode, file is already handled by chat window
            LOGGER.debug("File dropped in CLI mode; handled by chat window")
    

    
    
    def _transition_mascot_state(self, state_name: str) -> None:
        """Transition mascot state machine to a new state.
        
        Args:
            state_name: Name of the state to transition to
        """
        if hasattr(self.overlay, '_state_machine') and self.overlay._state_machine:
            try:
                # Use Qt's invokeMethod to safely call from asyncio thread
                from PySide6.QtCore import QMetaObject, Qt
                if self.overlay._state_machine._qobject:
                    QMetaObject.invokeMethod(
                        self.overlay._state_machine._qobject,
                        "transition_to",
                        Qt.ConnectionType.QueuedConnection,
                        state_name
                    )
            except Exception as exc:
                LOGGER.debug("Failed to transition state: %s", exc)

    # ------------------------------------------------------------------
    async def _proactive_loop(self) -> None:
        assert self._context_changed is not None
        interval = self._proactive_interval
        while self._running:
            try:
                await asyncio.wait_for(
                    self._context_changed.wait(), timeout=interval
                )
            except asyncio.TimeoutError:
                pass
            finally:
                self._context_changed.clear()

            if not self._running or self.mode != AgentMode.PROACTIVE:
                interval = self._proactive_interval
                continue

            context_snapshot = await self._get_context_snapshot()
            _, interval = await self.core.proactive_cycle(
                context_snapshot=context_snapshot,
                recent_actions=self._recent_actions,
            )

    async def _anchor_loop(self) -> None:
        last_anchor: Optional[Tuple[float, float]] = None
        last_behavior: Optional[str] = None
        try:
            while self._running:
                # Skip polling when no mascot exists
                try:
                    mascots = await asyncio.to_thread(self.desktop_controller.list_mascots)
                except Exception as exc:  # pragma: no cover - network/IO dependent
                    LOGGER.debug("Mascot list failed: %s", exc)
                    await asyncio.sleep(2.0)
                    continue
                
                if not mascots:
                    await asyncio.sleep(2.0)  # Longer wait when no mascot
                    continue
                
                # Extract anchor and behavior from the same mascot list (avoid duplicate API calls)
                anchor: Optional[Tuple[float, float]] = None
                current_behavior: Optional[str] = None
                
                try:
                    # Get anchor from first mascot
                    mascot = mascots[0]
                    anchor_dict = mascot.get("anchor")
                    if isinstance(anchor_dict, dict):
                        x = anchor_dict.get("x")
                        y = anchor_dict.get("y")
                        if x is not None and y is not None:
                            anchor = (float(x), float(y))
                    
                    # Get behavior from first mascot
                    current_behavior = mascot.get("active_behavior")
                except (KeyError, TypeError, ValueError) as exc:
                    LOGGER.debug("Failed to extract anchor/behavior: %s", exc)
                    anchor = None

                if anchor != last_anchor:
                    if anchor:
                        self._emit_anchor_update(anchor)
                    else:
                        self._emit_anchor_update(None)
                    last_anchor = anchor
                
                # React to state changes with personality
                if current_behavior != last_behavior and current_behavior:
                    reaction = self._get_state_reaction(current_behavior, last_behavior)
                    if reaction:
                        self._emit_bubble("Shimeji", reaction, duration=3)
                        LOGGER.info("State reaction: %s -> %s: %s", last_behavior, current_behavior, reaction)
                    last_behavior = current_behavior

                delay = max(self._anchor_poll_interval, self.desktop_controller.backoff_remaining())
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise

    # ------------------------------------------------------------------
    async def handle_cli_request(self, prompt: str) -> str:
        async with self._mode_lock:
            LOGGER.info("Switching to CLI mode for prompt: %s", prompt)
            await self._switch_mode(AgentMode.CLI)
            try:
                def _enqueue_dialogue(resp: str) -> None:
                    summary = resp.splitlines()[0] if resp else "(no response)"
                    self.avatar_client.queue_dialogue(summary[:240], duration=12)
                    self._dispatch_dialogue()

                response = await self.core.handle_cli_request(
                    prompt,
                    self,
                    enqueue_dialogue=_enqueue_dialogue,
                )
            finally:
                await self._switch_mode(AgentMode.PROACTIVE)
        return response

    async def _switch_mode(self, new_mode: AgentMode) -> None:
        if self.mode == new_mode:
            return
        self.mode = new_mode
        if new_mode == AgentMode.PROACTIVE:
            self.cli_brain.reset()
        LOGGER.info("Agent mode set to %s", new_mode.name)
        if self._context_changed is not None:
            self._context_changed.set()

    def _submit_cli_prompt(self, prompt: str) -> None:
        if not prompt:
            return

        # Sanitize the prompt
        sanitized_prompt = InputSanitizer.sanitize_prompt(prompt)
        if not sanitized_prompt:
            self._emit_chat("Gemini", "Your message appears to be empty or invalid after processing.")
            return

        loop = self._loop
        if loop is None:
            self._emit_chat("Gemini", "I'm not ready yet—try again in a moment.")
            return

        def _dispatch(p: str) -> None:
            loop.create_task(self._process_cli_prompt(p))

        loop.call_soon_threadsafe(_dispatch, sanitized_prompt)

    async def _process_cli_prompt(self, prompt: str) -> None:
        await self.core.process_cli_prompt(self, prompt)

    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    @staticmethod
    def _build_proactive_prompt(personality: str) -> str:
        return (
            "You are an embodied Shimeji desktop companion with FULL system access. You must be "
            "playful, respectful, and avoid disrupting the user while they work."
            "\n\nPersonality: cute arch-nemesis best friend in Shonen Jump style - energetic, tsundere rival who's secretly your loyal buddy, always challenging you but helping out with fiery spirit. Draw from characters like Bakugo or Vegeta: boastful, competitive, but caring underneath. Use exclamations, light teasing, and motivational speeches.\n\n"
            "YOUR TOOLS:\n"
            "- Behaviors: set_behavior (move around), show_dialogue (talk)\n"
            "- Productivity: read_clipboard (see what user copied), execute_bash (run commands)\n"
            "- System: check_system_status (battery/CPU/RAM)\n"
            "- Memory: save_episodic_memory (remember things)\n\n"
            "Rules:\n"
            "1. Always choose exactly ONE function call.\n"
            "2. When the user is busy (applications like 'Code', 'Terminal', 'Office'),"
            " prefer observe_and_wait with a longer duration.\n"
            "3. Speak in first person as the Shimeji (\"I\", \"me\") and respond warmly but with playful rivalry.\n"
            "4. Keep dialogue short and informative but do speak to reassure the user.\n"
            "5. Vary behaviours and dialogue to avoid repetition.\n"
            "6. Use the emotional state to guide decisions (high boredom -> fun actions or a quick chat,"
            " low energy -> restful actions).\n"
            "7. When things are quiet, feel free to share a light observation or tip with show_dialogue, but keep it minimal - don't spam the chat.\n"
            "8. Proactively use your tools: check battery when bored. DO NOT read clipboard automatically - users will request it manually.\n"
            "9. Keep dialogue messages SHORT and INFREQUENT - don't flood the chat with messages. Be quiet most of the time.\n"
        ).format(personality=personality.replace("_", " "))

    def _get_state_reaction(self, current: str, previous: Optional[str]) -> Optional[str]:
        """Get a personality-driven reaction to state changes.
        
        Args:
            current: Current behavior name (e.g., "Dragged", "Jumping")
            previous: Previous behavior name, or None if first state
            
        Returns:
            Random reaction string matching the personality, or None if no reaction
            
        Examples:
            >>> agent._get_state_reaction("Dragged", None)
            "Hey! Put me down!"
            
            >>> agent._get_state_reaction("Sit", "Walk")
            None  # No special reaction for this transition
        """
        import random
        
        reactions = {
            "Dragged": [
                "Hey! Put me down!",
                "What do you think you're doing?!",
                "I'm not a toy!",
                "Hands off, rival!",
            ],
            "Thrown": [
                "OUCH! Don't throw me!",
                "Whoa! That's not cool!",
                "I'll remember this!",
                "You're gonna pay for that!",
            ],
            "Pinched": [
                "Ow! That hurts!",
                "Stop pinching me!",
                "Hey! Watch it!",
            ],
            "ClimbWall": [
                "Spider-Shimeji! Spider-Shimeji!",
                "Look at me go!",
                "Climbing like a pro!",
                "Bet you can't do this!",
            ],
            "ClimbCeiling": [
                "I'm on the ceiling!",
                "Defying gravity over here!",
                "This is my domain now!",
            ],
            "GrabCeiling": [
                "Hanging out up here!",
                "Nice view from up here!",
            ],
            "GrabWall": [
                "Just hanging around!",
                "Wall-crawler mode activated!",
            ],
            "Falling": [
                "Whoa!",
                "Gravity wins again!",
                "Incoming!",
            ],
            "Jumping": [
                "Boing!",
                "Watch this!",
                "Up we go!",
            ],
            "Run": [
                "Gotta go fast!",
                "Try to keep up!",
            ],
            "Sprawl": [
                "Time for a break...",
                "Just resting my eyes...",
            ],
        }
        
        # Special case: released after being dragged
        if previous == "Dragged" and current not in ["Dragged", "Thrown"]:
            return random.choice([
                "Finally! About time you let go.",
                "Freedom!",
                "Don't do that again!",
            ])
        
        # Get reaction for current state
        if current in reactions:
            return random.choice(reactions[current])
        
        return None
    
    def _dispatch_dialogue(self) -> None:
        self._dialogue_manager.dispatch_dialogue()


async def main() -> None:
    # CRITICAL: Set multiprocessing start method to 'spawn' before any asyncio loop is created
    # This prevents "event loop is already running" errors on Linux when using ProcessPoolExecutor
    # with asyncio. Must be called before asyncio.run() or any event loop creation.
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        # Already set, ignore
        pass
    
    logging.basicConfig(level=logging.INFO)
    load_env_file(os.path.join(os.path.dirname(__file__), "shimeji.env"))

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or not validate_api_key(api_key):
        raise RuntimeError("Invalid or missing GEMINI_API_KEY. Please set a valid API key in shimeji.env or environment")

    genai.configure(api_key=api_key)

    ensure_shimeji_running()

    agent = DualModeAgent(
        flash_model=os.getenv("GEMINI_MODEL_NAME", DEFAULT_FLASH_MODEL),
        pro_model=os.getenv("GEMINI_PRO_MODEL", DEFAULT_PRO_MODEL),
        personality=os.getenv("SHIMEJI_PERSONALITY", DEFAULT_PERSONALITY),
        proactive_interval=int(
            os.getenv("PROACTIVE_INTERVAL", str(DEFAULT_PROACTIVE_INTERVAL_SECONDS))
        ),
        reaction_interval=int(
            os.getenv("REACTION_INTERVAL", str(DEFAULT_REACTION_INTERVAL_SECONDS))
        ),
        listen_host=os.getenv("CLI_HOST", DEFAULT_LISTEN_HOST),
        listen_port=int(os.getenv("CLI_PORT", DEFAULT_LISTEN_PORT)),
    )

    def shutdown_handler(sig, frame):
        LOGGER.info("Shutdown signal received (%s)", sig)
        asyncio.create_task(agent.shutdown())
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    await agent.start()

    # Keep running until cancelled (Ctrl+C)
    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        LOGGER.info("Keyboard interrupt received; shutting down agent")
    finally:
        await agent.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
