"""User model synthesis agent for building dynamic user profiles."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, Optional

LOGGER = logging.getLogger(__name__)


class SynthesisAgent:
    """Agent that synthesizes user behavior into a dynamic user model."""
    
    def __init__(
        self,
        memory_manager: Any,
        proactive_brain: Any,
        run_interval_hours: int = 24
    ) -> None:
        """Initialize synthesis agent.
        
        Args:
            memory_manager: Memory manager for accessing feedback and event logs
            proactive_brain: Proactive brain for Gemini API calls
            run_interval_hours: Hours between synthesis runs (default: 24)
        """
        self._memory = memory_manager
        self._brain = proactive_brain
        self._run_interval = run_interval_hours * 3600  # Convert to seconds
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
    
    async def start(self) -> None:
        """Start synthesis agent."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._synthesis_loop())
        LOGGER.info("Synthesis agent started")
    
    async def stop(self) -> None:
        """Stop synthesis agent."""
        self._running = False
        if self._task:
            self._task.cancel()
            from contextlib import suppress
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
    
    async def _synthesis_loop(self) -> None:
        """Main synthesis loop - runs periodically."""
        # Wait before first run (don't run immediately on startup)
        await asyncio.sleep(self._run_interval)
        
        while self._running:
            try:
                await self._synthesize_user_model()
            except Exception as exc:
                LOGGER.error("Synthesis error: %s", exc)
            
            # Wait for next interval
            await asyncio.sleep(self._run_interval)
    
    async def _synthesize_user_model(self) -> None:
        """Synthesize user model from recent behavior and feedback."""
        try:
            # Get feedback log from last 24 hours
            cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
            
            # Query episodic memory for recent feedback
            # Note: This assumes feedback is stored in episodic memory
            recent_episodes = self._memory.episodic.recent(limit=100)
            
            # Filter to last 24 hours
            recent_feedback = [
                ep for ep in recent_episodes
                if ep.get("timestamp", "") >= cutoff and "feedback" in ep.get("fact", "").lower()
            ]
            
            # Get current user model
            current_model = self._get_current_user_model()
            
            # Build prompt for Gemini
            feedback_summary = "\n".join([ep.get("fact", "") for ep in recent_feedback[:20]])
            
            prompt = (
                f"Here is a log of user behavior and explicit feedback from the last 24 hours:\n\n"
                f"{feedback_summary}\n\n"
                f"Current user profile:\n{json.dumps(current_model, indent=2)}\n\n"
                "Summarize this into a set of user preferences, goals, and habits. "
                "Update the existing user profile. Respond ONLY with valid JSON matching this structure:\n"
                "{\n"
                "  'preferred_apps': ['app1', 'app2'],\n"
                "  'habits': ['habit1', 'habit2'],\n"
                "  'preferences': {'key': 'value'}\n"
                "}"
            )
            
            # Call Gemini Pro for synthesis
            # Note: This would need to be adapted to use the actual brain API
            LOGGER.info("Synthesizing user model from %d feedback entries", len(recent_feedback))
            
            # Store updated model
            # For MVP, we'll just log it - full implementation would parse response and store
            LOGGER.debug("User model synthesis completed")
            
        except Exception as exc:
            LOGGER.error("User model synthesis failed: %s", exc)
    
    def _get_current_user_model(self) -> Dict[str, Any]:
        """Get current user model from database.
        
        Returns:
            Current user model dictionary
        """
        # Check if user_model table exists in episodic memory
        try:
            # Try to get from episodic memory database
            if hasattr(self._memory, 'episodic') and self._memory.episodic._conn:
                cursor = self._memory.episodic._conn.execute(
                    "SELECT value FROM user_model WHERE key = 'profile'"
                )
                row = cursor.fetchone()
                if row:
                    return json.loads(row[0])
        except Exception:
            pass
        
        # Return default model
        return {
            "preferred_apps": [],
            "habits": [],
            "preferences": {}
        }
    
    def _store_user_model(self, model: Dict[str, Any]) -> None:
        """Store user model in database.
        
        Args:
            model: User model dictionary to store
        """
        try:
            if hasattr(self._memory, 'episodic') and self._memory.episodic._conn:
                from datetime import UTC, datetime
                model_json = json.dumps(model, ensure_ascii=False)
                with self._memory.episodic._conn:
                    self._memory.episodic._conn.execute(
                        """
                        INSERT INTO user_model(key, value, updated_at)
                        VALUES ('profile', ?, ?)
                        ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?
                        """,
                        (model_json, datetime.now(UTC).isoformat(), model_json, datetime.now(UTC).isoformat())
                    )
        except Exception as exc:
            LOGGER.error("Failed to store user model: %s", exc)

