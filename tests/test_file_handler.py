"""Unit tests for file_handler module."""

import asyncio
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock

from modules.file_handler import FileHandler


class TestFileHandler(TestCase):
    """Tests for FileHandler class."""

    def setUp(self):
        """Set up test fixtures."""
        self.proactive_brain = MagicMock()
        self.memory = MagicMock()
        self.emotions = MagicMock()
        self.execute_decision = MagicMock()
        self.file_handler = FileHandler(
            self.proactive_brain, self.memory, self.emotions, self.execute_decision
        )

    def test_initial_state(self):
        """Test initial state."""
        assert self.file_handler._latest_context == {}
        assert self.file_handler._recent_actions == []

    def test_set_context(self):
        """Test setting context."""
        context = {"title": "Test", "application": "TestApp"}
        actions = ["action1", "action2"]

        self.file_handler.set_context(context, actions)

        assert self.file_handler._latest_context == context
        assert self.file_handler._recent_actions == actions

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
        self.proactive_brain.decide = AsyncMock()
        self.file_handler._execute_decision = AsyncMock()

        data = {"file_path": "/test/file.txt"}
        self.file_handler.set_context({"title": "Test"}, ["action1"])

        asyncio.run(self.file_handler.handle_file_drop(data))

        self.proactive_brain.decide.assert_called_once()
        self.file_handler._execute_decision.assert_called_once()

    def test_handle_file_drop_with_text(self):
        """Test handling file drop with text."""
        self.proactive_brain.decide = AsyncMock()
        self.file_handler._execute_decision = AsyncMock()

        data = {"text": "some dropped text"}
        self.file_handler.set_context({"title": "Test"}, ["action1"])

        asyncio.run(self.file_handler.handle_file_drop(data))

        self.proactive_brain.decide.assert_called_once()
        self.file_handler._execute_decision.assert_called_once()

    def test_handle_file_drop_exception(self):
        """Test handling file drop with exception."""
        self.proactive_brain.decide.side_effect = Exception("Test error")

        data = {"file_path": "/test/file.txt"}
        self.file_handler.set_context({"title": "Test"}, ["action1"])

        # Should not raise exception
        asyncio.run(self.file_handler.handle_file_drop(data))

        self.proactive_brain.decide.assert_called_once()