"""Feedback-based learning for user preferences."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

LOGGER = logging.getLogger(__name__)

# Optional dependency
NUMPY_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    LOGGER.debug("numpy not available; feedback scoring will be limited")


class FeedbackLearner:
    """Learns user preferences from feedback."""
    
    def __init__(self, memory_manager: Any) -> None:
        """Initialize feedback learner.
        
        Args:
            memory_manager: MemoryManager instance
        """
        self.memory = memory_manager
        self._preference_scores: Dict[str, float] = {}
        self._load_preferences()
    
    def _load_preferences(self) -> None:
        """Load learned preferences from memory."""
        try:
            # Get all feedback from episodic memory
            episodes = self.memory.episodic.recent(limit=1000)
            
            for episode in episodes:
                fact = episode.get("fact", "")
                metadata = episode.get("metadata", "")
                
                # Check if this is feedback
                if "feedback:" in fact.lower():
                    # Parse feedback
                    import json
                    try:
                        if isinstance(metadata, str):
                            meta_dict = json.loads(metadata)
                        else:
                            meta_dict = metadata or {}
                        
                        action = meta_dict.get("action", "")
                        response = meta_dict.get("response", "")
                        
                        if action and response:
                            self._update_preference_score(action, response)
                    except (json.JSONDecodeError, TypeError, KeyError):
                        pass
        except Exception as exc:
            LOGGER.error("Error loading preferences: %s", exc)
    
    def record_feedback(
        self,
        action: str,
        user_response: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record user feedback on an action.
        
        Args:
            action: Action that was taken
            user_response: User response ("positive", "negative", "neutral", or specific feedback)
            context: Optional context dictionary
        """
        # Normalize response
        response_lower = user_response.lower()
        
        if "positive" in response_lower or "good" in response_lower or "yes" in response_lower or "like" in response_lower:
            score = 1.0
        elif "negative" in response_lower or "bad" in response_lower or "no" in response_lower or "dislike" in response_lower:
            score = -1.0
        elif "neutral" in response_lower or "ok" in response_lower:
            score = 0.0
        else:
            # Try to extract sentiment
            score = self._extract_sentiment(user_response)
        
        # Update preference score
        self._update_preference_score(action, score)
        
        # Store in episodic memory
        metadata = {
            "action": action,
            "response": user_response,
            "score": score,
            "context": context or {},
        }
        
        self.memory.save_fact(
            f"feedback: {action} - {user_response}",
            metadata=metadata,
        )
        
        LOGGER.info("Recorded feedback: %s -> %s (score: %.2f)", action, user_response, score)
    
    def _update_preference_score(self, action: str, response: Any) -> None:
        """Update preference score for an action.
        
        Args:
            action: Action name
            response: Response (float score or string)
        """
        # Convert response to score if needed
        if isinstance(response, (int, float)):
            score = float(response)
        elif isinstance(response, str):
            score = self._extract_sentiment(response)
        else:
            score = 0.0
        
        # Update score with exponential moving average
        current_score = self._preference_scores.get(action, 0.0)
        alpha = 0.3  # Learning rate
        new_score = current_score * (1 - alpha) + score * alpha
        self._preference_scores[action] = new_score
        
        # Store in memory preferences
        self.memory.set_pref(f"pref_score_{action}", new_score)
    
    def _extract_sentiment(self, text: str) -> float:
        """Extract sentiment score from text.
        
        Args:
            text: Text to analyze
        
        Returns:
            Sentiment score (-1.0 to 1.0)
        """
        text_lower = text.lower()
        
        # Simple keyword-based sentiment
        positive_words = ["good", "great", "excellent", "love", "like", "yes", "perfect", "awesome"]
        negative_words = ["bad", "terrible", "hate", "dislike", "no", "awful", "horrible"]
        
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        
        if positive_count > negative_count:
            return 0.5
        elif negative_count > positive_count:
            return -0.5
        else:
            return 0.0
    
    def get_preference_score(self, action: str) -> float:
        """Get preference score for an action.
        
        Args:
            action: Action name
        
        Returns:
            Preference score (-1.0 to 1.0)
        """
        # Try to get from cache
        if action in self._preference_scores:
            return self._preference_scores[action]
        
        # Try to get from memory
        score = self.memory.get_pref(f"pref_score_{action}", 0.0)
        self._preference_scores[action] = score
        return score
    
    def should_perform_action(self, action: str, threshold: float = 0.0) -> bool:
        """Check if an action should be performed based on preferences.
        
        Args:
            action: Action name
            threshold: Minimum score threshold (default 0.0 = neutral)
        
        Returns:
            True if action should be performed
        """
        score = self.get_preference_score(action)
        return score >= threshold
    
    def get_top_preferences(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top preferred actions.
        
        Args:
            limit: Maximum number of preferences to return
        
        Returns:
            List of preference dictionaries
        """
        preferences = [
            {"action": action, "score": score}
            for action, score in self._preference_scores.items()
        ]
        preferences.sort(key=lambda x: x["score"], reverse=True)
        return preferences[:limit]
    
    def get_bottom_preferences(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get least preferred actions.
        
        Args:
            limit: Maximum number of preferences to return
        
        Returns:
            List of preference dictionaries
        """
        preferences = [
            {"action": action, "score": score}
            for action, score in self._preference_scores.items()
        ]
        preferences.sort(key=lambda x: x["score"])
        return preferences[:limit]

