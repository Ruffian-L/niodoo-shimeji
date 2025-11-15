"""Pattern recognition and habit mining for user behavior."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional

LOGGER = logging.getLogger(__name__)

# Optional dependencies
PANDAS_AVAILABLE = False
SKLEARN_AVAILABLE = False

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    LOGGER.debug("pandas not available; pattern learning will be limited")

try:
    from sklearn.cluster import DBSCAN
    SKLEARN_AVAILABLE = True
except ImportError:
    LOGGER.debug("scikit-learn not available; clustering disabled")


class PatternLearner:
    """Learns patterns and habits from user behavior."""
    
    def __init__(self, memory_manager: Any) -> None:
        """Initialize pattern learner.
        
        Args:
            memory_manager: MemoryManager instance for accessing episodic memory
        """
        self.memory = memory_manager
    
    def detect_patterns(
        self,
        time_range_days: int = 7,
        pattern_type: str = "app_usage",
    ) -> List[Dict[str, Any]]:
        """Detect patterns in user behavior.
        
        Args:
            time_range_days: Number of days to analyze
            pattern_type: Type of pattern to detect ("app_usage", "time_based", "sequence")
        
        Returns:
            List of detected patterns
        """
        if not PANDAS_AVAILABLE:
            LOGGER.warning("pandas not available; pattern detection limited")
            return []
        
        try:
            # Get recent episodes
            episodes = self.memory.episodic.recent(limit=1000)
            
            if not episodes:
                return []
            
            # Convert to DataFrame
            df = pd.DataFrame(episodes)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Filter by time range
            cutoff = datetime.now(UTC) - timedelta(days=time_range_days)
            df = df[df['timestamp'] >= cutoff]
            
            if pattern_type == "app_usage":
                return self._detect_app_usage_patterns(df)
            elif pattern_type == "time_based":
                return self._detect_time_based_patterns(df)
            elif pattern_type == "sequence":
                return self._detect_sequence_patterns(df)
            else:
                LOGGER.warning("Unknown pattern type: %s", pattern_type)
                return []
                
        except Exception as exc:
            LOGGER.error("Error detecting patterns: %s", exc)
            return []
    
    def _detect_app_usage_patterns(self, df: Any) -> List[Dict[str, Any]]:
        """Detect application usage patterns."""
        patterns = []
        
        try:
            # Extract application names from facts/metadata
            app_counts = {}
            for _, row in df.iterrows():
                fact = row.get('fact', '')
                metadata = row.get('metadata', '')
                
                # Try to extract app name from fact or metadata
                if isinstance(metadata, str):
                    import json
                    try:
                        meta_dict = json.loads(metadata)
                        app = meta_dict.get('application', '')
                        if app and app != 'Unknown':
                            app_counts[app] = app_counts.get(app, 0) + 1
                    except (json.JSONDecodeError, TypeError):
                        pass
                
                # Also check fact text for app mentions
                if 'application' in fact.lower():
                    # Simple extraction - could be improved
                    for word in fact.split():
                        if word.isalnum() and len(word) > 2:
                            app_counts[word] = app_counts.get(word, 0) + 1
            
            # Find frequently used apps
            total = sum(app_counts.values())
            if total > 0:
                for app, count in sorted(app_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                    frequency = count / total
                    if frequency > 0.1:  # At least 10% of usage
                        patterns.append({
                            'type': 'app_usage',
                            'app': app,
                            'frequency': frequency,
                            'count': count,
                        })
        except Exception as exc:
            LOGGER.error("Error detecting app usage patterns: %s", exc)
        
        return patterns
    
    def _detect_time_based_patterns(self, df: Any) -> List[Dict[str, Any]]:
        """Detect time-based patterns (e.g., work hours)."""
        patterns = []
        
        try:
            # Extract hour of day
            df['hour'] = df['timestamp'].dt.hour
            df['day_of_week'] = df['timestamp'].dt.dayofweek
            
            # Find most active hours
            hour_counts = df['hour'].value_counts()
            if len(hour_counts) > 0:
                peak_hour = hour_counts.idxmax()
                peak_count = hour_counts.max()
                total = len(df)
                
                if peak_count / total > 0.15:  # At least 15% of activity
                    patterns.append({
                        'type': 'time_based',
                        'pattern': 'peak_hour',
                        'hour': int(peak_hour),
                        'frequency': peak_count / total,
                    })
            
            # Find most active day of week
            day_counts = df['day_of_week'].value_counts()
            if len(day_counts) > 0:
                peak_day = day_counts.idxmax()
                peak_count = day_counts.max()
                total = len(df)
                
                if peak_count / total > 0.2:  # At least 20% of activity
                    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                    patterns.append({
                        'type': 'time_based',
                        'pattern': 'peak_day',
                        'day': day_names[int(peak_day)],
                        'frequency': peak_count / total,
                    })
        except Exception as exc:
            LOGGER.error("Error detecting time-based patterns: %s", exc)
        
        return patterns
    
    def _detect_sequence_patterns(self, df: Any) -> List[Dict[str, Any]]:
        """Detect sequence patterns (e.g., app switching patterns)."""
        patterns = []
        
        try:
            # Extract sequences from metadata
            sequences = []
            prev_app = None
            
            for _, row in df.iterrows():
                metadata = row.get('metadata', '')
                if isinstance(metadata, str):
                    import json
                    try:
                        meta_dict = json.loads(metadata)
                        app = meta_dict.get('application', '')
                        if app and app != 'Unknown':
                            if prev_app and prev_app != app:
                                sequences.append((prev_app, app))
                            prev_app = app
                    except (json.JSONDecodeError, TypeError):
                        pass
            
            # Find frequent sequences
            if sequences:
                from collections import Counter
                seq_counts = Counter(sequences)
                total = len(sequences)
                
                for (app1, app2), count in seq_counts.most_common(5):
                    frequency = count / total
                    if frequency > 0.1:  # At least 10% of transitions
                        patterns.append({
                            'type': 'sequence',
                            'from_app': app1,
                            'to_app': app2,
                            'frequency': frequency,
                            'count': count,
                        })
        except Exception as exc:
            LOGGER.error("Error detecting sequence patterns: %s", exc)
        
        return patterns
    
    def mine_insights(self, time_range_days: int = 30) -> Dict[str, Any]:
        """Mine insights from user behavior patterns.
        
        Args:
            time_range_days: Number of days to analyze
        
        Returns:
            Dictionary of insights
        """
        insights = {
            'productivity_trends': [],
            'usage_patterns': [],
            'suggestions': [],
        }
        
        try:
            # Get patterns
            app_patterns = self.detect_patterns(time_range_days, "app_usage")
            time_patterns = self.detect_patterns(time_range_days, "time_based")
            
            insights['usage_patterns'] = app_patterns + time_patterns
            
            # Analyze productivity trends
            episodes = self.memory.episodic.recent(limit=1000)
            if PANDAS_AVAILABLE and episodes:
                df = pd.DataFrame(episodes)
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                
                cutoff = datetime.now(UTC) - timedelta(days=time_range_days)
                df = df[df['timestamp'] >= cutoff]
                
                # Group by day and count activity
                df['date'] = df['timestamp'].dt.date
                daily_counts = df.groupby('date').size()
                
                if len(daily_counts) > 7:
                    # Calculate trend
                    recent_avg = daily_counts.tail(7).mean()
                    older_avg = daily_counts.head(len(daily_counts) - 7).mean() if len(daily_counts) > 7 else recent_avg
                    
                    if recent_avg > older_avg * 1.2:
                        insights['productivity_trends'].append({
                            'type': 'increasing',
                            'message': 'Activity has increased recently',
                        })
                    elif recent_avg < older_avg * 0.8:
                        insights['productivity_trends'].append({
                            'type': 'decreasing',
                            'message': 'Activity has decreased recently',
                        })
            
            # Generate suggestions based on patterns
            for pattern in app_patterns:
                if pattern.get('frequency', 0) > 0.3:
                    insights['suggestions'].append({
                        'type': 'frequent_app',
                        'message': f"You frequently use {pattern.get('app')}. Consider creating shortcuts or automation.",
                    })
            
        except Exception as exc:
            LOGGER.error("Error mining insights: %s", exc)
        
        return insights


