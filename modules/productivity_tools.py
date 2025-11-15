"""Productivity tool integrations for the Shimeji agent."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

LOGGER = logging.getLogger(__name__)

# Only block truly destructive commands that could cause immediate system damage
# Allow sensitive but useful commands (like editing configs) - Gemini will warn first
DANGEROUS_COMMANDS = {
    "rm -rf /",  # Only block root deletion, not regular rm -rf
    "rm -f /",   # Only block root deletion
    "dd if=",    # Block disk imaging that could overwrite drives
    "mkfs",      # Block filesystem creation
    "fdisk",     # Block disk partitioning
    "> /dev/sd", # Block writing to raw disk devices
    "shutdown",  # Block system shutdown
    "reboot",    # Block system reboot
    "init 0",    # Block system halt
    "init 6",    # Block system reboot
    "halt",      # Block system halt
    "poweroff",  # Block system poweroff
    "chmod -R 777 /",  # Only block system-wide permission changes
    "chown -R root /", # Only block system-wide ownership changes
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
        # Try to find the actual battery device
        battery_devices = []
        try:
            result = subprocess.run(
                ["upower", "-e"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if "battery" in line.lower():
                        battery_devices.append(line.strip())
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        # If no devices found via upower -e, try common paths
        if not battery_devices:
            battery_devices = [
                "/org/freedesktop/UPower/devices/battery_BAT1",
                "/org/freedesktop/UPower/devices/battery_BAT0",
            ]
        
        # Try each battery device until we find one with valid data
        for device_path in battery_devices:
            try:
                result = subprocess.run(
                    ["upower", "-i", device_path],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    output = result.stdout
                    percentage = None
                    state = None
                    power_supply = None
                    energy = None
                    energy_full = None
                    
                    for line in output.split("\n"):
                        line_lower = line.lower()
                        if "power supply:" in line_lower:
                            power_supply = line.split(":")[1].strip().lower()
                        if "percentage:" in line:
                            pct_str = line.split(":")[1].strip()
                            # Skip if it says "should be ignored"
                            if "should be ignored" not in line_lower:
                                # Extract numeric value (e.g., "85%" -> 85)
                                try:
                                    percentage = float(pct_str.rstrip("%"))
                                except ValueError:
                                    percentage = pct_str
                        if "state:" in line and "battery" in line_lower:
                            state = line.split(":")[1].strip()
                        # Calculate from energy if percentage not available
                        if "energy:" in line_lower and "energy-empty" not in line_lower and "energy-full" not in line_lower:
                            try:
                                energy = float(line.split(":")[1].strip().split()[0])
                            except (ValueError, IndexError):
                                pass
                        if "energy-full:" in line_lower:
                            try:
                                energy_full = float(line.split(":")[1].strip().split()[0])
                            except (ValueError, IndexError):
                                pass
                    
                    # Calculate percentage from energy if not directly available
                    if percentage is None and energy is not None and energy_full is not None and energy_full > 0:
                        percentage = (energy / energy_full) * 100
                    
                    # Only return if we have a valid power supply (yes) and percentage
                    if power_supply == "yes" and percentage is not None:
                        # Check if percentage is actually valid (not 0% with "should be ignored")
                        if isinstance(percentage, (int, float)) and percentage >= 0:
                            return {"percentage": f"{percentage:.0f}%", "state": state}
                        elif isinstance(percentage, str):
                            return {"percentage": percentage, "state": state}
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
            except Exception as exc:
                LOGGER.debug("Error checking battery device %s: %s", device_path, exc)
                continue
        
        # Fallback: try /sys/class/power_supply if upower fails
        try:
            for battery_dir in Path("/sys/class/power_supply").glob("BAT*"):
                capacity_file = battery_dir / "capacity"
                status_file = battery_dir / "status"
                if capacity_file.exists():
                    with open(capacity_file, "r") as f:
                        percentage = f.read().strip()
                    state = None
                    if status_file.exists():
                        with open(status_file, "r") as f:
                            state = f.read().strip()
                    return {"percentage": f"{percentage}%", "state": state}
        except Exception as exc:
            LOGGER.debug("Error reading /sys/class/power_supply: %s", exc)
        
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

