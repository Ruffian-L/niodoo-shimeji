"""HTTP client for controlling Shijima-Qt mascots.

This module offers a small, resilient wrapper around the Shijima-Qt REST
API.  It supports fetching active mascots, triggering behaviours, spawning
additional companions, and queuing dialogue events to be rendered by the
Python overlay.
"""

from __future__ import annotations

import logging
import os
import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Iterable, List, Optional, Set, Tuple

import requests
from requests import Response
from requests.adapters import HTTPAdapter

LOGGER = logging.getLogger(__name__)
DEFAULT_BASE_URL = "http://127.0.0.1:32456/shijima/api/v1"


class DesktopControllerError(RuntimeError):
    """Raised when the Shijima API returns an unexpected response."""


@dataclass
class DesktopController:
    """High level controller for the Shijima-Qt HTTP API."""

    base_url: str = field(default_factory=lambda: os.getenv("SHIMEJI_API_URL", DEFAULT_BASE_URL))
    session: requests.Session = field(default_factory=requests.Session)
    request_timeout: float = 2.5
    dialogue_queue: Deque[Dict[str, str]] = field(default_factory=lambda: deque(maxlen=50))
    allowed_behaviours: Optional[Set[str]] = None

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        self._active_mascot_id: Optional[int] = None
        self._mascots_cache: List[Dict[str, object]] = []
        self._mascots_cached_at: float = 0.0
        
        # Configure connection pooling
        adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=3
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        try:
            self.mascot_cache_ttl = max(0.0, float(os.getenv("SHIMEJI_MASCOT_CACHE_TTL", "2.0")))
        except ValueError:
            self.mascot_cache_ttl = 2.0
        try:
            self._initial_backoff = max(0.5, float(os.getenv("SHIMEJI_API_BACKOFF_INITIAL", "1.5")))
        except ValueError:
            self._initial_backoff = 1.5
        try:
            self._max_backoff = max(self._initial_backoff, float(os.getenv("SHIMEJI_API_BACKOFF_MAX", "12")))
        except ValueError:
            self._max_backoff = max(self._initial_backoff, 12.0)
        self._current_backoff = self._initial_backoff
        self._backoff_until = 0.0
        self._api_available = True
        try:
            self._error_log_interval = max(0.5, float(os.getenv("SHIMEJI_API_ERROR_LOG_INTERVAL", "3.0")))
        except ValueError:
            self._error_log_interval = 3.0
        self._last_error_log = 0.0

    # ------------------------------------------------------------------
    # Mascot discovery helpers
    # ------------------------------------------------------------------
    def _invalidate_mascot_cache(self) -> None:
        self._mascots_cache = []
        self._mascots_cached_at = 0.0

    def list_mascots(self, *, force: bool = False) -> List[Dict[str, object]]:
        now = time.monotonic()
        if not force and self._mascots_cache and now - self._mascots_cached_at < self.mascot_cache_ttl:
            return self._mascots_cache
        if not self._api_available and now < self._backoff_until:
            if force:
                raise DesktopControllerError("Shijima API backoff active")
            return self._mascots_cache

        try:
            response = self._request("GET", "/mascots")
        except DesktopControllerError:
            if force:
                raise
            return self._mascots_cache

        payload = response.json()
        mascots = payload.get("mascots", [])
        if mascots:
            self._active_mascot_id = mascots[0].get("id")
        self._mascots_cache = mascots
        self._mascots_cached_at = now
        return mascots

    def ensure_mascot(self) -> Optional[int]:
        if self._active_mascot_id is not None:
            return self._active_mascot_id
        self._refresh_active_mascot()
        return self._active_mascot_id

    def set_allowed_behaviours(self, behaviours: Iterable[str]) -> None:
        self.allowed_behaviours = {behaviour for behaviour in behaviours}

    def wait_for_mascot(self, timeout: float = 20.0, poll_interval: float = 0.5) -> bool:
        """Poll the API until at least one mascot is active.

        Parameters
        ----------
        timeout:
            Maximum number of seconds to wait.
        interval:
            Delay between polling attempts.
        """

        start = time.monotonic()
        while time.monotonic() - start < timeout:
            try:
                mascots = self.list_mascots(force=True)
            except DesktopControllerError:
                backoff_wait = max(poll_interval, self.backoff_remaining())
                time.sleep(backoff_wait)
                continue
            if mascots:
                LOGGER.debug("Mascot detected: %s", mascots[0])
                return True
            time.sleep(poll_interval)
        LOGGER.warning("Timed out waiting for a mascot to appear")
        return False

    def backoff_remaining(self) -> float:
        return max(0.0, self._backoff_until - time.monotonic())

    def get_primary_mascot_anchor(self) -> Optional[Tuple[float, float]]:
        try:
            mascots = self.list_mascots()
        except DesktopControllerError:
            return None
        if not mascots:
            return None
        anchor = mascots[0].get("anchor")
        if isinstance(anchor, dict):
            x = anchor.get("x")
            y = anchor.get("y")
            if x is not None and y is not None:
                try:
                    return float(x), float(y)
                except (TypeError, ValueError):
                    return None
        return None

    # ------------------------------------------------------------------
    # Behaviour control
    # ------------------------------------------------------------------
    def set_behavior(self, behavior: str, *, mascot_id: Optional[int] = None) -> bool:
        mascot_id = mascot_id if mascot_id is not None else self.ensure_mascot()
        if mascot_id is None:
            LOGGER.warning("No Shijima mascots are active; cannot trigger behaviour '%s'", behavior)
            return False

        if self.allowed_behaviours and behavior not in self.allowed_behaviours:
            LOGGER.warning(
                "Behaviour '%s' is not part of the discovered actions set; issuing command anyway.",
                behavior,
            )

        payload = {"behavior": behavior}
        payload["id"] = mascot_id

        def _attempt() -> bool:
            try:
                response = self._request("PUT", f"/mascots/{mascot_id}", json=payload)
            except DesktopControllerError as exc:
                LOGGER.warning("Failed to trigger behaviour '%s': %s", behavior, exc)
                return False
            if response.status_code == 404:
                LOGGER.warning("Mascot id %s not recognised; refreshing cache", mascot_id)
                self._refresh_active_mascot()
                return False
            success_local = 200 <= response.status_code < 300
            if not success_local:
                LOGGER.warning(
                    "Unexpected status from behaviour '%s': %s %s",
                    behavior,
                    response.status_code,
                    response.text,
                )
            return success_local

        if not _attempt():
            mascot_id = self.ensure_mascot()
            if mascot_id is None:
                return False
            payload["id"] = mascot_id
            if not _attempt():
                return False

        LOGGER.info("Triggered behaviour '%s' for mascot %s", behavior, mascot_id)
        self._invalidate_mascot_cache()
        return True

    def spawn_friend(self, name: str = "Default Mascot", *, anchor: Optional[Dict[str, float]] = None) -> bool:
        payload = {"name": name}
        if anchor:
            payload["anchor"] = anchor
        try:
            response = self._request("POST", "/mascots", json=payload)
        except DesktopControllerError as exc:
            LOGGER.warning("Failed to spawn mascot '%s': %s", name, exc)
            return False

        success = 200 <= response.status_code < 300
        if success:
            result = response.json()
            LOGGER.info("Spawned new mascot '%s': %s", name, result)
            self._invalidate_mascot_cache()
        return success
    
    def get_current_behavior(self) -> Optional[str]:
        """Get the active behavior of the primary mascot."""
        try:
            mascots = self.list_mascots()
            if mascots:
                behavior = mascots[0].get("active_behavior")
                return behavior
        except DesktopControllerError:
            pass
        return None

    def chase_mouse(self, duration: int = 5) -> bool:
        mascot_id = self.ensure_mascot()
        if mascot_id is None:
            return False
        return self.set_behavior("ChaseMouse", mascot_id=mascot_id)

    def show_dialogue(self, text: str, *, duration: int = 6, author: str = "Shimeji") -> None:
        """Queue dialogue for display by the overlay layer."""

        entry = {"text": text, "duration": str(duration), "author": author}
        self.dialogue_queue.append(entry)
        LOGGER.debug("Queued dialogue: %s", entry)

    def drain_dialogue_queue(self) -> List[Dict[str, str]]:
        entries = list(self.dialogue_queue)
        self.dialogue_queue.clear()
        return entries

    # ------------------------------------------------------------------
    # HTTP helper
    # ------------------------------------------------------------------
    def _request(self, method: str, path: str, **kwargs) -> Response:
        url = f"{self.base_url}{path}"
        kwargs.setdefault("timeout", self.request_timeout)
        now = time.monotonic()
        if now < self._backoff_until:
            raise DesktopControllerError("Shijima API backoff active")

        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
        except requests.RequestException as exc:
            if now - self._last_error_log >= self._error_log_interval:
                LOGGER.error("Shijima API request failed (%s %s): %s", method, url, exc)
                self._last_error_log = now
            self._api_available = False
            # Add jitter to backoff to prevent thundering herd
            jitter = random.uniform(0, self._current_backoff * 0.1)
            self._backoff_until = now + self._current_backoff + jitter
            self._current_backoff = min(self._current_backoff * 2, self._max_backoff)
            raise DesktopControllerError(str(exc)) from exc

        if not self._api_available:
            LOGGER.info("Reconnected to Shijima API")
        self._api_available = True
        self._current_backoff = self._initial_backoff
        self._backoff_until = 0.0
        return response

    def _refresh_active_mascot(self) -> None:
        try:
            mascots = self.list_mascots(force=True)
        except DesktopControllerError:
            return
        if mascots:
            self._active_mascot_id = mascots[0].get("id")
        else:
            self._active_mascot_id = None
