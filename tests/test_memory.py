"""Memory 记忆库单元测试。"""

import pytest
from unittest.mock import patch, MagicMock

from src.models import CleanedFeedback, FeedbackSource, QualityReport
from src.memory.embedding import embed_texts


class TestEmbedding:
    """嵌入管线测试。"""

    @patch("src.memory.embedding.check_ollama")
    @patch("src.memory.embedding.embed_ollama")
    def test_embed_texts_with_ollama(self, mock_embed, mock_check):
        mock_check.return_value = True
        mock_embed.return_value = [[0.1, 0.2, 0.3]]

        result = embed_texts(["测试文本"])
        assert len(result) == 1
        assert len(result[0]) == 3

    @patch("src.memory.embedding.check_ollama")
    def test_embed_texts_fallback_zero(self, mock_check):
        mock_check.return_value = False

        result = embed_texts(["测试文本"])
        assert len(result) == 1
        assert len(result[0]) == 768  # shaw/dmeta-embedding-zh 默认维度
        assert all(v == 0.0 for v in result[0])

    def test_embed_empty_list(self):
        result = embed_texts([])
        assert result == []


class TestMemoryStore:
    """向量存储测试（需要 mock Chroma）。"""

    @patch("src.memory.store.chromadb.PersistentClient")
    def test_store_feedback(self, mock_client_class):
        mock_collection = MagicMock()
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_client_class.return_value = mock_client

        from src.memory.store import store_feedback, _client
        # 重置 client
        import src.memory.store as store_module
        store_module._client = None

        cleaned = CleanedFeedback(
            id="clean_001",
            raw_id="raw_001",
            raw_text="测试",
            normalized_text="测试反馈内容",
            dedup_hash="abc123",
            source=FeedbackSource.OTHER_JINGYAN,
            quality=QualityReport(),
        )

        store_feedback(cleaned, embedding=[0.1, 0.2, 0.3])

        mock_collection.add.assert_called_once()
