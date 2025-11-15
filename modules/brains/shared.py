"""Shared types and utilities for brain modules."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict

import asyncio
import time


@dataclass
class ProactiveDecision:
    """A decision made by the proactive brain."""
    action: str
    arguments: Dict[str, Any]


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class RateLimiter:
    """Sliding window rate limiter with circuit breaker for API calls."""

    def __init__(
        self,
        max_calls: int = 60,
        window_seconds: int = 60,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type[Exception] = Exception
    ):
        self.max_calls = max_calls
        self.window = window_seconds
        self._calls: deque = deque()

        # Circuit breaker settings
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        # Circuit breaker state
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._next_attempt_time = 0.0

    async def acquire(self) -> None:
        """Wait if necessary to respect rate limit and circuit breaker."""
        # Check circuit breaker
        if self._state == CircuitBreakerState.OPEN:
            if time.monotonic() < self._next_attempt_time:
                raise Exception(f"Circuit breaker is OPEN. Next retry at {self._next_attempt_time}")
            else:
                self._state = CircuitBreakerState.HALF_OPEN

        now = time.monotonic()
        # Remove old calls outside window
        while self._calls and self._calls[0] < now - self.window:
            self._calls.popleft()

        if len(self._calls) >= self.max_calls:
            sleep_time = self._calls[0] + self.window - now
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
                # Clean up again after waiting
                now = time.monotonic()
                while self._calls and self._calls[0] < now - self.window:
                    self._calls.popleft()

        self._calls.append(time.monotonic())

    def record_success(self) -> None:
        """Record a successful operation."""
        if self._state == CircuitBreakerState.HALF_OPEN:
            self._state = CircuitBreakerState.CLOSED
            self._failure_count = 0
        elif self._state == CircuitBreakerState.CLOSED:
            self._failure_count = max(0, self._failure_count - 1)  # Gradual recovery

    def record_failure(self, exc: Exception) -> None:
        """Record a failed operation."""
        if isinstance(exc, self.expected_exception):
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._failure_count >= self.failure_threshold:
                self._state = CircuitBreakerState.OPEN
                self._next_attempt_time = time.monotonic() + self.recovery_timeout

    @property
    def state(self) -> CircuitBreakerState:
        """Get current circuit breaker state."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Get current failure count."""
        return self._failure_count


