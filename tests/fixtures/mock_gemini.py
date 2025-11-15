"""Mock Gemini API for testing."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock


class MockResponsePart:
    """Mock response part."""
    def __init__(self, text: Optional[str] = None, function_call: Optional[Dict[str, Any]] = None):
        self.text = text
        self.function_call = function_call


class MockCandidate:
    """Mock candidate."""
    def __init__(self, parts: List[MockResponsePart]):
        self.content = MagicMock()
        self.content.parts = parts


class MockResponse:
    """Mock Gemini API response."""
    def __init__(self, text: Optional[str] = None, function_call: Optional[Dict[str, Any]] = None):
        parts = []
        if text:
            parts.append(MockResponsePart(text=text))
        if function_call:
            parts.append(MockResponsePart(function_call=MagicMock(
                name=function_call.get("name", "unknown"),
                args=function_call.get("args", {})
            )))
        self.candidates = [MockCandidate(parts)] if parts else []


class MockGenerativeModel:
    """Mock GenerativeModel for testing."""
    
    def __init__(self, *args, **kwargs):
        self._responses: List[MockResponse] = []
        self._model_name = kwargs.get("model_name", "gemini-2.5-flash")
        self._tools = kwargs.get("tools", [])
        self._system_instruction = kwargs.get("system_instruction", "")
    
    def add_response(self, text: Optional[str] = None, function_call: Optional[Dict[str, Any]] = None):
        """Add a mock response."""
        self._responses.append(MockResponse(text=text, function_call=function_call))
    
    def generate_content(self, *args, **kwargs):
        """Generate mock content."""
        if self._responses:
            return self._responses.pop(0)
        # Default mock response
        return MockResponse(text="Mock response")

