"""Unit tests for context_manager module."""

import asyncio
from unittest import TestCase
from unittest.mock import MagicMock

from modules.context_manager import ContextManager
from modules.event_bus import EventBus, EventType


class TestContextManager(TestCase):
    """Tests for ContextManager class."""

    def setUp(self):
        """Set up test fixtures."""
        self.privacy_filter = MagicMock()
        self.memory = MagicMock()
        self.event_bus = EventBus()
        self.metrics = MagicMock()
        self.context_manager = ContextManager(
            self.privacy_filter, self.memory, self.event_bus, self.metrics
        )

    def test_initial_state(self):
        """Test initial state."""
        assert self.context_manager.latest_context == {
            "title": "Unknown",
            "application": "Unknown",
            "pid": -1,
            "source": "initial",
        }
        assert self.context_manager.context_changed is None

    def test_update_context(self):
        """Test context updating."""
        new_context = {
            "title": "Test Window",
            "application": "TestApp",
            "pid": 123,
            "source": "test"
        }

        self.context_manager._update_context(new_context)

        assert self.context_manager.latest_context == new_context
        self.memory.record_observation.assert_called_once_with(new_context)
        self.metrics.record_context_update.assert_called_once()
        # Note: event_bus.publish is a function that calls subscribers, not a mock

    def test_start_without_loop(self):
        """Test starting without event loop."""
        context_sniffer = MagicMock()
        context_sniffer.subscribe.return_value = lambda: None
        context_sniffer.get_current_context.return_value = {
            "title": "Initial", "application": "InitApp", "pid": 0, "source": "init"
        }
        self.context_manager.context_sniffer = context_sniffer

        # Should not crash without loop
        self.context_manager.start(None)

        # Should have subscribed
        context_sniffer.subscribe.assert_called_once()

    def test_start_with_loop(self):
        """Test starting with event loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            context_sniffer = MagicMock()
            context_sniffer.subscribe.return_value = lambda: None
            context_sniffer.get_current_context.return_value = {
                "title": "Initial", "application": "InitApp", "pid": 0, "source": "init"
            }
            self.context_manager.context_sniffer = context_sniffer

            self.context_manager.start(loop)

            # Should have subscribed and set up context changed event
            context_sniffer.subscribe.assert_called_once()
            assert self.context_manager.context_changed is not None
            assert isinstance(self.context_manager.context_changed, asyncio.Event)
        finally:
            loop.close()

    def test_stop(self):
        """Test stopping the context manager."""
        unsubscribe_callback = MagicMock()
        self.context_manager._unsubscribe_callback = unsubscribe_callback

        self.context_manager.stop()

        unsubscribe_callback.assert_called_once()
        assert self.context_manager._unsubscribe_callback is None