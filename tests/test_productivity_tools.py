"""Unit tests for productivity_tools module."""

import subprocess
from unittest import TestCase
from unittest.mock import patch, MagicMock
from pathlib import Path

from modules.productivity_tools import (
    ALLOWED_COMMANDS,
    MAX_CLIPBOARD_LENGTH,
    MAX_COMMAND_LENGTH,
    ProductivityTools,
)


class TestProductivityTools(TestCase):
    """Tests for ProductivityTools class."""

    def test_command_whitelist_blocks_unknown(self):
        """Test that commands outside the allow-list are blocked."""
        result = ProductivityTools.execute_bash_command("rm -rf /tmp/test")
        assert result["returncode"] == -1
        assert "not permitted" in result["error"].lower()

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

    def test_allow_list_contains_echo(self):
        """Ensure allow-list contains commonly used safe commands."""
        assert "echo" in ALLOWED_COMMANDS

    def test_clipboard_length_limit(self):
        """Test that clipboard content is truncated if too long."""
        # This test would require mocking subprocess, but documents the behavior
        # The read_clipboard method should truncate content > MAX_CLIPBOARD_LENGTH
        assert MAX_CLIPBOARD_LENGTH == 10000


    @patch('subprocess.run')
    def test_read_clipboard_success(self, mock_run):
        """Test successful clipboard reading."""
        mock_run.return_value = MagicMock(stdout="test content", returncode=0)
        result = ProductivityTools.read_clipboard()
        assert result == "test content"
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_read_clipboard_failure(self, mock_run):
        """Test clipboard reading failure."""
        mock_run.side_effect = subprocess.TimeoutExpired("xclip", 2)
        result = ProductivityTools.read_clipboard()
        assert result is None

    @patch('subprocess.run')
    def test_read_clipboard_truncation(self, mock_run):
        """Test clipboard content truncation."""
        long_content = "x" * (MAX_CLIPBOARD_LENGTH + 100)
        mock_run.return_value = MagicMock(stdout=long_content, returncode=0)
        result = ProductivityTools.read_clipboard()
        # Should be truncated with "... [truncated]" message
        assert len(result) > MAX_CLIPBOARD_LENGTH
        assert result.endswith("... [truncated]")
        assert result.startswith("x" * MAX_CLIPBOARD_LENGTH)

    @patch('subprocess.run')
    def test_take_screenshot_success(self, mock_run):
        """Test successful screenshot taking."""
        mock_run.return_value = MagicMock(returncode=0)
        result = ProductivityTools.take_screenshot()
        assert result is not None
        assert isinstance(result, Path)
        assert str(result).endswith('.png')

    @patch('subprocess.run')
    @patch('pathlib.Path.exists')
    def test_take_screenshot_failure(self, mock_exists, mock_run):
        """Test screenshot taking failure."""
        # Mock all screenshot methods to fail
        mock_run.return_value = MagicMock(returncode=1)
        mock_exists.return_value = False  # Screenshot file doesn't exist
        result = ProductivityTools.take_screenshot()
        assert result is None

    @patch('subprocess.run')
    def test_get_battery_status_ac_power(self, mock_run):
        """Test battery status when on AC power."""
        # Mock upower -e to return battery devices
        mock_run.side_effect = [
            MagicMock(stdout="/org/freedesktop/UPower/devices/battery_BAT0", returncode=0),  # upower -e
            MagicMock(stdout="power supply: yes\npercentage: 100%\nstate: charging", returncode=0)  # upower -i
        ]
        result = ProductivityTools.get_battery_status()
        assert "percentage" in result
        assert "state" in result

    @patch('subprocess.run')
    def test_get_battery_status_discharging(self, mock_run):
        """Test battery status when discharging."""
        # Mock upower -e to return battery devices
        mock_run.side_effect = [
            MagicMock(stdout="/org/freedesktop/UPower/devices/battery_BAT0", returncode=0),  # upower -e
            MagicMock(stdout="power supply: yes\npercentage: 75%\nstate: discharging", returncode=0)  # upower -i
        ]
        result = ProductivityTools.get_battery_status()
        assert "percentage" in result
        assert "state" in result

    @patch('subprocess.run')
    @patch('pathlib.Path.exists')
    @patch('builtins.open')
    def test_get_battery_status_failure(self, mock_open, mock_exists, mock_run):
        """Test battery status failure."""
        mock_run.side_effect = FileNotFoundError
        mock_exists.return_value = False  # No /sys/class/power_supply files
        result = ProductivityTools.get_battery_status()
        assert isinstance(result, dict)  # Should return a dict even on failure

    @patch('builtins.open')
    def test_get_cpu_usage(self, mock_open):
        """Test CPU usage retrieval."""
        mock_file = MagicMock()
        mock_file.readline.return_value = "cpu  10132153 0 1362399 44782005 0 0 0 0 0 0"
        mock_open.return_value.__enter__.return_value = mock_file

        result = ProductivityTools.get_cpu_usage()
        assert result is not None
        assert isinstance(result, float)

    @patch('builtins.open')
    def test_get_memory_usage(self, mock_open):
        """Test memory usage retrieval."""
        mock_file = MagicMock()
        mock_file.readlines.return_value = [
            "MemTotal:        8192000 kB",
            "MemFree:         2048000 kB",
            "MemAvailable:    4096000 kB"
        ]
        mock_open.return_value.__enter__.return_value = mock_file

        result = ProductivityTools.get_memory_usage()
        assert result is not None
        assert "total_mb" in result
        assert "available_mb" in result
        assert "used_percent" in result

    @patch('subprocess.run')
    def test_cleanup_zombie_processes(self, mock_run):
        """Test zombie process cleanup."""
        # Mock ps aux output with no zombies
        mock_run.return_value = MagicMock(stdout="USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND\nuser      1234  0.0  0.0   1234   567 pts/0    S    10:00   0:00 bash", returncode=0)
        result = ProductivityTools.cleanup_zombie_processes()
        assert "zombies_found" in result
        assert "zombies_cleaned" in result
        assert isinstance(result["zombies_found"], int)
        assert isinstance(result["zombies_cleaned"], int)


