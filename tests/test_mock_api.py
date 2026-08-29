"""模拟面试 Web 端点测试（v1 单轮版）。

- judge_single_round：单轮判定逻辑（mock LLM）
- mock/start：出题范围=只考错题（mock store）
- mock/verdict / mock/complete：端到端行为（mock store + LLM）

注意：不触发真实 chromadb（环境坑：pytest 跑 chromadb 会 numpy access violation）。
"""
from unittest.mock import patch

import src.mock as mi


class TestJudgeSingleRound:
    """单轮判定（Web v1 核心）。"""

    @patch.object(mi, "chat_json")
    def test_normal(self, mock_llm):
        mock_llm.return_value = {
            "points": ["点1", "点2", "点3"],
            "misses": ["漏了点"],
            "suggested": "partial",
            "reason": "漏了关键点",
        }
        r = mi.judge_single_round("题", "答")
        assert r["suggested"] == "partial"
        assert len(r["points"]) == 3
        assert r["misses"] == ["漏了点"]

    @patch.object(mi, "chat_json")
    def test_normalizes_bad_suggested(self, mock_llm):
        """LLM 输出非法判定 → 兜底 partial。"""
        mock_llm.return_value = {
            "points": ["点1"], "misses": [], "suggested": "完美", "reason": "",
        }
        r = mi.judge_single_round("题", "答")
        assert r["suggested"] == "partial"

    @patch.object(mi, "chat_json")
    def test_points_misses_must_be_lists(self, mock_llm):
        """points/misses 非数组 → 拒绝并兜底。"""
        mock_llm.return_value = {"points": "不是数组", "misses": [], "suggested": "pass", "reason": ""}
        r = mi.judge_single_round("题", "答")
        assert r["suggested"] == "partial"
        assert r["points"] == []

    @patch.object(mi, "chat_json")
    def test_llm_failure_falls_back_partial(self, mock_llm):
        """LLM 异常 → 兜底 partial，不抛。"""
        mock_llm.side_effect = RuntimeError("network")
        r = mi.judge_single_round("题", "答")
        assert r["suggested"] == "partial"
        assert r["reason"] != ""
