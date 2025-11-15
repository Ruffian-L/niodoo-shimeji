"""Unit tests for dialogue_manager module."""

from unittest import TestCase
from unittest.mock import MagicMock

from modules.dialogue_manager import DialogueManager


class TestDialogueManager(TestCase):
    """Tests for DialogueManager class."""

    def setUp(self):
        """Set up test fixtures."""
        self.desktop_controller = MagicMock()
        self.overlay = MagicMock()
        self.dialogue_manager = DialogueManager(self.desktop_controller, self.overlay)

    def test_initial_state(self):
        """Test initial state."""
        assert self.dialogue_manager._greeting_shown is False

    def test_dispatch_dialogue_empty_queue(self):
        """Test dispatching with empty dialogue queue."""
        self.desktop_controller.drain_dialogue_queue.return_value = []

        self.dialogue_manager.dispatch_dialogue()

        self.desktop_controller.drain_dialogue_queue.assert_called_once()
        self.overlay.show_bubble_message.assert_not_called()
        self.overlay.show_chat_message.assert_not_called()

    def test_dispatch_dialogue_with_messages(self):
        """Test dispatching dialogue messages."""
        messages = [
            {"text": "Hello!", "author": "Shimeji", "duration": 5},
            {"text": "How are you?", "author": "Shimeji", "duration": 3},
        ]
        self.desktop_controller.drain_dialogue_queue.return_value = messages

        self.dialogue_manager.dispatch_dialogue()

        # Should show both messages as bubbles
        assert self.overlay.show_bubble_message.call_count == 2
        self.overlay.show_bubble_message.assert_any_call("Shimeji", "Hello!", duration=5)
        self.overlay.show_bubble_message.assert_any_call("Shimeji", "How are you?", duration=3)

        # First message should also show in chat (greeting)
        self.overlay.show_chat_message.assert_called_once_with("Shimeji", "Hello!")
        assert self.dialogue_manager._greeting_shown is True

    def test_dispatch_dialogue_skip_empty_text(self):
        """Test that empty text messages are skipped."""
        messages = [
            {"text": "", "author": "Shimeji"},
            {"text": "Valid message", "author": "Shimeji"},
        ]
        self.desktop_controller.drain_dialogue_queue.return_value = messages

        self.dialogue_manager.dispatch_dialogue()

        # Should only show the valid message
        self.overlay.show_bubble_message.assert_called_once_with("Shimeji", "Valid message", duration=6)

    def test_dispatch_dialogue_default_duration(self):
        """Test default duration when not specified."""
        messages = [{"text": "Test", "author": "Shimeji"}]  # No duration
        self.desktop_controller.drain_dialogue_queue.return_value = messages

        self.dialogue_manager.dispatch_dialogue()

        self.overlay.show_bubble_message.assert_called_once_with("Shimeji", "Test", duration=6)

    def test_dispatch_dialogue_invalid_duration(self):
        """Test handling of invalid duration."""
        messages = [{"text": "Test", "author": "Shimeji", "duration": "invalid"}]
        self.desktop_controller.drain_dialogue_queue.return_value = messages

        self.dialogue_manager.dispatch_dialogue()

        self.overlay.show_bubble_message.assert_called_once_with("Shimeji", "Test", duration=6)

    def test_show_bubble_message(self):
        """Test direct bubble message display."""
        self.dialogue_manager.show_bubble_message("TestAuthor", "Test message", 10)

        self.overlay.show_bubble_message.assert_called_once_with("TestAuthor", "Test message", duration=10)

    def test_show_chat_message(self):
        """Test direct chat message display."""
        self.dialogue_manager.show_chat_message("TestAuthor", "Test message")

        self.overlay.show_chat_message.assert_called_once_with("TestAuthor", "Test message")

    def test_dispatch_dialogue_with_no_overlay(self):
        """If overlay is None, DialogueManager should not raise and simply skip UI updates."""
        self.dialogue_manager = DialogueManager(self.desktop_controller, None)
        messages = [{"text": "Hello!", "author": "Shimeji", "duration": 5}]
        self.desktop_controller.drain_dialogue_queue.return_value = messages

        # Should not raise
        self.dialogue_manager.dispatch_dialogue()