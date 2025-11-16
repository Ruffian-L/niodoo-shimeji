"""Dialogue management for speech bubbles and chat interactions."""

from typing import Any

from modules.presentation_api import UIEvent, UIEventSink


class DialogueManager:
    """Manages dialogue display through speech bubbles and chat panel."""

    def __init__(
        self,
        desktop_controller,
        ui_event_sink: UIEventSink,
    ) -> None:
        self.desktop_controller = desktop_controller
        self.ui_event_sink = ui_event_sink
        self._greeting_shown = False

    def dispatch_dialogue(self) -> None:
        """Dispatch pending dialogue messages to speech bubbles and chat."""
        messages = self.desktop_controller.drain_dialogue_queue()
        for message in messages:
            text = message.get("text", "").strip()
            if not text:
                continue
            author = message.get("author", "Shimeji")
            try:
                duration = int(message.get("duration", 6))
            except (TypeError, ValueError):
                duration = 6
            self._emit_bubble(author, text, duration)
            # Only add to chat panel if it's the initial greeting (to reduce spam)
            # Proactive dialogue should only show in bubbles, not chat
            if not self._greeting_shown:
                self._emit_chat(author, text)
                self._greeting_shown = True

    def show_bubble_message(self, author: str, text: str, duration: int = 6) -> None:
        """Show a message in the speech bubble."""
        self._emit_bubble(author, text, duration)

    def show_chat_message(self, author: str, text: str) -> None:
        """Show a message in the chat panel."""
        self._emit_chat(author, text)

    def _emit_bubble(self, author: str, text: str, duration: int) -> None:
        if not text:
            return
        self.ui_event_sink.emit(
            UIEvent(
                "bubble_message",
                {"author": author, "text": text, "duration": int(max(1, duration))},
            )
        )

    def _emit_chat(self, author: str, text: str) -> None:
        if not text:
            return
        self.ui_event_sink.emit(UIEvent("chat_message", {"author": author, "text": text}))