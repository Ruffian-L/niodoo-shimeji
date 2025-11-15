"""Shared types and utilities for brain modules."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Dict

import asyncio
import time


@dataclass
class ProactiveDecision:
    """A decision made by the proactive brain."""
    action: str
    arguments: Dict[str, Any]


class RateLimiter:
    """Sliding window rate limiter for API calls."""
    
    def __init__(self, max_calls: int = 60, window_seconds: int = 60):
        self.max_calls = max_calls
        self.window = window_seconds
        self._calls: deque = deque()
    
    async def acquire(self) -> None:
        """Wait if necessary to respect rate limit."""
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

