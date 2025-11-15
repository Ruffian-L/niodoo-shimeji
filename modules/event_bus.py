"""Event bus for loose coupling between components."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Callable, Dict, List

LOGGER = logging.getLogger(__name__)


class EventType(Enum):
    """Types of events that can be published."""
    CONTEXT_CHANGED = "context_changed"
    BEHAVIOR_CHANGED = "behavior_changed"
    MESSAGE_SENT = "message_sent"
    ERROR_OCCURRED = "error_occurred"
    MODE_SWITCHED = "mode_switched"
    DECISION_MADE = "decision_made"
    SYSTEM_ALERT = "system_alert"
    GESTURE_DETECTED = "gesture_detected"
    VOICE_COMMAND = "voice_command"
    FILE_DROPPED = "file_dropped"
    FEEDBACK_RECEIVED = "feedback_received"
    PATTERN_DETECTED = "pattern_detected"
    AUDIO_DETECTED = "audio_detected"
    PERMISSION_REQUESTED = "permission_requested"
    TASK_SCHEDULED = "task_scheduled"
    AGENT_SPAWNED = "agent_spawned"
    DBUS_NOTIFICATION = "dbus_notification"


class EventBus:
    """Simple pub/sub event bus for component communication."""
    
    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable[[Any], None]]] = {}
    
    def subscribe(self, event_type: EventType, handler: Callable[[Any], None]) -> None:
        """Subscribe to an event type.
        
        Args:
            event_type: The type of event to subscribe to
            handler: Callback function that receives event data
        """
        self._subscribers.setdefault(event_type, []).append(handler)
        LOGGER.debug("Subscribed handler to event type: %s", event_type.value)
    
    def unsubscribe(self, event_type: EventType, handler: Callable[[Any], None]) -> None:
        """Unsubscribe from an event type.
        
        Args:
            event_type: The type of event to unsubscribe from
            handler: The handler to remove
        """
        handlers = self._subscribers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)
            LOGGER.debug("Unsubscribed handler from event type: %s", event_type.value)
    
    def publish(self, event_type: EventType, data: Any = None) -> None:
        """Publish an event to all subscribers.
        
        Args:
            event_type: The type of event
            data: Optional event data
        """
        handlers = self._subscribers.get(event_type, [])
        for handler in handlers:
            try:
                handler(data)
            except Exception as exc:
                LOGGER.error("Event handler failed for %s: %s", event_type.value, exc)
    
    def clear(self) -> None:
        """Clear all subscribers."""
        self._subscribers.clear()
        LOGGER.debug("Event bus cleared")

