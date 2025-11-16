"""Unit tests for dialogue_manager module."""

from unittest import TestCase
from unittest.mock import MagicMock, call

from modules.dialogue_manager import DialogueManager
from modules.presentation_api import UIEvent


class TestDialogueManager(TestCase):
    """Tests for DialogueManager class."""

    def setUp(self):
        """Set up test fixtures."""
        self.desktop_controller = MagicMock()
        self.ui_sink = MagicMock()
        self.dialogue_manager = DialogueManager(
            self.desktop_controller,
            self.ui_sink,
        )

    def test_initial_state(self):
        """Test initial state."""
        assert self.dialogue_manager._greeting_shown is False

    def test_dispatch_dialogue_empty_queue(self):
        """Test dispatching with empty dialogue queue."""
        self.desktop_controller.drain_dialogue_queue.return_value = []

        self.dialogue_manager.dispatch_dialogue()

        self.desktop_controller.drain_dialogue_queue.assert_called_once()
        self.ui_sink.emit.assert_not_called()

    def test_dispatch_dialogue_with_messages(self):
        """Test dispatching dialogue messages."""
        messages = [
            {"text": "Hello!", "author": "Shimeji", "duration": 5},
            {"text": "How are you?", "author": "Shimeji", "duration": 3},
        ]
        self.desktop_controller.drain_dialogue_queue.return_value = messages

        self.dialogue_manager.dispatch_dialogue()

        bubble_calls = [
            args for args in self.ui_sink.emit.call_args_list if args.args[0].kind == "bubble_message"
        ]
        assert len(bubble_calls) == 2
        assert bubble_calls[0] == call(UIEvent("bubble_message", {"author": "Shimeji", "text": "Hello!", "duration": 5}))
        assert bubble_calls[1] == call(UIEvent("bubble_message", {"author": "Shimeji", "text": "How are you?", "duration": 3}))

        chat_calls = [
            args for args in self.ui_sink.emit.call_args_list if args.args[0].kind == "chat_message"
        ]
        assert len(chat_calls) == 1
        assert chat_calls[0] == call(UIEvent("chat_message", {"author": "Shimeji", "text": "Hello!"}))
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
        bubble_calls = [
            args for args in self.ui_sink.emit.call_args_list if args.args[0].kind == "bubble_message"
        ]
        assert len(bubble_calls) == 1
        assert bubble_calls[0] == call(
            UIEvent("bubble_message", {"author": "Shimeji", "text": "Valid message", "duration": 6})
        )

    def test_dispatch_dialogue_default_duration(self):
        """Test default duration when not specified."""
        messages = [{"text": "Test", "author": "Shimeji"}]  # No duration
        self.desktop_controller.drain_dialogue_queue.return_value = messages

        self.dialogue_manager.dispatch_dialogue()

        bubble_calls = [
            args for args in self.ui_sink.emit.call_args_list if args.args[0].kind == "bubble_message"
        ]
        assert len(bubble_calls) == 1
        assert bubble_calls[0] == call(
            UIEvent("bubble_message", {"author": "Shimeji", "text": "Test", "duration": 6})
        )

    def test_dispatch_dialogue_invalid_duration(self):
        """Test handling of invalid duration."""
        messages = [{"text": "Test", "author": "Shimeji", "duration": "invalid"}]
        self.desktop_controller.drain_dialogue_queue.return_value = messages

        self.dialogue_manager.dispatch_dialogue()

        bubble_calls = [
            args for args in self.ui_sink.emit.call_args_list if args.args[0].kind == "bubble_message"
        ]
        assert len(bubble_calls) == 1
        assert bubble_calls[0] == call(
            UIEvent("bubble_message", {"author": "Shimeji", "text": "Test", "duration": 6})
        )

    def test_show_bubble_message(self):
        """Test direct bubble message display."""
        self.dialogue_manager.show_bubble_message("TestAuthor", "Test message", 10)

        self.ui_sink.emit.assert_called_once_with(
            UIEvent("bubble_message", {"author": "TestAuthor", "text": "Test message", "duration": 10})
        )

    def test_show_chat_message(self):
        """Test direct chat message display."""
        self.dialogue_manager.show_chat_message("TestAuthor", "Test message")

        self.ui_sink.emit.assert_called_once_with(
            UIEvent("chat_message", {"author": "TestAuthor", "text": "Test message"})
        )
