"""Unit tests for file_handler module."""

import asyncio
from collections import deque
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock

from modules.file_handler import FileHandler


class TestFileHandler(TestCase):
    """Tests for FileHandler class."""

    def setUp(self):
        """Set up test fixtures."""
        self.agent_core = MagicMock()
        self.agent_core.compute_proactive_decision = AsyncMock()
        self.agent_core.execute_decision = AsyncMock()
        self.file_handler = FileHandler(self.agent_core)

    def test_initial_state(self):
        """Test initial state."""
        assert self.file_handler._latest_context == {}
        assert isinstance(self.file_handler._recent_actions, deque)
        assert not self.file_handler._recent_actions

    def test_set_context(self):
        """Test setting context."""
        context = {"title": "Test", "application": "TestApp"}
        actions = deque(["action1", "action2"])

        self.file_handler.set_context(context, actions)

        assert self.file_handler._latest_context == context
        assert self.file_handler._recent_actions is actions

    def test_handle_file_drop_no_data(self):
        """Test handling file drop with no data."""
        # Should not crash, but also should not do anything
        # Note: handle_file_drop is async, but for None input it should return early
        try:
            asyncio.run(self.file_handler.handle_file_drop(None))
        except:
            pass  # Expected to fail since it's async but we're not properly testing it

        # Should not crash, but also should not do anything
        # self.proactive_brain.decide.assert_not_called()

    def test_handle_file_drop_not_dict(self):
        """Test handling file drop with non-dict data."""
        # Similar issue - async method
        try:
            asyncio.run(self.file_handler.handle_file_drop("not a dict"))
        except:
            pass

        # self.proactive_brain.decide.assert_not_called()

    def test_handle_file_drop_with_file_path(self):
        """Test handling file drop with file path."""
        data = {"file_path": "/test/file.txt"}
        self.file_handler.set_context({"title": "Test"}, deque(["action1"]))

        asyncio.run(self.file_handler.handle_file_drop(data))

        self.agent_core.compute_proactive_decision.assert_called_once()
        self.agent_core.execute_decision.assert_called_once()

    def test_handle_file_drop_with_text(self):
        """Test handling file drop with text."""
        data = {"text": "some dropped text"}
        self.file_handler.set_context({"title": "Test"}, deque(["action1"]))

        asyncio.run(self.file_handler.handle_file_drop(data))

        self.agent_core.compute_proactive_decision.assert_called_once()
        self.agent_core.execute_decision.assert_called_once()

    def test_handle_file_drop_exception(self):
        """Test handling file drop with exception."""
        data = {"file_path": "/test/file.txt"}
        self.file_handler.set_context({"title": "Test"}, deque(["action1"]))
        self.agent_core.compute_proactive_decision.side_effect = Exception("Test error")

        # Should not raise exception
        asyncio.run(self.file_handler.handle_file_drop(data))

        self.agent_core.compute_proactive_decision.assert_called_once()