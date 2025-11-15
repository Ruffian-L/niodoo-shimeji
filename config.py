"""Centralized configuration management for the Shimeji agent."""

from __future__ import annotations

import os
from pathlib import Path

from modules.constants import (
    DEFAULT_ANCHOR_POLL_SECONDS,
    DEFAULT_BUBBLE_REPOSITION_INTERVAL_MS,
    DEFAULT_FLASH_MODEL,
    DEFAULT_LISTEN_HOST,
    DEFAULT_LISTEN_PORT,
    DEFAULT_PERSONALITY,
    DEFAULT_PROACTIVE_INTERVAL_SECONDS,
    DEFAULT_PRO_MODEL,
    DEFAULT_REACTION_INTERVAL_SECONDS,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
)

try:
    from pydantic import BaseModel, Field, validator
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    # Fallback to dataclass if pydantic not available
    from dataclasses import dataclass


if PYDANTIC_AVAILABLE:
    class AgentConfig(BaseModel):
        """Type-safe configuration for the dual-mode agent with validation."""
        
        flash_model: str = Field(default=DEFAULT_FLASH_MODEL)
        pro_model: str = Field(default=DEFAULT_PRO_MODEL)
        personality: str = Field(default=DEFAULT_PERSONALITY)
        proactive_interval: int = Field(default=DEFAULT_PROACTIVE_INTERVAL_SECONDS, ge=1, le=300)
        reaction_interval: int = Field(default=DEFAULT_REACTION_INTERVAL_SECONDS, ge=1, le=60)
        listen_host: str = Field(default=DEFAULT_LISTEN_HOST)
        listen_port: int = Field(default=DEFAULT_LISTEN_PORT, ge=1, le=65535)
        anchor_poll_interval: float = Field(default=DEFAULT_ANCHOR_POLL_SECONDS, ge=0.1, le=5.0)
        mascot_cache_ttl: float = Field(default=2.0, ge=0.0)
        bubble_reposition_interval_ms: int = Field(default=DEFAULT_BUBBLE_REPOSITION_INTERVAL_MS, ge=10, le=1000)
        request_timeout: float = Field(default=DEFAULT_REQUEST_TIMEOUT_SECONDS, ge=0.1, le=60.0)
        
        @validator("flash_model", "pro_model")
        def validate_model_name(cls, v):
            if not v.startswith("gemini-"):
                raise ValueError("Model name must start with 'gemini-'")
            return v
        
        @classmethod
        def from_env(cls) -> "AgentConfig":
            """Load configuration from environment variables."""
            return cls(
                flash_model=os.getenv("GEMINI_MODEL_NAME", DEFAULT_FLASH_MODEL),
                pro_model=os.getenv("GEMINI_PRO_MODEL", DEFAULT_PRO_MODEL),
                personality=os.getenv("SHIMEJI_PERSONALITY", DEFAULT_PERSONALITY),
                proactive_interval=int(
                    os.getenv("PROACTIVE_INTERVAL", str(DEFAULT_PROACTIVE_INTERVAL_SECONDS))
                ),
                reaction_interval=int(
                    os.getenv("REACTION_INTERVAL", str(DEFAULT_REACTION_INTERVAL_SECONDS))
                ),
                listen_host=os.getenv("CLI_HOST", DEFAULT_LISTEN_HOST),
                listen_port=int(os.getenv("CLI_PORT", DEFAULT_LISTEN_PORT)),
                anchor_poll_interval=max(
                    0.1,
                    float(os.getenv("SHIMEJI_ANCHOR_POLL", str(DEFAULT_ANCHOR_POLL_SECONDS))),
                ),
                mascot_cache_ttl=max(0.0, float(os.getenv("SHIMEJI_MASCOT_CACHE_TTL", "2.0"))),
                bubble_reposition_interval_ms=int(os.getenv("BUBBLE_REPOSITION_INTERVAL_MS", str(DEFAULT_BUBBLE_REPOSITION_INTERVAL_MS))),
                request_timeout=float(
                    os.getenv("SHIMEJI_REQUEST_TIMEOUT", str(DEFAULT_REQUEST_TIMEOUT_SECONDS))
                ),
            )
else:
    # Fallback to dataclass if pydantic not available
    @dataclass
    class AgentConfig:
        """Centralized configuration for the dual-mode agent."""
        
        flash_model: str
        pro_model: str
        personality: str
        proactive_interval: int
        reaction_interval: int
        listen_host: str
        listen_port: int
        anchor_poll_interval: float
        mascot_cache_ttl: float
        bubble_reposition_interval_ms: int
        request_timeout: float
        
        @classmethod
        def from_env(cls) -> "AgentConfig":
            """Load configuration from environment variables."""
            return cls(
                flash_model=os.getenv("GEMINI_MODEL_NAME", DEFAULT_FLASH_MODEL),
                pro_model=os.getenv("GEMINI_PRO_MODEL", DEFAULT_PRO_MODEL),
                personality=os.getenv("SHIMEJI_PERSONALITY", DEFAULT_PERSONALITY),
                proactive_interval=int(
                    os.getenv("PROACTIVE_INTERVAL", str(DEFAULT_PROACTIVE_INTERVAL_SECONDS))
                ),
                reaction_interval=int(
                    os.getenv("REACTION_INTERVAL", str(DEFAULT_REACTION_INTERVAL_SECONDS))
                ),
                listen_host=os.getenv("CLI_HOST", DEFAULT_LISTEN_HOST),
                listen_port=int(os.getenv("CLI_PORT", DEFAULT_LISTEN_PORT)),
                anchor_poll_interval=max(
                    0.1,
                    float(os.getenv("SHIMEJI_ANCHOR_POLL", str(DEFAULT_ANCHOR_POLL_SECONDS))),
                ),
                mascot_cache_ttl=max(0.0, float(os.getenv("SHIMEJI_MASCOT_CACHE_TTL", "2.0"))),
                bubble_reposition_interval_ms=int(os.getenv("BUBBLE_REPOSITION_INTERVAL_MS", str(DEFAULT_BUBBLE_REPOSITION_INTERVAL_MS))),
                request_timeout=float(
                    os.getenv("SHIMEJI_REQUEST_TIMEOUT", str(DEFAULT_REQUEST_TIMEOUT_SECONDS))
                ),
            )

