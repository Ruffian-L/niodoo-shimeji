"""Core cognitive helpers extracted from the dual-mode agent.

The goal of this module is to decouple heavyweight cognitive/workflow
logic from the UI/process orchestration that lives in
``shimeji_dual_mode_agent.py``.  Functions here operate purely on injected
collaborators (brains, overlays, process pools) so they can be re-used by
future FastAPI services or alternative presentation layers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from collections import deque
from datetime import UTC, datetime
from concurrent.futures import Executor
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Deque, Dict, Optional, Tuple, TYPE_CHECKING
from datetime import UTC, datetime

import google.generativeai as genai
from google.generativeai import types as genai_types

from modules.constants import DEFAULT_PRO_MODEL
from modules.genai_utils import get_cached_model
from modules.permission_manager import PermissionScope, PermissionStatus
from modules.presentation_api import UIEvent
from modules.system_monitor import SystemAlert, AlertSeverity
from modules.event_bus import EventType
from modules.file_handler import FileHandler
from modules.input_sanitizer import InputSanitizer

LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    from modules.brains import CLIBrain
    from modules.brains import ProactiveBrain, ProactiveDecision
    from modules.memory_manager import MemoryManager
    from modules.emotion_model import EmotionModel
    from modules.metrics import PerformanceMetrics
    from modules.event_bus import EventBus
    from modules.decision_executor import DecisionExecutor
    from modules.presentation_api import AvatarClient, UIEventSink
    from modules.permission_manager import PermissionManager
    from modules.system_monitor import MonitoringManager
    from shimeji_dual_mode_agent import DualModeAgent


@dataclass
class AgentCoreConfig:
    cli_brain: "CLIBrain"
    proactive_brain: "ProactiveBrain"
    avatar_client: "AvatarClient"
    ui_event_sink: "UIEventSink"
    process_pool: Optional[Executor]
    memory: "MemoryManager"
    emotions: "EmotionModel"
    metrics: "PerformanceMetrics"
    permission_manager: Optional["PermissionManager"]
    take_screenshot: Callable[[], Optional[str]]
    update_context: Callable[[Dict[str, Any]], None]
    latest_context_getter: Callable[[], Dict[str, Any]]
    context_getter: Callable[[], Awaitable[Dict[str, Any]]]
    context_lock_getter: Optional[Callable[[], Optional[asyncio.Lock]]] = None
    set_latest_vision_analysis: Optional[Callable[[Optional[Dict[str, Any]]], None]] = None
    transition_mascot_state: Optional[Callable[[str], None]] = None
    event_bus: Optional["EventBus"] = None
    decision_executor: Optional["DecisionExecutor"] = None
    monitoring_manager: Optional["MonitoringManager"] = None
    show_alert_notification: Optional[Callable[[SystemAlert], None]] = None


class AgentCore:
    """Container for reusable agent behaviours and helpers.

    The core owns cognition-heavy flows (CLI, proactive cycles, vision analysis,
    decision execution) while exposing small utilities runners can call, such as
    context accessors and `register_action` for history/memory bookkeeping.
    """

    def __init__(
        self,
        config: AgentCoreConfig,
    ) -> None:
        self._cli_brain = config.cli_brain
        self._proactive_brain = config.proactive_brain
        self._avatar_client = config.avatar_client
        self._ui_event_sink = config.ui_event_sink
        self._process_pool = config.process_pool
        self._memory = config.memory
        self._emotions = config.emotions
        self._metrics = config.metrics
        self._permission_manager = config.permission_manager
        self._take_screenshot = config.take_screenshot
        self._update_context_callback = config.update_context
        self._latest_context_getter = config.latest_context_getter
        self._context_lock_getter = config.context_lock_getter or (lambda: None)
        self._set_latest_vision_analysis = config.set_latest_vision_analysis or (lambda _: None)
        self._context_getter = config.context_getter
        self._transition_mascot_state = config.transition_mascot_state or (lambda _state: None)
        self._event_bus = config.event_bus
        self._decision_executor = config.decision_executor
        self._monitoring_manager = config.monitoring_manager
        self._show_alert_notification = config.show_alert_notification or (lambda _alert: None)
        self._critical_alert_cache: Dict[str, float] = {}
        self._recent_actions: Optional[Deque[str]] = None
        self._vision_prompt = (
            "Analyze this desktop screenshot. Identify the active application, "
            "window title, and any key UI elements or text. Based on this, "
            "what is the user's most likely current task? Also detect any error "
            "messages, pop-up dialogs, or stack traces. If found, extract the "
            "full text of the error. Respond with JSON: "
            "{'app': '...', 'task': '...', 'file': '...', 'error_text': '...'}"
        )
        self._file_handler = FileHandler(self)
        if self._event_bus:
            self._event_bus.subscribe(EventType.DECISION_MADE, self._handle_decision_made_event)
            self._event_bus.subscribe(EventType.MESSAGE_SENT, self._handle_message_sent_event)
            self._event_bus.subscribe(EventType.SYSTEM_ALERT, self._handle_system_alert_event)
            self._event_bus.subscribe(EventType.DBUS_NOTIFICATION, self._handle_dbus_notification_event)

    async def process_cli_prompt(self, agent: "DualModeAgent", prompt: str) -> None:
        """Process a CLI prompt, including vision and chat updates."""

        # Image analysis shortcut: "[IMAGE_ANALYZE:/path] question"
        if prompt.startswith("[IMAGE_ANALYZE:"):
            match = re.match(r"\[IMAGE_ANALYZE:(.+?)\]\s*(.*)", prompt)
            if match:
                image_path = match.group(1)
                question = match.group(2) or "What do you see in this image? Describe it in detail."
                self._show_typing_indicator()
                try:
                    analysis = await self._analyze_image_with_vision(image_path, question)
                    self._hide_typing_indicator()
                    if analysis:
                        self._emit_chat("Shimeji", f"Image Analysis:\n{analysis}")
                    else:
                        self._emit_chat("Shimeji", "Couldn't analyze image.")
                except Exception as exc:  # pragma: no cover - runtime dependent
                    LOGGER.exception("Image analysis failed: %s", exc)
                    self._hide_typing_indicator()
                    self._emit_chat("Shimeji", f"Failed to analyze image: {exc}")
                return

        self._show_typing_indicator()

        try:
            response = await self._cli_brain.respond(prompt, agent)
            self._hide_typing_indicator()

            if response:
                response = self.add_emojis(response)
                self._emit_chat("Shimeji", response)
                if len(response.split()) <= 30:
                    self._emit_bubble("Shimeji", response, duration=8)
                else:
                    short_response = " ".join(response.split()[:15]) + "..."
                    self._emit_bubble("Shimeji", short_response, duration=5)
        except (genai_types.BlockedPromptException, genai_types.StopCandidateException) as exc:
            LOGGER.warning("Gemini API error: %s", exc)
            self._hide_typing_indicator()
            self._emit_chat(
                "Shimeji",
                "Sorry, I can't process that request right now. Please try again.",
            )
        except Exception as exc:  # pragma: no cover - runtime dependent
            LOGGER.exception("Unexpected error in CLI prompt: %s", exc)
            self._hide_typing_indicator()
            self._emit_chat("Shimeji", f"Oops! Something went wrong: {exc}")

    async def handle_cli_request(
        self,
        prompt: str,
        agent: "DualModeAgent",
        *,
        enqueue_dialogue: Callable[[str], None],
    ) -> Optional[str]:
        """Handle a CLI request end-to-end."""

        response = await self._cli_brain.respond(prompt, agent)
        if not response:
            return response

        response = self.add_emojis(response)
        self._emit_chat("Shimeji", response)
        self._emit_bubble("Shimeji", response, duration=8)
        enqueue_dialogue(response)
        self._emit_chat("Gemini", response)
        return response

    def sanitize_cli_prompt(self, prompt: str) -> Optional[str]:
        """Normalize a CLI prompt or return ``None`` if it collapses to empty."""

        if not prompt:
            return None
        sanitized = InputSanitizer.sanitize_prompt(prompt)
        return sanitized or None

    def update_file_handler_context(
        self,
        latest_context: Dict[str, Any],
        recent_actions: Deque[str],
    ) -> None:
        self._recent_actions = recent_actions
        self._file_handler.set_context(latest_context, recent_actions)

    async def handle_file_drop(self, data: Any) -> None:
        await self._file_handler.handle_file_drop(data)

    def register_action(self, action: str, arguments: Dict[str, Any]) -> None:
        """Record an action in history and memory for downstream context."""

        timestamp = datetime.now(UTC).isoformat()
        if self._recent_actions is not None:
            self._recent_actions.append(f"{timestamp}:{action}")
        self._memory.record_action(action, arguments)

    def latest_context(self) -> Dict[str, Any]:
        """Return the most recent context snapshot supplied by the manager."""

        return self._latest_context_getter()

    def update_context(self, context: Dict[str, Any]) -> None:
        """Replace the latest context using the injected callback."""

        self._update_context_callback(context)

    async def merge_context(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Merge updates into the latest context under the shared lock."""

        lock = self._context_lock_getter()
        if lock:
            async with lock:
                merged = {**self._latest_context_getter(), **updates}
                self._update_context_callback(merged)
                return merged

        merged = {**self._latest_context_getter(), **updates}
        self._update_context_callback(merged)
        return merged

    def _handle_decision_made_event(self, data: Any) -> None:
        self._transition_mascot_state("Pondering")

    def _handle_message_sent_event(self, data: Any) -> None:
        self._transition_mascot_state("Interacting")

    def _handle_dbus_notification_event(self, data: Any) -> None:
        self.handle_dbus_notification(data)

    def _handle_system_alert_event(self, alert: SystemAlert) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            LOGGER.warning("System alert received without running event loop; dropping alert")
            return
        loop.create_task(self.handle_system_alert(alert))

    async def handle_system_alert(self, alert: SystemAlert) -> None:
        """Route system alerts to notifications or proactive handling."""

        if alert.severity == AlertSeverity.CRITICAL:
            recent_actions = self._recent_actions
            if recent_actions is None:
                recent_actions = deque(maxlen=20)
                self._recent_actions = recent_actions
            context_snapshot = await self._context_getter()
            await self.handle_critical_alert(
                alert,
                context=context_snapshot,
                recent_actions=recent_actions,
                show_alert_notification=self._show_alert_notification,
            )
            return

        self._show_alert_notification(alert)

    def handle_dbus_notification(self, data: Any) -> None:
        """Process DBus notification/metadata events published on the bus."""

        if not isinstance(data, dict):
            LOGGER.debug("Ignoring non-dict DBus payload: %s", data)
            return

        event_type = data.get("type")
        if event_type == "media_playing":
            player = data.get("player", "unknown")
            metadata = data.get("metadata", {})
            title = metadata.get("xesam:title", "Unknown")
            LOGGER.debug("Media playing: %s - %s", player, title)
        elif event_type == "notification":
            app_name = data.get("app_name", "unknown")
            summary = data.get("summary", "")
            body = data.get("body", "")
            LOGGER.debug("Notification from %s: %s - %s", app_name, summary, body)

    async def compute_proactive_decision(
        self,
        *,
        context_snapshot: Dict[str, Any],
        recent_actions: Deque[str],
    ) -> "ProactiveDecision":
        """Run the proactive brain and record metrics.

        Args:
            context_snapshot: Latest desktop context dict.
            recent_actions: Deque of recent behaviour summaries (shared with runner).

        Returns:
            The `ProactiveDecision` generated by the Gemini Flash brain.
        """

        working_summary = self._memory.recent_observations()
        episodic_summary = await self._memory.recall_relevant_async(context_snapshot)
        self._emotions.natural_decay()

        decision_start = time.monotonic()
        decision = await self._proactive_brain.decide(
            context_snapshot,
            recent_actions,
            working_summary,
            episodic_summary,
            self._emotions.snapshot(),
        )
        self._metrics.record_decision(time.monotonic() - decision_start)
        return decision

    async def proactive_cycle(
        self,
        *,
        context_snapshot: Dict[str, Any],
        recent_actions: Deque[str],
    ) -> Tuple["ProactiveDecision", int]:
        """Run a full proactive decision cycle and return the interval.

        This helper mirrors the historical `_proactive_loop` responsibilities by
        chaining `compute_proactive_decision` with `execute_decision`, returning
        both the decision object (for logging/tests) and the next interval the
        scheduler should wait before the following cycle.
        """

        decision = await self.compute_proactive_decision(
            context_snapshot=context_snapshot,
            recent_actions=recent_actions,
        )
        interval = await self.execute_decision(decision, context_snapshot)
        return decision, interval

    async def proactive_loop(
        self,
        *,
        context_event: asyncio.Event,
        is_running: Callable[[], bool],
        is_proactive_mode: Callable[[], bool],
        interval_getter: Callable[[], int],
        recent_actions: Deque[str],
    ) -> None:
        """Own the proactive wait loop and reuse AgentCore's decision helpers."""

        interval = interval_getter()
        while is_running():
            try:
                await asyncio.wait_for(context_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
            finally:
                context_event.clear()

            if not is_running():
                break

            if not is_proactive_mode():
                interval = interval_getter()
                continue

            context_snapshot = await self._context_getter()
            _, interval = await self.proactive_cycle(
                context_snapshot=context_snapshot,
                recent_actions=recent_actions,
            )

    async def vision_analysis_loop(
        self,
        agent: "DualModeAgent",
        *,
        interval: int,
        is_running: Callable[[], bool],
    ) -> None:
        """Background loop that performs periodic vision probes."""

        while is_running():
            try:
                await asyncio.sleep(interval)
                if not is_running():
                    break
                await self._perform_vision_analysis(agent)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - runtime dependent
                LOGGER.error("Vision analysis loop error: %s", exc)

    async def memory_cleanup_loop(
        self,
        *,
        is_running: Callable[[], bool],
        interval_seconds: int,
        days_to_keep: int,
    ) -> None:
        """Periodically prune old episodic memories while the agent runs."""

        interval = max(0, interval_seconds)
        while is_running():
            await asyncio.sleep(interval)
            if not is_running():
                break
            try:
                await self._memory.cleanup_old_episodes_async(days_to_keep=days_to_keep)
                LOGGER.debug(
                    "Cleaned up old episodic memories (kept last %d days)",
                    days_to_keep,
                )
            except Exception as exc:  # pragma: no cover - defensive logging
                LOGGER.warning("Memory cleanup failed: %s", exc)

    async def start_system_monitoring(self) -> None:
        """Start the MonitoringManager if one was provided."""

        if not self._monitoring_manager:
            return
        try:
            await self._monitoring_manager.start()
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.error("Failed to start system monitoring: %s", exc)

    async def stop_system_monitoring(self) -> None:
        """Stop the MonitoringManager if running."""

        if not self._monitoring_manager:
            return
        try:
            await self._monitoring_manager.stop()
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.error("Failed to stop system monitoring: %s", exc)

    async def _perform_vision_analysis(self, agent: "DualModeAgent") -> None:
        if not self._take_screenshot:
            return

        if self._permission_manager:
            agent_id = "ProactiveBrain"
            permission = await self._permission_manager.check_permission_async(
                agent_id,
                PermissionScope.CONTEXT_VISION_READ_SCREEN,
            )
            if permission == PermissionStatus.DENY:
                LOGGER.debug("Vision analysis denied by permission")
                return

        screenshot_path = self._take_screenshot()
        if not screenshot_path:
            return

        analysis = await self._analyze_image_with_vision(str(screenshot_path), self._vision_prompt)
        if not analysis:
            return

        try:
            parsed = self._parse_vision_analysis(analysis)
            if parsed:
                self._set_latest_vision_analysis(parsed)
                await self.merge_context({"vision_analysis": parsed})
                error_text = parsed.get("error_text")
                if error_text:
                    await self.handle_detected_error(agent, error_text)
            else:
                LOGGER.debug("Vision analysis returned unstructured content; caching raw output")
                cached = {"raw": analysis}
                self._set_latest_vision_analysis(cached)
                await self.merge_context({"vision_analysis": cached})
        except Exception as exc:  # pragma: no cover - runtime dependent
            LOGGER.error("Vision analysis parsing error: %s", exc)
            cached = {"raw": analysis}
            self._set_latest_vision_analysis(cached)
            await self.merge_context({"vision_analysis": cached})

    @staticmethod
    def _parse_vision_analysis(analysis: str) -> Optional[Dict[str, Any]]:
        if "{" not in analysis or "}" not in analysis:
            return None
        json_start = analysis.find("{")
        json_end = analysis.rfind("}")
        if json_start == -1 or json_end == -1 or json_end <= json_start:
            return None
        json_str = analysis[json_start:json_end + 1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as exc:
            LOGGER.warning("Vision analysis JSON decode failed: %s", exc)
            LOGGER.debug("Vision analysis payload: %s", analysis)
            return None

    async def handle_detected_error(self, agent: "DualModeAgent", error_text: str) -> None:
        context = await self._context_getter()
        context["detected_error"] = error_text
        working_summary = self._memory.recent_observations()
        error_prompt = (
            f"The user just encountered this error on their screen: {error_text}\n\n"
            "1. Explain this error in simple terms.\n"
            "2. Provide 3 concrete, step-by-step solutions the user might try.\n"
            "3. Suggest a bash command or code snippet as a tool-call if appropriate."
        )

        try:
            response = await self._cli_brain.respond(error_prompt, agent)
            if response:
                self._emit_chat("Shimeji", f"🚨 Error Detected!\n\n{response}")
                self._emit_bubble("Shimeji", "I saw an error! Check chat for help.", duration=10)
                self._transition_mascot_state("Alert")
        except Exception as exc:  # pragma: no cover - runtime dependent
            LOGGER.error("Error resolution failed: %s", exc)

    async def handle_critical_alert(
        self,
        alert: SystemAlert,
        *,
        context: Dict[str, Any],
        recent_actions: Deque[str],
        show_alert_notification: Callable[[SystemAlert], None],
        rate_limit_seconds: int = 300,
    ) -> None:
        """Handle a critical system alert via the proactive brain."""

        cache_key = f"critical_alert:{alert.alert_type}"
        now = time.monotonic()
        last_trigger = self._critical_alert_cache.get(cache_key)
        if last_trigger is not None and now - last_trigger < rate_limit_seconds:
            LOGGER.debug("Critical alert rate limited: %s", alert.alert_type)
            show_alert_notification(alert)
            return

        self._critical_alert_cache[cache_key] = now

        try:
            context = dict(context)
            context["system_alert"] = {
                "type": alert.alert_type,
                "message": alert.message,
                "details": alert.details,
            }
            working_summary = self._memory.recent_observations()
            episodic_summary = await self._memory.recall_relevant_async(context)
            decision = await self._proactive_brain.decide(
                context,
                recent_actions,
                working_summary,
                episodic_summary,
                self._emotions.snapshot(),
            )
            await self.execute_decision(decision, context)
        except Exception as exc:  # pragma: no cover - runtime dependent
            LOGGER.error("Failed to handle critical alert: %s", exc)
            show_alert_notification(alert)

    async def execute_decision(
        self,
        decision: "ProactiveDecision",
        context_snapshot: Dict[str, Any],
    ) -> int:
        if self._event_bus:
            self._event_bus.publish(EventType.DECISION_MADE, {"action": decision.action})
        self._transition_mascot_state("ExecutingTask")
        if not self._decision_executor:
            LOGGER.warning("Decision executor unavailable; skipping execution")
            self._transition_mascot_state("Idle")
            return 0
        result = await self._decision_executor.execute(decision, context_snapshot)
        self._transition_mascot_state("Idle")
        return result

    def _emit_chat(self, author: str, text: str) -> None:
        if not text or not self._ui_event_sink:
            return
        self._ui_event_sink.emit(UIEvent("chat_message", {"author": author, "text": text}))

    def _emit_bubble(self, author: str, text: str, *, duration: int) -> None:
        if not text or not self._ui_event_sink:
            return
        payload = {"author": author, "text": text, "duration": int(max(1, duration))}
        self._ui_event_sink.emit(UIEvent("bubble_message", payload))

    def _show_typing_indicator(self) -> None:
        if self._ui_event_sink:
            self._ui_event_sink.emit(UIEvent("chat_typing", {"state": "show"}))

    def _hide_typing_indicator(self) -> None:
        if self._ui_event_sink:
            self._ui_event_sink.emit(UIEvent("chat_typing", {"state": "hide"}))

    async def _analyze_image_with_vision(self, image_path: str, question: str) -> Optional[str]:
        if not os.path.exists(image_path):
            return None

        loop = asyncio.get_running_loop()
        vision_model = get_cached_model(DEFAULT_PRO_MODEL)
        executor = self._process_pool
        try:
            response = await loop.run_in_executor(
                executor,
                lambda: vision_model.generate_content([image_path, question]),
            )
            return self._extract_text_from_response(response)
        except Exception as exc:
            LOGGER.debug("Direct file path failed, trying PIL: %s", exc)
            return await self._analyze_with_pil_fallback(image_path, question, vision_model, loop)

    async def _analyze_with_pil_fallback(
        self,
        image_path: str,
        question: str,
        model: Any,
        loop: asyncio.AbstractEventLoop,
    ) -> Optional[str]:
        try:
            import PIL.Image

            def _generate_content(img_path: str, q: str, mdl) -> Any:
                img = PIL.Image.open(img_path)
                return mdl.generate_content([img, q])

            response = await loop.run_in_executor(
                self._process_pool,
                _generate_content,
                image_path,
                question,
                model,
            )
            return self._extract_text_from_response(response)
        except ImportError:
            return await self._analyze_with_upload_fallback(image_path, question, model, loop)
        except Exception as exc:
            LOGGER.error("PIL fallback failed: %s", exc)
            return None

    async def _analyze_with_upload_fallback(
        self,
        image_path: str,
        question: str,
        model: Any,
        loop: asyncio.AbstractEventLoop,
    ) -> Optional[str]:
        uploaded_file = None
        try:
            def _upload_file(path: str) -> Any:
                return genai.upload_file(path=path)

            def _generate_with_upload(uf, q: str, mdl) -> Any:
                return mdl.generate_content([uf, q])

            executor = self._process_pool
            uploaded_file = await loop.run_in_executor(executor, _upload_file, image_path)
            response = await loop.run_in_executor(
                executor,
                _generate_with_upload,
                uploaded_file,
                question,
                model,
            )
            return self._extract_text_from_response(response)
        except Exception as exc:
            LOGGER.error("Upload fallback failed: %s", exc)
            return None
        finally:
            if uploaded_file is not None:
                try:
                    def _delete_file(name: str) -> None:
                        genai.delete_file(name)

                    await loop.run_in_executor(self._process_pool, _delete_file, uploaded_file.name)
                except Exception as cleanup_exc:
                    LOGGER.warning("Failed to cleanup uploaded file: %s", cleanup_exc)

    @staticmethod
    def _extract_text_from_response(response) -> Optional[str]:
        text_parts = []
        for candidate in getattr(response, "candidates", []):
            content = getattr(candidate, "content", None)
            if content is None:
                continue
            for part in getattr(content, "parts", []):
                text = getattr(part, "text", None)
                if text:
                    text_parts.append(text)
        return " ".join(text_parts) if text_parts else None

    @staticmethod
    def add_emojis(text: str) -> str:
        if text.endswith("!"):
            return text[:-1] + "! 😎"
        if text.endswith("?"):
            return text[:-1] + "? 🤔"
        return text

    @staticmethod
    def get_random_fact(topic: Optional[str] = None) -> str:
        try:
            import wikipediaapi
        except ImportError:
            return "Did you know? The universe is expanding faster than expected!"

        wiki = wikipediaapi.Wikipedia("en")
        if topic:
            page = wiki.page(topic)
            if page.exists():
                summaries = page.summary.split('. ')
                return summaries[0].strip() + '.' if summaries else page.summary
        return "Did you know? The universe is expanding faster than expected!"
