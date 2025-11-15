"""Mouse gesture recognition for Shimeji interactions."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

LOGGER = logging.getLogger(__name__)


class GestureType(Enum):
    """Types of gestures that can be recognized."""
    CIRCLE = "circle"
    SWIPE_LEFT = "swipe_left"
    SWIPE_RIGHT = "swipe_right"
    SWIPE_UP = "swipe_up"
    SWIPE_DOWN = "swipe_down"
    UNKNOWN = "unknown"


@dataclass
class Gesture:
    """Represents a recognized gesture."""
    gesture_type: GestureType
    points: List[Tuple[float, float]]
    confidence: float


class GestureRecognizer:
    """Recognizes mouse gestures from a sequence of points."""
    
    def __init__(
        self,
        min_points: int = 10,
        circle_threshold: float = 0.7,
        swipe_threshold: float = 0.8,
    ) -> None:
        """Initialize gesture recognizer.
        
        Args:
            min_points: Minimum number of points to recognize a gesture
            circle_threshold: Minimum circularity score for circle detection (0-1)
            swipe_threshold: Minimum direction consistency for swipe detection (0-1)
        """
        self.min_points = min_points
        self.circle_threshold = circle_threshold
        self.swipe_threshold = swipe_threshold
        self._points: List[Tuple[float, float]] = []
        self._is_tracking = False
    
    def start_tracking(self) -> None:
        """Start tracking a new gesture."""
        self._points = []
        self._is_tracking = True
    
    def add_point(self, x: float, y: float) -> None:
        """Add a point to the current gesture.
        
        Args:
            x: X coordinate
            y: Y coordinate
        """
        if self._is_tracking:
            self._points.append((x, y))
    
    def stop_tracking(self) -> Optional[Gesture]:
        """Stop tracking and recognize the gesture.
        
        Returns:
            Recognized gesture or None if no valid gesture detected
        """
        if not self._is_tracking:
            return None
        
        self._is_tracking = False
        
        if len(self._points) < self.min_points:
            return None
        
        # Try to recognize different gesture types
        gesture = self._recognize_circle()
        if gesture:
            return gesture
        
        gesture = self._recognize_swipe()
        if gesture:
            return gesture
        
        return Gesture(
            gesture_type=GestureType.UNKNOWN,
            points=self._points.copy(),
            confidence=0.0
        )
    
    def _recognize_circle(self) -> Optional[Gesture]:
        """Recognize a circular gesture."""
        if len(self._points) < self.min_points:
            return None
        
        # Calculate center point
        center_x = sum(p[0] for p in self._points) / len(self._points)
        center_y = sum(p[1] for p in self._points) / len(self._points)
        
        # Calculate average radius
        radii = [
            math.sqrt((p[0] - center_x) ** 2 + (p[1] - center_y) ** 2)
            for p in self._points
        ]
        avg_radius = sum(radii) / len(radii)
        
        if avg_radius < 20:  # Too small to be a circle
            return None
        
        # Calculate circularity: how consistent the radius is
        radius_variance = sum((r - avg_radius) ** 2 for r in radii) / len(radii)
        radius_std = math.sqrt(radius_variance)
        circularity = 1.0 - min(1.0, radius_std / avg_radius) if avg_radius > 0 else 0.0
        
        if circularity >= self.circle_threshold:
            return Gesture(
                gesture_type=GestureType.CIRCLE,
                points=self._points.copy(),
                confidence=circularity
            )
        
        return None
    
    def _recognize_swipe(self) -> Optional[Gesture]:
        """Recognize a swipe gesture (left, right, up, down)."""
        if len(self._points) < self.min_points:
            return None
        
        # Calculate direction vectors
        directions = []
        for i in range(1, len(self._points)):
            dx = self._points[i][0] - self._points[i-1][0]
            dy = self._points[i][1] - self._points[i-1][1]
            directions.append((dx, dy))
        
        # Calculate overall direction
        total_dx = sum(d[0] for d in directions)
        total_dy = sum(d[1] for d in directions)
        
        # Calculate direction consistency
        avg_dx = total_dx / len(directions)
        avg_dy = total_dy / len(directions)
        avg_magnitude = math.sqrt(avg_dx ** 2 + avg_dy ** 2)
        
        if avg_magnitude < 10:  # Too small movement
            return None
        
        # Check consistency: how aligned are individual movements with overall direction
        consistent_count = 0
        for dx, dy in directions:
            dot_product = dx * avg_dx + dy * avg_dy
            magnitude = math.sqrt(dx ** 2 + dy ** 2)
            if magnitude > 0:
                cos_angle = dot_product / (magnitude * avg_magnitude)
                if cos_angle > 0.7:  # Roughly same direction
                    consistent_count += 1
        
        consistency = consistent_count / len(directions)
        
        if consistency < self.swipe_threshold:
            return None
        
        # Determine swipe direction
        abs_dx = abs(avg_dx)
        abs_dy = abs(avg_dy)
        
        if abs_dx > abs_dy:
            # Horizontal swipe
            gesture_type = GestureType.SWIPE_LEFT if avg_dx < 0 else GestureType.SWIPE_RIGHT
        else:
            # Vertical swipe
            gesture_type = GestureType.SWIPE_UP if avg_dy < 0 else GestureType.SWIPE_DOWN
        
        return Gesture(
            gesture_type=gesture_type,
            points=self._points.copy(),
            confidence=consistency
        )
    
    def reset(self) -> None:
        """Reset the recognizer state."""
        self._points = []
        self._is_tracking = False


