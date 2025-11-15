"""Audio processing for ambient awareness."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

LOGGER = logging.getLogger(__name__)

# Optional dependencies
PYAUDIO_AVAILABLE = False
NUMPY_AVAILABLE = False

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    LOGGER.debug("pyaudio not available; audio processing disabled")

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    LOGGER.debug("numpy not available; audio analysis limited")


class AudioProcessor:
    """Processes ambient audio for awareness."""
    
    def __init__(
        self,
        sample_rate: int = 44100,
        chunk_size: int = 1024,
        sensitivity: float = 0.5,
    ) -> None:
        """Initialize audio processor.
        
        Args:
            sample_rate: Audio sample rate (default 44100)
            chunk_size: Size of audio chunks to process
            sensitivity: Sensitivity threshold (0.0-1.0) for detecting sounds
        """
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.sensitivity = sensitivity
        self._pyaudio_instance: Optional[Any] = None
        self._audio_stream: Optional[Any] = None
        self._is_monitoring = False
        self._monitoring_task: Optional[asyncio.Task] = None
        self._callback: Optional[Callable[[float, str], None]] = None
    
    def is_available(self) -> bool:
        """Check if audio processing is available.
        
        Returns:
            True if audio processing is available
        """
        return PYAUDIO_AVAILABLE
    
    def set_callback(self, callback: Callable[[float, str], None]) -> None:
        """Set callback for detected audio events.
        
        Args:
            callback: Function called with (volume, event_type)
        """
        self._callback = callback
    
    async def start_monitoring(self) -> None:
        """Start monitoring ambient audio."""
        if self._is_monitoring:
            return
        
        if not self.is_available():
            LOGGER.warning("Audio processing not available (missing pyaudio)")
            return
        
        self._is_monitoring = True
        self._monitoring_task = asyncio.create_task(self._monitor_loop())
    
    async def stop_monitoring(self) -> None:
        """Stop monitoring ambient audio."""
        self._is_monitoring = False
        
        if self._monitoring_task:
            await self._monitoring_task
            self._monitoring_task = None
        
        if self._audio_stream:
            try:
                self._audio_stream.stop_stream()
                self._audio_stream.close()
            except Exception:
                pass
            self._audio_stream = None
        
        if self._pyaudio_instance:
            try:
                self._pyaudio_instance.terminate()
            except Exception:
                pass
            self._pyaudio_instance = None
    
    async def _monitor_loop(self) -> None:
        """Main audio monitoring loop."""
        try:
            import pyaudio
            
            self._pyaudio_instance = pyaudio.PyAudio()
            self._audio_stream = self._pyaudio_instance.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size,
            )
            
            while self._is_monitoring:
                try:
                    data = self._audio_stream.read(self.chunk_size, exception_on_overflow=False)
                    
                    # Calculate volume
                    volume = self._calculate_volume(data)
                    
                    # Detect events based on volume
                    event_type = self._detect_event(volume)
                    
                    if event_type and self._callback:
                        loop = asyncio.get_event_loop()
                        loop.call_soon_threadsafe(self._callback, volume, event_type)
                    
                    await asyncio.sleep(0.1)  # Small delay
                    
                except Exception as exc:
                    LOGGER.debug("Error reading audio: %s", exc)
                    await asyncio.sleep(0.5)
                    
        except Exception as exc:
            LOGGER.error("Error in audio monitoring loop: %s", exc)
        finally:
            await self.stop_monitoring()
    
    def _calculate_volume(self, audio_data: bytes) -> float:
        """Calculate volume level from audio data.
        
        Args:
            audio_data: Raw audio bytes
        
        Returns:
            Volume level (0.0-1.0)
        """
        if not NUMPY_AVAILABLE:
            # Simple calculation without numpy
            max_val = max(abs(int.from_bytes(audio_data[i:i+2], byteorder='little', signed=True))
                         for i in range(0, len(audio_data)-1, 2))
            return min(1.0, max_val / 32768.0)
        
        try:
            import numpy as np
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            rms = np.sqrt(np.mean(audio_array**2))
            # Normalize to 0-1 range
            volume = min(1.0, rms / 32768.0)
            return volume
        except Exception as exc:
            LOGGER.debug("Error calculating volume: %s", exc)
            return 0.0
    
    def _detect_event(self, volume: float) -> Optional[str]:
        """Detect audio event type from volume.
        
        Args:
            volume: Current volume level
        
        Returns:
            Event type string or None
        """
        threshold = self.sensitivity
        
        if volume > threshold * 0.8:
            # High volume - could be notification, error beep, etc.
            if volume > threshold * 1.5:
                return "loud_sound"  # Very loud - might be error
            else:
                return "notification"  # Moderate - might be notification
        elif volume < threshold * 0.1:
            # Very quiet - silence detected
            return "silence"
        
        return None
    
    def is_monitoring(self) -> bool:
        """Check if currently monitoring.
        
        Returns:
            True if monitoring
        """
        return self._is_monitoring


