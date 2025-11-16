"""Selectable vector store backends for semantic memory."""

from __future__ import annotations

import logging
import os
import pickle
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

LOGGER = logging.getLogger(__name__)

try:  # Optional dependency
    from sentence_transformers import SentenceTransformer
    _SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    _SENTENCE_TRANSFORMERS_AVAILABLE = False

try:  # Optional dependency
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qmodels
    _QDRANT_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    _QDRANT_AVAILABLE = False
    QdrantClient = None  # type: ignore
    qmodels = None  # type: ignore


@dataclass(frozen=True)
class VectorStoreConfig:
    """Configuration used to instantiate a vector store backend."""

    backend: str = "sqlite"
    model_name: str = "all-MiniLM-L6-v2"
    db_path: Path = Path(os.getenv("SHIMEJI_STATE_DIR", Path.cwd() / "var")) / "shimeji_memory.db"
    qdrant_url: Optional[str] = None
    qdrant_api_key: Optional[str] = None
    qdrant_collection: str = "shimeji_episodes"

    @classmethod
    def from_env(cls) -> "VectorStoreConfig":
        backend = os.getenv("VECTOR_STORE_BACKEND", "sqlite").strip().lower()
        model_name = os.getenv("VECTOR_STORE_MODEL", "all-MiniLM-L6-v2")
        state_dir = Path(os.getenv("SHIMEJI_STATE_DIR", Path.cwd() / "var"))
        state_dir.mkdir(parents=True, exist_ok=True)
        db_path = Path(os.getenv("VECTOR_STORE_DB", state_dir / "shimeji_memory.db"))
        q_url = os.getenv("QDRANT_URL")
        q_key = os.getenv("QDRANT_API_KEY")
        collection = os.getenv("QDRANT_COLLECTION", "shimeji_episodes")
        return cls(
            backend=backend,
            model_name=model_name,
            db_path=Path(db_path),
            qdrant_url=q_url,
            qdrant_api_key=q_key,
            qdrant_collection=collection,
        )


class BaseVectorStore:
    """Common interface for vector storage implementations."""

    def is_available(self) -> bool:
        raise NotImplementedError

    def add_embedding(self, episode_id: int, text: str) -> bool:
        raise NotImplementedError

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def update_missing_embeddings(self, limit: int = 100) -> int:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class SQLiteVectorStore(BaseVectorStore):
    """Lightweight vector store backed by SQLite and sentence-transformers."""

    def __init__(self, config: VectorStoreConfig) -> None:
        self.config = config
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._model: Optional[SentenceTransformer] = None
        self._initialise()

    def _initialise(self) -> None:
        if not _SENTENCE_TRANSFORMERS_AVAILABLE:
            LOGGER.warning("sentence-transformers not available; semantic search disabled")
            return
        try:
            self._model = SentenceTransformer(self.config.model_name)
        except Exception as exc:  # pragma: no cover - optional failure path
            LOGGER.error("Failed to load sentence transformer model '%s': %s", self.config.model_name, exc)
            self._model = None
            return
        try:
            self._conn = sqlite3.connect(self.config.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            with self._conn:
                self._conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS episode_embeddings (
                        episode_id INTEGER PRIMARY KEY,
                        embedding BLOB NOT NULL,
                        FOREIGN KEY (episode_id) REFERENCES episodes(id)
                    )
                    """
                )
                self._conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_episode_embeddings_id
                    ON episode_embeddings(episode_id)
                    """
                )
        except Exception as exc:  # pragma: no cover - sqlite failure
            LOGGER.error("Failed to initialise SQLite vector store: %s", exc)
            self._conn = None

    def is_available(self) -> bool:
        return self._conn is not None and self._model is not None

    def _encode(self, text: str) -> Optional[List[float]]:
        if not text or not self.is_available():
            return None
        try:
            assert self._model is not None
            embedding = self._model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        except Exception as exc:  # pragma: no cover - model failure
            LOGGER.error("Error generating embedding: %s", exc)
            return None

    def add_embedding(self, episode_id: int, text: str) -> bool:
        if not self.is_available():
            return False
        embedding = self._encode(text)
        if embedding is None:
            return False
        try:
            blob = pickle.dumps(embedding)
            assert self._conn is not None
            with self._lock, self._conn:
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO episode_embeddings (episode_id, embedding)
                    VALUES (?, ?)
                    """,
                    (episode_id, blob),
                )
            return True
        except Exception as exc:  # pragma: no cover - sqlite failure
            LOGGER.error("Error storing embedding: %s", exc)
            return False

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not self.is_available() or not query:
            return []
        embedding = self._encode(query)
        if embedding is None:
            return []
        try:
            import numpy as np

            assert self._conn is not None
            cursor = self._conn.execute(
                """
                SELECT e.id, e.timestamp, e.fact, e.metadata, ve.embedding
                FROM episodes e
                JOIN episode_embeddings ve ON e.id = ve.episode_id
                ORDER BY e.id DESC
                LIMIT 1000
                """
            )
            query_vec = np.array(embedding)
            results: List[Dict[str, Any]] = []
            for row in cursor.fetchall():
                embedding_vec = pickle.loads(row["embedding"])
                emb_np = np.array(embedding_vec)
                denom = float(np.linalg.norm(query_vec) * np.linalg.norm(emb_np))
                if denom == 0:
                    continue
                similarity = float(np.dot(query_vec, emb_np) / denom)
                results.append(
                    {
                        "id": row["id"],
                        "timestamp": row["timestamp"],
                        "fact": row["fact"],
                        "metadata": row["metadata"],
                        "similarity": similarity,
                    }
                )
            results.sort(key=lambda item: item["similarity"], reverse=True)
            return results[:limit]
        except Exception as exc:  # pragma: no cover - numpy/sqlite failure
            LOGGER.error("Error performing semantic search: %s", exc)
            return []

    def update_missing_embeddings(self, limit: int = 100) -> int:
        if not self.is_available():
            return 0
        try:
            assert self._conn is not None
            with self._lock:
                cursor = self._conn.execute(
                    """
                    SELECT e.id, e.fact
                    FROM episodes e
                    LEFT JOIN episode_embeddings ve ON e.id = ve.episode_id
                    WHERE ve.episode_id IS NULL
                    ORDER BY e.id DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                updated = 0
                for row in cursor.fetchall():
                    if self.add_embedding(row["id"], row["fact"]):
                        updated += 1
                return updated
        except Exception as exc:  # pragma: no cover - sqlite failure
            LOGGER.error("Error updating embeddings: %s", exc)
            return 0

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


