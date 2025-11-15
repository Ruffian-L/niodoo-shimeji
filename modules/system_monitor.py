"""System monitoring and alerting for the Shimeji agent."""

from __future__ import annotations

import asyncio
import glob
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from modules.memory_manager import MemoryManager
    from modules.event_bus import EventBus

LOGGER = logging.getLogger(__name__)

# Optional dependencies - handle gracefully if missing
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    LOGGER.warning("psutil not available; system monitoring will be limited")

try:
    import pynvml
    PYNVML_AVAILABLE = True
except ImportError:
    PYNVML_AVAILABLE = False
    pynvml = None  # Type stub for linter
    LOGGER.debug("pynvml not available; GPU monitoring disabled")

try:
    from systemd import journal
    SYSTEMD_JOURNAL_AVAILABLE = True
except ImportError:
    SYSTEMD_JOURNAL_AVAILABLE = False
    LOGGER.debug("systemd.journal not available; log monitoring will use file tailing")


class AlertSeverity(Enum):
    """Alert severity levels."""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class SystemAlert:
    """System alert data structure."""
    severity: AlertSeverity
    alert_type: str  # "ram", "gpu", "zombie", "disk", "network", "log"
    message: str
    details: Dict[str, Any]
    timestamp: str


class MonitoringManager:
    """Manages all system monitoring tasks."""
    
    def __init__(
        self,
        memory_manager: "MemoryManager",
        event_bus: "EventBus",
        alert_handler: Optional[Callable[[SystemAlert], None]] = None,
    ) -> None:
        self.memory = memory_manager
        self.event_bus = event_bus
        self.alert_handler = alert_handler
        self._tasks: List[asyncio.Task[None]] = []
        self._running = False
        self._rate_limit_cache: Dict[str, float] = {}  # alert_type -> last_alert_time
        
        # Get rate limit from preferences
        self._rate_limit_minutes = self.memory.get_pref("alert_rate_limit_minutes", 5)
    
    async def start(self) -> None:
        """Start all monitoring tasks."""
        if self._running:
            return
        
        self._running = True
        LOGGER.info("Starting system monitoring...")
        
        # Start RAM monitor
        if PSUTIL_AVAILABLE:
            self._tasks.append(asyncio.create_task(self._ram_monitor()))
            self._tasks.append(asyncio.create_task(self._disk_monitor()))
            self._tasks.append(asyncio.create_task(self._zombie_monitor()))
            self._tasks.append(asyncio.create_task(self._network_monitor()))
            
            # GPU monitor (optional)
            if PYNVML_AVAILABLE:
                try:
                    pynvml.nvmlInit()
                    self._tasks.append(asyncio.create_task(self._gpu_monitor()))
                except Exception as exc:
                    LOGGER.debug("GPU monitoring unavailable: %s", exc)
        
        # Log monitor
        self._tasks.append(asyncio.create_task(self._log_monitor()))
        
        LOGGER.info("System monitoring started with %d monitors", len(self._tasks))
    
    async def stop(self) -> None:
        """Stop all monitoring tasks."""
        if not self._running:
            return
        
        self._running = False
        LOGGER.info("Stopping system monitoring...")
        
        # Cancel all tasks
        for task in self._tasks:
            task.cancel()
        
        # Wait for tasks to finish
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        
        self._tasks.clear()
        LOGGER.info("System monitoring stopped")
    
    def _should_alert(self, alert_type: str, device: Optional[str] = None) -> bool:
        """Check if alert should be sent (rate limiting).
        
        Args:
            alert_type: Type of alert (e.g., "disk", "ram", "network")
            device: Optional device identifier for per-device rate limiting (e.g., "/dev/sda1")
        """
        now = time.monotonic()
        # Use device-specific key if provided (for disk alerts)
        cache_key = f"{alert_type}:{device}" if device else alert_type
        last_alert = self._rate_limit_cache.get(cache_key, 0)
        rate_limit_seconds = self._rate_limit_minutes * 60
        
        if now - last_alert < rate_limit_seconds:
            return False
        
        self._rate_limit_cache[cache_key] = now
        return True
    
    def _route_alert(self, alert: SystemAlert, device: Optional[str] = None) -> None:
        """Route alert based on severity.
        
        Args:
            alert: The system alert to route
            device: Optional device identifier for per-device rate limiting
        """
        # Check if this alert type is enabled
        enabled = self.memory.get_pref(f"alert_enabled_{alert.alert_type}", True)
        if not enabled:
            LOGGER.debug("Alert type %s is disabled, skipping", alert.alert_type)
            return
        
        if not self._should_alert(alert.alert_type, device):
            LOGGER.debug("Alert rate limited: %s%s", alert.alert_type, f" ({device})" if device else "")
            return
        
        # Publish to event bus
        from modules.event_bus import EventType
        self.event_bus.publish(EventType.SYSTEM_ALERT, alert)
        
        # Call custom handler if provided
        if self.alert_handler:
            try:
                self.alert_handler(alert)
            except Exception as exc:
                LOGGER.error("Alert handler failed: %s", exc)
        
        # Log alert
        LOGGER.warning(
            "[%s] %s: %s",
            alert.severity.value.upper(),
            alert.alert_type.upper(),
            alert.message
        )
    
    async def _ram_monitor(self) -> None:
        """Monitor RAM usage."""
        if not PSUTIL_AVAILABLE:
            return
        
        last_usage = 0.0
        poll_interval = self.memory.get_pref("monitor_poll_interval_s", 30)
        threshold = self.memory.get_pref("ram_threshold_pct", 85.0)
        critical = self.memory.get_pref("ram_critical_pct", 90.0)
        
        while self._running:
            try:
                await asyncio.sleep(poll_interval)
                if not self._running:
                    break
                
                mem = psutil.virtual_memory()
                usage_pct = mem.percent
                available_gb = mem.available / (1024**3)
                used_gb = mem.used / (1024**3)
                total_gb = mem.total / (1024**3)
                
                # Check swap pressure
                swap = psutil.swap_memory()
                swap_used_pct = swap.percent if swap.total > 0 else 0
                
                # Only alert on state change (crossing threshold)
                if usage_pct > critical and usage_pct > last_usage:
                    alert = SystemAlert(
                        severity=AlertSeverity.CRITICAL,
                        alert_type="ram",
                        message=f"RAM usage critical: {usage_pct:.1f}% ({used_gb:.1f}GB used, {available_gb:.1f}GB available)",
                        details={
                            "usage_pct": usage_pct,
                            "used_gb": used_gb,
                            "available_gb": available_gb,
                            "total_gb": total_gb,
                            "swap_used_pct": swap_used_pct,
                        },
                        timestamp=datetime.now(UTC).isoformat(),
                    )
                    self._route_alert(alert)
                elif usage_pct > threshold and usage_pct > last_usage:
                    alert = SystemAlert(
                        severity=AlertSeverity.WARNING,
                        alert_type="ram",
                        message=f"RAM usage high: {usage_pct:.1f}% ({used_gb:.1f}GB used, {available_gb:.1f}GB available)",
                        details={
                            "usage_pct": usage_pct,
                            "used_gb": used_gb,
                            "available_gb": available_gb,
                            "total_gb": total_gb,
                            "swap_used_pct": swap_used_pct,
                        },
                        timestamp=datetime.now(UTC).isoformat(),
                    )
                    self._route_alert(alert)
                
                last_usage = usage_pct
                
            except Exception as exc:
                LOGGER.error("RAM monitor error: %s", exc)
                await asyncio.sleep(poll_interval)
    
    async def _gpu_monitor(self) -> None:
        """Monitor GPU usage (NVIDIA only)."""
        if not PYNVML_AVAILABLE or pynvml is None:
            return
        
        try:
            pynvml.nvmlInit()
            device_count = pynvml.nvmlDeviceGetCount()
            if device_count == 0:
                return
            
            handles = []
            for i in range(device_count):
                handles.append(pynvml.nvmlDeviceGetHandleByIndex(i))
        except Exception as exc:
            LOGGER.debug("GPU initialization failed: %s", exc)
            return
        
        poll_interval = self.memory.get_pref("monitor_poll_interval_s", 30)
        mem_threshold = self.memory.get_pref("gpu_mem_threshold_pct", 80.0)
        temp_threshold = self.memory.get_pref("gpu_temp_threshold_c", 85.0)
        
        while self._running:
            try:
                await asyncio.sleep(poll_interval)
                if not self._running:
                    break
                
                for idx, handle in enumerate(handles):
                    try:
                        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                        mem_usage_pct = (mem_info.used / mem_info.total) * 100
                        temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                        
                        # Check memory threshold
                        if mem_usage_pct > mem_threshold:
                            alert = SystemAlert(
                                severity=AlertSeverity.WARNING,
                                alert_type="gpu",
                                message=f"GPU {idx} memory high: {mem_usage_pct:.1f}% ({mem_info.used / (1024**3):.1f}GB used)",
                                details={
                                    "gpu_index": idx,
                                    "mem_usage_pct": mem_usage_pct,
                                    "mem_used_gb": mem_info.used / (1024**3),
                                    "mem_total_gb": mem_info.total / (1024**3),
                                    "temperature_c": temp,
                                    "utilization_pct": util.gpu,
                                },
                                timestamp=datetime.now(UTC).isoformat(),
                            )
                            self._route_alert(alert)
                        
                        # Check temperature threshold
                        if temp > temp_threshold:
                            alert = SystemAlert(
                                severity=AlertSeverity.WARNING,
                                alert_type="gpu",
                                message=f"GPU {idx} temperature high: {temp}°C",
                                details={
                                    "gpu_index": idx,
                                    "temperature_c": temp,
                                    "mem_usage_pct": mem_usage_pct,
                                    "utilization_pct": util.gpu,
                                },
                                timestamp=datetime.now(UTC).isoformat(),
                            )
                            self._route_alert(alert)
                            
                    except Exception as exc:
                        LOGGER.debug("GPU %d monitor error: %s", idx, exc)
                        
            except Exception as exc:
                LOGGER.error("GPU monitor error: %s", exc)
                await asyncio.sleep(poll_interval)
    
    async def _zombie_monitor(self) -> None:
        """Monitor for zombie processes."""
        if not PSUTIL_AVAILABLE:
            return
        
        last_count = 0
        poll_interval = 60  # Check every minute
        threshold = self.memory.get_pref("zombie_threshold_count", 5)
        critical = self.memory.get_pref("zombie_critical_count", 10)
        
        while self._running:
            try:
                await asyncio.sleep(poll_interval)
                if not self._running:
                    break
                
                zombies = []
                try:
                    # Use psutil for efficient scanning
                    for proc in psutil.process_iter(attrs=['pid', 'name', 'status']):
                        try:
                            if proc.info['status'] == psutil.STATUS_ZOMBIE:
                                zombies.append(proc.info)
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                except Exception:
                    # Fallback to direct /proc scanning
                    for pid_dir in glob.glob('/proc/[0-9]*'):
                        try:
                            with open(f"{pid_dir}/stat", 'r') as f:
                                state = f.read().split()[2]
                                if state == 'Z':
                                    pid = int(pid_dir.split('/')[-1])
                                    zombies.append({'pid': pid, 'name': 'unknown', 'status': 'Z'})
                        except (IOError, IndexError, ValueError):
                            pass
                
                zombie_count = len(zombies)
                
                # Only alert on increase
                if zombie_count > critical and zombie_count > last_count:
                    alert = SystemAlert(
                        severity=AlertSeverity.CRITICAL,
                        alert_type="zombie",
                        message=f"{zombie_count} zombie processes detected",
                        details={
                            "count": zombie_count,
                            "zombies": [(z.get('pid'), z.get('name')) for z in zombies[:10]],
                        },
                        timestamp=datetime.now(UTC).isoformat(),
                    )
                    self._route_alert(alert)
                elif zombie_count > threshold and zombie_count > last_count:
                    alert = SystemAlert(
                        severity=AlertSeverity.WARNING,
                        alert_type="zombie",
                        message=f"{zombie_count} zombie processes detected",
                        details={
                            "count": zombie_count,
                            "zombies": [(z.get('pid'), z.get('name')) for z in zombies[:10]],
                        },
                        timestamp=datetime.now(UTC).isoformat(),
                    )
                    self._route_alert(alert)
                
                last_count = zombie_count
                
            except Exception as exc:
                LOGGER.error("Zombie monitor error: %s", exc)
                await asyncio.sleep(poll_interval)
    
    async def _disk_monitor(self) -> None:
        """Monitor disk space."""
        if not PSUTIL_AVAILABLE:
            return
        
        last_free: Dict[str, float] = {}
        poll_interval = 60  # Check every minute
        threshold = self.memory.get_pref("disk_threshold_pct", 20.0)
        critical = self.memory.get_pref("disk_critical_pct", 5.0)
        
        while self._running:
            try:
                await asyncio.sleep(poll_interval)
                if not self._running:
                    break
                
                for part in psutil.disk_partitions():
                    try:
                        # Skip loop devices (snap packages, etc.) - they're not real disks
                        if part.device.startswith('/dev/loop'):
                            continue
                        
                        usage = psutil.disk_usage(part.mountpoint)
                        free_pct = (usage.free / usage.total) * 100
                        used_pct = 100 - free_pct
                        free_gb = usage.free / (1024**3)
                        
                        # Only alert on state change (crossing threshold)
                        if free_pct < critical and free_pct < last_free.get(part.device, 100):
                            alert = SystemAlert(
                                severity=AlertSeverity.CRITICAL,
                                alert_type="disk",
                                message=f"Disk {part.device} critical: {used_pct:.1f}% full ({free_gb:.1f}GB free)",
                                details={
                                    "device": part.device,
                                    "mountpoint": part.mountpoint,
                                    "used_pct": used_pct,
                                    "free_pct": free_pct,
                                    "free_gb": free_gb,
                                    "total_gb": usage.total / (1024**3),
                                },
                                timestamp=datetime.now(UTC).isoformat(),
                            )
                            self._route_alert(alert, device=part.device)
                        elif free_pct < threshold and free_pct < last_free.get(part.device, 100):
                            alert = SystemAlert(
                                severity=AlertSeverity.WARNING,
                                alert_type="disk",
                                message=f"Disk {part.device} low: {used_pct:.1f}% full ({free_gb:.1f}GB free)",
                                details={
                                    "device": part.device,
                                    "mountpoint": part.mountpoint,
                                    "used_pct": used_pct,
                                    "free_pct": free_pct,
                                    "free_gb": free_gb,
                                    "total_gb": usage.total / (1024**3),
                                },
                                timestamp=datetime.now(UTC).isoformat(),
                            )
                            self._route_alert(alert, device=part.device)
                        
                        last_free[part.device] = free_pct
                        
                    except PermissionError:
                        # Skip inaccessible mount points
                        pass
                    except Exception as exc:
                        LOGGER.debug("Disk monitor error for %s: %s", part.device, exc)
                        
            except Exception as exc:
                LOGGER.error("Disk monitor error: %s", exc)
                await asyncio.sleep(poll_interval)
    
    async def _network_monitor(self) -> None:
        """Monitor network connections for suspicious activity."""
        if not PSUTIL_AVAILABLE:
            return
        
        known_conns: set = set()
        last_alert_count = 0
        poll_interval = self.memory.get_pref("monitor_poll_interval_s", 30)
        
        while self._running:
            try:
                await asyncio.sleep(poll_interval)
                if not self._running:
                    break
                
                conns = psutil.net_connections(kind='inet')
                established = [c for c in conns if c.status == 'ESTABLISHED']
                new_conns = [
                    c for c in established
                    if (c.laddr, c.raddr) not in known_conns
                ]
                
                new_count = len(new_conns)
                
                # Only alert if new connection count increased (state change)
                # Reset last_alert_count if count drops below threshold
                if new_count <= 10:
                    last_alert_count = 0
                elif new_count > last_alert_count:
                    alert = SystemAlert(
                        severity=AlertSeverity.WARNING,
                        alert_type="network",
                        message=f"{new_count} new network connections detected",
                        details={
                            "new_connections": [
                                {
                                    "local": f"{c.laddr.ip}:{c.laddr.port}",
                                    "remote": f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else None,
                                }
                                for c in new_conns[:10]
                            ],
                        },
                        timestamp=datetime.now(UTC).isoformat(),
                    )
                    self._route_alert(alert)
                    last_alert_count = new_count
                
                # Update known connections
                known_conns = {(c.laddr, c.raddr) for c in established if c.raddr}
                
            except Exception as exc:
                LOGGER.error("Network monitor error: %s", exc)
                await asyncio.sleep(poll_interval)
    
    async def _log_monitor(self) -> None:
        """Monitor system logs for anomalies."""
        poll_interval = self.memory.get_pref("monitor_poll_interval_s", 30)
        last_timestamp = 0.0
        
        # Try systemd journal first
        if SYSTEMD_JOURNAL_AVAILABLE:
            try:
                j = journal.Reader()
                j.add_match("PRIORITY=3")  # Errors/criticals
                j.seek_tail()
                
                while self._running:
                    try:
                        await asyncio.sleep(poll_interval)
                        if not self._running:
                            break
                        
                        for entry in j:
                            ts = entry.get('__REALTIME_TIMESTAMP', 0)
                            if ts <= last_timestamp:
                                break
                            
                            msg = entry.get('MESSAGE', '')
                            if re.search(r'Failed password|segfault|OOM|Out of memory', msg, re.IGNORECASE):
                                alert = SystemAlert(
                                    severity=AlertSeverity.WARNING,
                                    alert_type="log",
                                    message=f"Log anomaly detected: {msg[:100]}",
                                    details={
                                        "message": msg,
                                        "priority": entry.get('PRIORITY'),
                                        "unit": entry.get('_SYSTEMD_UNIT'),
                                    },
                                    timestamp=datetime.now(UTC).isoformat(),
                                )
                                self._route_alert(alert)
                            
                            last_timestamp = ts
                            
                    except Exception as exc:
                        LOGGER.debug("Journal monitor error: %s", exc)
                        await asyncio.sleep(poll_interval)
                
                return
            except Exception as exc:
                LOGGER.debug("Systemd journal unavailable: %s", exc)
        
        # Fallback: tail syslog
        syslog_path = Path("/var/log/syslog")
        if not syslog_path.exists():
            return
        
        while self._running:
            try:
                await asyncio.sleep(poll_interval)
                if not self._running:
                    break
                
                # Simple tail - read last 100 lines
                try:
                    with open(syslog_path, 'r') as f:
                        lines = f.readlines()
                        for line in lines[-100:]:
                            if re.search(r'error|failed|segfault|OOM', line, re.IGNORECASE):
                                alert = SystemAlert(
                                    severity=AlertSeverity.INFO,
                                    alert_type="log",
                                    message=f"Log entry: {line.strip()[:100]}",
                                    details={"log_line": line.strip()},
                                    timestamp=datetime.now(UTC).isoformat(),
                                )
                                self._route_alert(alert)
                                break  # One alert per poll
                except PermissionError:
                    LOGGER.debug("No permission to read syslog")
                    break
                    
            except Exception as exc:
                LOGGER.error("Log monitor error: %s", exc)
                await asyncio.sleep(poll_interval)

