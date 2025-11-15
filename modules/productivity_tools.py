"""Productivity tool integrations for the Shimeji agent."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

LOGGER = logging.getLogger(__name__)

# Dangerous command patterns that should be blocked
DANGEROUS_COMMANDS = {
    "rm -rf",
    "dd if=",
    "mkfs",
    "fdisk",
    "format",
    "> /dev/sd",
    "shutdown",
    "reboot",
    "init 0",
    "init 6",
    "halt",
    "poweroff",
    "rm -f /",
    "chmod -R 777",
    "chown -R",
}

# Maximum clipboard content length to prevent paste attacks
MAX_CLIPBOARD_LENGTH = 10000

# Maximum command length
MAX_COMMAND_LENGTH = 1000


class ProductivityTools:
    """Collection of system integration tools for the agent."""

    @staticmethod
    def read_clipboard() -> Optional[str]:
        """Read current clipboard content with length limits."""
        try:
            result = subprocess.run(
                ["xclip", "-selection", "clipboard", "-o"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                content = result.stdout
                # Additional sanitization before returning
                if len(content) > MAX_CLIPBOARD_LENGTH:
                    LOGGER.warning("Clipboard content too long, truncating")
                    return content[:MAX_CLIPBOARD_LENGTH] + "... [truncated]"
                return content
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Try wl-paste for Wayland
            try:
                result = subprocess.run(
                    ["wl-paste"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    content = result.stdout
                    # Additional sanitization before returning
                    if len(content) > MAX_CLIPBOARD_LENGTH:
                        LOGGER.warning("Clipboard content too long, truncating")
                        return content[:MAX_CLIPBOARD_LENGTH] + "... [truncated]"
                    return content
            except (subprocess.TimeoutExpired, FileNotFoundError):
                LOGGER.debug("Clipboard tools not available")
        return None

    @staticmethod
    def execute_bash_command(command: str, timeout: float = 10.0) -> dict:
        """Execute a bash command safely and return output."""
        # Validate command length
        if len(command) > MAX_COMMAND_LENGTH:
            return {
                "error": f"Command too long (max {MAX_COMMAND_LENGTH} chars)",
                "returncode": -1
            }
        
        # Validate against dangerous commands
        cmd_lower = command.lower()
        for dangerous in DANGEROUS_COMMANDS:
            if dangerous.lower() in cmd_lower:
                LOGGER.warning("Command blocked: contains dangerous pattern '%s'", dangerous)
                return {
                    "error": f"Command blocked: contains dangerous pattern '{dangerous}'",
                    "returncode": -1
                }
        
        try:
            result = subprocess.run(
                ["bash", "-c", command],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out", "returncode": -1}
        except Exception as exc:
            return {"error": str(exc), "returncode": -1}

    @staticmethod
    def take_screenshot() -> Optional[Path]:
        """Capture a screenshot and return the file path."""
        screenshot_path = Path("/tmp/shimeji_screenshot.png")
        
        # Try gnome-screenshot first
        try:
            result = subprocess.run(
                ["gnome-screenshot", "-f", str(screenshot_path)],
                capture_output=True,
                timeout=5,
            )
            # gnome-screenshot may output warnings to stderr but still succeed
            if screenshot_path.exists():
                LOGGER.debug("Screenshot captured via gnome-screenshot: %s", screenshot_path)
                return screenshot_path
            elif result.returncode != 0:
                LOGGER.debug("gnome-screenshot failed with returncode %d: %s", result.returncode, result.stderr.decode()[:200])
        except subprocess.TimeoutExpired:
            LOGGER.warning("gnome-screenshot timed out")
        except FileNotFoundError:
            LOGGER.debug("gnome-screenshot not found")
        except Exception as exc:
            LOGGER.debug("gnome-screenshot error: %s", exc)
        
        # Try scrot as fallback
        try:
            result = subprocess.run(
                ["scrot", str(screenshot_path)],
                capture_output=True,
                timeout=5,
            )
            if screenshot_path.exists():
                LOGGER.debug("Screenshot captured via scrot: %s", screenshot_path)
                return screenshot_path
            elif result.returncode != 0:
                LOGGER.debug("scrot failed with returncode %d: %s", result.returncode, result.stderr.decode()[:200])
        except subprocess.TimeoutExpired:
            LOGGER.warning("scrot timed out")
        except FileNotFoundError:
            LOGGER.debug("scrot not found")
        except Exception as exc:
            LOGGER.debug("scrot error: %s", exc)
        
        LOGGER.warning("Screenshot tools not available or failed")
        return None

    @staticmethod
    def get_battery_status() -> dict:
        """Get battery percentage and charging status."""
        try:
            result = subprocess.run(
                ["upower", "-i", "/org/freedesktop/UPower/devices/battery_BAT0"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                output = result.stdout
                percentage = None
                state = None
                for line in output.split("\n"):
                    if "percentage:" in line:
                        percentage = line.split(":")[1].strip()
                    if "state:" in line:
                        state = line.split(":")[1].strip()
                return {"percentage": percentage, "state": state}
        except (subprocess.TimeoutExpired, FileNotFoundError):
            LOGGER.debug("Battery info not available")
        return {}

    @staticmethod
    def get_cpu_usage() -> Optional[float]:
        """Get current CPU usage percentage."""
        try:
            with open("/proc/stat", "r") as f:
                line = f.readline()
                fields = line.split()
                idle = int(fields[4])
                total = sum(int(x) for x in fields[1:])
                usage = 100.0 * (1.0 - idle / total)
                return usage
        except Exception as exc:
            LOGGER.debug("CPU usage unavailable: %s", exc)
        return None

    @staticmethod
    def get_memory_usage() -> Optional[dict]:
        """Get memory usage statistics."""
        try:
            with open("/proc/meminfo", "r") as f:
                lines = f.readlines()
                mem_info = {}
                for line in lines[:3]:
                    parts = line.split()
                    if len(parts) >= 2:
                        mem_info[parts[0].rstrip(":")] = int(parts[1])
                
                total = mem_info.get("MemTotal", 0)
                available = mem_info.get("MemAvailable", 0)
                if total > 0:
                    used_percent = 100.0 * (1.0 - available / total)
                    return {
                        "total_mb": total // 1024,
                        "available_mb": available // 1024,
                        "used_percent": round(used_percent, 1),
                    }
        except Exception as exc:
            LOGGER.debug("Memory info unavailable: %s", exc)
        return None

