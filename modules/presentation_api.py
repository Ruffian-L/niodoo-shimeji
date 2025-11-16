"""Abstractions for avatar control and UI event delivery.

This module introduces small adapter interfaces so higher level code can
speak in terms of avatar directives and UI events without depending on the
Qt-specific implementations in ``DesktopController`` and
``SpeechBubbleOverlay``.  The goal is to make it easy to plug in new
presentation layers (Flutter, alternative overlays, headless renderers)
while keeping backwards compatibility with the existing Shijima stack.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

AvatarAnchor = Dict[str, float]


@dataclass
class AvatarDirective:
    """Declarative avatar instruction forwarded to the presentation layer."""

    behavior: Optional[str] = None
    dialogue: Optional[str] = None
    dialogue_author: str = "Shimeji"
    dialogue_duration: int = 6
    spawn_friend: Optional[str] = None
    spawn_anchor: Optional[AvatarAnchor] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def is_noop(self) -> bool:
        return not any([
            self.behavior,
            self.dialogue,
            self.spawn_friend,
            self.extra,
        ])


@dataclass
class UIEvent:
    """Typed UI directive for chat panels, alerts, or overlay state."""

    kind: str
    payload: Dict[str, Any] = field(default_factory=dict)


class AvatarClient(ABC):
    """Abstract control surface for an embodied avatar."""

    @abstractmethod
    def set_behavior(self, behavior: str) -> bool:
        """Trigger a mascot behavior. Returns True if accepted."""

    @abstractmethod
    def queue_dialogue(self, text: str, *, duration: int = 6, author: str = "Shimeji") -> None:
        """Enqueue dialogue for bubble display or speech output."""

    @abstractmethod
    def spawn_friend(self, name: str, *, anchor: Optional[AvatarAnchor] = None) -> bool:
        """Spawn an additional mascot if supported."""

    def apply_directive(self, directive: AvatarDirective) -> None:
        if directive.is_noop():
            return
        if directive.behavior:
            self.set_behavior(directive.behavior)
        if directive.spawn_friend:
            self.spawn_friend(directive.spawn_friend, anchor=directive.spawn_anchor)
        if directive.dialogue:
            self.queue_dialogue(
                directive.dialogue,
                duration=max(1, directive.dialogue_duration),
                author=directive.dialogue_author,
            )
        if directive.extra:
            self.handle_extra_directive(directive.extra)

    def handle_extra_directive(self, data: Dict[str, Any]) -> None:
        """Hook for adapters that support additional, implementation-specific directives."""


class UIEventSink(ABC):
    """Abstract consumer for UI events produced by the agent core."""

    @abstractmethod
    def emit(self, event: UIEvent) -> None:
        """Dispatch a UI event to the presentation layer."""


class ShijimaAvatarClient(AvatarClient):
    """Avatar client backed by the existing ``DesktopController`` API."""

    def __init__(self, controller: "DesktopController") -> None:
        self._controller = controller

    def set_behavior(self, behavior: str) -> bool:
        return self._controller.set_behavior(behavior)

    def queue_dialogue(self, text: str, *, duration: int = 6, author: str = "Shimeji") -> None:
        self._controller.show_dialogue(text, duration=duration, author=author)

    def spawn_friend(self, name: str, *, anchor: Optional[AvatarAnchor] = None) -> bool:
        return self._controller.spawn_friend(name, anchor=anchor)

    def handle_extra_directive(self, data: Dict[str, Any]) -> None:
        # Currently unused; kept for forward compatibility with richer directives.
        # Example future keys: {"highlight": true}, {"pose": {...}}.
        _ = data


class SpeechBubbleUISink(UIEventSink):
    """UI sink backed by ``SpeechBubbleOverlay``."""

    def __init__(self, overlay: "SpeechBubbleOverlay") -> None:
        self._overlay = overlay

    def start(self) -> None:
        if hasattr(self._overlay, "start"):
            self._overlay.start()

    def stop(self) -> None:
        if hasattr(self._overlay, "stop"):
            self._overlay.stop()

    def set_prompt_sender(self, callback) -> None:
        if hasattr(self._overlay, "set_prompt_sender"):
            self._overlay.set_prompt_sender(callback)

    def set_agent_reference(self, agent: Any) -> None:
        # Store agent reference for overlay callbacks (file drops, etc.).
        setattr(self._overlay, "_agent_ref", agent)

    def emit(self, event: UIEvent) -> None:
        kind = event.kind
        payload = event.payload
        if kind == "chat_message":
            author = payload.get("author", "Shimeji")
            text = payload.get("text", "")
            if text:
                self._overlay.show_chat_message(author, text)
            return
        if kind == "bubble_message":
            author = payload.get("author", "Shimeji")
            text = payload.get("text", "")
            duration = int(payload.get("duration", 6))
            if text:
                self._overlay.show_bubble_message(author, text, duration=duration)
            return
        if kind == "permission_request":
            if not payload:
                return
            if hasattr(self._overlay, "show_permission_request"):
                self._overlay.show_permission_request(payload)
                return
            # Fallback: reuse chat + bubble for legacy overlay
            agent_id = payload.get("agent_id", "unknown")
            action = payload.get("action", "unknown")
            scope = payload.get("scope", "unknown")
            message = (
                "🔐 Permission Request\n\n"
                f"Agent: {agent_id}\n"
                f"Action: {action}\n"
                f"Scope: {scope}\n\n"
                "Allow this action? (Reply 'yes', 'no', or 'always')."
            )
            self._overlay.show_chat_message("System", message)
            self._overlay.show_bubble_message(
                "System",
                f"Permission needed: {scope}",
                duration=int(payload.get("duration", 10)),
            )
            return
        if kind == "open_chat":
            self._overlay.open_chat_panel()
            return
        if kind == "update_anchor":
            anchor_x = payload.get("x")
            anchor_y = payload.get("y")
            self._overlay.update_anchor(anchor_x, anchor_y)
            return
        if kind == "enqueue_dialogue_batch":
            entries = payload.get("entries")
            if isinstance(entries, list):
                self._overlay.enqueue(entries)
            return
        self.handle_custom_event(event)

    def handle_custom_event(self, event: UIEvent) -> None:
        if event.kind == "chat_typing":
            state = event.payload.get("state")
            if not hasattr(self._overlay, "_chat_window") or not self._overlay._chat_window:
                return
            if state == "show":
                self._overlay._chat_window.show_typing()
            elif state == "hide":
                self._overlay._chat_window.hide_typing()
            return
        # Placeholder for richer events. Concrete adapters can override this
        # to support additional features like toasts, notifications, or UI state sync.
        _ = event


# Late imports to avoid heavy GUI dependencies at module import time.
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from modules.desktop_controller import DesktopController
    from modules.speech_bubble import SpeechBubbleOverlay
