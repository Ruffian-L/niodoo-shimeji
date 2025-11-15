"""DBus integration for GNOME/KDE desktop notifications and media control."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, Optional

LOGGER = logging.getLogger(__name__)

# Try asyncdbus first (pure-Python, asyncio-native)
ASYNCDBUS_AVAILABLE = False
try:
    import asyncdbus
    ASYNCDBUS_AVAILABLE = True
except ImportError:
    LOGGER.debug("asyncdbus not available; trying pydbus fallback")

# Fallback to pydbus if asyncdbus not available
PYDBUS_AVAILABLE = False
if not ASYNCDBUS_AVAILABLE:
    try:
        import pydbus
        PYDBUS_AVAILABLE = True
    except ImportError:
        LOGGER.debug("pydbus not available; DBus integration disabled")


class DBusListener:
    """Async D-Bus listener for notifications and media state."""
    
    def __init__(self, event_bus: Optional[Any] = None) -> None:
        """Initialize D-Bus listener.
        
        Args:
            event_bus: Event bus to publish D-Bus events to
        """
        self._event_bus = event_bus
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._bus: Optional[Any] = None
        
        if ASYNCDBUS_AVAILABLE:
            self._use_asyncdbus = True
        elif PYDBUS_AVAILABLE:
            self._use_asyncdbus = False
        else:
            self._use_asyncdbus = False
            LOGGER.warning("No D-Bus library available; D-Bus integration disabled")
    
    async def start(self) -> None:
        """Start listening to D-Bus signals."""
        if self._running:
            return
        
        if not ASYNCDBUS_AVAILABLE and not PYDBUS_AVAILABLE:
            LOGGER.warning("D-Bus libraries not available; cannot start listener")
            return
        
        self._running = True
        
        if self._use_asyncdbus:
            self._task = asyncio.create_task(self._listen_asyncdbus())
        else:
            # Fallback to pydbus (synchronous, less ideal)
            LOGGER.warning("Using pydbus fallback (synchronous); consider installing asyncdbus")
            self._task = asyncio.create_task(self._listen_pydbus_fallback())
    
    async def stop(self) -> None:
        """Stop listening to D-Bus signals."""
        self._running = False
        if self._task:
            self._task.cancel()
            from contextlib import suppress
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
    
    async def _listen_asyncdbus(self) -> None:
        """Listen to D-Bus signals using asyncdbus."""
        try:
            from modules.event_bus import EventType
            
            async with asyncdbus.SessionBus() as bus:
                self._bus = bus
                
                # Subscribe to notification signals
                try:
                    notifications = await bus.get_proxy(
                        "org.freedesktop.Notifications",
                        "/org/freedesktop/Notifications"
                    )
                    
                    # Listen for NotificationClosed signal
                    notifications.on_notification_closed = self._on_notification_closed
                    
                    # Note: asyncdbus doesn't directly support signal subscriptions
                    # We'll need to poll or use a different approach
                    # For now, we'll query media state periodically
                    LOGGER.info("D-Bus notification service connected (asyncdbus)")
                except Exception as exc:
                    LOGGER.debug("D-Bus notification service not available: %s", exc)
                
                # Query MPRIS media players periodically
                while self._running:
                    try:
                        await self._query_mpris_media_state(bus)
                    except Exception as exc:
                        LOGGER.debug("MPRIS query failed: %s", exc)
                    
                    await asyncio.sleep(5.0)  # Poll every 5 seconds
                    
        except Exception as exc:
            LOGGER.error("D-Bus listener error: %s", exc)
            self._running = False
    
    async def _listen_pydbus_fallback(self) -> None:
        """Fallback listener using pydbus (synchronous, less ideal)."""
        try:
            import pydbus
            from modules.event_bus import EventType
            
            bus = pydbus.SessionBus()
            self._bus = bus
            
            # Try to get notification service
            try:
                notifications = bus.get(
                    "org.freedesktop.Notifications",
                    "/org/freedesktop/Notifications"
                )
                LOGGER.info("D-Bus notification service connected (pydbus fallback)")
            except Exception as exc:
                LOGGER.debug("D-Bus notification service not available: %s", exc)
            
            # Poll for media state
            while self._running:
                try:
                    # Query MPRIS in thread to avoid blocking
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, self._query_mpris_media_state_sync, bus)
                except Exception as exc:
                    LOGGER.debug("MPRIS query failed: %s", exc)
                
                await asyncio.sleep(5.0)
                
        except Exception as exc:
            LOGGER.error("D-Bus listener error: %s", exc)
            self._running = False
    
    async def _query_mpris_media_state(self, bus: Any) -> None:
        """Query MPRIS media player state (asyncdbus)."""
        try:
            from modules.event_bus import EventType
            
            # List MPRIS players
            # MPRIS players register under org.mpris.MediaPlayer2.*
            # We'll try common players
            players = ["spotify", "vlc", "firefox", "chromium"]
            
            for player_name in players:
                try:
                    service_name = f"org.mpris.MediaPlayer2.{player_name}"
                    player = await bus.get_proxy(service_name, "/org/mpris/MediaPlayer2")
                    
                    # Get playback status
                    playback_status = await player.get_async("org.mpris.MediaPlayer2.Player", "PlaybackStatus")
                    
                    if playback_status == "Playing":
                        # Get metadata
                        metadata = await player.get_async("org.mpris.MediaPlayer2.Player", "Metadata")
                        
                        if self._event_bus:
                            self._event_bus.publish(
                                EventType.DBUS_NOTIFICATION,
                                {
                                    "type": "media_playing",
                                    "player": player_name,
                                    "metadata": metadata,
                                }
                            )
                except Exception:
                    # Player not available, continue
                    continue
                    
        except Exception as exc:
            LOGGER.debug("MPRIS query error: %s", exc)
    
    def _query_mpris_media_state_sync(self, bus: Any) -> None:
        """Query MPRIS media player state (pydbus synchronous)."""
        try:
            import pydbus
            from modules.event_bus import EventType
            
            players = ["spotify", "vlc", "firefox", "chromium"]
            
            for player_name in players:
                try:
                    service_name = f"org.mpris.MediaPlayer2.{player_name}"
                    player = bus.get(service_name, "/org/mpris/MediaPlayer2")
                    
                    playback_status = player.PlaybackStatus
                    
                    if playback_status == "Playing":
                        metadata = player.Metadata
                        
                        if self._event_bus:
                            # Publish in thread-safe way
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                asyncio.create_task(
                                    self._publish_event_async(
                                        EventType.DBUS_NOTIFICATION,
                                        {
                                            "type": "media_playing",
                                            "player": player_name,
                                            "metadata": dict(metadata) if metadata else {},
                                        }
                                    )
                                )
                except Exception:
                    continue
                    
        except Exception as exc:
            LOGGER.debug("MPRIS query error: %s", exc)
    
    async def _publish_event_async(self, event_type: Any, data: Any) -> None:
        """Publish event asynchronously."""
        if self._event_bus:
            self._event_bus.publish(event_type, data)
    
    def _on_notification_closed(self, notification_id: int, reason: int) -> None:
        """Handle notification closed signal."""
        LOGGER.debug("Notification %d closed (reason: %d)", notification_id, reason)


class DBusIntegration:
    """Handles DBus communication for desktop notifications (legacy compatibility)."""
    
    def __init__(self) -> None:
        """Initialize DBus integration."""
        self._bus: Optional[Any] = None
        self._notification_proxy: Optional[Any] = None
        self._is_available = False
        
        if PYDBUS_AVAILABLE:
            self._connect()
    
    def _connect(self) -> None:
        """Connect to DBus session bus."""
        if not PYDBUS_AVAILABLE:
            return
        
        try:
            import pydbus
            self._bus = pydbus.SessionBus()
            
            # Try to get notification service (GNOME/KDE)
            try:
                self._notification_proxy = self._bus.get(
                    "org.freedesktop.Notifications",
                    "/org/freedesktop/Notifications"
                )
                self._is_available = True
                LOGGER.info("DBus notification service connected")
            except Exception as exc:
                LOGGER.debug("DBus notification service not available: %s", exc)
                self._notification_proxy = None
                
        except Exception as exc:
            LOGGER.warning("Failed to connect to DBus: %s", exc)
            self._bus = None
            self._is_available = False
    
    def is_available(self) -> bool:
        """Check if DBus integration is available.
        
        Returns:
            True if DBus is available
        """
        return self._is_available and self._notification_proxy is not None
    
    def send_notification(
        self,
        title: str,
        message: str,
        urgency: str = "normal",
        timeout: int = 5000,
    ) -> Optional[int]:
        """Send a desktop notification via DBus.
        
        Args:
            title: Notification title
            message: Notification message
            urgency: Urgency level ("low", "normal", "critical")
            timeout: Timeout in milliseconds (0 = server default, -1 = never expire)
        
        Returns:
            Notification ID or None if failed
        """
        if not self.is_available():
            # Fallback to notify-send
            return self._fallback_notification(title, message, urgency)
        
        try:
            # Map urgency string to DBus urgency level
            urgency_map = {
                "low": 0,
                "normal": 1,
                "critical": 2,
            }
            urgency_level = urgency_map.get(urgency.lower(), 1)
            
            # Call Notify method
            # Signature: (app_name, replaces_id, app_icon, summary, body, actions, hints, expire_timeout)
            notification_id = self._notification_proxy.Notify(
                "Shimeji",  # app_name
                0,  # replaces_id (0 = new notification)
                "",  # app_icon (empty = use default)
                title,  # summary
                message,  # body
                [],  # actions (empty list)
                {"urgency": urgency_level},  # hints
                timeout,  # expire_timeout
            )
            
            LOGGER.debug("Sent DBus notification: %s - %s", title, message)
            return notification_id
            
        except Exception as exc:
            LOGGER.error("Failed to send DBus notification: %s", exc)
            return self._fallback_notification(title, message, urgency)
    
    def _fallback_notification(
        self,
        title: str,
        message: str,
        urgency: str,
    ) -> Optional[int]:
        """Fallback to notify-send command."""
        try:
            import subprocess
            
            urgency_map = {
                "low": "low",
                "normal": "normal",
                "critical": "critical",
            }
            urgency_level = urgency_map.get(urgency.lower(), "normal")
            
            subprocess.run(
                [
                    "notify-send",
                    "-t", "5000",
                    "-u", urgency_level,
                    title,
                    message,
                ],
                check=False,
                timeout=2,
            )
            return 0  # Return dummy ID
        except Exception as exc:
            LOGGER.debug("Fallback notification failed: %s", exc)
            return None
    
    def close_notification(self, notification_id: int) -> bool:
        """Close a notification by ID.
        
        Args:
            notification_id: ID of notification to close
        
        Returns:
            True if successful
        """
        if not self.is_available():
            return False
        
        try:
            self._notification_proxy.CloseNotification(notification_id)
            return True
        except Exception as exc:
            LOGGER.debug("Failed to close notification: %s", exc)
            return False
