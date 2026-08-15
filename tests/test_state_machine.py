"""status 状态机测试 —— 转换约束 + 证据留痕（2026-08-15 共识）。"""

from datetime import datetime

import pytest

from src.cleaner.schema import KnowledgeItem, ItemStatus
from src.cleaner.state_machine import (
    transition,
    record_birth,
    MAX_HISTORY,
)

NOW = datetime(2026, 8, 15, 18, 0, 0)


def make_item(status=ItemStatus.UNKNOWN, history=None):
    return KnowledgeItem(
        id="ki_1", question="题", status=status, history=history or [],
    )


class TestTransition:
    def test_unknown_to_fail(self):
        out = transition(make_item(), ItemStatus.FAIL, reason="不会", now=NOW)
        assert out.status == ItemStatus.FAIL

    def test_known_to_unknown_rejected(self):
        with pytest.raises(ValueError, match="不能退回 unknown"):
            transition(make_item(ItemStatus.FAIL), ItemStatus.UNKNOWN, reason="x", now=NOW)

    def test_unknown_to_unknown_ok(self):
        """unknown → unknown 不是「退回」，是保持，应放行。"""
        out = transition(make_item(), ItemStatus.UNKNOWN, reason="保持", now=NOW)
        assert out.status == ItemStatus.UNKNOWN

    def test_fail_to_pass_ok(self):
        """fail → pass 自由（复习/纠错），不卡。"""
        out = transition(make_item(ItemStatus.FAIL), ItemStatus.PASS, reason="复习会了", now=NOW)
        assert out.status == ItemStatus.PASS

    def test_records_evidence(self):
        out = transition(make_item(), ItemStatus.FAIL, reason="不会", actor="annotate", now=NOW)
        assert out.history == [{
            "time": NOW.isoformat(),
            "from": "unknown",
            "to": "fail",
            "reason": "不会",
            "actor": "annotate",
        }]

    def test_does_not_mutate_input(self):
        item = make_item()
        transition(item, ItemStatus.FAIL, reason="不会", now=NOW)
        assert item.status == ItemStatus.UNKNOWN
        assert item.history == []


class TestRecordBirth:
    def test_birth_record(self):
        item = make_item(ItemStatus.FAIL)
        out = record_birth(item, reason="LLM 推断", actor="decompose", now=NOW)
        assert out.history == [{
            "time": NOW.isoformat(),
            "from": None,
            "to": "fail",
            "reason": "LLM 推断",
            "actor": "decompose",
        }]


class TestMaxHistory:
    def test_history_capped(self):
        item = make_item()
        # 连续合法转换 60 次（fail ↔ partial 交替），超过 MAX_HISTORY
        for i in range(60):
            nxt = ItemStatus.PARTIAL if item.status == ItemStatus.FAIL else ItemStatus.FAIL
            item = transition(item, nxt, reason=f"第{i}次", now=NOW)
        assert len(item.history) == MAX_HISTORY
        # 保留的是最近 50 条：最后一条 reason 是"第59次"
        assert item.history[-1]["reason"] == "第59次"
