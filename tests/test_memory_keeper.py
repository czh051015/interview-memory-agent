"""记忆管家 Agent 测试：快照分层、LLM 规划、失败回退。"""

from unittest.mock import patch

import pytest

from src.memory import memory_keeper as keeper


def _fake_item(question="题", status="fail", mastery=0.3, days=10, tags=None):
    from src.cleaner.schema import KnowledgeItem, ItemStatus
    from datetime import datetime, timedelta

    created = datetime.utcnow() - timedelta(days=days)
    return KnowledgeItem(
        id=f"ki_{abs(hash(question)) % 10000}",
        question=question,
        status=ItemStatus(status),
        mastery_score=mastery,
        created_at=created,
        behavior_tags=tags or [],
    )


class TestMemorySnapshot:
    def test_red_yellow_green_tiers(self, monkeypatch):
        """快照分层：gap≥0.5 红、≥0.2 黄、其余绿。"""
        items = [
            _fake_item("快忘的题", mastery=0.2, days=30),   # e^-1.5*0.2≈0.04 → gap≈0.96 红
            _fake_item("该看看的题", mastery=0.5, days=10),  # e^-0.5*0.5≈0.30 → gap≈0.70 红
            _fake_item("刚看过的题", mastery=1.0, days=1),   # gap 小 → 绿
        ]
        # read_memory_state 会分别查 fail 和 partial，各返回 items 的一部分
        def fake_search(status, **kw):
            if status == "fail":
                return items[:2]
            if status == "partial":
                return items[2:]
            return []

        with patch.object(keeper.store, "search", side_effect=fake_search):
            snap = keeper.read_memory_state("default")
        assert len(snap.red) >= 2
        assert len(snap.green) >= 1
        assert snap.total_weak == 3

    def test_snapshot_prompt_text(self):
        """快照转 prompt 文本含分层标签。"""
        snap = keeper.MemorySnapshot(
            red=[{"status": "fail", "question": "Q", "mastery": 0.1, "gap": 0.9,
                  "days": 20, "behavior_tags": ["表达绕弯"]}],
            yellow=[], green=[], total_weak=1,
        )
        text = snap.to_prompt_text()
        assert "🔴 快忘了" in text
        assert "表达绕弯" in text


class TestPlanReview:
    def test_llm_plan(self):
        """LLM 正常输出 → 解析 plan/focus_topics，截断到 5 条。"""
        snap = keeper.MemorySnapshot(red=[{"status": "fail", "question": f"Q{i}",
                                           "mastery": 0.1, "gap": 0.9, "days": 10,
                                           "behavior_tags": []} for i in range(8)],
                                     yellow=[], green=[], total_weak=8)
        with patch.object(keeper, "chat_json", return_value={
            "focus_note": "线程池缺口最大",
            "plan": [{"question": f"Q{i}", "why": "gap 大"} for i in range(8)],
            "focus_topics": ["线程池", "RAG"],
        }):
            plan = keeper.plan_review(snap, [])
        assert len(plan["plan"]) == 5  # 截断
        assert plan["focus_topics"] == ["线程池", "RAG"]
        assert plan["focus_note"] == "线程池缺口最大"

    def test_llm_failure_falls_back_to_rules(self):
        """LLM 挂了 → 回退规则版：直接列 red 前 5，不抛异常。"""
        snap = keeper.MemorySnapshot(
            red=[{"status": "fail", "question": f"Q{i}", "mastery": 0.1,
                  "gap": 0.9, "days": 10, "behavior_tags": []} for i in range(3)],
            yellow=[], green=[], total_weak=3)
        with patch.object(keeper, "chat_json", side_effect=RuntimeError("llm down")):
            plan = keeper.plan_review(snap, [])
        assert len(plan["plan"]) == 3
        assert "快忘了" in plan["focus_note"]


class TestRun:
    def test_run_no_notify_prints_plan(self, capsys):
        """run(notify=False) 打印规划结果，不弹窗。"""
        snap = keeper.MemorySnapshot(red=[{"status": "fail", "question": "Q1",
                                           "mastery": 0.1, "gap": 0.9, "days": 9,
                                           "behavior_tags": []}],
                                     yellow=[], green=[], total_weak=1)
        with patch.object(keeper, "read_memory_state", return_value=snap), \
             patch.object(keeper, "read_review_history", return_value=[]), \
             patch.object(keeper, "plan_review", return_value={
                 "focus_note": "补线程池", "plan": [{"question": "Q1", "why": "gap 0.9"}],
                 "focus_topics": ["线程池"],
             }):
            plan = keeper.run("default", notify=False)
        assert plan["focus_note"] == "补线程池"
        out = capsys.readouterr().out
        assert "记忆管家" in out

    def test_run_notify_silent_when_no_red(self):
        """notify=True 但没有快忘的题 → 静默，不弹窗。"""
        snap = keeper.MemorySnapshot(red=[], yellow=[], green=[], total_weak=0)
        with patch.object(keeper, "read_memory_state", return_value=snap), \
             patch.object(keeper, "_notify_windows") as mock_notify, \
             patch.object(keeper, "plan_review", return_value={
                 "focus_note": "", "plan": [], "focus_topics": []}):
            keeper.run("default", notify=True)
        mock_notify.assert_not_called()
