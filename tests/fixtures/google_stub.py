"""Helpers for stubbing ``google.generativeai`` during tests."""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager
from types import ModuleType
from typing import Type


@contextmanager
def mock_google_generativeai(model_cls: Type) -> ModuleType:
    """Temporarily register a fake ``google.generativeai`` module.

    Many unit tests patch ``google.generativeai.GenerativeModel`` even when the
    real SDK is not installed locally (e.g. on CI).  This context manager
    injects lightweight stub modules into ``sys.modules`` so imports succeed and
    the provided ``model_cls`` is used wherever ``GenerativeModel`` is looked up.
    """

    google_module = types.ModuleType("google")
    generativeai_module = types.ModuleType("google.generativeai")

    class _StubException(Exception):
        pass

    class _BlockedPromptException(_StubException):
        pass

    class _StopCandidateException(_StubException):
        pass

    class _Config:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    types_module = types.ModuleType("google.generativeai.types")
    types_module.BlockedPromptException = _BlockedPromptException
    types_module.StopCandidateException = _StopCandidateException
    types_module.CreateCachedContentConfig = _Config
    types_module.GenerateContentConfig = _Config

    generativeai_module.GenerativeModel = model_cls
    generativeai_module.types = types_module
    google_module.generativeai = generativeai_module

    previous_google = sys.modules.get("google")
    previous_generativeai = sys.modules.get("google.generativeai")
    previous_generativeai_types = sys.modules.get("google.generativeai.types")

    sys.modules["google"] = google_module
    sys.modules["google.generativeai"] = generativeai_module
    sys.modules["google.generativeai.types"] = types_module
    try:
        yield generativeai_module
    finally:
        if previous_google is not None:
            sys.modules["google"] = previous_google
        else:
            sys.modules.pop("google", None)

        if previous_generativeai is not None:
            sys.modules["google.generativeai"] = previous_generativeai
        else:
            sys.modules.pop("google.generativeai", None)

        if previous_generativeai_types is not None:
            sys.modules["google.generativeai.types"] = previous_generativeai_types
        else:
            sys.modules.pop("google.generativeai.types", None)
