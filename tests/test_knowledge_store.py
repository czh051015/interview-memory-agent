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
    """v1.5 source metadata 往返与存量兼容。"""

    def _store_mod(self):
        import src.memory.knowledge_store as store_mod
        return store_mod

    def test_to_metadata_includes_source(self):
        store_mod = self._store_mod()
        item = KnowledgeItem(
            id="jy_001", question="RAG", topic="RAG", source=ItemSource.PUBLIC_JINGYAN,
            behavior_tags=["表达绕弯"],
        )
        meta = store_mod._to_metadata(item)
        assert meta["source"] == "public_jingyan"
        assert meta["last_reviewed_at"] == ""
        assert meta["behavior_tags"] == '["表达绕弯"]'

    def test_parse_results_defaults_old_data(self):
        """v1.0 存量记录没有 source key → 回退 self_review。"""
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
        assert items[0].last_reviewed_at is None
        assert items[0].behavior_tags == []

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


class TestDedupe:
    """维护 Agent 去重测试。"""

    def _mod(self):
        import src.memory.knowledge_store as store_mod
        return store_mod

    def test_normalize(self):
        store_mod = self._mod()
        assert store_mod._normalize(" RRF 原理？ ") == "rrf原理"
        assert store_mod._normalize("Agent 的短期、长期记忆") == "agent的短期长期记忆"
        assert store_mod._normalize("TCP 三次握手") == "tcp三次握手"

    @patch("src.memory.knowledge_store.embed_texts")
    @patch("src.memory.knowledge_store.get_collection")
    def test_find_duplicates_catches_similar(self, mock_get_col, mock_embed):
        """语义相似度 >= 阈值 → 判重。"""
        mock_collection = MagicMock()
        mock_collection.count.return_value = 5
        mock_collection.query.return_value = {
            "documents": [["RRF 融合多路检索结果的原理是什么？"]],
            "distances": [[0.02]],  # sim = 0.98
        }
        mock_get_col.return_value = mock_collection
        mock_embed.return_value = [[0.1] * 768]

        store_mod = self._mod()
        items = [KnowledgeItem(id="new_1", question="RRF 融合多路检索结果的原理")]
        dupes = store_mod.find_duplicates(items)
        assert len(dupes) == 1
        assert dupes[0][1] == "RRF 融合多路检索结果的原理是什么？"
        assert dupes[0][2] > 0.9

    @patch("src.memory.knowledge_store.embed_texts")
    @patch("src.memory.knowledge_store.get_collection")
    def test_find_duplicates_skips_below_threshold(self, mock_get_col, mock_embed):
        """相似度低于阈值 → 不算重复。"""
        mock_collection = MagicMock()
        mock_collection.count.return_value = 5
        mock_collection.query.return_value = {
            "documents": [["完全不同的另一道题"]],
            "distances": [[0.5]],  # sim = 0.5
        }
        mock_get_col.return_value = mock_collection
        mock_embed.return_value = [[0.1] * 768]

        store_mod = self._mod()
        items = [KnowledgeItem(id="new_1", question="RRF 原理")]
        dupes = store_mod.find_duplicates(items)
        assert dupes == []

    @patch("src.memory.knowledge_store.find_duplicates")
    def test_dedupe_within_batch(self, mock_find):
        """批内完全相同的题，只留一道。"""
        mock_find.return_value = []
        store_mod = self._mod()
        items = [
            KnowledgeItem(id="a", question="RRF 原理？"),
            KnowledgeItem(id="b", question="RRF原理"),
            KnowledgeItem(id="c", question="TCP 三次握手"),
        ]
        kept, reports = store_mod.dedupe_items(items)
        assert len(kept) == 2  # RRF 去重后留一道 + TCP
        assert len(reports) == 1
        assert reports[0]["kind"] == "within_batch"

    @patch("src.memory.knowledge_store.find_duplicates")
    def test_dedupe_existing(self, mock_find):
        """对库重复的题被过滤，报告 kind=existing。"""
        mock_find.return_value = [("RRF 原理", "已有 RRF 原理", 0.98)]
        store_mod = self._mod()
        items = [
            KnowledgeItem(id="a", question="RRF 原理"),
            KnowledgeItem(id="b", question="TCP 三次握手"),
        ]
        kept, reports = store_mod.dedupe_items(items)
        assert len(kept) == 1
        assert kept[0].question == "TCP 三次握手"
        assert reports[0]["kind"] == "existing"
        assert reports[0]["existing"] == "已有 RRF 原理"

    @patch("src.memory.knowledge_store.embed_texts")
    @patch("src.memory.knowledge_store.get_collection")
    def test_find_intra_duplicates(self, mock_get_col, mock_embed):
        """全库体检：A-B 与 B-A 只报一次。"""
        mock_collection = MagicMock()
        mock_collection.count.return_value = 3
        mock_collection.get.return_value = {
            "documents": ["RRF 原理", "RRF 融合多路检索结果的原理是什么？", "TCP 三次握手"],
        }
        mock_collection.query.return_value = {
            "documents": [
                ["RRF 原理", "RRF 融合多路检索结果的原理是什么？"],
                ["RRF 融合多路检索结果的原理是什么？", "RRF 原理"],
                ["TCP 三次握手", "RRF 原理"],
            ],
            "distances": [
                [0.0, 0.02],  # sim=0.98 → 重复
                [0.0, 0.02],  # 同一对，去重
                [0.0, 0.6],   # sim=0.4 → 不重复
            ],
        }
        mock_get_col.return_value = mock_collection
        mock_embed.return_value = [[0.1] * 768] * 3

        store_mod = self._mod()
        pairs = store_mod.find_intra_duplicates()
        assert len(pairs) == 1
        assert pairs[0][2] > 0.9


class TestAutoClean:
    """维护 Agent 自动清理测试。"""

    def _mod(self):
        import src.memory.knowledge_store as store_mod
        return store_mod

    @patch("src.memory.knowledge_store.search")
    def test_find_exact_duplicates(self, mock_search):
        """归一化后完全相同的题，归为一组。"""
        mock_search.return_value = [
            KnowledgeItem(id="a", question="RRF 原理？", status=ItemStatus.UNKNOWN),
            KnowledgeItem(id="b", question="RRF原理", status=ItemStatus.FAIL),  # 归一化后相同
            KnowledgeItem(id="c", question="TCP 三次握手", status=ItemStatus.UNKNOWN),
        ]
        store_mod = self._mod()
        groups = store_mod.find_exact_duplicates()
        assert len(groups) == 1
        assert {it.id for it in groups[0]} == {"a", "b"}

    @patch("src.memory.knowledge_store.delete_by_ids")
    @patch("src.memory.knowledge_store.find_exact_duplicates")
    def test_auto_clean_keeps_best(self, mock_find, mock_delete):
        """每组保留信息最全的（有 answer + fail 优先），删信息少的。"""
        keep = KnowledgeItem(id="keep", question="RRF原理", status=ItemStatus.FAIL, answer="答案")
        dup = KnowledgeItem(id="dup", question="RRF原理", status=ItemStatus.UNKNOWN, answer="")
        mock_find.return_value = [[keep, dup]]
        mock_delete.return_value = 1

        store_mod = self._mod()
        result = store_mod.auto_clean()
        assert result["removed"] == 1
        assert mock_delete.call_args.args[0] == ["dup"]

    @patch("src.memory.knowledge_store.find_exact_duplicates")
    def test_auto_clean_nothing(self, mock_find):
        """无重复 → 不删。"""
        mock_find.return_value = []
        store_mod = self._mod()
        assert store_mod.auto_clean() == {"removed": 0, "groups": 0}
