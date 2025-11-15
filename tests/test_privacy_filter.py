"""Unit tests for privacy_filter module."""

from unittest import TestCase

from modules.privacy_filter import PrivacyFilter


class TestPrivacyFilter(TestCase):
    """Tests for PrivacyFilter class."""

    def setUp(self):
        """Set up test filter."""
        self.filter = PrivacyFilter()

    def test_email_scrubbing(self):
        """Test that email addresses are scrubbed."""
        text = "Contact me at user@example.com"
        result = self.filter.sanitise(text)
        assert "[EMAIL]" in result
        assert "user@example.com" not in result

    def test_blocklist_filtering(self):
        """Test that blocklisted keywords trigger replacement."""
        text = "I'm using 1password for passwords"
        result = self.filter.sanitise(text)
        assert "User in sensitive application" in result
        assert "1password" not in result

    def test_nested_structure_sanitization(self):
        """Test sanitization of nested data structures."""
        data = {
            "title": "Email from user@example.com",
            "application": "Gmail",
            "nested": {
                "content": "Secret information here"
            }
        }
        result = self.filter.sanitise(data)
        assert "[EMAIL]" in str(result)
        assert "user@example.com" not in str(result)

    def test_ip_address_scrubbing(self):
        """Test that IP addresses are scrubbed."""
        text = "Server at 192.168.1.1"
        result = self.filter.sanitise(text)
        assert "[IP]" in result
        assert "192.168.1.1" not in result

    def test_credit_card_scrubbing(self):
        """Test that credit card numbers are scrubbed."""
        text = "Card number: 1234-5678-9012-3456"
        result = self.filter.sanitise(text)
        assert "[CARD]" in result


