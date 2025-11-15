"""Dialogue management for speech bubbles and chat interactions."""

from typing import Any, Dict, Optional


class DialogueManager:
    """Manages dialogue display through speech bubbles and chat panel."""

    def __init__(self, desktop_controller, overlay: Optional[Any] = None):
        self.desktop_controller = desktop_controller
        self.overlay = overlay
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
            # Show bubble above Shimeji
            if self.overlay:
                self.overlay.show_bubble_message(author, text, duration=duration)
            # Only add to chat panel if it's the initial greeting (to reduce spam)
            # Proactive dialogue should only show in bubbles, not chat
            if not self._greeting_shown and self.overlay:
                self.overlay.show_chat_message(author, text)
                self._greeting_shown = True

    def show_bubble_message(self, author: str, text: str, duration: int = 6) -> None:
        """Show a message in the speech bubble."""
        if self.overlay:
            self.overlay.show_bubble_message(author, text, duration=duration)

    def show_chat_message(self, author: str, text: str) -> None:
        """Show a message in the chat panel."""
        if self.overlay:
            self.overlay.show_chat_message(author, text)