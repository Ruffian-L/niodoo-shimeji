"""Unit tests for DualModeAgent initialization."""

from unittest.mock import patch

from tests.fixtures.mock_gemini import MockGenerativeModel


def test_dual_mode_agent_initializes_overlay_and_dialogue_manager():
    """Ensure agent initializes overlay before dialogue manager to avoid attribute errors."""
    # Delay imports so that patch is in effect
    with patch('google.generativeai.GenerativeModel', MockGenerativeModel):
        from shimeji_dual_mode_agent import DualModeAgent

        agent = DualModeAgent(
            flash_model="gemini-2.5-flash",
            pro_model="gemini-2.5-pro",
        )

        # Overlay should exist and be an instance of SpeechBubbleOverlay
        assert hasattr(agent, "overlay")
        assert agent.overlay is not None

        # Dialogue manager should be present and reference the overlay
        assert hasattr(agent, "_dialogue_manager")
        assert agent._dialogue_manager.overlay is agent.overlay

        # Recent actions should be initialized before file handler context is set
        assert hasattr(agent, "_recent_actions")
        assert isinstance(agent._recent_actions, list) or hasattr(agent._recent_actions, "append")
