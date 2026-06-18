from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.utils import vector_store


def test_missing_pinecone_index_is_created(monkeypatch):
    fake_client = MagicMock()
    fake_client.list_indexes.return_value = []
    fake_client.describe_index.return_value = SimpleNamespace(
        status=SimpleNamespace(ready=True)
    )
    fake_index = object()
    fake_client.Index.return_value = fake_index
    monkeypatch.setattr(vector_store.settings, "pinecone_api_key", "test-key")
    monkeypatch.setattr(vector_store.settings, "pinecone_index_name", "agentic-system")

    with patch("src.utils.vector_store.Pinecone", return_value=fake_client):
        result = vector_store.get_pinecone_index()

    fake_client.create_index.assert_called_once()
    assert result is fake_index


def test_existing_pinecone_index_is_reused(monkeypatch):
    fake_client = MagicMock()
    fake_client.list_indexes.return_value = [SimpleNamespace(name="agentic-system")]
    fake_index = object()
    fake_client.Index.return_value = fake_index
    monkeypatch.setattr(vector_store.settings, "pinecone_api_key", "test-key")
    monkeypatch.setattr(vector_store.settings, "pinecone_index_name", "agentic-system")

    with patch("src.utils.vector_store.Pinecone", return_value=fake_client):
        result = vector_store.get_pinecone_index()

    fake_client.create_index.assert_not_called()
    assert result is fake_index
