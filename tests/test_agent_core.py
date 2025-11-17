"""Focused tests for AgentCore helpers."""

import asyncio
import logging
from collections import deque
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from modules.agent_core import AgentCore, AgentCoreConfig
from modules.system_monitor import SystemAlert, AlertSeverity
import modules.agent_core as agent_core_module


async def _get_context_stub():
    return {}


def _build_core(**overrides: Any) -> AgentCore:
    params = dict(
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
        update_context=lambda ctx: None,
        latest_context_getter=lambda: {},
        context_lock_getter=lambda: None,
        set_latest_vision_analysis=lambda _: None,
        context_getter=_get_context_stub,
        transition_mascot_state=lambda _state: None,
        event_bus=MagicMock(),
        decision_executor=MagicMock(),
        monitoring_manager=None,
        show_alert_notification=lambda alert: None,
    )
    params.update(overrides)
    config = AgentCoreConfig(**params)
    return AgentCore(config)


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


@pytest.mark.asyncio
async def test_merge_context_routes_through_callback():
    updates = []

    def _update(context):
        updates.append(context)

    base_context = {"app": "Code"}

    core = _build_core(
        update_context=_update,
        latest_context_getter=lambda: base_context,
        context_lock_getter=lambda: None,
    )

    merged = await core.merge_context({"status": "Ready"})

    assert merged == {"app": "Code", "status": "Ready"}
    assert updates[-1] == merged


@pytest.mark.asyncio
async def test_handle_critical_alert_rate_limits(monkeypatch):
    current_time = 100.0

    def _fake_monotonic():
        return current_time

    monkeypatch.setattr(agent_core_module.time, "monotonic", _fake_monotonic)

    core = _build_core()
    core._memory.recent_observations.return_value = []  # type: ignore[attr-defined]
    core._memory.recall_relevant_async = AsyncMock(return_value=[])  # type: ignore[attr-defined]
    core._emotions.snapshot = MagicMock(return_value={})  # type: ignore[attr-defined]
    decision = MagicMock()
    core._proactive_brain.decide = AsyncMock(return_value=decision)  # type: ignore[attr-defined]
    core.execute_decision = AsyncMock(return_value=0)  # type: ignore[attr-defined]

    show_alert = MagicMock()
    context = {"title": "Test"}
    actions = deque(maxlen=5)

    await core.handle_critical_alert(
        MagicMock(alert_type="CPU", message="High load", details={}),
        context=context,
        recent_actions=actions,
        show_alert_notification=show_alert,
        rate_limit_seconds=300,
    )

    core._proactive_brain.decide.assert_awaited_once()  # type: ignore[attr-defined]
    core.execute_decision.assert_awaited_once()
    show_alert.assert_not_called()

    await core.handle_critical_alert(
        MagicMock(alert_type="CPU", message="High load", details={}),
        context=context,
        recent_actions=actions,
        show_alert_notification=show_alert,
        rate_limit_seconds=300,
    )

    assert show_alert.call_count == 1
    assert core._proactive_brain.decide.await_count == 1  # type: ignore[attr-defined]

    current_time += 400

    await core.handle_critical_alert(
        MagicMock(alert_type="CPU", message="High load", details={}),
        context=context,
        recent_actions=actions,
        show_alert_notification=show_alert,
        rate_limit_seconds=300,
    )

    assert core._proactive_brain.decide.await_count == 2  # type: ignore[attr-defined]


def test_register_action_updates_history_and_memory():
    core = _build_core()
    history = deque(maxlen=5)
    core._recent_actions = history  # type: ignore[attr-defined]

    core.register_action("set_behavior", {"behavior": "Sit"})

    assert history
    entry = history[-1]
    assert "set_behavior" in entry
    core._memory.record_action.assert_called_once_with("set_behavior", {"behavior": "Sit"})  # type: ignore[attr-defined]


def test_handle_dbus_notification_logs_media(caplog):
    core = _build_core()
    payload = {
        "type": "media_playing",
        "player": "spotify",
        "metadata": {"xesam:title": "Song"},
    }

    with caplog.at_level(logging.DEBUG, logger="modules.agent_core"):
        core.handle_dbus_notification(payload)

    assert "Media playing" in caplog.text


def test_handle_dbus_notification_ignores_non_dict(caplog):
    core = _build_core()

    with caplog.at_level(logging.DEBUG, logger="modules.agent_core"):
        core.handle_dbus_notification("oops")

    assert "Ignoring non-dict DBus payload" in caplog.text


@pytest.mark.asyncio
async def test_handle_system_alert_routes_non_critical_notifications():
    show_alert = MagicMock()
    core = _build_core(show_alert_notification=show_alert)

    alert = SystemAlert(AlertSeverity.WARNING, "ram", "Warning", {}, "ts")

    await core.handle_system_alert(alert)

    show_alert.assert_called_once_with(alert)


@pytest.mark.asyncio
async def test_handle_system_alert_invokes_critical_flow():
    show_alert = MagicMock()
    context = {"app": "Code"}
    recent = deque(maxlen=5)

    async def _context_stub():
        return context

    core = _build_core(show_alert_notification=show_alert)
    core._context_getter = _context_stub  # type: ignore[attr-defined]
    core._recent_actions = recent  # type: ignore[attr-defined]
    core.handle_critical_alert = AsyncMock()  # type: ignore[attr-defined]

    alert = SystemAlert(AlertSeverity.CRITICAL, "ram", "Critical", {}, "ts")

    await core.handle_system_alert(alert)

    core.handle_critical_alert.assert_awaited_once_with(  # type: ignore[attr-defined]
        alert,
        context=context,
        recent_actions=recent,
        show_alert_notification=show_alert,
    )


@pytest.mark.asyncio
async def test_start_system_monitoring_delegates_to_manager():
    manager = MagicMock()
    manager.start = AsyncMock()
    core = _build_core(monitoring_manager=manager)

    await core.start_system_monitoring()

    manager.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_system_monitoring_handles_missing_manager():
    manager = MagicMock()
    manager.stop = AsyncMock()
    core = _build_core(monitoring_manager=manager)

    await core.stop_system_monitoring()

    manager.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_memory_cleanup_loop_runs_until_stopped():
    core = _build_core()

    running = True

    async def _cleanup_side_effect(*, days_to_keep):
        nonlocal running
        running = False

    core._memory.cleanup_old_episodes_async = AsyncMock(side_effect=_cleanup_side_effect)  # type: ignore[attr-defined]

    await core.memory_cleanup_loop(
        is_running=lambda: running,
        interval_seconds=0,
        days_to_keep=10,
    )

    core._memory.cleanup_old_episodes_async.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_proactive_loop_runs_cycle_when_active():
    core = _build_core()

    context_calls = 0

    async def _context_stub():
        nonlocal context_calls
        context_calls += 1
        return {"app": "Code"}

    core._context_getter = _context_stub  # type: ignore[attr-defined]
    core.proactive_cycle = AsyncMock(return_value=(MagicMock(), 0.01))

    running = True
    event = asyncio.Event()
    event.set()
    actions = deque(["observe"])

    async def stop_loop():
        nonlocal running
        await asyncio.sleep(0.05)
        running = False

    stopper = asyncio.create_task(stop_loop())

    await core.proactive_loop(
        context_event=event,
        is_running=lambda: running,
        is_proactive_mode=lambda: True,
        interval_getter=lambda: 0.01,
        recent_actions=actions,
    )

    await stopper
    core.proactive_cycle.assert_awaited()
    assert context_calls >= 1
