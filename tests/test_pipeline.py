"""面经消化集成测试。"""

import pytest
from unittest.mock import patch

from src.cleaner.schema import KnowledgeItem, ItemStatus, DecomposeResult


class TestKnowledgeItem:
    """KnowledgeItem 模型测试。"""

    def test_create_item(self):
        item = KnowledgeItem(
            id="ki_001",
            question="RRF重排序原理？",
            topic="混合检索",
            company="字节",
            role="AI应用开发",
            round="技术一面",
            date="2026-08-12",
            status=ItemStatus.FAIL,
            user_note="忘了",
        )
        assert item.question == "RRF重排序原理？"
        assert item.status == ItemStatus.FAIL
        assert item.mastery_score == 1.0

    def test_default_values(self):
        item = KnowledgeItem(question="测试题")
        assert item.status == ItemStatus.UNKNOWN
        assert item.mastery_score == 1.0
        assert item.review_count == 0
        assert item.related_items == []


class TestDecomposeResult:
    """拆解结果模型测试。"""

    def test_empty_result(self):
        result = DecomposeResult(raw_text="", total_count=0)
        assert result.total_count == 0
        assert result.unknown_count == 0

    def test_with_items(self):
        items = [
            KnowledgeItem(question="Q1", status=ItemStatus.FAIL, user_note="忘了"),
            KnowledgeItem(question="Q2", status=ItemStatus.PASS, user_note="过了"),
            KnowledgeItem(question="Q3", status=ItemStatus.UNKNOWN),
        ]
        result = DecomposeResult(
            company="字节",
            role="AI",
            items=items,
            total_count=3,
            unknown_count=1,
        )
        assert result.company == "字节"
        assert result.total_count == 3


class TestDecompose:
    """拆解管线测试（mock LLM）。"""

    @patch("src.cleaner.decompose.chat_json")
    def test_decompose_basic(self, mock_chat):
        mock_chat.return_value = {
            "company": "字节",
            "role": "AI应用开发",
            "round": "一面",
            "date": "2026-07-14",
            "items": [
                {"question": "RRF原理？", "topic": "混合检索", "user_note": "忘了", "status": "fail"},
                {"question": "Agent安全？", "topic": "Agent", "user_note": "不会", "status": "fail"},
                {"question": "单例模式？", "topic": "设计模式", "user_note": "过了", "status": "pass"},
            ],
        }

        from src.cleaner.decompose import decompose

        result = decompose("字节一面：RRF忘了，Agent安全不会，单例过了")
        assert result.total_count == 3
        assert result.company == "字节"
        assert result.unknown_count == 0

        statuses = {item.status for item in result.items}
        assert ItemStatus.FAIL in statuses
        assert ItemStatus.PASS in statuses

    @patch("src.cleaner.decompose.chat_json")
    def test_decompose_rule_override(self, mock_chat):
        """规则覆盖 LLM：LLM 返回 unknown，规则兜底修正。"""
        mock_chat.return_value = {
            "company": "",
            "role": "",
            "round": "",
            "date": "",
            "items": [
                {"question": "Q1", "topic": "", "user_note": "答得一坨", "status": "unknown"},
                {"question": "Q2", "topic": "", "user_note": "秒了", "status": "unknown"},
            ],
        }

        from src.cleaner.decompose import decompose

        result = decompose("Q1答得一坨 Q2秒了")
        assert result.total_count == 2
        # 规则应覆盖 LLM 的 unknown
        item1 = result.items[0]
        item2 = result.items[1]
        assert item1.status == ItemStatus.FAIL  # "答得一坨" → fail
        assert item2.status == ItemStatus.PASS  # "秒了" → pass
