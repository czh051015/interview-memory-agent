"""统一写回核心 _build_writeback_items（06 计划 §3.4）＋ apply_verdict 层 —— 锁死方案 A 行为契约。

不碰真实 Chroma/review_log。纯计算路径测 _build_writeback_items（返回
(updated_items, new_items) 对象）；apply_verdict 层测计数与落库调用。
"""

import pytest
from unittest.mock import patch

from src.mock import writeback as wb
from src.cleaner.schema import KnowledgeItem, ItemStatus, ItemSource


def _weak_result(item, performance, **extra):
    return {
        "question": item.question, "source": "weak", "topic": item.topic,
        "performance": performance, "item": item, "space": "default",
        "points": ["要点A", "要点B"], "misses": ["漏点X"], "reason": "没答到点",
        **extra,
    }


# ── 纯计算层：_build_writeback_items ──
def test_weak_fail_writes_feedback_not_answer():
    """weak fail → item.feedback 含「漏掉的」，answer 保持原题值不动。"""
    item = KnowledgeItem(id="ki_a", question="题", answer="原参考答案",
                         status=ItemStatus.FAIL, mastery_score=0.3)
    updated, new = wb._build_writeback_items([_weak_result(item, "fail")], [])
    u = updated[0]
    assert "漏掉的" in u.feedback and "要点A" in u.feedback
    assert u.answer == "原参考答案"  # feedback 不污染 answer
    assert u.mastery_score == pytest.approx(0.3)  # fail：封顶不涨
    assert new == []


def test_weak_pass_no_feedback_noise():
    """weak pass → mastery 涨；feedback 为空（无需对照）。"""
    item = KnowledgeItem(id="ki_a", question="题", answer="原参考答案",
                         status=ItemStatus.FAIL, mastery_score=0.3)
    updated, new = wb._build_writeback_items([_weak_result(item, "pass")], [])
    assert updated[0].mastery_score == pytest.approx(0.45)  # 0.3 × 1.5
    assert updated[0].feedback == ""
    assert updated[0].answer == "原参考答案"
    assert new == []


def test_new_item_collected_with_feedback():
    """非 weak + fail → 采集，feedback=judge 文本，answer 留空。"""
    r = {
        "question": "现场新题", "source": "resume", "topic": "项目深挖",
        "performance": "fail", "item": None, "space": "default",
        "points": ["要点A"], "misses": ["漏点X"], "reason": "不会",
    }
    updated, new = wb._build_writeback_items([r], [])
    assert updated == []
    assert len(new) == 1
    assert new[0].source == ItemSource.MOCK_INTERVIEW
    assert new[0].status == ItemStatus.FAIL
    assert "漏掉的" in new[0].feedback
    assert new[0].answer == ""  # 方案 A：answer 留空
    assert new[0].space == "default"


def test_new_item_pass_not_collected():
    """答好的新题不采集。"""
    r = {"question": "现场新题", "source": "resume", "topic": "t",
         "performance": "pass", "item": None, "space": "default",
         "points": [], "misses": [], "reason": ""}
    updated, new = wb._build_writeback_items([r], [])
    assert updated == []
    assert new == []


def test_behavior_tags_merged():
    """behaviors 合并进 weak 题 behavior_tags。"""
    item = KnowledgeItem(id="ki_a", question="题", status=ItemStatus.FAIL,
                         mastery_score=0.3, behavior_tags=["旧标签"])
    updated, _ = wb._build_writeback_items([_weak_result(item, "fail")], ["表达绕弯"])
    assert set(updated[0].behavior_tags) == {"旧标签", "表达绕弯"}


# ── 落库层：apply_verdict ──
def test_apply_verdict_returns_counts_and_stores_once():
    """返回 (updated, new) 计数；store_items 一次写入；review_log actor 统一。"""
    item = KnowledgeItem(id="ki_a", question="题", status=ItemStatus.FAIL, mastery_score=0.3)
    new_r = {"question": "新题", "source": "resume", "topic": "t",
             "performance": "fail", "item": None, "space": "default",
             "points": ["p"], "misses": ["m"], "reason": "r"}
    log_calls = []
    with patch.object(wb.store, "store_items", return_value=2) as mock_store, \
         patch.object(wb.review_log, "append", side_effect=lambda **kw: log_calls.append(kw)):
        updated, new = wb.apply_verdict(
            [_weak_result(item, "fail"), new_r], ["表达绕弯"], space="default")
    assert updated == 1 and new == 1
    mock_store.assert_called_once()  # 一次性落库（"失败不半写"）
    assert len(log_calls) == 1  # 只对 weak 题记日志
    assert log_calls[0]["actor"] == "mock_interview"
    assert log_calls[0]["action"] == "review_fail"


def test_apply_verdict_no_items_skips_store():
    """无任何 writeback 项 → 不调用 store，不记 review_log。"""
    ok = {"question": "新题", "source": "resume", "topic": "t",
          "performance": "pass", "item": None, "space": "default",
          "points": [], "misses": [], "reason": ""}
    with patch.object(wb.store, "store_items") as mock_store, \
         patch.object(wb.review_log, "append") as mock_log:
        updated, new = wb.apply_verdict([ok], [])
    assert updated == 0 and new == 0
    mock_store.assert_not_called()
    mock_log.assert_not_called()