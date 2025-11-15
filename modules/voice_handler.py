"""Voice input/output handling for Shimeji."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Any, Optional, Callable

LOGGER = logging.getLogger(__name__)

# Optional dependencies
VOSK_AVAILABLE = False
PYAUDIO_AVAILABLE = False
PYTTSX3_AVAILABLE = False

try:
    import vosk
    VOSK_AVAILABLE = True
except ImportError:
    LOGGER.debug("vosk not available; voice recognition disabled")

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    LOGGER.debug("pyaudio not available; audio input disabled")

try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    LOGGER.debug("pyttsx3 not available; text-to-speech disabled")


class VoiceHandler:
    """Handles speech-to-text and text-to-speech."""
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        sample_rate: int = 16000,
        language: str = "en",
    ) -> None:
        """Initialize voice handler.
        
        Args:
            model_path: Path to Vosk model directory
            sample_rate: Audio sample rate (default 16000 for Vosk)
            language: Language code (default "en")
        """
        self.sample_rate = sample_rate
        self.language = language
        self._model: Optional[Any] = None
        self._recognizer: Optional[Any] = None
        self._audio_stream: Optional[Any] = None
        self._pyaudio_instance: Optional[Any] = None
        self._is_listening = False
        self._listening_task: Optional[asyncio.Task] = None
        self._callback: Optional[Callable[[str], None]] = None
        
        # Try to load Vosk model
        if VOSK_AVAILABLE and PYAUDIO_AVAILABLE:
            self._load_model(model_path)
    
    def _load_model(self, model_path: Optional[str] = None) -> None:
        """Load Vosk model."""
        if not VOSK_AVAILABLE:
            return
        
        try:
            if model_path is None:
                # Try to find model in common locations
                model_path = os.getenv("VOSK_MODEL_PATH")
                if not model_path or not os.path.exists(model_path):
                    # Try default locations
                    default_paths = [
                        os.path.expanduser("~/vosk-models"),
                        "/usr/share/vosk-models",
                        os.path.join(os.path.dirname(__file__), "..", "vosk-models"),
                    ]
                    for path in default_paths:
                        # Look for English model
                        for subdir in os.listdir(path) if os.path.exists(path) else []:
                            full_path = os.path.join(path, subdir)
                            if os.path.isdir(full_path) and "model-conf.json" in os.listdir(full_path):
                                model_path = full_path
                                break
                        if model_path:
                            break
            
            if model_path and os.path.exists(model_path):
                import vosk
                self._model = vosk.Model(model_path)
                self._recognizer = vosk.KaldiRecognizer(self._model, self.sample_rate)
                LOGGER.info("Vosk model loaded from %s", model_path)
            else:
                LOGGER.warning("Vosk model not found. Voice recognition disabled.")
                LOGGER.info("Download a model from: https://alphacephei.com/vosk/models")
        except Exception as exc:
            LOGGER.error("Failed to load Vosk model: %s", exc)
            self._model = None
            self._recognizer = None
    
    def set_callback(self, callback: Callable[[str], None]) -> None:
        """Set callback for recognized speech.
        
        Args:
            callback: Function to call with recognized text
        """
        self._callback = callback
    
    async def start_listening(self) -> None:
        """Start listening for voice input asynchronously."""
        if self._is_listening:
            return
        
        if not VOSK_AVAILABLE or not PYAUDIO_AVAILABLE:
            LOGGER.warning("Voice recognition not available (missing dependencies)")
            return
        
        if self._model is None or self._recognizer is None:
            LOGGER.warning("Vosk model not loaded")
            return
        
        self._is_listening = True
        self._listening_task = asyncio.create_task(self._listen_loop())
    
    async def stop_listening(self) -> None:
        """Stop listening for voice input."""
        self._is_listening = False
        if self._listening_task:
            await self._listening_task
            self._listening_task = None
        
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
    
    async def _listen_loop(self) -> None:
        """Main listening loop."""
        try:
            import pyaudio
            
            self._pyaudio_instance = pyaudio.PyAudio()
            self._audio_stream = self._pyaudio_instance.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=4000,
            )
            
            while self._is_listening:
                data = self._audio_stream.read(4000, exception_on_overflow=False)
                
                if self._recognizer.AcceptWaveform(data):
                    result = self._recognizer.Result()
                    import json
                    result_dict = json.loads(result)
                    text = result_dict.get("text", "").strip()
                    
                    if text and self._callback:
                        # Call callback in thread-safe way
                        loop = asyncio.get_event_loop()
                        loop.call_soon_threadsafe(self._callback, text)
                else:
                    # Partial result
                    partial = self._recognizer.PartialResult()
                    import json
                    partial_dict = json.loads(partial)
                    partial_text = partial_dict.get("partial", "").strip()
                    # Could emit partial results if needed
                
                await asyncio.sleep(0.1)  # Small delay to prevent CPU spinning
                
        except Exception as exc:
            LOGGER.error("Error in voice listening loop: %s", exc)
        finally:
            await self.stop_listening()
    
    def speak(self, text: str) -> None:
        """Convert text to speech (synchronous).
        
        Args:
            text: Text to speak
        """
        if not PYTTSX3_AVAILABLE:
            LOGGER.debug("Text-to-speech not available")
            return
        
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
        except Exception as exc:
            LOGGER.error("Text-to-speech error: %s", exc)
    
    async def speak_async(self, text: str) -> None:
        """Convert text to speech asynchronously.
        
        Args:
            text: Text to speak
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.speak, text)
    
    def is_available(self) -> bool:
        """Check if voice recognition is available.
        
        Returns:
            True if voice recognition is available
        """
        return VOSK_AVAILABLE and PYAUDIO_AVAILABLE and self._model is not None
    
    def is_listening(self) -> bool:
        """Check if currently listening.
        
        Returns:
            True if listening
        """
        return self._is_listening

