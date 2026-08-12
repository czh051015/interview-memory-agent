"""网上面经导入器测试（phase-2-plan §2.5 验收标准 1）。"""

from pathlib import Path
from unittest.mock import patch

from src.cleaner.schema import ItemStatus, ItemCategory, ItemSource
from src.market.jingyan import parse_jingyan_lines, import_jingyan

SEED_FILE = Path(__file__).resolve().parent.parent / "data" / "seed" / "public_jingyan.txt"

TOPIC_RESULT = {"topics": [{"index": i, "topic": f"主题{i}"} for i in range(1, 21)]}


class TestParseJingyanLines:
    def test_basic_lines(self):
        assert parse_jingyan_lines("题一\n题二\n") == ["题一", "题二"]

    def test_skips_blank_comment_separator(self):
        text = "\n# 注释行\n---\n***\n=== \n题一\n"
        assert parse_jingyan_lines(text) == ["题一"]

    def test_strips_number_prefixes(self):
        text = "1. 第一题\n第2题 第二题\n3）第三题\n4、第四题\n无编号题"
        assert parse_jingyan_lines(text) == ["第一题", "第二题", "第三题", "第四题", "无编号题"]

    def test_empty_input(self):
        assert parse_jingyan_lines("") == []
        assert parse_jingyan_lines("# 只有注释\n\n") == []


class TestImportJingyan:
    @patch("src.market.jingyan.chat_json")
    def test_import_20_from_seed_file(self, mock_chat):
        """验收标准 1：导入 20 条网上面经，全部 status=unknown、category=knowledge。"""
        mock_chat.return_value = TOPIC_RESULT
        items = import_jingyan(SEED_FILE.read_text(encoding="utf-8"))

        assert len(items) == 20
        assert all(i.status == ItemStatus.UNKNOWN for i in items)
        assert all(i.category == ItemCategory.KNOWLEDGE for i in items)
        assert all(i.source == ItemSource.PUBLIC_JINGYAN for i in items)
        assert all(i.topic for i in items)  # mock 返回了全部 topic

    @patch("src.market.jingyan.chat_json")
    def test_topic_index_mapping(self, mock_chat):
        """topic 按 index 回填，而不是按位置。"""
        mock_chat.return_value = {"topics": [{"index": 1, "topic": "线程池"}]}
        items = import_jingyan("java线程池核心参数？\n什么是RAG？")
        assert items[0].topic == "线程池"
        assert items[1].topic == ""

    @patch("src.market.jingyan.chat_json")
    def test_llm_failure_degrades_to_empty_topics(self, mock_chat):
        """LLM 失败 → 降级空 topic，照常入库（题目本身仍有价值）。"""
        mock_chat.side_effect = ValueError("LLM down")
        items = import_jingyan("题一\n题二")
        assert len(items) == 2
        assert all(i.topic == "" for i in items)
        assert all(i.status == ItemStatus.UNKNOWN for i in items)

    @patch("src.market.jingyan.chat_json")
    def test_idempotent_ids(self, mock_chat):
        """同一题目两次导入 → id 相同（幂等 upsert）。"""
        mock_chat.return_value = {"topics": []}
        text = "什么是RAG？"
        ids1 = {i.id for i in import_jingyan(text)}
        ids2 = {i.id for i in import_jingyan(text)}
        assert ids1 == ids2
        assert all(i.startswith("jy_") for i in ids1)

    def test_empty_text(self):
        assert import_jingyan("") == []
