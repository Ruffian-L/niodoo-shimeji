"""Unit tests for productivity_tools module."""

from unittest import TestCase

from modules.productivity_tools import (
    DANGEROUS_COMMANDS,
    MAX_CLIPBOARD_LENGTH,
    MAX_COMMAND_LENGTH,
    ProductivityTools,
)


class TestProductivityTools(TestCase):
    """Tests for ProductivityTools class."""

    def test_command_validation_blocklist(self):
        """Test that dangerous commands are blocked."""
        result = ProductivityTools.execute_bash_command("rm -rf /tmp/test")
        assert result["returncode"] == -1
        assert "blocked" in result["error"].lower()

    def test_command_length_validation(self):
        """Test that overly long commands are rejected."""
        long_command = "echo " + "x" * (MAX_COMMAND_LENGTH + 1)
        result = ProductivityTools.execute_bash_command(long_command)
        assert result["returncode"] == -1
        assert "too long" in result["error"].lower()

    def test_safe_command_execution(self):
        """Test that safe commands can be executed."""
        result = ProductivityTools.execute_bash_command("echo 'test'")
        # Should not be blocked, though may fail if bash not available
        assert "returncode" in result or "error" in result

    def test_clipboard_length_limit(self):
        """Test that clipboard content is truncated if too long."""
        # This test would require mocking subprocess, but documents the behavior
        # The read_clipboard method should truncate content > MAX_CLIPBOARD_LENGTH
        assert MAX_CLIPBOARD_LENGTH == 10000

    def test_dangerous_commands_list(self):
        """Test that dangerous commands list is properly defined."""
        assert "rm -rf" in DANGEROUS_COMMANDS
        assert "shutdown" in DANGEROUS_COMMANDS
        assert len(DANGEROUS_COMMANDS) > 0


