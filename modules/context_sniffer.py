"""Wayland/GNOME desktop context discovery utilities.

This module provides a :class:`ContextSniffer` that integrates with the
"Window Calls Extended" (or compatible) GNOME Shell extension via D-Bus
in order to retrieve information about the currently focused window in a
Wayland-safe manner.  The class exposes synchronous polling helpers as
well as a lightweight signal subscription API for event-driven
applications.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

try:
    import pydbus
except ImportError as exc:  # pragma: no cover - import guard
    raise ImportError(
        "pydbus is required for ContextSniffer. Install it via 'pip install pydbus'"
    ) from exc

LOGGER = logging.getLogger(__name__)

# Default D-Bus identifiers exposed by the recommended GNOME shell extension.
BUS_NAME = "org.gnome.Shell"
OBJECT_PATH = "/org/gnome/Shell/Extensions/WindowsExt"


@dataclass
class ContextSniffer:
    """Retrieve active window metadata using GNOME's accessibility stack.

    Parameters
    ----------
    bus_name:
        Name of the D-Bus service exporting window focus information.
    object_path:
        Object path for the service.
    bus_getter:
        Optional callable that returns a configured pydbus bus. Defaults to
        :func:`pydbus.SessionBus`.
    """

    bus_name: str = BUS_NAME
    object_path: str = OBJECT_PATH
    bus_getter: Callable[[], Any] = field(default_factory=lambda: (lambda: pydbus.SessionBus()))

    def __post_init__(self) -> None:
        self._bus = None
        self._proxy = None
        self._connect()

    # ---------------------------------------------------------------------
    # Connection handling
    # ---------------------------------------------------------------------
    def _connect(self) -> None:
        try:
            self._bus = self.bus_getter()
            self._proxy = self._bus.get(self.bus_name, self.object_path)
            LOGGER.debug("Connected to D-Bus proxy %s%s", self.bus_name, self.object_path)
        except Exception as exc:  # pragma: no cover - runtime environment dependent
            LOGGER.warning(
                "Failed to connect to GNOME focus tracking extension (%s%s): %s",
                self.bus_name,
                self.object_path,
                exc,
            )
            self._proxy = None

    def _ensure_proxy(self) -> bool:
        if self._proxy is None:
            self._connect()
        return self._proxy is not None

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def get_current_context(self) -> Dict[str, Any]:
        """Return metadata for the currently focused window.

        Returns
        -------
        dict
            Keys include ``title``, ``application`` and ``pid``. Missing
            data is populated with placeholder values.
        """

        if not self._ensure_proxy():
            return {
                "title": "Unknown",
                "application": "Unknown",
                "pid": -1,
                "source": "context-sniffer-unavailable",
            }

        try:
            title = getattr(self._proxy, "FocusTitle", None)
            app_id = getattr(self._proxy, "FocusClass", None)
            pid = getattr(self._proxy, "FocusPID", None)

            # Some extensions expose callables instead of properties.
            if callable(title):
                title = title()
            if callable(app_id):
                app_id = app_id()
            if callable(pid):
                pid = pid()

            # Fallback to generic accessor method if provided.
            if (title is None or app_id is None) and hasattr(self._proxy, "GetFocus"):
                try:
                    focus_info = self._proxy.GetFocus()
                    title = focus_info.get("title", title)
                    app_id = focus_info.get("class", app_id)
                    pid = focus_info.get("pid", pid)
                except Exception as exc:  # pragma: no cover - implementation specific
                    LOGGER.debug("GetFocus call failed: %s", exc)

            return {
                "title": title or "Unknown",
                "application": app_id or "Unknown",
                "pid": pid if isinstance(pid, int) else -1,
                "source": "context-sniffer",
            }
        except Exception as exc:  # pragma: no cover - runtime dependent
            LOGGER.warning("Error retrieving focused window data: %s", exc)
            self._proxy = None
            return {
                "title": "Unknown",
                "application": "Unknown",
                "pid": -1,
                "source": "context-sniffer-error",
            }

    def subscribe(self, callback: Callable[[Dict[str, Any]], None]) -> Optional[Callable[[], None]]:
        """Register ``callback`` to be invoked when the focus changes.

        The provided callback receives the latest context dictionary. The
        returned callable can be used to unsubscribe.
        """

        if not self._ensure_proxy():  # pragma: no cover - runtime dependent
            LOGGER.warning("Cannot subscribe to focus changes; D-Bus proxy unavailable")
            return None

        signal_name = None
        # Identify a focus-changed signal exposed by the extension.
        if hasattr(self._proxy, "FocusChanged"):
            signal_name = "FocusChanged"
        elif hasattr(self._proxy, "FocusChangedDetailed"):
            signal_name = "FocusChangedDetailed"

        if signal_name is None:
            LOGGER.warning(
                "Connected proxy does not expose a recognised focus change signal."
            )
            return None

        proxy = self._proxy

        def handler(*_args: Any, **_kwargs: Any) -> None:
            try:
                callback(self.get_current_context())
            except Exception as exc:  # pragma: no cover - user callback
                LOGGER.exception("ContextSniffer callback raised an exception: %s", exc)

        setattr(proxy, f"on{signal_name}", handler)
        LOGGER.debug("Subscribed to %s focus signal", signal_name)

        def unsubscribe() -> None:
            setattr(proxy, f"on{signal_name}", None)
            LOGGER.debug("Unsubscribed from %s focus signal", signal_name)

        return unsubscribe
