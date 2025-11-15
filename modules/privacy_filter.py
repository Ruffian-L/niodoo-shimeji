"""Privacy filtering utilities for sanitising desktop context payloads.

This module provides a `PrivacyFilter` class that can be used to scrub
potentially sensitive information prior to sending it to any remote API.
It supports keyword block-listing as well as regular expression based
replacement for common personally identifiable information (PII) such as
email addresses, credit card numbers, IP addresses, and Social Security
numbers.

The filter operates recursively over arbitrary Python data structures
(dict, list, tuple, set) and preserves the original data type when
returning sanitised values.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Sequence


_DEFAULT_BLOCKLIST = {
    "1password",
    "lastpass",
    "keepass",
    "bitwarden",
    "outlook",
    "gmail",
    "confidential",
    "private",
    "secret",
    "bank",
    "vault",
}


@dataclass
class PrivacyFilter:
    """Sanitises strings and nested payloads using keyword and regex rules."""

    blocklist: Iterable[str] = field(default_factory=lambda: _DEFAULT_BLOCKLIST)
    sensitive_replacement: str = "User in sensitive application"

    def __post_init__(self) -> None:
        self._blocklist = {word.casefold() for word in self.blocklist}
        self._patterns: Sequence[tuple[re.Pattern[str], str]] = (
            # Email addresses
            (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
            # Credit card numbers (13-16 digits with optional separators)
            (re.compile(r"\b(?:\d[ -]*?){13,16}\b"), "[CARD]"),
            # US Social Security numbers
            (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
            # IPv4 addresses
            (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[IP]"),
            # IPv6 addresses
            (re.compile(r"\b(?:[A-Fa-f0-9]{1,4}:){1,7}[A-Fa-f0-9]{1,4}\b"), "[IP]"),
            # UUIDs
            (
                re.compile(
                    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
                ),
                "[UUID]",
            ),
        )

    def sanitise(self, value: Any) -> Any:
        """Return a privacy-safe copy of ``value``.

        Supports arbitrarily nested mappings, sequences, and sets. Strings are
        scrubbed according to the block-list and regex patterns. Non-string
        scalar types are returned unchanged.
        """

        if isinstance(value, str):
            return self._scrub_string(value)

        if isinstance(value, Mapping):
            return {key: self.sanitise(val) for key, val in value.items()}

        if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
            return type(value)(self.sanitise(item) for item in value)

        if isinstance(value, set):
            return {self.sanitise(item) for item in value}

        return value

    def sanitise_context(self, context: MutableMapping[str, Any]) -> Dict[str, Any]:
        """Sanitise a mutable mapping representing desktop context.

        Parameters
        ----------
        context:
            A mapping of contextual data (e.g. active window metadata) that may
            contain sensitive strings.

        Returns
        -------
        Dict[str, Any]
            A deep-copied, sanitised version of ``context``.
        """

        return self.sanitise(copy.deepcopy(context))

    # Backwards compatible alias for American spelling.
    sanitize = sanitise
    sanitize_context = sanitise_context

    def _scrub_string(self, text: str) -> str:
        lowered = text.casefold()
        for keyword in self._blocklist:
            if keyword in lowered:
                return self.sensitive_replacement

        scrubbed = text
        for pattern, replacement in self._patterns:
            scrubbed = pattern.sub(replacement, scrubbed)

        # Collapse excessive whitespace caused by replacements
        scrubbed = re.sub(r"\s{2,}", " ", scrubbed).strip()
        return scrubbed
