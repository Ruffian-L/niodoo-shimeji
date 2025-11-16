"""Focused tests for AgentCore helpers."""

import asyncio
from collections import deque
from unittest.mock import AsyncMock, MagicMock

from modules.agent_core import AgentCore


async def _merge_context_stub(context):
    return context


async def _get_context_stub():
    return {}


def _build_core() -> AgentCore:
    return AgentCore(
        cli_brain=MagicMock(),
        proactive_brain=MagicMock(),
        avatar_client=MagicMock(),
        ui_event_sink=MagicMock(),
        process_pool=None,
        memory=MagicMock(),
        emotions=MagicMock(),
        metrics=MagicMock(),
        permission_manager=None,
        take_screenshot=lambda: None,
        merge_context=_merge_context_stub,
        set_latest_vision_analysis=lambda _: None,
        context_getter=_get_context_stub,
        transition_mascot_state=lambda _state: None,
        event_bus=MagicMock(),
        decision_executor=MagicMock(),
    )


def test_sanitize_cli_prompt_trims_and_returns_value():
    core = _build_core()

    result = core.sanitize_cli_prompt("  Hello there!  ")

    assert result == "Hello there!"


def test_sanitize_cli_prompt_rejects_empty_input():
    core = _build_core()

    assert core.sanitize_cli_prompt("") is None
    assert core.sanitize_cli_prompt("   \t") is None


def test_file_handler_hooks_are_exposed():
    core = _build_core()
    fake_handler = MagicMock()
    fake_handler.handle_file_drop = AsyncMock()
    core._file_handler = fake_handler  # type: ignore[attr-defined]

    actions = deque(["a1", "a2"])
    core.update_file_handler_context({"app": "Code"}, actions)
    fake_handler.set_context.assert_called_once_with({"app": "Code"}, actions)

    asyncio.run(core.handle_file_drop({"file_path": "/tmp/file.txt"}))
    fake_handler.handle_file_drop.assert_awaited_once()
