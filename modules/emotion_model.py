"""Lightweight emotional state tracker for the Shimeji agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class EmotionModel:
    """Tracks scalar emotion values used to influence proactive behaviour."""

    boredom: float = 0.2
    happiness: float = 0.6
    energy: float = 0.8
    _decay_rate: float = field(default=0.02, repr=False)

    def snapshot(self) -> Dict[str, float]:
        """Return a copy of the current emotional state."""

        return {
            "boredom": round(self._clamp(self.boredom), 3),
            "happiness": round(self._clamp(self.happiness), 3),
            "energy": round(self._clamp(self.energy), 3),
        }

    def on_observe_only(self, duration: int) -> None:
        """Called when the agent chooses observe_and_wait."""

        self._adjust("boredom", 0.05 + min(duration / 300.0, 0.1))
        self._adjust("energy", -0.02)

    def on_behavior(self, behaviour: str) -> None:
        behaviour_lower = behaviour.casefold()
        if "sleep" in behaviour_lower:
            self._adjust("energy", 0.2)
            self._adjust("boredom", -0.1)
        elif any(keyword in behaviour_lower for keyword in ("dance", "jump", "run", "climb")):
            self._adjust("energy", -0.05)
            self._adjust("boredom", -0.08)
            self._adjust("happiness", 0.05)
        elif "sit" in behaviour_lower or "idle" in behaviour_lower:
            self._adjust("boredom", 0.02)
        else:
            self._adjust("boredom", -0.01)

    def on_dialogue(self) -> None:
        self._adjust("happiness", 0.04)
        self._adjust("boredom", -0.04)

    def natural_decay(self) -> None:
        """Apply a small decay nudging values toward baseline."""

        self._adjust("boredom", -self._decay_rate)
        self._adjust("happiness", -self._decay_rate / 2)
        self._adjust("energy", -self._decay_rate / 3)

    def _adjust(self, key: str, delta: float) -> None:
        setattr(self, key, self._clamp(getattr(self, key) + delta))

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))



