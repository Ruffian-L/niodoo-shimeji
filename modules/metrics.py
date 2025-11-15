"""Performance metrics collection for monitoring."""

from collections import deque
from typing import Any, Deque, Dict


class PerformanceMetrics:
    """Performance metrics collection for monitoring."""

    def __init__(self) -> None:
        self.api_call_times: Deque[float] = deque(maxlen=100)
        self.decision_times: Deque[float] = deque(maxlen=100)
        self.context_updates: int = 0
        self.errors: int = 0

    def record_api_call(self, duration: float) -> None:
        """Record an API call duration."""
        self.api_call_times.append(duration)

    def record_decision(self, duration: float) -> None:
        """Record a decision-making duration."""
        self.decision_times.append(duration)

    def record_context_update(self) -> None:
        """Record a context update."""
        self.context_updates += 1

    def record_error(self) -> None:
        """Record an error."""
        self.errors += 1

    def get_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        return {
            "avg_api_time_ms": (
                sum(self.api_call_times) / len(self.api_call_times) * 1000
                if self.api_call_times else 0
            ),
            "avg_decision_time_ms": (
                sum(self.decision_times) / len(self.decision_times) * 1000
                if self.decision_times else 0
            ),
            "total_context_updates": self.context_updates,
            "total_errors": self.errors,
            "api_call_count": len(self.api_call_times),
            "decision_count": len(self.decision_times),
        }