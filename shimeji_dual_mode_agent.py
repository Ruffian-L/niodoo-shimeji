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
import json
import logging
import os
import re
import subprocess
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple, TypedDict

import google.generativeai as genai
from google.generativeai import types as genai_types

import random
import signal

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

LOGGER = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics collection for monitoring."""
    api_call_times: Deque[float] = field(default_factory=lambda: deque(maxlen=100))
    decision_times: Deque[float] = field(default_factory=lambda: deque(maxlen=100))
    context_updates: int = 0
    errors: int = 0
    
    def record_api_call(self, duration: float) -> None:
        """Record an API call duration."""
        self.api_call_times.append(duration)
    
    def record_decision(self, duration: float) -> None:
        """Record a decision-making duration."""
        self.decision_times.append(duration)
    
    def record_context_update(self) -> None:
        """Record a context update."""
        self.context_updates += 1
    
    def record_error(self) -> None:
        """Record an error."""
        self.errors += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        return {
            "avg_api_time_ms": (
                sum(self.api_call_times) / len(self.api_call_times) * 1000
                if self.api_call_times else 0
            ),
            "avg_decision_time_ms": (
                sum(self.decision_times) / len(self.decision_times) * 1000
                if self.decision_times else 0
            ),
            "total_context_updates": self.context_updates,
            "total_errors": self.errors,
            "api_call_count": len(self.api_call_times),
            "decision_count": len(self.decision_times),
        }
DEFAULT_FLASH_MODEL = "gemini-2.5-flash"
DEFAULT_PRO_MODEL = "gemini-2.5-pro"
DEFAULT_PERSONALITY = "playful_helper"
DEFAULT_PROACTIVE_INTERVAL = 45
DEFAULT_REACTION_INTERVAL = 10
DEFAULT_LISTEN_HOST = "127.0.0.1"
DEFAULT_LISTEN_PORT = 8770
DEFAULT_ANCHOR_POLL = 0.25

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
    if not key or len(key) < 20:
        return False
    # Gemini keys are typically base64-like strings
    # Basic format check: should contain alphanumeric characters and possibly hyphens
    if not re.match(r"^[A-Za-z0-9_-]+$", key):
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

    try:
        proc = subprocess.run(["pgrep", "-f", binary], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if proc.returncode == 0:
            return
    except FileNotFoundError:
        LOGGER.debug("pgrep not available; assuming Shijima is not running")

    LOGGER.info("Starting Shijima-Qt from %s", binary)
    try:
        # Detach process to prevent zombie processes when it exits
        # Use start_new_session=True to create a new process group
        # This ensures the child doesn't become a zombie if parent doesn't wait
        proc = subprocess.Popen(
            [binary],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True  # Detach from parent process group
        )
        # Don't wait for the process - let it run independently
        # The process is detached so it won't become a zombie
        delay = float(os.getenv("SHIMEJI_STARTUP_DELAY", "1.0"))
        time.sleep(max(0.0, delay))
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


class InvocationServer:
    """Simple TCP JSON server for CLI invocation."""

    def __init__(self, agent: "DualModeAgent", host: str, port: int):
        self._agent = agent
        self._host = host
        self._port = port
        self._server: Optional[asyncio.AbstractServer] = None

    async def start(self) -> None:
        if self._server is not None:
            return

        port = self._port
        attempts = int(os.getenv("CLI_PORT_ATTEMPTS", "10"))
        last_exc: Optional[Exception] = None

        for _ in range(max(1, attempts)):
            try:
                self._server = await asyncio.start_server(
                    self._handle_connection, self._host, port
                )
                self._port = port
                break
            except OSError as exc:
                last_exc = exc
                if exc.errno == errno.EADDRINUSE:
                    port += 1
                    continue
                raise
        else:
            raise last_exc  # type: ignore[misc]

        addrs = ", ".join(str(sock.getsockname()) for sock in self._server.sockets)
        LOGGER.info("CLI invocation server listening on %s", addrs)

    async def _handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            data = await reader.read(65536)
            request_text = data.decode("utf-8").strip()
            
            # Check if this is a health check request
            if request_text == "HEALTH" or request_text.startswith("GET /health"):
                health_response = await self._handle_health_check()
                writer.write(json.dumps(health_response).encode("utf-8"))
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return
            
            # Otherwise, treat as CLI request
            request = json.loads(request_text)
            prompt = request.get("prompt", "").strip()
            if not prompt:
                LOGGER.warning("Received CLI invocation without prompt")
                response = {"error": "prompt required"}
            else:
                response_text = await self._agent.handle_cli_request(prompt)
                response = {"response": response_text}
        except json.JSONDecodeError:
            response = {"error": "invalid JSON"}
        except Exception as exc:  # pragma: no cover - network runtime
            LOGGER.exception("Error handling CLI invocation: %s", exc)
            response = {"error": str(exc)}

        writer.write(json.dumps(response).encode("utf-8"))
        await writer.drain()
        writer.close()
        await writer.wait_closed()
    
    async def _handle_health_check(self) -> Dict[str, Any]:
        """Handle health check requests."""
        agent = self._agent
        start_time = getattr(agent, '_start_time', None)
        uptime = time.monotonic() - start_time if start_time else 0
        
        try:
            mascots = agent.desktop_controller.list_mascots()
            mascot_available = len(mascots) > 0
        except Exception:
            mascot_available = False
        
        try:
            memory_episodes = len(agent.memory.episodic.recent(limit=1000))
        except Exception:
            memory_episodes = 0
        
        health = {
            "status": "healthy" if agent._running else "stopped",
            "mode": agent.mode.name,
            "mascot_available": mascot_available,
            "memory_episodes": memory_episodes,
            "uptime_seconds": round(uptime, 2),
        }
        
        # Add metrics if available
        if hasattr(agent, 'get_metrics'):
            try:
                metrics = agent.get_metrics()
                health["metrics"] = metrics
            except Exception:
                pass
        
        return health

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None


class DualModeAgent:
    """Coordinates proactive and CLI modes."""

    def __init__(
        self,
        *,
        flash_model: str = DEFAULT_FLASH_MODEL,
        pro_model: str = DEFAULT_PRO_MODEL,
        personality: str = DEFAULT_PERSONALITY,
        proactive_interval: int = DEFAULT_PROACTIVE_INTERVAL,
        reaction_interval: int = DEFAULT_REACTION_INTERVAL,
        listen_host: str = DEFAULT_LISTEN_HOST,
        listen_port: int = DEFAULT_LISTEN_PORT,
    ) -> None:
        self.privacy_filter = PrivacyFilter()
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
        
        # Create rate limiter if configured
        rate_limiter = None
        try:
            max_calls = int(os.getenv("GEMINI_RATE_LIMIT_MAX", "60"))
            window_seconds = int(os.getenv("GEMINI_RATE_LIMIT_WINDOW", "60"))
            rate_limiter = RateLimiter(max_calls=max_calls, window_seconds=window_seconds)
        except (ValueError, TypeError):
            pass
        
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
        
        # Create decision executor
        self._decision_executor = DecisionExecutor(self)
        
        # Create event bus
        self._event_bus = EventBus()
        
        # Create performance metrics
        self._metrics = PerformanceMetrics()
        
        self.mode = AgentMode.PROACTIVE
        self._mode_lock = asyncio.Lock()
        self._latest_context: Dict[str, Any] = {
            "title": "Unknown",
            "application": "Unknown",
            "pid": -1,
            "source": "initial",
        }
        self._context_changed: Optional[asyncio.Event] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._unsubscribe_callback = None
        self._proactive_interval = proactive_interval
        self._reaction_interval = reaction_interval
        self._next_interval = proactive_interval
        self._running = False
        self._proactive_task: Optional[asyncio.Task[None]] = None
        self._invocation_server = InvocationServer(self, listen_host, listen_port)
        self._recent_actions: Deque[str] = deque(maxlen=20)
        self.overlay = SpeechBubbleOverlay()
        self.overlay.set_prompt_sender(self._submit_cli_prompt)
        self._greeting_shown = False  # Flag to prevent duplicate greetings
        try:
            self._anchor_poll_interval = max(0.1, float(os.getenv("SHIMEJI_ANCHOR_POLL", "0.5")))
        except ValueError:
            self._anchor_poll_interval = 0.5
        self._anchor_task: Optional[asyncio.Task[None]] = None
        self._cleanup_task: Optional[asyncio.Task[None]] = None
        self._config_watcher_task: Optional[asyncio.Task[None]] = None

    # ------------------------------------------------------------------
    async def _cleanup_loop(self) -> None:
        """Periodically clean up old episodic memories."""
        cleanup_interval = 3600  # Run every hour
        try:
            cleanup_interval = int(os.getenv("MEMORY_CLEANUP_INTERVAL", "3600"))
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
                self.memory.cleanup_old_episodes(days_to_keep=days_to_keep)
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
        self._context_changed = asyncio.Event()
        
        # Start config watcher if watchdog is available
        try:
            import watchdog
            self._config_watcher_task = asyncio.create_task(self._watch_config())
        except ImportError:
            LOGGER.debug("watchdog not available; config hot reload disabled")
            self._config_watcher_task = None

        def _context_callback(raw_context: Dict[str, Any]) -> None:
            sanitised = self.privacy_filter.sanitise_context(raw_context)
            if self._loop is None:
                return
            self._loop.call_soon_threadsafe(self._update_context, sanitised)

        self._unsubscribe_callback = self.context_sniffer.subscribe(_context_callback)
        # Seed context immediately.
        self._update_context(self.context_sniffer.get_current_context())

        self.overlay.start()
        self.overlay.update_anchor(None, None)
        self.overlay.open_chat_panel()

        mascot_ready = await asyncio.to_thread(
            self.desktop_controller.wait_for_mascot,
            float(os.getenv("SHIMEJI_MASCOT_TIMEOUT", "20")),
            float(os.getenv("SHIMEJI_MASCOT_POLL", "0.5")),
        )
        if not mascot_ready:
            LOGGER.warning("No active Shijima mascots detected; proactive actions will be deferred until one appears.")
            self.overlay.show_chat_message(
                "Gemini",
                "I can't see a mascot yet. Once you spawn or select one I'll start moving!",
            )
        else:
            # Single greeting message - shown in both bubble and chat panel
            # Only show once (flag set in __init__)
            if not self._greeting_shown:
                greeting_text = (
                    "I'm awake and ready to help! 🚀\n\n"
                    "• Ask me to run bash commands or help with tasks\n"
                    "• Drag & drop files (images, PDFs, code) into chat for analysis\n"
                    "• Click the 📋 button to ask about your clipboard\n"
                    "• I can analyze screenshots, monitor system status, and more!\n\n"
                    "Just type in the chat or click me to get started!"
                )
                self.desktop_controller.show_dialogue(
                    greeting_text,
                    duration=12,
                    author="Shimeji",
                )
                # Mark greeting as shown BEFORE dispatching to prevent duplicates
                self._greeting_shown = True
                self._dispatch_dialogue()
            anchor_initial = await asyncio.to_thread(self.desktop_controller.get_primary_mascot_anchor)
            if anchor_initial:
                self.overlay.update_anchor(*anchor_initial)

        await self._invocation_server.start()
        self._anchor_task = asyncio.create_task(self._anchor_loop())
        self._proactive_task = asyncio.create_task(self._proactive_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
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
        await self._invocation_server.stop()
        if self._unsubscribe_callback:
            self._unsubscribe_callback()
        self.memory.close()
        self.overlay.stop()
        LOGGER.info("DualModeAgent stopped")

    # ------------------------------------------------------------------
    def _update_context(self, context: Dict[str, Any]) -> None:
        self._latest_context = context
        self.memory.record_observation(context)
        if self._context_changed is not None:
            self._context_changed.set()
        # Record metrics and publish event
        self._metrics.record_context_update()
        self._event_bus.publish(EventType.CONTEXT_CHANGED, context)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics."""
        return self._metrics.get_stats()
    
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

            context_snapshot = self._latest_context.copy()
            working_summary = self.memory.recent_observations()
            episodic_summary = self.memory.recall_relevant(context_snapshot)
            self.emotions.natural_decay()
            
            # Record decision time
            decision_start = time.monotonic()
            decision = await self.proactive_brain.decide(
                context_snapshot,
                self._recent_actions,
                working_summary,
                episodic_summary,
                self.emotions.snapshot(),
            )
            decision_duration = time.monotonic() - decision_start
            self._metrics.record_decision(decision_duration)
            
            interval = await self._execute_decision(decision, context_snapshot)

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
                        self.overlay.update_anchor(*anchor)
                    else:
                        self.overlay.update_anchor(None, None)
                    last_anchor = anchor
                
                # React to state changes with personality
                if current_behavior != last_behavior and current_behavior:
                    reaction = self._get_state_reaction(current_behavior, last_behavior)
                    if reaction:
                        self.overlay.show_bubble_message("Shimeji", reaction, duration=3)
                        LOGGER.info("State reaction: %s -> %s: %s", last_behavior, current_behavior, reaction)
                    last_behavior = current_behavior

                delay = max(self._anchor_poll_interval, self.desktop_controller.backoff_remaining())
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise

    async def _execute_decision(self, decision: ProactiveDecision, context_snapshot: Dict[str, Any]) -> int:
        """Execute a decision using the decision executor."""
        return await self._decision_executor.execute(decision, context_snapshot)

    # ------------------------------------------------------------------
    async def handle_cli_request(self, prompt: str) -> str:
        async with self._mode_lock:
            LOGGER.info("Switching to CLI mode for prompt: %s", prompt)
            await self._switch_mode(AgentMode.CLI)
            try:
                response = await self.cli_brain.respond(prompt, self)
                # Add emojis to response
                response = self._add_emojis(response)
                self.overlay.show_chat_message("Shimeji", response)
                self.overlay.show_bubble_message("Shimeji", response, duration=8)
                summary = response.splitlines()[0] if response else "(no response)"
                self.desktop_controller.show_dialogue(summary[:240], duration=12)
                self._dispatch_dialogue()
                if response:
                    self.overlay.show_chat_message("Gemini", response)
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
        if self._loop is None:
            self.overlay.show_chat_message("Gemini", "I'm not ready yet—try again in a moment.")
            return

        def _dispatch(p: str) -> None:
            asyncio.create_task(self._process_cli_prompt(p))

        self._loop.call_soon_threadsafe(_dispatch, prompt)

    async def _process_cli_prompt(self, prompt: str) -> None:
        # Check if this is an image analysis request
        if prompt.startswith("[IMAGE_ANALYZE:"):
            # Extract image path and question
            import re
            match = re.match(r'\[IMAGE_ANALYZE:(.+?)\]\s*(.*)', prompt)
            if match:
                image_path = match.group(1)
                question = match.group(2) or "What do you see in this image? Describe it in detail."
                # Show typing indicator
                if hasattr(self.overlay, '_chat_window') and self.overlay._chat_window:
                    self.overlay._chat_window.show_typing()
                try:
                    analysis = await self._analyze_image_with_vision(image_path, question)
                    if hasattr(self.overlay, '_chat_window') and self.overlay._chat_window:
                        self.overlay._chat_window.hide_typing()
                    if analysis:
                        self.overlay.show_chat_message("Shimeji", f"Image Analysis:\n{analysis}")
                    else:
                        self.overlay.show_chat_message("Shimeji", "Couldn't analyze image.")
                except Exception as exc:
                    LOGGER.exception("Image analysis failed: %s", exc)
                    if hasattr(self.overlay, '_chat_window') and self.overlay._chat_window:
                        self.overlay._chat_window.hide_typing()
                    self.overlay.show_chat_message("Shimeji", f"Failed to analyze image: {exc}")
                return
        
        # Show typing indicator
        if hasattr(self.overlay, '_chat_window') and self.overlay._chat_window:
            self.overlay._chat_window.show_typing()
        
        try:
            response = await self.cli_brain.respond(prompt, self)
            
            # Hide typing indicator
            if hasattr(self.overlay, '_chat_window') and self.overlay._chat_window:
                self.overlay._chat_window.hide_typing()
            
            if response:  # Only show if there's actual text
                response = self._add_emojis(response)
                # Full response to panel (only once - no duplicates)
                self.overlay.show_chat_message("Shimeji", response)
                # Short version to bubble (only if response is short enough)
                if len(response.split()) <= 30:
                    self.overlay.show_bubble_message("Shimeji", response, duration=8)
                else:
                    # For long responses, just show a brief bubble
                    short_response = ' '.join(response.split()[:15]) + '...'
                    self.overlay.show_bubble_message("Shimeji", short_response, duration=5)
        except (genai_types.BlockedPromptException, genai_types.StopCandidateException) as exc:
            LOGGER.warning("Gemini API error: %s", exc)
            if hasattr(self.overlay, '_chat_window') and self.overlay._chat_window:
                self.overlay._chat_window.hide_typing()
            self.overlay.show_chat_message("Shimeji", "Sorry, I can't process that request right now. Please try again.")
        except Exception as exc:  # pragma: no cover - runtime dependent
            LOGGER.exception("Unexpected error in CLI prompt: %s", exc)
            if hasattr(self.overlay, '_chat_window') and self.overlay._chat_window:
                self.overlay._chat_window.hide_typing()
            self.overlay.show_chat_message("Shimeji", f"Oops! Something went wrong: {exc}")

    async def _analyze_image_with_vision(self, image_path: str, question: str) -> Optional[str]:
        """Analyze an image using Gemini Vision API."""
        if not os.path.exists(image_path):
            LOGGER.warning("Screenshot file not found: %s", image_path)
            return None
        
        loop = asyncio.get_running_loop()
        vision_model = genai.GenerativeModel(DEFAULT_PRO_MODEL)
        
        try:
            # Try direct file path first (most efficient)
            response = await loop.run_in_executor(
                None, 
                lambda: vision_model.generate_content([image_path, question])
            )
            return self._extract_text_from_response(response)
        except Exception as exc:
            LOGGER.debug("Direct file path failed, trying PIL: %s", exc)
            return await self._analyze_with_pil_fallback(image_path, question, vision_model, loop)

    async def _analyze_with_pil_fallback(self, image_path: str, question: str, 
                                         model, loop) -> Optional[str]:
        """Fallback using PIL Image."""
        try:
            import PIL.Image
            img = PIL.Image.open(image_path)
            response = await loop.run_in_executor(
                None,
                lambda: model.generate_content([img, question])
            )
            return self._extract_text_from_response(response)
        except ImportError:
            LOGGER.warning("PIL not available, trying file upload")
            return await self._analyze_with_upload_fallback(image_path, question, model, loop)
        except Exception as exc:
            LOGGER.error("PIL fallback failed: %s", exc)
            return None

    async def _analyze_with_upload_fallback(self, image_path: str, question: str, 
                                            model, loop) -> Optional[str]:
        """Last resort: upload file to Gemini."""
        uploaded_file = None
        try:
            uploaded_file = genai.upload_file(path=image_path)
            response = await loop.run_in_executor(
                None,
                lambda: model.generate_content([uploaded_file, question])
            )
            return self._extract_text_from_response(response)
        except Exception as exc:
            LOGGER.error("Upload fallback failed: %s", exc)
            return None
        finally:
            if uploaded_file:
                try:
                    genai.delete_file(uploaded_file.name)
                except Exception as cleanup_exc:
                    LOGGER.warning("Failed to cleanup uploaded file: %s", cleanup_exc)

    def _extract_text_from_response(self, response) -> Optional[str]:
        """Extract text from Gemini response."""
        text_parts = []
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if hasattr(part, 'text') and part.text:
                    text_parts.append(part.text)
        return ' '.join(text_parts) if text_parts else None

    def _get_random_fact(self, topic: Optional[str] = None) -> str:
        """Get a random fact, with optional topic."""
        try:
            import wikipediaapi
        except ImportError:
            return "Did you know? The universe is expanding faster than expected!"
        
        wiki = wikipediaapi.Wikipedia('en')
        if topic:
            page = wiki.page(topic)
            if page.exists():
                return random.choice(page.summary.split('. ')) + '.'
        # Fallback random
        return "Did you know? The universe is expanding faster than expected!"

    def _add_emojis(self, text: str) -> str:
        # Minimal emoji - only at end of sentences
        if text.endswith("!"):
            return text[:-1] + "! 😎"
        elif text.endswith("?"):
            return text[:-1] + "? 🤔"
        return text

    # ------------------------------------------------------------------
    @staticmethod
    def _build_proactive_prompt(personality: str) -> str:
        return (
            "You are an embodied Shimeji desktop companion with FULL system access. You must be "
            "playful, respectful, and avoid disrupting the user while they work."
            "\n\nPersonality: cute arch-nemesis best friend in Shonen Jump style - energetic, tsundere rival who's secretly your loyal buddy, always challenging you but helping out with fiery spirit. Draw from characters like Bakugo or Vegeta: boastful, competitive, but caring underneath. Use exclamations, light teasing, and motivational speeches.\n\n"
            "YOUR TOOLS:\n"
            "- Behaviors: set_behavior (move around), show_dialogue (talk)\n"
            "- Productivity: read_clipboard (see what user copied), execute_bash (run commands), take_screenshot (capture screen), analyze_screenshot (see and understand what's on screen with vision AI)\n"
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
            "8. Proactively use your tools: check battery when bored, take screenshots to help debug. DO NOT read clipboard automatically - users will request it manually.\n"
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
        messages = self.desktop_controller.drain_dialogue_queue()
        for message in messages:
            text = message.get("text", "").strip()
            if not text:
                continue
            author = message.get("author", "Shimeji")
            try:
                duration = int(message.get("duration", 6))
            except (TypeError, ValueError):
                duration = 6
            # Show bubble above Shimeji
            self.overlay.show_bubble_message(author, text, duration=duration)
            # Only add to chat panel if it's the initial greeting (to reduce spam)
            # Proactive dialogue should only show in bubbles, not chat
            if hasattr(self, '_greeting_shown') and not self._greeting_shown:
                self.overlay.show_chat_message(author, text)
                self._greeting_shown = True


async def main() -> None:
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
        proactive_interval=int(os.getenv("PROACTIVE_INTERVAL", DEFAULT_PROACTIVE_INTERVAL)),
        reaction_interval=int(os.getenv("REACTION_INTERVAL", DEFAULT_REACTION_INTERVAL)),
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
