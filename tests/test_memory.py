"""Memory 记忆库单元测试。"""

import pytest
from unittest.mock import patch

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
