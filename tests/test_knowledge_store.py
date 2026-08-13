"""KnowledgeItem 存储层测试。"""

import pytest
from unittest.mock import patch, MagicMock

from src.cleaner.schema import KnowledgeItem, ItemStatus, ItemSource


class TestKnowledgeStore:
    """存储层测试（mock Chroma）。"""

    @patch("src.memory.knowledge_store.chromadb.PersistentClient")
    @patch("src.memory.knowledge_store.embed_texts")
    def test_store_items(self, mock_embed, mock_client_class):
        mock_collection = MagicMock()
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_client_class.return_value = mock_client
        mock_embed.return_value = [[0.1] * 768]

        import src.memory.knowledge_store as store_mod
        store_mod._client = None

        items = [
            KnowledgeItem(id="ki_001", question="RRF原理？", topic="混合检索",
                          company="字节", status=ItemStatus.FAIL, user_note="忘了"),
        ]

        count = store_mod.store_items(items)
        assert count == 1
        mock_collection.upsert.assert_called_once()

    @patch("src.memory.knowledge_store.chromadb.PersistentClient")
    @patch("src.memory.knowledge_store.embed_texts")
    def test_search_by_status(self, mock_embed, mock_client_class):
        mock_collection = MagicMock()
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_client_class.return_value = mock_client
        mock_embed.return_value = [[0.1] * 768]

        mock_collection.count.return_value = 10
        # search() 无 query → 走 collection.get()
        mock_collection.get.return_value = {
            "ids": ["ki_001"],
            "documents": ["RRF原理？"],
            "metadatas": [{"question": "RRF原理？", "topic": "混合检索",
                           "company": "字节", "status": "fail", "user_note": "忘了",
                           "mastery_score": 1.0, "review_count": 0, "role": "", "round": "",
                           "date": "", "created_at": "2026-08-12T00:00:00"}],
        }

        import src.memory.knowledge_store as store_mod
        store_mod._client = None

        results = store_mod.search(status="fail")
        assert len(results) == 1
        assert results[0].status == ItemStatus.FAIL

    def test_store_empty_list(self):
        import src.memory.knowledge_store as store_mod
        assert store_mod.store_items([]) == 0


class TestStats:
    """统计功能测试。"""

    @patch("src.memory.knowledge_store.search")
    def test_stats(self, mock_search):
        mock_search.return_value = [
            KnowledgeItem(id="ki_001", question="Q1", topic="Agent", status=ItemStatus.FAIL),
            KnowledgeItem(id="ki_002", question="Q2", topic="Agent", status=ItemStatus.PARTIAL),
            KnowledgeItem(id="ki_003", question="Q3", topic="RAG", status=ItemStatus.PASS),
        ]

        import src.memory.knowledge_store as store_mod
        stats = store_mod.get_stats()

        assert stats["total"] == 3
        assert stats["by_status"]["fail"] == 1
        assert stats["by_status"]["partial"] == 1
        assert stats["by_status"]["pass"] == 1
        assert stats["hot_topics"][0]["topic"] == "Agent"
        assert stats["hot_topics"][0]["count"] == 2


class TestV15Metadata:
    """v1.5 source/priority metadata 往返与存量兼容。"""

    def _store_mod(self):
        import src.memory.knowledge_store as store_mod
        return store_mod

    def test_to_metadata_includes_source_priority(self):
        store_mod = self._store_mod()
        item = KnowledgeItem(
            id="jy_001", question="RAG", topic="RAG", source=ItemSource.PUBLIC_JINGYAN, priority=1.8,
        )
        meta = store_mod._to_metadata(item)
        assert meta["source"] == "public_jingyan"
        assert meta["priority"] == 1.8
        assert meta["last_reviewed_at"] == ""

    def test_parse_results_defaults_old_data(self):
        """v1.0 存量记录没有 source/priority key → 回退 self_review / 1.0。"""
        store_mod = self._store_mod()
        results = {
            "ids": ["ki_old"],
            "documents": ["旧题"],
            "metadatas": [{
                "question": "旧题", "topic": "RAG", "company": "", "role": "",
                "round": "", "date": "", "status": "fail", "user_note": "",
                "category": "knowledge", "mastery_score": 1.0, "review_count": 0,
                "created_at": "2026-08-12T00:00:00",
            }],
        }
        items = store_mod._parse_results(results)
        assert len(items) == 1
        assert items[0].source == ItemSource.SELF_REVIEW
        assert items[0].priority == 1.0
        assert items[0].last_reviewed_at is None

    @patch("src.memory.knowledge_store.chromadb.PersistentClient")
    def test_search_by_source_where(self, mock_client_class):
        """验收标准 4：source 过滤传到 Chroma where。"""
        mock_collection = MagicMock()
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_client_class.return_value = mock_client
        mock_collection.get.return_value = {"ids": [], "documents": [], "metadatas": []}

        store_mod = self._store_mod()
        store_mod._client = None

        store_mod.search(source="public_jingyan")
        mock_collection.get.assert_called_once()
        assert mock_collection.get.call_args.kwargs["where"] == {"source": "public_jingyan"}

        # 组合过滤 → $and
        store_mod.search(status="fail", source="self_review")
        assert mock_collection.get.call_args.kwargs["where"] == {
            "$and": [{"status": "fail"}, {"source": "self_review"}],
        }
