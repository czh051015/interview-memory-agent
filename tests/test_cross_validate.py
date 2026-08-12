"""交叉验证纯函数测试（phase-2-plan §2.4 / §2.5 验收标准 3）。"""

import pytest

from src.cleaner.schema import (
    KnowledgeItem,
    ItemStatus,
    ItemCategory,
    ItemSource,
)
from src.market.cross_validate import (
    _topics_match,
    build_market_stats,
    adjust_priority,
    apply_priorities,
)


def make_item(topic: str, *, status=ItemStatus.FAIL, source=ItemSource.SELF_REVIEW,
              category=ItemCategory.KNOWLEDGE, id_prefix="ki") -> KnowledgeItem:
    return KnowledgeItem(
        id=f"{id_prefix}_t_{abs(hash(topic)) % 1000:03d}",
        question=f"题目 {topic}",
        topic=topic,
        category=category,
        status=status,
        source=source,
    )


STATS = {
    "high_freq_topics": {"RAG"},
    "low_freq_topics": {"死锁"},
    "jd_required_topics": {"RAG", "线程池"},
}


class TestAdjustPriority:
    """公式六分支（计划书 §2.4）。"""

    def test_high_freq_only(self):
        assert adjust_priority(make_item("RAG"), {
            "high_freq_topics": {"RAG"}, "low_freq_topics": set(), "jd_required_topics": set(),
        }) == 1.5

    def test_low_freq_only(self):
        assert adjust_priority(make_item("死锁"), {
            "high_freq_topics": set(), "low_freq_topics": {"死锁"}, "jd_required_topics": set(),
        }) == 0.5

    def test_jd_only(self):
        # 题库 0 次 + JD 要求 → 只乘 JD 系数
        assert adjust_priority(make_item("线程池"), {
            "high_freq_topics": set(), "low_freq_topics": set(), "jd_required_topics": {"线程池"},
        }) == 1.2

    def test_high_and_jd(self):
        # 1.5 * 1.2 有浮点误差，用 approx 断言
        assert adjust_priority(make_item("RAG"), STATS) == pytest.approx(1.8)

    def test_low_and_jd(self):
        assert adjust_priority(make_item("死锁"), {
            "high_freq_topics": set(), "low_freq_topics": {"死锁"}, "jd_required_topics": {"死锁"},
        }) == 0.6

    def test_no_signal(self):
        assert adjust_priority(make_item("合并数组"), STATS) == 1.0

    def test_acceptance_jd_boosts_fail_item(self):
        """验收标准 3：答错的题 topic 命中 JD 关键词 → 优先级 ≥ 1.5。"""
        fail_item = make_item("RAG", status=ItemStatus.FAIL)
        priority = adjust_priority(fail_item, STATS)
        assert priority >= 1.5


class TestTopicsMatch:
    def test_exact(self):
        assert _topics_match("RAG", "RAG")

    def test_containment_both_directions(self):
        assert _topics_match("RAG", "RAG检索增强")
        assert _topics_match("RAG检索增强", "RAG")

    def test_no_match(self):
        assert not _topics_match("RAG", "线程池")
        assert not _topics_match("", "RAG")


class TestBuildMarketStats:
    def test_freq_threshold(self):
        """出现 2 次 → 高频；1 次 → 低频。"""
        items = [
            make_item("RAG"),
            make_item("RAG", id_prefix="k2"),
            make_item("死锁"),
        ]
        stats = build_market_stats(items, high_freq_min=2)
        assert "RAG" in stats["high_freq_topics"]
        assert "死锁" in stats["low_freq_topics"]

    def test_containment_alias_expands(self):
        """'RAG' 与 'RAG检索增强' 同 cluster → 两个拼写都进 high_freq/jd_required。"""
        items = [
            make_item("RAG"),
            make_item("RAG", id_prefix="k2"),
            make_item("RAG检索增强", source=ItemSource.JD, id_prefix="jd"),
        ]
        stats = build_market_stats(items, high_freq_min=2)
        assert "RAG" in stats["high_freq_topics"]
        assert "RAG检索增强" in stats["high_freq_topics"]
        assert "RAG" in stats["jd_required_topics"]
        assert "RAG检索增强" in stats["jd_required_topics"]

    def test_pure_jd_topic_not_in_freq_sets(self):
        """题库 0 次的 topic 不进高/低频，只进 jd_required。"""
        items = [
            make_item("向量检索", source=ItemSource.JD, id_prefix="jd"),
        ]
        stats = build_market_stats(items)
        assert "向量检索" not in stats["high_freq_topics"]
        assert "向量检索" not in stats["low_freq_topics"]
        assert "向量检索" in stats["jd_required_topics"]

    def test_excludes_info_and_jd_from_freq_pool(self):
        """info 类题目和 JD 关键词不计入题库频率。"""
        items = [
            make_item("RAG"),
            make_item("RAG", category=ItemCategory.INFO, id_prefix="k3"),
            make_item("RAG", source=ItemSource.JD, id_prefix="jd"),
        ]
        stats = build_market_stats(items, high_freq_min=2)
        assert "RAG" in stats["low_freq_topics"]  # 池中只有 1 次

    def test_empty_topic_no_signal(self):
        item = make_item("")
        stats = build_market_stats([item])
        assert adjust_priority(item, stats) == 1.0


class TestApplyPriorities:
    def test_does_not_mutate_input(self):
        items = [make_item("RAG")]
        result = apply_priorities(items, STATS)
        assert items[0].priority == 1.0
        assert result[0].priority == pytest.approx(1.8)

    def test_applies_to_all(self):
        items = [make_item("RAG"), make_item("死锁"), make_item("合并数组")]
        result = apply_priorities(items, STATS)
        assert [round(r.priority, 2) for r in result] == [1.8, 0.5, 1.0]
