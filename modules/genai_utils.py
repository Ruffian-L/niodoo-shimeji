"""Utilities for working with Google Gemini SDK."""

from __future__ import annotations

import threading
from typing import Any, Dict, Tuple

import google.generativeai as genai

_MODEL_CACHE: Dict[Tuple[str, Tuple[Tuple[str, Any], ...]], genai.GenerativeModel] = {}
_CACHE_LOCK = threading.Lock()


def get_cached_model(model_name: str, **kwargs: Any) -> genai.GenerativeModel:
    """Return a cached GenerativeModel instance for the given configuration."""
    key = (model_name, tuple(sorted(kwargs.items())))
    with _CACHE_LOCK:
        model = _MODEL_CACHE.get(key)
        if model is None:
            model = genai.GenerativeModel(model_name, **kwargs)
            _MODEL_CACHE[key] = model
        return model
