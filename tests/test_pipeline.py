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
    """拆解管线测试（mock LLM）：复盘带自评 → 自动判别，纯题目/无备注 → unknown；段级声明 → suspected_fail。"""

    @patch("src.cleaner.decompose.chat_json")
    def test_decompose_auto_status_from_user_note(self, mock_chat):
        """方案 B：复盘带自评 → 根据 user_note 自动判别 fail/partial/pass。"""
        mock_chat.return_value = {
            "company": "字节",
            "role": "AI应用开发",
            "round": "一面",
            "date": "2026-07-14",
            "items": [
                {"question": "RRF原理？", "topic": "混合检索", "user_note": "忘了"},
                {"question": "单例模式？", "topic": "设计模式", "user_note": "过了"},
            ],
        }

        from src.cleaner.decompose import decompose

        result = decompose("字节一面：RRF忘了，单例过了")
        assert result.total_count == 2
        assert result.company == "字节"
        assert result.unknown_count == 0  # 有自评 → 全部自动判别，无 unknown
        assert result.suspected_fail is False  # 无段级声明
        assert result.items[0].status == ItemStatus.FAIL   # "忘了" → fail
        assert result.items[1].status == ItemStatus.PASS   # "过了" → pass

    @patch("src.cleaner.decompose.chat_json")
    def test_decompose_suspected_fail(self, mock_chat):
        """段级声明"没答上"→ suspected_fail=True，但题仍 unknown（待用户确认）。"""
        mock_chat.return_value = {
            "company": "",
            "role": "",
            "round": "",
            "date": "",
            "default_status": "fail",
            "items": [
                {"question": "Q1", "topic": "", "user_note": ""},
                {"question": "Q2", "topic": "", "user_note": ""},
            ],
        }

        from src.cleaner.decompose import decompose

        result = decompose("这些我都没答上来：Q1、Q2")
        assert result.total_count == 2
        assert result.suspected_fail is True  # 段级声明"没答上"
        assert all(item.status == ItemStatus.UNKNOWN for item in result.items)  # 但题仍 unknown

    @patch("src.cleaner.decompose.chat_json")
    def test_decompose_answer_points_not_suspected(self, mock_chat):
        """回答要点 → suspected_fail=False，题 unknown，参考答案存进 answer。"""
        mock_chat.return_value = {
            "company": "",
            "role": "",
            "round": "",
            "date": "",
            "default_status": "pass",
            "items": [
                {"question": "Q1", "topic": "", "user_note": "", "answer": "答案1"},
                {"question": "Q2", "topic": "", "user_note": "", "answer": "答案2"},
            ],
        }

        from src.cleaner.decompose import decompose

        result = decompose("回答要点：Q1答案1 Q2答案2")
        assert result.total_count == 2
        assert result.suspected_fail is False
        assert all(item.status == ItemStatus.UNKNOWN for item in result.items)
        assert all(item.answer for item in result.items)  # 答案保留
