"""Hybrid working and episodic memory utilities for the AI agent."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Deque, Dict, Iterable, List, Optional


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class WorkingMemory:
    capacity: int = 20
    observations: Deque[str] = field(init=False)
    actions: Deque[str] = field(init=False)

    def __post_init__(self) -> None:
        self.observations = deque(maxlen=self.capacity)
        self.actions = deque(maxlen=self.capacity)

    def record_observation(self, context: Dict[str, object]) -> None:
        serialised = json.dumps(context, ensure_ascii=False)
        self.observations.appendleft(f"{_timestamp()} | {serialised}")

    def record_action(self, action_summary: str) -> None:
        self.actions.appendleft(f"{_timestamp()} | {action_summary}")

    def recent_observations(self, limit: int = 5) -> List[str]:
        return list(list(self.observations)[:limit])

    def recent_actions(self, limit: int = 5) -> List[str]:
        return list(list(self.actions)[:limit])


class EpisodicMemory:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        default_dir = Path(os.getenv("SHIMEJI_STATE_DIR", Path.cwd() / "var"))
        default_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path or (default_dir / "shimeji_memory.db")
        self._conn: Optional[sqlite3.Connection] = sqlite3.connect(self.db_path, check_same_thread=False)
        if self._conn:
            self._conn.row_factory = sqlite3.Row
        self._initialise()

    def _initialise(self) -> None:
        if not self._conn:
            return
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    fact TEXT NOT NULL,
                    metadata TEXT
                )
                """
            )
            # Create user preferences table
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_prefs (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            # Create user model table (P3.1)
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_model (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            # Create event log table (P3.2)
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS event_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    data TEXT
                )
                """
            )
            # Create potential workflow table (P3.2)
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS potential_workflow (
                    pattern_sequence TEXT PRIMARY KEY,
                    count INTEGER NOT NULL,
                    last_seen TEXT NOT NULL
                )
                """
            )
            # Initialize default preferences if table is empty
            self._init_default_preferences()

    def add(self, fact: str, metadata: Optional[Dict[str, object]] = None) -> None:
        if not self._conn:
            return
        fact = fact.strip()
        if not fact:
            return
        meta = json.dumps(metadata, ensure_ascii=False) if metadata else None
        with self._conn:
            self._conn.execute(
                "INSERT INTO episodes(timestamp, fact, metadata) VALUES (?, ?, ?)",
                (_timestamp(), fact, meta),
            )

    def recent(self, limit: int = 5) -> List[Dict[str, str]]:
        if not self._conn:
            return []
        cursor = self._conn.execute(
            "SELECT timestamp, fact, metadata FROM episodes ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def search(self, query: str, limit: int = 5) -> List[Dict[str, str]]:
        if not self._conn:
            return []
        if not query:
            return self.recent(limit)

        tokens = [token.lower() for token in re.findall(r"\w+", query) if len(token) > 2]
        cursor = self._conn.execute(
            "SELECT id, timestamp, fact, metadata FROM episodes ORDER BY id DESC LIMIT 200"
        )
        scored: List[tuple[int, Dict[str, str]]] = []
        for row in cursor.fetchall():
            fact_text = row["fact"].lower()
            score = sum(fact_text.count(token) for token in tokens) if tokens else 1
            if score > 0:
                scored.append(
                    (
                        score,
                        {
                            "timestamp": row["timestamp"],
                            "fact": row["fact"],
                            "metadata": row["metadata"],
                        },
                    )
                )
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[:limit]]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def cleanup_old_episodes(self, days_to_keep: int = 30) -> None:
        """Remove episodes older than N days."""
        if not self._conn:
            return
        cutoff = (datetime.now(UTC) - timedelta(days=days_to_keep)).isoformat()
        with self._conn:
            self._conn.execute(
                "DELETE FROM episodes WHERE timestamp < ?",
                (cutoff,)
            )
    
    def _init_default_preferences(self) -> None:
        """Initialize default monitoring preferences if they don't exist."""
        if not self._conn:
            return
        
        defaults = {
            "ram_threshold_pct": "85.0",
            "ram_critical_pct": "90.0",
            "gpu_mem_threshold_pct": "80.0",
            "gpu_temp_threshold_c": "85.0",
            "disk_threshold_pct": "20.0",
            "disk_critical_pct": "5.0",
            "zombie_threshold_count": "5",
            "zombie_critical_count": "10",
            "monitor_poll_interval_s": "30",
            "alert_rate_limit_minutes": "5",
            # Alert enable/disable flags (default: all enabled)
            "alert_enabled_ram": "true",
            "alert_enabled_gpu": "true",
            "alert_enabled_disk": "true",
            "alert_enabled_zombie": "true",
            "alert_enabled_network": "true",
            "alert_enabled_log": "true",
        }
        
        with self._conn:
            for key, value in defaults.items():
                cursor = self._conn.execute("SELECT key FROM user_prefs WHERE key = ?", (key,))
                if not cursor.fetchone():
                    self._conn.execute(
                        "INSERT INTO user_prefs(key, value, updated_at) VALUES (?, ?, ?)",
                        (key, value, _timestamp())
                    )
    
    def get_pref(self, key: str, default: Any = None) -> Any:
        """Get a user preference value.
        
        Args:
            key: Preference key
            default: Default value if key doesn't exist
            
        Returns:
            Preference value (auto-converted to int/float/bool if possible), or default
        """
        if not self._conn:
            return default
        
        cursor = self._conn.execute("SELECT value FROM user_prefs WHERE key = ?", (key,))
        row = cursor.fetchone()
        if not row:
            return default
        
        value = row[0]
        
        # Auto-convert types
        if isinstance(value, str):
            # Try int
            try:
                if '.' not in value:
                    return int(value)
            except ValueError:
                pass
            
            # Try float
            try:
                return float(value)
            except ValueError:
                pass
            
            # Try bool
            if value.lower() in ('true', 'false', '1', '0', 'yes', 'no'):
                return value.lower() in ('true', '1', 'yes')
        
        return value
    
    def set_pref(self, key: str, value: Any) -> None:
        """Set a user preference value.
        
        Args:
            key: Preference key
            value: Preference value (will be converted to string)
        """
        if not self._conn:
            return
        
        value_str = str(value)
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO user_prefs(key, value, updated_at) 
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?
                """,
                (key, value_str, _timestamp(), value_str, _timestamp())
            )
    
    def get_all_prefs(self) -> Dict[str, Any]:
        """Get all user preferences.
        
        Returns:
            Dictionary of all preferences with auto-converted types
        """
        if not self._conn:
            return {}
        
        cursor = self._conn.execute("SELECT key, value FROM user_prefs")
        prefs = {}
        for row in cursor.fetchall():
            key = row[0]
            value = row[1]
            prefs[key] = self.get_pref(key, value)
        
        return prefs


class MemoryManager:
    def __init__(self, working_capacity: int = 20, db_path: Optional[Path] = None) -> None:
        self.working = WorkingMemory(working_capacity)
        self.episodic = EpisodicMemory(db_path)

    def __enter__(self) -> "MemoryManager":
        return self

    def __exit__(self, exc_type: Optional[type], exc_val: Optional[Exception], exc_tb: Optional[object]) -> None:
        self.close()

    def record_observation(self, context: Dict[str, object]) -> None:
        self.working.record_observation(context)

    def record_action(self, action: str, args: Optional[Dict[str, object]] = None) -> None:
        if args:
            summary = f"{action} {json.dumps(args, ensure_ascii=False)}"
        else:
            summary = action
        self.working.record_action(summary)

    def save_fact(self, fact: str, metadata: Optional[Dict[str, object]] = None) -> None:
        self.episodic.add(fact, metadata)

    def recent_observations(self, limit: int = 5) -> List[str]:
        return self.working.recent_observations(limit)

    def recent_actions(self, limit: int = 5) -> List[str]:
        return self.working.recent_actions(limit)

    def recall_relevant(self, context: Dict[str, object], limit: int = 5) -> List[str]:
        summary_parts: List[str] = []
        for key in ("title", "application"):
            value = context.get(key)
            if isinstance(value, str):
                summary_parts.append(value)
        query = " ".join(summary_parts)
        results = self.episodic.search(query, limit)
        formatted: List[str] = []
        for row in results:
            fact = row["fact"]
            timestamp = row.get("timestamp", "")
            formatted.append(f"{timestamp}: {fact}")
        return formatted

    def close(self) -> None:
        if self.episodic:
            self.episodic.close()

    def cleanup_old_episodes(self, days_to_keep: int = 30) -> None:
        """Remove episodes older than N days."""
        if self.episodic:
            self.episodic.cleanup_old_episodes(days_to_keep)
    
    def get_pref(self, key: str, default: Any = None) -> Any:
        """Get a user preference value."""
        return self.episodic.get_pref(key, default)
    
    def set_pref(self, key: str, value: Any) -> None:
        """Set a user preference value."""
        self.episodic.set_pref(key, value)
    
    def get_all_prefs(self) -> Dict[str, Any]:
        """Get all user preferences."""
        return self.episodic.get_all_prefs()
    
    def get_vector_memory(self):
        """Get vector memory instance if available."""
        try:
            from modules.vector_memory import VectorMemory
            return VectorMemory()
        except ImportError:
            return None
    