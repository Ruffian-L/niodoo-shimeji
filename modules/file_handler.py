"""File handling for drag-and-drop file analysis."""

import asyncio
import logging
from inspect import isawaitable
from typing import Any, Optional

from modules.emotion_model import EmotionModel
from modules.input_sanitizer import InputSanitizer
from modules.memory_manager import MemoryManager

LOGGER = logging.getLogger(__name__)


async def _maybe_await(value: Any) -> Any:
    """Return awaited value when coroutine-like, otherwise passthrough."""
    if isawaitable(value):
        return await value
    return value


class FileHandler:
    """Handles file drop events and analysis."""

    def __init__(self, proactive_brain, memory: MemoryManager, emotions: EmotionModel, execute_decision_callback):
        self.proactive_brain = proactive_brain
        self.memory = memory
        self.emotions = emotions
        self._execute_decision = execute_decision_callback
        self._latest_context = {}
        self._recent_actions = []

    def set_context(self, latest_context: dict, recent_actions: list) -> None:
        """Update context information."""
        self._latest_context = latest_context
        self._recent_actions = recent_actions

    async def handle_file_drop(self, data: Any) -> None:
        """Handle file drop event.

        Args:
            data: Event data containing file_path or text
        """
        if not isinstance(data, dict):
            return

        file_path = data.get("file_path")
        text = data.get("text")
        source = data.get("source", "unknown")

        # Trigger proactive analysis
        await self._handle_proactive_file_drop(file_path, text)

    async def _handle_proactive_file_drop(self, file_path: Optional[str], text: Optional[str]) -> None:
        """Handle file drop in proactive mode.

        Args:
            file_path: Path to dropped file (if file)
            text: Dropped text (if text)
        """
        if file_path:
            # Sanitize file path
            sanitized_path = InputSanitizer.sanitize_file_path(file_path)
            if not sanitized_path:
                LOGGER.warning("Invalid file path provided: %s", file_path)
                return

            # Analyze file with proactive agent
            prompt = (
                f"The user just dropped this file on me: {sanitized_path}\n"
                "Analyze its content and suggest 3-5 relevant, actionable tool calls "
                "(e.g., 'Summarize', 'Rename based on content', 'Move to /Documents/Reports')."
            )
            try:
                decision = await _maybe_await(
                    self.proactive_brain.decide(
                        self._latest_context,
                        self._recent_actions,
                        self.memory.recent_observations(),
                        await _maybe_await(self.memory.recall_relevant_async(self._latest_context)),
                        self.emotions.snapshot(),
                    )
                )
                await _maybe_await(self._execute_decision(decision, self._latest_context))
            except Exception as exc:
                LOGGER.error("Proactive file analysis failed: %s", exc)
        elif text:
            # Sanitize text input
            sanitized_text = InputSanitizer.sanitize_text(text)
            if not sanitized_text:
                LOGGER.warning("Text input is empty after sanitization")
                return

            # Analyze text snippet
            prompt = f"The user dropped this text: {sanitized_text}\nWhat should I do with it?"
            try:
                decision = await _maybe_await(
                    self.proactive_brain.decide(
                        self._latest_context,
                        self._recent_actions,
                        self.memory.recent_observations(),
                        await _maybe_await(self.memory.recall_relevant_async(self._latest_context)),
                        self.emotions.snapshot(),
                    )
                )
                await _maybe_await(self._execute_decision(decision, self._latest_context))
            except Exception as exc:
                LOGGER.error("Proactive text analysis failed: %s", exc)