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
    build_topic_ranking,
    adjust_priority,
    apply_priorities,
)


def make_item(topic: str, *, status=ItemStatus.FAIL, source=ItemSource.SELF_REVIEW,
              category=ItemCategory.KNOWLEDGE, id_prefix="ki", company: str = "",
              role: str = "") -> KnowledgeItem:
    return KnowledgeItem(
        id=f"{id_prefix}_t_{abs(hash(topic)) % 1000:03d}",
        question=f"题目 {topic}",
        topic=topic,
        category=category,
        status=status,
        source=source,
        company=company,
        role=role,
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

    def test_whitespace_insensitive(self):
        # "Prompt 工程"（JD 原文带空格）与 "Prompt工程"（清洗后）视为同一 topic
        assert _topics_match("Prompt 工程", "Prompt工程")
        assert _topics_match("R A G", "RAG")


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

    def test_bridge_keyword_merges_multiple_clusters(self):
        """回归：JD 关键词 'Agent' 同时命中多个 cluster 时全部合并。

        否则贪心只桥接第一个，'Agent设计' 会被漏掉（E2E 实测发现）。
        """
        items = [
            make_item("Agent记忆"),
            make_item("Agent设计"),
            make_item("Agent", source=ItemSource.JD, id_prefix="jd"),
        ]
        stats = build_market_stats(items, high_freq_min=2)
        assert "Agent记忆" in stats["high_freq_topics"]
        assert "Agent设计" in stats["high_freq_topics"]
        assert "Agent设计" in stats["jd_required_topics"]

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



class TestBuildTopicRanking:
    """高频考点榜：聚类合并 / 题库口径 / 排序 / top_n。"""

    def test_merges_spellings_and_counts_companies(self):
        items = [
            make_item("RAG", company="腾讯", role="AI应用开发"),
            make_item("RAG", company="腾讯", role="AI应用开发"),
            make_item("RAG检索增强", company="字节", role="AI应用工程师"),
            make_item("线程池", company="字节"),
        ]
        ranking = build_topic_ranking(items)
        assert ranking[0]["topic"] == "RAG"  # 出现最多的拼写作展示名
        assert ranking[0]["count"] == 3
        assert ranking[0]["company_count"] == 2
        assert set(ranking[0]["companies"]) == {"腾讯", "字节"}
        assert ranking[0]["role_count"] == 2
        assert set(ranking[0]["roles"]) == {"AI应用开发", "AI应用工程师"}
        assert ranking[1]["topic"] == "线程池"
        assert ranking[1]["count"] == 1
        assert ranking[1]["companies"] == ["字节"]

    def test_filters_jd_info_and_empty_topic(self):
        items = [
            make_item("RAG"),
            make_item("RAG", source=ItemSource.JD),       # JD 关键词不是"题"
            make_item("RAG", category=ItemCategory.INFO),  # info 类不计入
            KnowledgeItem(id="x_empty", question="q", topic="", source=ItemSource.PUBLIC_JINGYAN),
        ]
        ranking = build_topic_ranking(items)
        assert len(ranking) == 1
        assert ranking[0]["topic"] == "RAG"
        assert ranking[0]["count"] == 1

    def test_public_jingyan_included(self):
        ranking = build_topic_ranking(
            [make_item("RAG", source=ItemSource.PUBLIC_JINGYAN, company="FOSHO")]
        )
        assert len(ranking) == 1
        assert ranking[0]["count"] == 1
        assert ranking[0]["companies"] == ["FOSHO"]

    def test_sorted_by_count_desc_then_topic(self):
        items = [make_item("低频"), make_item("高频"), make_item("高频")]
        assert [r["topic"] for r in build_topic_ranking(items)] == ["高频", "低频"]
        # 并列按 topic 字典序
        tie = build_topic_ranking([make_item("B题"), make_item("A题")])
        assert [r["topic"] for r in tie] == ["A题", "B题"]

    def test_top_n(self):
        items = [make_item(t) for t in ["A", "A", "B", "C", "D"]]
        assert len(build_topic_ranking(items, top_n=2)) == 2

    def test_role_dimension_filters_empty(self):
        """岗位维度：非空 role 才计入，榜单行带 roles/role_count。"""
        ranking = build_topic_ranking([
            make_item("RAG", company="腾讯", role="AI应用开发"),
            make_item("RAG", company="字节", role=""),  # 空 role 不计入
        ])
        row = ranking[0]
        assert row["role_count"] == 1
        assert row["roles"] == ["AI应用开发"]
