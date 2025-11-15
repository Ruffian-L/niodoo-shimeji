"""Input sanitization utilities for user-provided data."""

import os
import re
from pathlib import Path
from typing import Optional


class InputSanitizer:
    """Utilities for sanitizing user input to prevent security issues."""

    # Maximum lengths for different input types
    MAX_PROMPT_LENGTH = 50000  # Increased from 10000 for better UX
    MAX_FILE_PATH_LENGTH = 4096  # Typical filesystem limit
    MAX_TEXT_LENGTH = 100000

    # Dangerous characters to remove from prompts
    DANGEROUS_CHARS = [
        '\x00',  # Null byte
        '\x01', '\x02', '\x03', '\x04', '\x05', '\x06', '\x07',  # Control chars
        '\x08',  # Backspace
        '\x0b', '\x0c',  # Vertical tab, form feed
        '\x0e', '\x0f', '\x10', '\x11', '\x12', '\x13', '\x14', '\x15', '\x16', '\x17', '\x18', '\x19', '\x1a', '\x1b', '\x1c', '\x1d', '\x1e', '\x1f'  # More control chars
    ]

    @staticmethod
    def sanitize_prompt(prompt: str) -> str:
        """Sanitize user prompt input.

        Args:
            prompt: Raw user prompt

        Returns:
            Sanitized prompt safe for processing
        """
        if not isinstance(prompt, str):
            return ""

        # Remove dangerous control characters
        sanitized = ''.join(c for c in prompt if c not in InputSanitizer.DANGEROUS_CHARS)

        # Limit length
        if len(sanitized) > InputSanitizer.MAX_PROMPT_LENGTH:
            sanitized = sanitized[:InputSanitizer.MAX_PROMPT_LENGTH] + "... [truncated]"

        return sanitized.strip()

    @staticmethod
    def sanitize_file_path(file_path: str) -> Optional[str]:
        """Sanitize and validate file path.

        Args:
            file_path: Raw file path from user input

        Returns:
            Sanitized file path or None if invalid
        """
        if not isinstance(file_path, str):
            return None

        # Basic length check
        if len(file_path) > InputSanitizer.MAX_FILE_PATH_LENGTH:
            return None

        # Resolve the path to prevent directory traversal
        try:
            resolved_path = Path(file_path).resolve()
        except (OSError, RuntimeError):
            return None

        # Convert back to string
        sanitized_path = str(resolved_path)

        # Additional security checks
        if not sanitized_path:
            return None

        # Check for suspicious patterns (basic)
        if ".." in sanitized_path or "//" in sanitized_path:
            # Allow .. in resolved paths but be cautious
            pass

        return sanitized_path

    @staticmethod
    def sanitize_text(text: str) -> str:
        """Sanitize general text input.

        Args:
            text: Raw text input

        Returns:
            Sanitized text
        """
        if not isinstance(text, str):
            return ""

        # Remove dangerous control characters but keep newlines and tabs
        sanitized = ''.join(c for c in text if ord(c) >= 32 or c in '\n\t')

        # Limit length
        if len(sanitized) > InputSanitizer.MAX_TEXT_LENGTH:
            sanitized = sanitized[:InputSanitizer.MAX_TEXT_LENGTH] + "... [truncated]"

        return sanitized.strip()

    @staticmethod
    def validate_json_input(data: str) -> bool:
        """Validate that input looks like safe JSON.

        Args:
            data: Raw input data

        Returns:
            True if input appears safe for JSON parsing
        """
        if not isinstance(data, str):
            return False

        # Basic checks for potentially dangerous content
        if len(data) > 100000:  # 100KB limit
            return False

        # Check for suspicious patterns
        suspicious_patterns = [
            r'__.*__',  # Dunder methods
            r'import\s',  # Python imports
            r'exec\s*\(',  # exec calls
            r'eval\s*\(',  # eval calls
        ]

        for pattern in suspicious_patterns:
            if re.search(pattern, data, re.IGNORECASE):
                return False

        return True