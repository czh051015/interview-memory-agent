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

    @patch("src.market.jingyan.chat_json")
    def test_item_meta_fills_company_role_date(self, mock_chat):
        """item_meta 按题目下标回填公司/岗位/日期，缺省下标沿用默认。"""
        mock_chat.return_value = {"topics": []}
        items = import_jingyan(
            "题一\n题二",
            item_meta={
                0: {"company": "腾讯", "role": "AI应用开发", "date": "2026-07-25"},
            },
        )
        assert items[0].company == "腾讯"
        assert items[0].role == "AI应用开发"
        assert items[0].date == "2026-07-25"
        assert items[1].company == ""
        assert items[1].date == ""
        assert items[1].role == "AI应用开发"  # schema 默认值

    @patch("src.market.jingyan.chat_json")
    def test_item_meta_keeps_defaults_when_absent(self, mock_chat):
        """不传 item_meta：company/date 为空，role 用 schema 默认。"""
        mock_chat.return_value = {"topics": []}
        items = import_jingyan("题一")
        assert items[0].company == ""
        assert items[0].date == ""
        assert items[0].round == ""
        assert items[0].role == "AI应用开发"

    @patch("src.market.jingyan.chat_json")
    def test_item_meta_out_of_range_ignored(self, mock_chat):
        """超出题目数量的下标被忽略，不影响正常导入。"""
        mock_chat.return_value = {"topics": []}
        items = import_jingyan("题一", item_meta={9: {"company": "不存在"}})
        assert len(items) == 1
        assert items[0].company == ""

    def test_empty_text(self):
        assert import_jingyan("") == []

    @patch("src.market.jingyan.chat_json")
    def test_multi_chunk_topic_mapping(self, mock_chat):
        """分块提 topic：>40 题时各块返回全局下标，合并不互相覆盖（回归）。"""
        questions = [f"第{i}题" for i in range(1, 46)]  # 2 块：40 + 5
        mock_chat.side_effect = [
            {"topics": [{"index": i, "topic": f"块A-{i}"} for i in range(1, 41)]},
            {"topics": [{"index": i, "topic": f"块B-{i}"} for i in range(41, 46)]},
        ]
        items = import_jingyan("\n".join(questions))
        assert len(items) == 45
        assert items[0].topic == "块A-1"
        assert items[39].topic == "块A-40"
        assert items[40].topic == "块B-41"  # 旧实现第二块覆盖第一块 → 40 题前会串 topic
        assert items[44].topic == "块B-45"
