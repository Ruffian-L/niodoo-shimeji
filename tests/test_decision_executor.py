"""Tests for DecisionExecutor UI event emission."""

from collections import deque
from unittest.mock import AsyncMock, MagicMock

import pytest

from modules.decision_executor import DecisionExecutor
from modules.permission_manager import PermissionManager, PermissionScope, PermissionStatus
from modules.presentation_api import UIEvent


class _DummyEventBus:
    def __init__(self) -> None:
        self.published = []

    def publish(self, event_type, payload):
        self.published.append((event_type, payload))


class _DummyAgent:
    def __init__(self) -> None:
        self.ui_event_sink = MagicMock()
        self._event_bus = _DummyEventBus()
        self._permission_manager = None
        self._reaction_interval = 5
        self._proactive_interval = 30
        self._recent_actions = deque(maxlen=20)
        self.memory = MagicMock()
        self._dispatch_dialogue = MagicMock()


@pytest.mark.asyncio
async def test_request_permission_emits_ui_events():
    agent = _DummyAgent()
    executor = DecisionExecutor(agent)  # type: ignore[arg-type]

    granted = await executor._request_permission_interactive(
        agent_id="test-agent",
        scope=PermissionScope.TOOL_BASH_RUN,
        action="execute_bash",
        args={"command": "echo hi"},
    )

    assert granted is True

    calls = agent.ui_event_sink.emit.call_args_list
    assert len(calls) == 3

    emitted_events = [args[0] for args in (c.args for c in calls)]
    assert [event.kind for event in emitted_events] == [
        "permission_request",
        "chat_message",
        "bubble_message",
    ]

    permission_event = emitted_events[0]
    assert permission_event.payload["agent_id"] == "test-agent"
    assert permission_event.payload["scope"] == PermissionScope.TOOL_BASH_RUN.value
    assert permission_event.payload["action"] == "execute_bash"

    # Ensure event bus also recorded the request payload
    assert agent._event_bus.published
    _, payload = agent._event_bus.published[0]
    assert payload["scope"] == PermissionScope.TOOL_BASH_RUN.value


@pytest.mark.asyncio
async def test_execute_records_action_and_updates_history():
    agent = _DummyAgent()
    agent._permission_manager = MagicMock(spec=PermissionManager)
    agent._permission_manager.check_permission_async = AsyncMock(
        return_value=PermissionStatus.ALLOW
    )

    executor = DecisionExecutor(agent)  # type: ignore[arg-type]

    decision = MagicMock()
    decision.action = "execute_bash"
    decision.arguments = {"command": "echo hi"}
    decision.agent_id = "ProactiveBrain"

    # Use a simple context snapshot
    interval = await executor.execute(decision, {"title": "Test"})

    # Should return reaction interval for this action
    assert interval == agent._reaction_interval

    # Decision should be recorded in recent_actions and memory
    assert agent._recent_actions
    last_entry = agent._recent_actions[-1]
    assert "execute_bash" in last_entry
    agent.memory.record_action.assert_called_once_with("execute_bash", {"command": "echo hi"})


@pytest.mark.asyncio
async def test_execute_prefers_agent_core_action_hook():
    agent = _DummyAgent()
    agent.core = MagicMock()
    agent.core.register_action = MagicMock()

    executor = DecisionExecutor(agent)  # type: ignore[arg-type]
    custom_handler = AsyncMock(return_value=agent._reaction_interval)
    executor._handlers["custom_action"] = custom_handler

    decision = MagicMock()
    decision.action = "custom_action"
    decision.arguments = {"payload": 1}
    decision.agent_id = "ProactiveBrain"

    interval = await executor.execute(decision, {})

    assert interval == agent._reaction_interval
    agent.core.register_action.assert_called_once_with("custom_action", {"payload": 1})
    custom_handler.assert_awaited_once_with({"payload": 1}, {})
