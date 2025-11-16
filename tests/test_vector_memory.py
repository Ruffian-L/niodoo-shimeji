"""Unit tests for the VectorMemory facade."""

from unittest.mock import MagicMock, patch

from modules.vector_memory import VectorMemory
from modules.vector_store import BaseVectorStore, VectorStoreConfig


def _mock_store() -> MagicMock:
    store = MagicMock(spec=BaseVectorStore)
    store.is_available.return_value = True
    store.add_embedding.return_value = True
    store.search.return_value = [{"id": 1, "fact": "hello"}]
    store.update_missing_embeddings.return_value = 3
    return store


def test_vector_memory_delegates_to_injected_store():
    store = _mock_store()
    config = VectorStoreConfig(backend="sqlite")

    vm = VectorMemory(store=store, config=config)

    assert vm.is_available() is True
    assert vm.store_embedding(42, "fact text") is True
    store.add_embedding.assert_called_once_with(42, "fact text")

    results = vm.semantic_search("query", limit=2)
    store.search.assert_called_once_with("query", 2)
    assert results == [{"id": 1, "fact": "hello"}]

    updated = vm.update_episode_embeddings(limit=50)
    store.update_missing_embeddings.assert_called_once_with(50)
    assert updated == 3

    vm.close()
    store.close.assert_called_once_with()


def test_vector_memory_builds_store_from_config():
    store = _mock_store()

    with patch("modules.vector_memory.create_vector_store", return_value=store) as factory_mock:
        config = VectorStoreConfig(backend="sqlite")
        vm = VectorMemory(store=None, config=config)

    factory_mock.assert_called_once_with(config)
    assert vm.is_available() is True
    vm.close()
    store.close.assert_called_once()
