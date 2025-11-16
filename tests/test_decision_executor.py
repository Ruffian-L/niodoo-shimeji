"""Tests for DecisionExecutor UI event emission."""

from unittest.mock import MagicMock

import pytest

from modules.decision_executor import DecisionExecutor
from modules.permission_manager import PermissionScope
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
