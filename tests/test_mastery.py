"""掌握度衰减 / 复习重置 / 双因子召回排序测试（phase-2-plan §3.5 验收 1~3）。"""

from datetime import datetime, timedelta

import pytest

from src.cleaner.schema import KnowledgeItem, ItemStatus
from src.memory.mastery import (
    decay,
    effective_mastery,
    review,
    rank,
    _elapsed_days,
)

NOW = datetime(2026, 8, 13, 12, 0, 0)


def make_item(
    *,
    id="ki_1",
    topic="RAG",
    status=ItemStatus.FAIL,
    mastery=1.0,
    reviewed_at=None,
    created_at=NOW,
    review_count=0,
) -> KnowledgeItem:
    return KnowledgeItem(
        id=id,
        question=f"{topic} 的原理是什么",
        topic=topic,
        status=status,
        mastery_score=mastery,
        last_reviewed_at=reviewed_at,
        created_at=created_at,
        review_count=review_count,
    )


class TestDecay:
    """验收 1：30 天后 1.0 → 约 0.22（e^(-1.5)）。"""

    def test_30_days(self):
        assert decay(1.0, 30) == pytest.approx(0.2231, abs=1e-4)

    def test_15_days(self):
        assert decay(1.0, 15) == pytest.approx(0.4724, abs=1e-4)

    def test_zero_days_no_decay(self):
        assert decay(1.0, 0) == 1.0

    def test_negative_days_no_decay(self):
        assert decay(0.8, -3) == 0.8

    def test_partial_mastery_scales(self):
        assert decay(0.5, 30) == pytest.approx(0.1116, abs=1e-4)


class TestReview:
    """验收 2：复习后 mastery 回升，review_count +1，last_reviewed_at 更新。"""

    def test_full_mastery_caps_at_1(self):
        item = make_item(mastery=1.0)
        out = review(item, now=NOW)
        assert out.mastery_score == 1.0
        assert out.review_count == 1
        assert out.last_reviewed_at == NOW

    def test_bump_by_1_2(self):
        out = review(make_item(mastery=0.5), now=NOW)
        assert out.mastery_score == pytest.approx(0.6)

    def test_cap_at_1(self):
        out = review(make_item(mastery=0.9), now=NOW)
        assert out.mastery_score == 1.0

    def test_count_accumulates(self):
        item = make_item(review_count=3)
        assert review(item, now=NOW).review_count == 4

    def test_original_unchanged(self):
        item = make_item(mastery=0.5, review_count=1)
        review(item, now=NOW)
        assert item.mastery_score == 0.5
        assert item.review_count == 1
        assert item.last_reviewed_at is None

    def test_default_now_is_utcnow(self):
        out = review(make_item())
        assert out.last_reviewed_at is not None
        assert datetime.utcnow() - out.last_reviewed_at < timedelta(minutes=1)


class TestRank:
    """验收 3：同 topic 下，8 天未复习的题排在昨天刚复习的题前面。"""

    def test_stale_outranks_fresh(self):
        stale = make_item(id="a", reviewed_at=NOW - timedelta(days=8))
        fresh = make_item(id="b", reviewed_at=NOW - timedelta(days=1))
        ranked = rank([fresh, stale], now=NOW)
        assert [it.id for it in ranked] == ["a", "b"]
        assert ranked[0]._recall_score > ranked[1]._recall_score

    def test_importance_fail_above_partial(self):
        fail = make_item(id="a", reviewed_at=NOW - timedelta(days=1))
        partial = make_item(id="b", status=ItemStatus.PARTIAL,
                            reviewed_at=NOW - timedelta(days=1))
        ranked = rank([partial, fail], now=NOW)
        assert [it.id for it in ranked] == ["a", "b"]

    def test_relevance_beats_recency(self):
        relevant = make_item(id="a", reviewed_at=NOW - timedelta(days=1))
        stale = make_item(id="b", reviewed_at=NOW - timedelta(days=8))
        ranked = rank([stale, relevant], relevances={"a": 0.9}, now=NOW)
        assert ranked[0].id == "a"

    def test_relevance_from_similarity_attr(self):
        item = make_item(id="a", reviewed_at=NOW - timedelta(days=1))
        setattr(item, "_similarity", 0.9)
        ranked = rank([item, make_item(id="b", reviewed_at=NOW - timedelta(days=1))], now=NOW)
        assert ranked[0].id == "a"

    def test_unknown_sinks_below_fail(self):
        fail = make_item(id="a", reviewed_at=NOW - timedelta(days=1))
        unknown = make_item(id="b", status=ItemStatus.UNKNOWN,
                            reviewed_at=NOW - timedelta(days=8))
        ranked = rank([unknown, fail], now=NOW)
        assert ranked[0].id == "a"

    def test_never_reviewed_uses_created_at(self):
        never = make_item(id="a", reviewed_at=None, created_at=NOW - timedelta(days=10))
        reviewed = make_item(id="b", reviewed_at=NOW - timedelta(days=1))
        ranked = rank([reviewed, never], now=NOW)
        assert ranked[0].id == "a"

    def test_score_in_range(self):
        items = [make_item(id=f"k{i}", reviewed_at=NOW - timedelta(days=i)) for i in range(5)]
        for item in rank(items, now=NOW):
            assert 0.0 <= item._recall_score < 1.0

    def test_stable_tie_order(self):
        a = make_item(id="a", reviewed_at=NOW - timedelta(days=1))
        b = make_item(id="b", reviewed_at=NOW - timedelta(days=1))
        ranked = rank([a, b], now=NOW)
        assert [it.id for it in ranked] == ["a", "b"]

    def test_low_mastery_outranks_stale(self):
        """掌握度缺口优先于时间：mastery 低的题更该复习，即使另一题更久没复习。"""
        low = make_item(id="a", mastery=0.3, reviewed_at=NOW)               # 掌握度 0.3，刚复习
        stale = make_item(id="b", mastery=1.0, reviewed_at=NOW - timedelta(days=8))  # 8 天没复习但掌握度 1.0
        ranked = rank([stale, low], now=NOW)
        assert ranked[0].id == "a"

    def test_reviewed_fail_sinks_below_partial(self):
        """复习到会的 fail 题（mastery=1 刚复习）不再碾压遗忘的 partial 题。"""
        reviewed_fail = make_item(id="a", status=ItemStatus.FAIL, reviewed_at=NOW)
        stale_partial = make_item(id="b", status=ItemStatus.PARTIAL,
                                  reviewed_at=NOW - timedelta(days=8))
        ranked = rank([reviewed_fail, stale_partial], now=NOW)
        assert ranked[0].id == "b"


class TestEffectiveMastery:
    def test_30_days_after_review(self):
        item = make_item(reviewed_at=NOW - timedelta(days=30))
        assert effective_mastery(item, now=NOW) == pytest.approx(0.2231, abs=1e-4)

    def test_future_review_time_no_decay(self):
        item = make_item(reviewed_at=NOW + timedelta(days=1))
        assert effective_mastery(item, now=NOW) == 1.0

    def test_no_anchor_no_decay(self):
        item = KnowledgeItem(id="x", question="q", last_reviewed_at=None)
        assert _elapsed_days(item, NOW) == 0.0
