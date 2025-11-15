"""Context management for desktop environment monitoring."""

import asyncio
import logging
from copy import deepcopy
from typing import Any, Dict, Optional

from modules.context_sniffer import ContextSniffer
from modules.event_bus import EventBus, EventType
from modules.metrics import PerformanceMetrics
from modules.privacy_filter import PrivacyFilter

LOGGER = logging.getLogger(__name__)


class ContextManager:
    """Manages desktop context updates and monitoring."""

    def __init__(self, privacy_filter: PrivacyFilter, memory_manager, event_bus: EventBus, metrics: PerformanceMetrics):
        self.privacy_filter = privacy_filter
        self.memory = memory_manager
        self._event_bus = event_bus
        self._metrics = metrics
        self.context_sniffer = ContextSniffer()
        self._latest_context: Dict[str, Any] = {
            "title": "Unknown",
            "application": "Unknown",
            "pid": -1,
            "source": "initial",
        }
        self._context_changed: Optional[asyncio.Event] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._unsubscribe_callback = None

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        """Start context monitoring."""
        self._loop = loop
        self._context_changed = asyncio.Event()

        def _context_callback(raw_context: Dict[str, Any]) -> None:
            sanitised = self.privacy_filter.sanitise_context(raw_context)
            self._loop.call_soon_threadsafe(self._update_context, sanitised)

        self._unsubscribe_callback = self.context_sniffer.subscribe(_context_callback)
        # Seed context immediately.
        self._update_context(self.context_sniffer.get_current_context())

    def stop(self) -> None:
        """Stop context monitoring."""
        if self._unsubscribe_callback:
            self._unsubscribe_callback()
            self._unsubscribe_callback = None

    def _update_context(self, context: Dict[str, Any]) -> None:
        """Update the current context."""
        self._latest_context = deepcopy(context)
        self.memory.record_observation(context)
        if self._context_changed is not None:
            self._context_changed.set()
        # Record metrics and publish event
        self._metrics.record_context_update()
        self._event_bus.publish(EventType.CONTEXT_CHANGED, context)

    @property
    def latest_context(self) -> Dict[str, Any]:
        """Get the latest context."""
        return deepcopy(self._latest_context)

    @property
    def context_changed(self) -> Optional[asyncio.Event]:
        """Get the context changed event."""
        return self._context_changed