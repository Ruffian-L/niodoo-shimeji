"""Helpers for stubbing ``pydbus`` when running tests without GNOME."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from types import ModuleType
from typing import Callable, Optional


class _StubProxy:
    FocusTitle = "Stub Window"
    FocusClass = "StubApp"
    FocusPID = 4242

    def GetFocus(self) -> dict:  # pragma: no cover - trivial
        return {
            "title": self.FocusTitle,
            "class": self.FocusClass,
            "pid": self.FocusPID,
        }


class _StubBus:
    def get(self, _bus_name: str, _object_path: str) -> _StubProxy:
        return _StubProxy()


@contextmanager
def mock_pydbus(session_bus_factory: Optional[Callable[[], _StubBus]] = None) -> ModuleType:
    """Register a lightweight ``pydbus`` replacement for tests."""

    module = ModuleType("pydbus")
    factory = session_bus_factory or (lambda: _StubBus())
    module.SessionBus = factory

    previous = sys.modules.get("pydbus")
    sys.modules["pydbus"] = module
    try:
        yield module
    finally:
        if previous is not None:
            sys.modules["pydbus"] = previous
        else:
            sys.modules.pop("pydbus", None)
