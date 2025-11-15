"""Vector-embedded semantic memory for advanced search."""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

LOGGER = logging.getLogger(__name__)

# Optional dependencies
SENTENCE_TRANSFORMERS_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    LOGGER.debug("sentence-transformers not available; vector search disabled")


class VectorMemory:
    """Manages vector embeddings for semantic memory search."""
    
    def __init__(self, db_path: Optional[Path] = None, model_name: str = "all-MiniLM-L6-v2") -> None:
        """Initialize vector memory.
        
        Args:
            db_path: Path to SQLite database (will use same as episodic memory if None)
            model_name: Name of sentence transformer model to use
        """
        if db_path is None:
            default_dir = Path(os.getenv("SHIMEJI_STATE_DIR", Path.cwd() / "var"))
            default_dir.mkdir(parents=True, exist_ok=True)
            db_path = default_dir / "shimeji_memory.db"
        
        self.db_path = db_path
        self.model_name = model_name
        self._model: Optional[Any] = None
        self._conn: Optional[sqlite3.Connection] = None
        
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            self._load_model()
            self._initialize_db()
        else:
            LOGGER.warning("sentence-transformers not available; vector search disabled")
    
    def _load_model(self) -> None:
        """Load sentence transformer model."""
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            return
        
        try:
            self._model = SentenceTransformer(self.model_name)
            LOGGER.info("Loaded sentence transformer model: %s", self.model_name)
        except Exception as exc:
            LOGGER.error("Failed to load sentence transformer model: %s", exc)
            self._model = None
    
    def _initialize_db(self) -> None:
        """Initialize database with embeddings table."""
        if not os.path.exists(self.db_path):
            return
        
        try:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            
            with self._conn:
                # Create embeddings table if it doesn't exist
                self._conn.execute("""
                    CREATE TABLE IF NOT EXISTS episode_embeddings (
                        episode_id INTEGER PRIMARY KEY,
                        embedding BLOB NOT NULL,
                        FOREIGN KEY (episode_id) REFERENCES episodes(id)
                    )
                """)
                
                # Create index for faster lookups
                self._conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_episode_embeddings_id 
                    ON episode_embeddings(episode_id)
                """)
        except Exception as exc:
            LOGGER.error("Failed to initialize vector memory database: %s", exc)
            self._conn = None
    
    def is_available(self) -> bool:
        """Check if vector memory is available.
        
        Returns:
            True if vector memory is available
        """
        return SENTENCE_TRANSFORMERS_AVAILABLE and self._model is not None and self._conn is not None
    
    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for text.
        
        Args:
            text: Text to embed
        
        Returns:
            Embedding vector or None if unavailable
        """
        if not self.is_available() or not text:
            return None
        
        try:
            embedding = self._model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        except Exception as exc:
            LOGGER.error("Error generating embedding: %s", exc)
            return None
    
    def store_embedding(self, episode_id: int, text: str) -> bool:
        """Store embedding for an episode.
        
        Args:
            episode_id: ID of the episode
            text: Text to embed and store
        
        Returns:
            True if successful
        """
        if not self.is_available():
            return False
        
        embedding = self.generate_embedding(text)
        if embedding is None:
            return False
        
        try:
            import pickle
            embedding_blob = pickle.dumps(embedding)
            
            with self._conn:
                self._conn.execute("""
                    INSERT OR REPLACE INTO episode_embeddings (episode_id, embedding)
                    VALUES (?, ?)
                """, (episode_id, embedding_blob))
            
            return True
        except Exception as exc:
            LOGGER.error("Error storing embedding: %s", exc)
            return False
    
    def semantic_search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Perform semantic search on stored embeddings.
        
        Args:
            query: Search query
            limit: Maximum number of results
        
        Returns:
            List of matching episodes with similarity scores
        """
        if not self.is_available():
            return []
        
        query_embedding = self.generate_embedding(query)
        if query_embedding is None:
            return []
        
        try:
            import pickle
            import numpy as np
            
            # Get all embeddings
            cursor = self._conn.execute("""
                SELECT e.id, e.timestamp, e.fact, e.metadata, ve.embedding
                FROM episodes e
                JOIN episode_embeddings ve ON e.id = ve.episode_id
                ORDER BY e.id DESC
                LIMIT 1000
            """)
            
            results = []
            query_vec = np.array(query_embedding)
            
            for row in cursor.fetchall():
                episode_id = row['id']
                embedding_blob = row['embedding']
                embedding = pickle.loads(embedding_blob)
                embedding_vec = np.array(embedding)
                
                # Calculate cosine similarity
                similarity = np.dot(query_vec, embedding_vec) / (
                    np.linalg.norm(query_vec) * np.linalg.norm(embedding_vec)
                )
                
                results.append({
                    'id': episode_id,
                    'timestamp': row['timestamp'],
                    'fact': row['fact'],
                    'metadata': row['metadata'],
                    'similarity': float(similarity),
                })
            
            # Sort by similarity and return top results
            results.sort(key=lambda x: x['similarity'], reverse=True)
            return results[:limit]
            
        except Exception as exc:
            LOGGER.error("Error performing semantic search: %s", exc)
            return []
    
    def update_episode_embeddings(self, episode_ids: Optional[List[int]] = None) -> int:
        """Update embeddings for episodes (batch operation).
        
        Args:
            episode_ids: List of episode IDs to update (None = all missing)
        
        Returns:
            Number of embeddings updated
        """
        if not self.is_available():
            return 0
        
        try:
            if episode_ids is None:
                # Find episodes without embeddings
                cursor = self._conn.execute("""
                    SELECT e.id, e.fact
                    FROM episodes e
                    LEFT JOIN episode_embeddings ve ON e.id = ve.episode_id
                    WHERE ve.episode_id IS NULL
                    ORDER BY e.id DESC
                    LIMIT 100
                """)
            else:
                # Get specific episodes
                placeholders = ','.join('?' * len(episode_ids))
                cursor = self._conn.execute(f"""
                    SELECT e.id, e.fact
                    FROM episodes e
                    WHERE e.id IN ({placeholders})
                """, episode_ids)
            
            updated = 0
            for row in cursor.fetchall():
                episode_id = row['id']
                fact = row['fact']
                
                if self.store_embedding(episode_id, fact):
                    updated += 1
            
            return updated
            
        except Exception as exc:
            LOGGER.error("Error updating episode embeddings: %s", exc)
            return 0
    
    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


