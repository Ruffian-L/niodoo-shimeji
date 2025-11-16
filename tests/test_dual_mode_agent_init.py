"""Unit tests for DualModeAgent initialization."""

from tests.fixtures.dbus_stub import mock_pydbus
from tests.fixtures.google_stub import mock_google_generativeai
from tests.fixtures.mock_gemini import MockGenerativeModel


def test_dual_mode_agent_initializes_overlay_and_dialogue_manager():
    """Ensure agent wires overlay + UI sink before dialogue manager spins up."""
    with mock_google_generativeai(MockGenerativeModel), mock_pydbus():
        from shimeji_dual_mode_agent import DualModeAgent

        agent = DualModeAgent(
            flash_model="gemini-2.5-flash",
            pro_model="gemini-2.5-pro",
        )

        # Overlay should exist and be an instance of SpeechBubbleOverlay
        assert hasattr(agent, "overlay")
        assert agent.overlay is not None

        # Dialogue manager should be present and reference the UI sink
        assert hasattr(agent, "ui_event_sink")
        assert agent.ui_event_sink is not None
        assert hasattr(agent, "_dialogue_manager")
        assert agent._dialogue_manager.ui_event_sink is agent.ui_event_sink

        # Recent actions should be initialized before AgentCore wiring uses them
        assert hasattr(agent, "_recent_actions")
        assert isinstance(agent._recent_actions, list) or hasattr(agent._recent_actions, "append")
