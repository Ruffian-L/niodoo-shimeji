"""Unit tests for input_sanitizer module."""

from unittest import TestCase

from modules.input_sanitizer import InputSanitizer


class TestInputSanitizer(TestCase):
    """Tests for InputSanitizer class."""

    def test_sanitize_prompt_normal(self):
        """Test sanitizing normal prompt."""
        prompt = "Hello, how are you?"
        result = InputSanitizer.sanitize_prompt(prompt)
        assert result == prompt

    def test_sanitize_prompt_control_chars(self):
        """Test removing control characters from prompt."""
        prompt = "Hello\x00\x01\x02world"
        result = InputSanitizer.sanitize_prompt(prompt)
        assert result == "Helloworld"

    def test_sanitize_prompt_length_limit(self):
        """Test prompt length limiting."""
        long_prompt = "x" * (InputSanitizer.MAX_PROMPT_LENGTH + 100)
        result = InputSanitizer.sanitize_prompt(long_prompt)
        assert len(result) == InputSanitizer.MAX_PROMPT_LENGTH + len("... [truncated]")
        assert result.endswith("... [truncated]")

    def test_sanitize_prompt_empty(self):
        """Test sanitizing empty prompt."""
        result = InputSanitizer.sanitize_prompt("")
        assert result == ""

    def test_sanitize_prompt_none(self):
        """Test sanitizing None prompt."""
        result = InputSanitizer.sanitize_prompt(None)
        assert result == ""

    def test_sanitize_file_path_normal(self):
        """Test sanitizing normal file path."""
        path = "/home/user/document.txt"
        result = InputSanitizer.sanitize_file_path(path)
        assert result == path

    def test_sanitize_file_path_relative(self):
        """Test sanitizing relative file path."""
        path = "document.txt"
        result = InputSanitizer.sanitize_file_path(path)
        assert result is not None
        assert "document.txt" in result

    def test_sanitize_file_path_invalid(self):
        """Test sanitizing invalid file path."""
        path = "/nonexistent/path" * 1000  # Too long
        result = InputSanitizer.sanitize_file_path(path)
        assert result is None

    def test_sanitize_file_path_none(self):
        """Test sanitizing None file path."""
        result = InputSanitizer.sanitize_file_path(None)
        assert result is None

    def test_sanitize_text_normal(self):
        """Test sanitizing normal text."""
        text = "Some text\nwith newlines\tand tabs"
        result = InputSanitizer.sanitize_text(text)
        assert result == text

    def test_sanitize_text_control_chars(self):
        """Test removing control characters from text."""
        text = "Text\x00\x01with\x1fcontrol chars"
        result = InputSanitizer.sanitize_text(text)
        assert "\x00" not in result
        assert "\x01" not in result
        assert "\x1f" not in result

    def test_sanitize_text_length_limit(self):
        """Test text length limiting."""
        long_text = "x" * (InputSanitizer.MAX_TEXT_LENGTH + 100)
        result = InputSanitizer.sanitize_text(long_text)
        assert len(result) == InputSanitizer.MAX_TEXT_LENGTH + len("... [truncated]")
        assert result.endswith("... [truncated]")

    def test_validate_json_input_valid(self):
        """Test validating valid JSON input."""
        json_str = '{"prompt": "hello"}'
        result = InputSanitizer.validate_json_input(json_str)
        assert result is True

    def test_validate_json_input_too_long(self):
        """Test validating too long JSON input."""
        long_json = '{"data": "' + "x" * 100000 + '"}'
        result = InputSanitizer.validate_json_input(long_json)
        assert result is False

    def test_validate_json_input_suspicious(self):
        """Test validating suspicious JSON input."""
        suspicious_json = '{"prompt": "import os"}'
        result = InputSanitizer.validate_json_input(suspicious_json)
        assert result is False

    def test_validate_json_input_none(self):
        """Test validating None input."""
        result = InputSanitizer.validate_json_input(None)
        assert result is False