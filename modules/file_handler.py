"""File handling for drag-and-drop file analysis."""

import logging
from collections import deque
from typing import Any, Deque, Dict, Optional, TYPE_CHECKING

from modules.input_sanitizer import InputSanitizer

if TYPE_CHECKING:  # pragma: no cover
    from modules.agent_core import AgentCore

LOGGER = logging.getLogger(__name__)


class FileHandler:
    """Handles file drop events and analysis."""

    def __init__(self, agent_core: "AgentCore", *, action_history_size: int = 20):
        self._core = agent_core
        self._latest_context: Dict[str, Any] = {}
        self._recent_actions: Deque[str] = deque(maxlen=action_history_size)

    def set_context(self, latest_context: Dict[str, Any], recent_actions: Deque[str]) -> None:
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

            try:
                await self._run_file_analysis()
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.error("Proactive file analysis failed: %s", exc)
        elif text:
            # Sanitize text input
            sanitized_text = InputSanitizer.sanitize_text(text)
            if not sanitized_text:
                LOGGER.warning("Text input is empty after sanitization")
                return

            try:
                await self._run_file_analysis()
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.error("Proactive text analysis failed: %s", exc)

    async def _run_file_analysis(self) -> None:
        """Invoke the shared proactive decision pipeline via AgentCore."""

        decision = await self._core.compute_proactive_decision(
            context_snapshot=self._latest_context,
            recent_actions=self._recent_actions,
        )
        await self._core.execute_decision(decision, self._latest_context)