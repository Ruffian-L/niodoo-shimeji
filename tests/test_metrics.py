"""Unit tests for metrics module."""

from unittest import TestCase

from modules.metrics import PerformanceMetrics


class TestPerformanceMetrics(TestCase):
    """Tests for PerformanceMetrics class."""

    def setUp(self):
        """Set up test fixtures."""
        self.metrics = PerformanceMetrics()

    def test_initial_state(self):
        """Test initial state of metrics."""
        stats = self.metrics.get_stats()
        assert stats["avg_api_time_ms"] == 0
        assert stats["avg_decision_time_ms"] == 0
        assert stats["total_context_updates"] == 0
        assert stats["total_errors"] == 0
        assert stats["api_call_count"] == 0
        assert stats["decision_count"] == 0

    def test_record_api_call(self):
        """Test recording API calls."""
        self.metrics.record_api_call(0.5)  # 500ms
        self.metrics.record_api_call(1.0)  # 1000ms

        stats = self.metrics.get_stats()
        assert stats["avg_api_time_ms"] == 750.0  # (500 + 1000) / 2
        assert stats["api_call_count"] == 2

    def test_record_decision(self):
        """Test recording decisions."""
        self.metrics.record_decision(0.2)  # 200ms
        self.metrics.record_decision(0.8)  # 800ms

        stats = self.metrics.get_stats()
        assert stats["avg_decision_time_ms"] == 500.0  # (200 + 800) / 2
        assert stats["decision_count"] == 2

    def test_record_context_update(self):
        """Test recording context updates."""
        self.metrics.record_context_update()
        self.metrics.record_context_update()

        stats = self.metrics.get_stats()
        assert stats["total_context_updates"] == 2

    def test_record_error(self):
        """Test recording errors."""
        self.metrics.record_error()
        self.metrics.record_error()
        self.metrics.record_error()

        stats = self.metrics.get_stats()
        assert stats["total_errors"] == 3

    def test_deque_maxlen(self):
        """Test that deques respect maxlen."""
        # Record more than maxlen (100) items
        for i in range(150):
            self.metrics.record_api_call(float(i))

        # Should only keep the last 100
        assert len(self.metrics.api_call_times) == 100
        assert self.metrics.api_call_times[0] == 50.0  # First should be 50 (150-100)
        assert self.metrics.api_call_times[-1] == 149.0  # Last should be 149