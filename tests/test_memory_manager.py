"""Unit tests for memory_manager module."""

import json
import tempfile
from pathlib import Path
from unittest import TestCase

from modules.memory_manager import EpisodicMemory, MemoryManager, WorkingMemory


class TestWorkingMemory(TestCase):
    """Tests for WorkingMemory class."""

    def test_working_memory_capacity(self):
        """Test that working memory respects capacity limits."""
        mem = WorkingMemory(capacity=5)
        for i in range(10):
            mem.record_observation({"test": i})
        assert len(mem.observations) == 5  # Should cap at 5

    def test_recent_observations(self):
        """Test recent observations retrieval."""
        mem = WorkingMemory(capacity=10)
        for i in range(5):
            mem.record_observation({"value": i})
        recent = mem.recent_observations(limit=3)
        assert len(recent) == 3

    def test_record_action(self):
        """Test action recording."""
        mem = WorkingMemory(capacity=10)
        mem.record_action("test_action")
        assert len(mem.actions) == 1


class TestEpisodicMemory(TestCase):
    """Tests for EpisodicMemory class."""

    def setUp(self):
        """Set up test database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_memory.db"
        self.episodic = EpisodicMemory(db_path=self.db_path)

    def tearDown(self):
        """Clean up test database."""
        self.episodic.close()

    def test_add_fact(self):
        """Test adding facts to episodic memory."""
        self.episodic.add("Test fact", {"key": "value"})
        recent = self.episodic.recent(limit=1)
        assert len(recent) == 1
        assert recent[0]["fact"] == "Test fact"

    def test_search(self):
        """Test searching episodic memory."""
        self.episodic.add("Python is a programming language")
        self.episodic.add("JavaScript is also a language")
        results = self.episodic.search("Python", limit=5)
        assert len(results) > 0
        assert "Python" in results[0]["fact"]

    def test_cleanup_old_episodes(self):
        """Test cleanup of old episodes."""
        self.episodic.add("Old fact")
        # Cleanup episodes older than 0 days (should remove all)
        self.episodic.cleanup_old_episodes(days_to_keep=0)
        recent = self.episodic.recent(limit=10)
        assert len(recent) == 0


class TestMemoryManager(TestCase):
    """Tests for MemoryManager class."""

    def setUp(self):
        """Set up test memory manager."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_memory.db"
        self.memory = MemoryManager(working_capacity=10, db_path=self.db_path)

    def tearDown(self):
        """Clean up test memory manager."""
        self.memory.close()

    def test_context_manager(self):
        """Test that MemoryManager works as context manager."""
        with MemoryManager(working_capacity=5, db_path=self.db_path) as mem:
            mem.record_observation({"test": "value"})
        # Should be closed after context exit

    def test_record_observation(self):
        """Test observation recording."""
        self.memory.record_observation({"app": "test"})
        recent = self.memory.recent_observations(limit=1)
        assert len(recent) == 1

    def test_save_fact(self):
        """Test fact saving."""
        self.memory.save_fact("Test fact", {"metadata": "value"})
        relevant = self.memory.recall_relevant({"application": "test"}, limit=1)
        assert len(relevant) > 0


