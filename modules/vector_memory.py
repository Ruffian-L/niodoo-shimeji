"""Vector-embedded semantic memory façade."""

from __future__ import annotations

from typing import Dict, List, Optional

from modules.vector_store import BaseVectorStore, VectorStoreConfig, create_vector_store


class VectorMemory:
    """Thin wrapper around the active vector store backend."""

    def __init__(self, store: Optional[BaseVectorStore] = None, config: Optional[VectorStoreConfig] = None) -> None:
        self.config = config or VectorStoreConfig.from_env()
        self._store = store or create_vector_store(self.config)

    def is_available(self) -> bool:
        return self._store.is_available()

    def store_embedding(self, episode_id: int, text: str) -> bool:
        return self._store.add_embedding(episode_id, text)

    def semantic_search(self, query: str, limit: int = 5) -> List[Dict[str, object]]:
        return self._store.search(query, limit)

    def update_episode_embeddings(self, limit: int = 100) -> int:
        return self._store.update_missing_embeddings(limit)

    def close(self) -> None:
        self._store.close()



