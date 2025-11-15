"""Workflow pattern recognition for detecting user behavior patterns."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional

LOGGER = logging.getLogger(__name__)


class WorkflowPatternRecognizer:
    """Recognizes repetitive user workflows from event logs."""
    
    def __init__(self, memory_manager: Any, event_bus: Optional[Any] = None) -> None:
        """Initialize workflow pattern recognizer.
        
        Args:
            memory_manager: Memory manager for accessing event logs
            event_bus: Event bus for publishing detected patterns
        """
        self._memory = memory_manager
        self._event_bus = event_bus
        self._running = False
        self._task: Optional[Any] = None
    
    async def start(self) -> None:
        """Start pattern recognition (runs nightly)."""
        if self._running:
            return
        
        self._running = True
        # Run pattern mining as a background task (nightly)
        self._task = asyncio.create_task(self._pattern_mining_loop())
        LOGGER.info("Workflow pattern recognizer started")
    
    async def stop(self) -> None:
        """Stop pattern recognition."""
        self._running = False
        if self._task:
            self._task.cancel()
            with asyncio.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
    
    async def _pattern_mining_loop(self) -> None:
        """Main pattern mining loop - runs nightly."""
        # Wait until midnight, then run daily
        while self._running:
            try:
                # Calculate seconds until next midnight
                now = datetime.now(UTC)
                next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                wait_seconds = (next_midnight - now).total_seconds()
                
                await asyncio.sleep(wait_seconds)
                
                if self._running:
                    await self._mine_patterns()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOGGER.error("Pattern mining loop error: %s", exc)
                await asyncio.sleep(3600)  # Wait 1 hour before retry
    
    async def _mine_patterns(self) -> None:
        """Mine patterns from event log."""
        try:
            if not hasattr(self._memory, 'episodic') or not self._memory.episodic._conn:
                return
            
            # Get events from last 30 days
            cutoff = (datetime.now(UTC) - timedelta(days=30)).isoformat()
            
            cursor = self._memory.episodic._conn.execute(
                "SELECT timestamp, event_type, data FROM event_log WHERE timestamp >= ? ORDER BY timestamp",
                (cutoff,)
            )
            events = [dict(row) for row in cursor.fetchall()]
            
            if len(events) < 5:
                LOGGER.debug("Not enough events for pattern mining")
                return
            
            # Find sequential patterns (simplified - full implementation would use more sophisticated algorithms)
            patterns = self._find_sequential_patterns(events)
            
            # Store patterns
            for pattern_seq, count in patterns.items():
                if count >= 5:  # Only store patterns seen 5+ times
                    self._store_pattern(pattern_seq, count)
                    LOGGER.info("Detected workflow pattern: %s (seen %d times)", pattern_seq, count)
                    
                    # Publish pattern detected event
                    if self._event_bus:
                        from modules.event_bus import EventType
                        self._event_bus.publish(
                            EventType.PATTERN_DETECTED,
                            {"pattern": pattern_seq, "count": count}
                        )
        
        except Exception as exc:
            LOGGER.error("Pattern mining failed: %s", exc)
    
    def _find_sequential_patterns(self, events: List[Dict[str, Any]]) -> Dict[str, int]:
        """Find sequential patterns in events.
        
        Args:
            events: List of event dictionaries
            
        Returns:
            Dictionary mapping pattern sequences to occurrence counts
        """
        patterns: Dict[str, int] = {}
        
        # Simple pattern: sequences of 3-5 consecutive events
        for i in range(len(events) - 2):
            # Try sequences of length 3, 4, 5
            for seq_len in [3, 4, 5]:
                if i + seq_len > len(events):
                    continue
                
                seq = events[i:i+seq_len]
                # Build pattern string from event types
                pattern_parts = []
                for event in seq:
                    event_type = event.get("event_type", "")
                    # Extract app name if available
                    data = event.get("data", "{}")
                    try:
                        data_dict = json.loads(data) if isinstance(data, str) else data
                        app = data_dict.get("application", "")
                        if app:
                            pattern_parts.append(f"{event_type}:{app}")
                        else:
                            pattern_parts.append(event_type)
                    except Exception:
                        pattern_parts.append(event_type)
                
                pattern_seq = " -> ".join(pattern_parts)
                patterns[pattern_seq] = patterns.get(pattern_seq, 0) + 1
        
        return patterns
    
    def _store_pattern(self, pattern_seq: str, count: int) -> None:
        """Store detected pattern in database.
        
        Args:
            pattern_seq: Pattern sequence string
            count: Occurrence count
        """
        try:
            if hasattr(self._memory, 'episodic') and self._memory.episodic._conn:
                with self._memory.episodic._conn:
                    self._memory.episodic._conn.execute(
                        """
                        INSERT INTO potential_workflow(pattern_sequence, count, last_seen)
                        VALUES (?, ?, ?)
                        ON CONFLICT(pattern_sequence) DO UPDATE SET
                            count = ?,
                            last_seen = ?
                        """,
                        (
                            pattern_seq,
                            count,
                            datetime.now(UTC).isoformat(),
                            count,
                            datetime.now(UTC).isoformat(),
                        )
                    )
        except Exception as exc:
            LOGGER.error("Failed to store pattern: %s", exc)
    
    def log_event(self, event_type: str, data: Any) -> None:
        """Log an event for pattern recognition.
        
        Args:
            event_type: Type of event (e.g., 'window_focus', 'tool_call_requested')
            data: Event data dictionary
        """
        try:
            if hasattr(self._memory, 'episodic') and self._memory.episodic._conn:
                data_json = json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else str(data)
                with self._memory.episodic._conn:
                    self._memory.episodic._conn.execute(
                        "INSERT INTO event_log(timestamp, event_type, data) VALUES (?, ?, ?)",
                        (datetime.now(UTC).isoformat(), event_type, data_json)
                    )
        except Exception as exc:
            LOGGER.debug("Failed to log event: %s", exc)

