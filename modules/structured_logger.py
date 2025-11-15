"""Structured logging with JSON-formatted context for better observability."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, Dict, Optional

LOGGER = logging.getLogger(__name__)


class StructuredLogger:
    """Logger that emits JSON-formatted structured logs for better analysis."""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def log_decision(
        self,
        decision_action: str,
        decision_args: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log a proactive decision with context."""
        event = {
            "event": "proactive_decision",
            "action": decision_action,
            "args": decision_args,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if context:
            event["context_app"] = context.get("application")
            event["context_title"] = context.get("title")
            event["context_pid"] = context.get("pid")
        
        self.logger.info(json.dumps(event, ensure_ascii=False))
    
    def log_api_call(
        self,
        model: str,
        duration: float,
        tokens: Optional[int] = None,
        cached: bool = False,
    ) -> None:
        """Log a Gemini API call with timing and token information."""
        event = {
            "event": "gemini_api_call",
            "model": model,
            "duration_ms": round(duration * 1000, 2),
            "cached": cached,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if tokens is not None:
            event["tokens"] = tokens
        
        self.logger.info(json.dumps(event, ensure_ascii=False))
    
    def log_error(
        self,
        error_type: str,
        error_message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log an error with context."""
        event = {
            "event": "error",
            "error_type": error_type,
            "error_message": error_message,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if context:
            event["context"] = context
        
        self.logger.error(json.dumps(event, ensure_ascii=False))
    
    def log_mode_switch(
        self,
        from_mode: str,
        to_mode: str,
        reason: Optional[str] = None,
    ) -> None:
        """Log a mode switch event."""
        event = {
            "event": "mode_switch",
            "from_mode": from_mode,
            "to_mode": to_mode,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if reason:
            event["reason"] = reason
        
        self.logger.info(json.dumps(event, ensure_ascii=False))
    
    def log_behavior_change(
        self,
        behavior: str,
        mascot_id: Optional[int] = None,
    ) -> None:
        """Log a behavior change event."""
        event = {
            "event": "behavior_change",
            "behavior": behavior,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if mascot_id is not None:
            event["mascot_id"] = mascot_id
        
        self.logger.info(json.dumps(event, ensure_ascii=False))

