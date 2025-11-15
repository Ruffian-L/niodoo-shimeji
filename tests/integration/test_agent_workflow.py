"""Integration tests for agent workflows."""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import MagicMock, patch

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from modules.brains.shared import ProactiveDecision
from tests.fixtures.mock_gemini import MockGenerativeModel


@pytest.mark.asyncio
async def test_proactive_to_cli_switch():
    """Test switching from proactive to CLI mode."""
    from shimeji_dual_mode_agent import DualModeAgent, AgentMode
    
    with patch('google.generativeai.GenerativeModel', MockGenerativeModel):
        agent = DualModeAgent(
            flash_model="gemini-2.5-flash",
            pro_model="gemini-2.5-pro",
        )
        
        # Mock overlay to avoid Qt dependency
        agent.overlay = MagicMock()
        agent.overlay.show_chat_message = MagicMock()
        agent.overlay.show_bubble_message = MagicMock()
        agent.overlay.start = MagicMock()
        agent.overlay.stop = MagicMock()
        agent.overlay.open_chat_panel = MagicMock()
        agent.overlay.update_anchor = MagicMock()
        
        # Mock desktop controller
        agent.desktop_controller = MagicMock()
        agent.desktop_controller.wait_for_mascot = MagicMock(return_value=True)
        agent.desktop_controller.list_mascots = MagicMock(return_value=[])
        agent.desktop_controller.ensure_mascot = MagicMock(return_value=1)
        agent.desktop_controller.set_behavior = MagicMock(return_value=True)
        agent.desktop_controller.show_dialogue = MagicMock()
        agent.desktop_controller.get_primary_mascot_anchor = MagicMock(return_value=None)
        agent.desktop_controller.backoff_remaining = MagicMock(return_value=0.0)
        
        # Mock context sniffer
        agent.context_sniffer = MagicMock()
        agent.context_sniffer.get_current_context = MagicMock(return_value={
            "title": "Test",
            "application": "TestApp",
            "pid": 123,
            "source": "test"
        })
        agent.context_sniffer.subscribe = MagicMock(return_value=lambda: None)
        
        await agent.start()
        
        # Should start in proactive mode
        assert agent.mode == AgentMode.PROACTIVE
        
        # Switch to CLI
        response = await agent.handle_cli_request("test prompt")
        assert agent.mode == AgentMode.PROACTIVE  # Should switch back after CLI
        
        await agent.shutdown()


@pytest.mark.asyncio
async def test_decision_execution():
    """Test decision execution."""
    from shimeji_dual_mode_agent import DualModeAgent
    
    with patch('google.generativeai.GenerativeModel', MockGenerativeModel):
        agent = DualModeAgent(
            flash_model="gemini-2.5-flash",
            pro_model="gemini-2.5-pro",
        )
        
        # Mock dependencies
        agent.overlay = MagicMock()
        agent.overlay.show_chat_message = MagicMock()
        agent.overlay.show_bubble_message = MagicMock()
        agent.desktop_controller = MagicMock()
        agent.desktop_controller.ensure_mascot = MagicMock(return_value=1)
        agent.desktop_controller.set_behavior = MagicMock(return_value=True)
        agent.emotions = MagicMock()
        agent.emotions.on_behavior = MagicMock()
        agent.memory = MagicMock()
        agent.memory.record_action = MagicMock()
        agent.memory.episodic = MagicMock()
        agent.memory.episodic.recent = MagicMock(return_value=[])
        agent.memory.working = MagicMock()
        agent.memory.working.recent_observations = MagicMock(return_value=[])
        agent.context_sniffer = MagicMock()
        agent.context_sniffer.get_current_context = MagicMock(return_value={
            "title": "Test",
            "application": "TestApp",
            "pid": 123,
            "source": "test"
        })
        agent.context_sniffer.subscribe = MagicMock(return_value=lambda: None)
        
        # Test decision execution
        decision = ProactiveDecision("set_behavior", {"behavior_name": "Sit"})
        interval = await agent._execute_decision(decision, agent._latest_context)
        
        assert interval > 0
        agent.desktop_controller.set_behavior.assert_called_once()


@pytest.mark.asyncio
async def test_memory_operations():
    """Test memory operations."""
    from modules.memory_manager import MemoryManager
    
    memory = MemoryManager()
    
    # Test working memory
    memory.record_observation({"title": "Test", "application": "TestApp"})
    observations = memory.recent_observations()
    assert len(observations) > 0
    
    # Test episodic memory
    memory.save_fact("Test fact", {"context": {"test": "data"}})
    facts = memory.episodic.recent(limit=10)
    assert len(facts) > 0
    
    memory.close()