class QdrantVectorStore(BaseVectorStore):
    """Qdrant-backed vector store for larger datasets."""

    def __init__(self, config: VectorStoreConfig) -> None:
        self.config = config
        self._client: Optional[QdrantClient] = None
        self._model: Optional[Any] = None
        self._initialise()

    def _initialise(self) -> None:
        if not _QDRANT_AVAILABLE:
            LOGGER.warning("qdrant-client not installed; falling back to SQLite backend")
            return
        if not _SENTENCE_TRANSFORMERS_AVAILABLE:
            LOGGER.warning("sentence-transformers not available; Qdrant backend disabled")
            return
        try:
            self._model = SentenceTransformer(self.config.model_name)
            self._client = QdrantClient(
                url=self.config.qdrant_url or "http://127.0.0.1:6333",
                api_key=self.config.qdrant_api_key,
            )
            self._ensure_collection()
        except Exception as exc:  # pragma: no cover - remote failure
            LOGGER.error("Failed to initialise Qdrant client: %s", exc)
            self._client = None
            self._model = None

    def _ensure_collection(self) -> None:
        if self._client is None or qmodels is None or self._model is None:
            return
        distance = qmodels.Distance.COSINE
        try:
            sample_vector = self._model.encode("bootstrap")
        except Exception as exc:  # pragma: no cover - model failure
            LOGGER.error("Failed to bootstrap embedding dimension: %s", exc)
            return
        dim = len(sample_vector)
        if dim == 0:
            LOGGER.error("Sentence transformer returned empty embedding; cannot configure Qdrant")
            return
        try:
            self._client.get_collection(self.config.qdrant_collection)
        except Exception:
            try:
                self._client.create_collection(
                    collection_name=self.config.qdrant_collection,
                    vectors_config=qmodels.VectorParams(size=dim, distance=distance),
                )
            except Exception as exc:  # pragma: no cover - remote failure
                LOGGER.error("Failed to create Qdrant collection: %s", exc)
                self._client = None

    def is_available(self) -> bool:
        return self._client is not None and self._model is not None

    def add_embedding(self, episode_id: int, text: str) -> bool:
        if not self.is_available():
            return False
        assert self._client is not None and self._model is not None
        try:
            vector = self._model.encode(text).tolist()
            payload = {"fact": text}
            self._client.upsert(
                collection_name=self.config.qdrant_collection,
                points=[
                    qmodels.PointStruct(id=episode_id, vector=vector, payload=payload)
                ],
            )
            return True
        except Exception as exc:  # pragma: no cover - remote failure
            LOGGER.error("Failed to upsert point in Qdrant: %s", exc)
            return False

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not self.is_available():
            return []
        assert self._client is not None and self._model is not None
        try:
            vector = self._model.encode(query).tolist()
            results = self._client.search(
                collection_name=self.config.qdrant_collection,
                query_vector=vector,
                limit=limit,
            )
            return [
                {
                    "id": int(hit.id),
                    "similarity": float(hit.score),
                    "fact": hit.payload.get("fact"),
                }
                for hit in results
            ]
        except Exception as exc:  # pragma: no cover - remote failure
            LOGGER.error("Failed to search Qdrant: %s", exc)
            return []

    def update_missing_embeddings(self, limit: int = 100) -> int:
        # Qdrant handles upserts directly; the agent should push updates via add_embedding
        return 0

    def close(self) -> None:
        self._client = None
        self._model = None


def create_vector_store(config: Optional[VectorStoreConfig] = None) -> BaseVectorStore:
    config = config or VectorStoreConfig.from_env()
    backend = config.backend.lower()
    if backend == "qdrant":
        store = QdrantVectorStore(config)
        if store.is_available():
            return store
        LOGGER.info("Falling back to SQLite vector store backend")
    return SQLiteVectorStore(config)


__all__ = [
    "BaseVectorStore",
    "SQLiteVectorStore",
    "QdrantVectorStore",
    "VectorStoreConfig",
    "create_vector_store",
]
