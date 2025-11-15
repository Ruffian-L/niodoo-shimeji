"""systemd.journal monitoring for proactive system maintenance."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

LOGGER = logging.getLogger(__name__)

# Optional dependency
SYSTEMD_JOURNAL_AVAILABLE = False
try:
    import systemd.journal
    SYSTEMD_JOURNAL_AVAILABLE = True
except ImportError:
    LOGGER.debug("systemd.journal not available; journal monitoring disabled")


class JournalMonitor:
    """Async monitor for systemd journal events."""
    
    def __init__(self, event_bus: Optional[Any] = None) -> None:
        """Initialize journal monitor.
        
        Args:
            event_bus: Event bus to publish journal events to
        """
        self._event_bus = event_bus
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._reader: Optional[Any] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    async def start(self) -> None:
        """Start monitoring journal."""
        if self._running:
            return
        
        if not SYSTEMD_JOURNAL_AVAILABLE:
            LOGGER.warning("systemd.journal not available; journal monitoring disabled")
            return
        
        self._running = True
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.create_task(self._monitor_loop())
    
    async def stop(self) -> None:
        """Stop monitoring journal."""
        self._running = False
        if self._task:
            self._task.cancel()
            from contextlib import suppress
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        
        if self._reader:
            try:
                self._reader.close()
            except Exception:
                pass
            self._reader = None
    
    async def _monitor_loop(self) -> None:
        """Main monitoring loop using async file descriptor."""
        if not SYSTEMD_JOURNAL_AVAILABLE:
            return
        
        try:
            import systemd.journal
            
            # Create journal reader
            self._reader = systemd.journal.Reader()
            self._reader.log_level(systemd.journal.LOG_INFO)  # INFO and above
            self._reader.seek_tail()  # Start from end
            
            # Get file descriptor for async monitoring
            fd = self._reader.fileno()
            
            # Add reader to event loop
            self._loop.add_reader(fd, self._journal_callback)
            
            LOGGER.info("Journal monitor started")
            
            # Keep running until stopped
            while self._running:
                await asyncio.sleep(1.0)
            
        except Exception as exc:
            LOGGER.error("Journal monitor error: %s", exc)
            self._running = False
        finally:
            if self._reader and self._loop:
                try:
                    self._loop.remove_reader(self._reader.fileno())
                except Exception:
                    pass
    
    def _journal_callback(self) -> None:
        """Callback for journal events (called from event loop)."""
        if not self._reader or not self._running:
            return
        
        try:
            import systemd.journal
            from modules.event_bus import EventType
            
            # Process new journal entries
            self._reader.process()
            
            for entry in self._reader:
                # Extract relevant information
                priority = entry.get("PRIORITY", "6")  # Default to INFO
                message = entry.get("MESSAGE", "")
                syslog_identifier = entry.get("SYSLOG_IDENTIFIER", "")
                
                # Convert priority to severity
                priority_int = int(priority) if priority.isdigit() else 6
                if priority_int <= 3:  # ERR, CRIT, ALERT, EMERG
                    severity = "CRITICAL"
                elif priority_int == 4:  # WARNING
                    severity = "WARNING"
                else:
                    severity = "INFO"
                
                # Only publish CRITICAL and WARNING events
                if severity in ("CRITICAL", "WARNING"):
                    if self._event_bus:
                        self._event_bus.publish(
                            EventType.SYSTEM_ALERT,
                            {
                                "type": "journal",
                                "severity": severity,
                                "message": message,
                                "source": syslog_identifier,
                                "priority": priority_int,
                            }
                        )
                        LOGGER.debug("Journal event: %s - %s", severity, message[:100])
        
        except Exception as exc:
            LOGGER.error("Journal callback error: %s", exc)

