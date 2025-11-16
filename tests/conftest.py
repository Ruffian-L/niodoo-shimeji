"""Pytest fixtures shared across the test suite."""

from __future__ import annotations

import asyncio
import inspect
from contextlib import ExitStack

import pytest

from tests.fixtures.dbus_stub import mock_pydbus
from tests.fixtures.google_stub import mock_google_generativeai
from tests.fixtures.mock_gemini import MockGenerativeModel


_EXIT_STACK = ExitStack()
_EXIT_STACK.enter_context(mock_google_generativeai(MockGenerativeModel))
_EXIT_STACK.enter_context(mock_pydbus())


def pytest_sessionfinish(session, exitstatus):  # pragma: no cover - pytest hook
    _EXIT_STACK.close()


def pytest_pyfunc_call(pyfuncitem):  # pragma: no cover - pytest hook
    """Allow ``async def`` tests without requiring pytest-asyncio."""

    if inspect.iscoroutinefunction(pyfuncitem.obj):
        testargs = {
            name: pyfuncitem.funcargs[name]
            for name in pyfuncitem._fixtureinfo.argnames  # pylint: disable=protected-access
        }
        asyncio.run(pyfuncitem.obj(**testargs))
        return True
    return None
