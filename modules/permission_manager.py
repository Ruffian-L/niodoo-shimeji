"""Granular permission system for agent actions and tool usage."""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import threading
from enum import Enum
from functools import partial
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TypeVar

LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


class PermissionScope(Enum):
    """Permission scopes for agent actions."""
    TOOL_BASH_RUN = "tool.bash.run"
    TOOL_FILE_READ_ALL = "tool.file.read_all"
    TOOL_FILE_WRITE_SANDBOX = "tool.file.write_sandbox"
    CONTEXT_VISION_READ_SCREEN = "context.vision.read_screen"
    CONTEXT_ATSPI_READ_APPS = "context.atspi.read_apps"
    CONTEXT_ATSPI_CONTROL_APPS = "context.atspi.control_apps"
    TOOL_CLIPBOARD_READ = "tool.clipboard.read"


class PermissionStatus(Enum):
    """Permission status values."""
    ASK = "ask"  # Ask user each time
    ALLOW = "allow"  # Always allow
    DENY = "deny"  # Always deny


class PermissionManager:
    """Manages granular permissions for agent actions."""
    
    def __init__(self, db_path: Optional[Path] = None) -> None:
        """Initialize permission manager with SQLite backend.
        
        Args:
            db_path: Optional path to SQLite database. If None, uses memory_manager database.
        """
        # Use same database as memory manager for consistency
        default_dir = Path(os.getenv("SHIMEJI_STATE_DIR", Path.cwd() / "var"))
        default_dir.mkdir(parents=True, exist_ok=True)
        if db_path is None:
            db_path = default_dir / "shimeji_memory.db"
        
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = sqlite3.connect(
            str(db_path), check_same_thread=False
        )
        if self._conn:
            self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._initialize()
    
    def _initialize(self) -> None:
        """Initialize permissions table in database."""
        if not self._conn:
            return
        
        with self._lock:
            with self._conn:
                self._conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS permissions (
                        agent_id TEXT NOT NULL,
                        scope TEXT NOT NULL,
                        status TEXT NOT NULL CHECK(status IN ('ask', 'allow', 'deny')),
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (agent_id, scope)
                    )
                    """
                )

    @staticmethod
    async def _run_in_executor(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute a blocking permission query/update outside the event loop."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))
    
    def check_permission(
        self, 
        agent_id: str, 
        scope: PermissionScope | str,
        default: PermissionStatus = PermissionStatus.ASK
    ) -> PermissionStatus:
        """Check if an agent has permission for a scope.
        
        Args:
            agent_id: Identifier for the agent (e.g., 'ProactiveBrain', 'DeveloperAgent')
            scope: Permission scope to check
            default: Default status if no permission record exists
            
        Returns:
            PermissionStatus indicating current permission state
        """
        if not self._conn:
            return default
        
        scope_str = scope.value if isinstance(scope, PermissionScope) else scope
        
        with self._lock:
            cursor = self._conn.execute(
                "SELECT status FROM permissions WHERE agent_id = ? AND scope = ?",
                (agent_id, scope_str)
            )
            row = cursor.fetchone()

        
        if row:
            try:
                return PermissionStatus(row["status"])
            except ValueError:
                LOGGER.warning("Invalid permission status in database: %s", row["status"])
                return default
        
        return default

    async def check_permission_async(
        self,
        agent_id: str,
        scope: PermissionScope | str,
        default: PermissionStatus = PermissionStatus.ASK
    ) -> PermissionStatus:
        """Async wrapper for :meth:`check_permission`."""
        return await self._run_in_executor(self.check_permission, agent_id, scope, default)
    
    def set_permission(
        self,
        agent_id: str,
        scope: PermissionScope | str,
        status: PermissionStatus
    ) -> None:
        """Set permission for an agent and scope.
        
        Args:
            agent_id: Identifier for the agent
            scope: Permission scope
            status: New permission status
        """
        if not self._conn:
            return
        
        from datetime import UTC, datetime
        
        scope_str = scope.value if isinstance(scope, PermissionScope) else scope
        status_str = status.value
        
        with self._lock:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO permissions(agent_id, scope, status, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(agent_id, scope) DO UPDATE SET
                        status = ?,
                        updated_at = ?
                    """,
                    (
                        agent_id,
                        scope_str,
                        status_str,
                        datetime.now(UTC).isoformat(),
                        status_str,
                        datetime.now(UTC).isoformat(),
                    )
                )
        LOGGER.info("Permission updated: %s.%s = %s", agent_id, scope_str, status_str)

    async def set_permission_async(
        self,
        agent_id: str,
        scope: PermissionScope | str,
        status: PermissionStatus
    ) -> None:
        """Async wrapper for :meth:`set_permission`."""
        await self._run_in_executor(self.set_permission, agent_id, scope, status)
    
    def get_all_permissions(self, agent_id: Optional[str] = None) -> Dict[str, Dict[str, str]]:
        """Get all permissions, optionally filtered by agent_id.
        
        Args:
            agent_id: Optional agent ID to filter by
            
        Returns:
            Dictionary mapping agent_id -> {scope: status}
        """
        if not self._conn:
            return {}
        
        with self._lock:
            if agent_id:
                cursor = self._conn.execute(
                    "SELECT scope, status FROM permissions WHERE agent_id = ?",
                    (agent_id,)
                )
            else:
                cursor = self._conn.execute(
                    "SELECT agent_id, scope, status FROM permissions"
                )
            
            result: Dict[str, Dict[str, str]] = {}
            for row in cursor.fetchall():
                if agent_id:
                    # Single agent query
                    if agent_id not in result:
                        result[agent_id] = {}
                    result[agent_id][row["scope"]] = row["status"]
                else:
                    # All agents query
                    aid = row["agent_id"]
                    if aid not in result:
                        result[aid] = {}
                    result[aid][row["scope"]] = row["status"]
        
        return result

    async def get_all_permissions_async(self, agent_id: Optional[str] = None) -> Dict[str, Dict[str, str]]:
        """Async wrapper for :meth:`get_all_permissions`."""
        return await self._run_in_executor(self.get_all_permissions, agent_id)
    
    def revoke_permission(self, agent_id: str, scope: PermissionScope | str) -> None:
        """Revoke (delete) a permission, causing it to default to ASK.
        
        Args:
            agent_id: Identifier for the agent
            scope: Permission scope to revoke
        """
        if not self._conn:
            return
        
        scope_str = scope.value if isinstance(scope, PermissionScope) else scope
        
        with self._lock:
            with self._conn:
                self._conn.execute(
                    "DELETE FROM permissions WHERE agent_id = ? AND scope = ?",
                    (agent_id, scope_str)
                )
        LOGGER.info("Permission revoked: %s.%s", agent_id, scope_str)

    async def revoke_permission_async(self, agent_id: str, scope: PermissionScope | str) -> None:
        """Async wrapper for :meth:`revoke_permission`."""
        await self._run_in_executor(self.revoke_permission, agent_id, scope)
    
    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            with self._lock:
                self._conn.close()
                self._conn = None

    def __enter__(self) -> "PermissionManager":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:  # pragma: no cover - defensive cleanup
        try:
            self.close()
        except Exception:
            pass

