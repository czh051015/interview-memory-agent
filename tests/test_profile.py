"""用户画像测试：分层阈值、主题聚合、source 加权、冷启动、持久化。"""

import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from src.memory import profile as prof
from src.cleaner.schema import KnowledgeItem, ItemStatus, ItemSource


def _item(question, status="fail", mastery=0.3, days=10, topic="线程池",
          source=ItemSource.MOCK_INTERVIEW, tags=None):
    return KnowledgeItem(
        id=f"ki_{abs(hash(question)) % 100000}",
        question=question,
        topic=topic,
        status=ItemStatus(status),
        mastery_score=mastery,
        created_at=datetime.utcnow() - timedelta(days=days),
        source=source,
        behavior_tags=tags or [],
    )


def _patch_search(items):
    """store.search 按 status 分流。"""
    def fake_search(status, **kw):
        if status == "fail":
            return [it for it in items if it.status == ItemStatus.FAIL]
        if status == "partial":
            return [it for it in items if it.status == ItemStatus.PARTIAL]
        return []
    return patch.object(prof.store, "search", side_effect=fake_search)


class TestTiering:
    def test_stable_weak_by_fail_count(self):
        """同主题 2 次 fail → red 稳定弱点（即使 gap 小）。"""
        items = [
            _item("线程池核心参数", topic="线程池", mastery=0.9, days=1),   # gap 小
            _item("线程池拒绝策略", topic="线程池", mastery=0.9, days=1),
            _item("缓存雪崩", topic="缓存", mastery=0.9, days=1),           # 低 gap 不干扰
        ]
        with _patch_search(items):
            p = prof.build_profile("default", save=False)
        assert len(p.weak_topics) == 1
        assert p.weak_topics[0].topic == "线程池"
        assert p.weak_topics[0].tier == "red"
        assert p.weak_topics[0].raw_fail_count == 2

    def test_yellow_when_gap_high_but_single_fail(self):
        """单次 fail：gap 极大 → red（快忘了）；gap 中等 → yellow。"""
        items = [
            _item("死锁代码", topic="死锁", mastery=0.3, days=20),   # e^-1 ≈ 0.37 → gap≈0.63 red
            _item("HashMap", topic="HashMap", mastery=0.85, days=10),  # e^-0.5≈0.61 → gap≈0.39 yellow
        ]
        with _patch_search(items):
            p = prof.build_profile("default", save=False)
        tiers = {t.topic: t.tier for t in p.weak_topics}
        assert tiers.get("死锁") == "red"
        assert tiers.get("HashMap") == "yellow"


class TestSourceWeighting:
    def test_self_review_counts_more(self):
        """真实面经（SELF_REVIEW）加权 1.5：1 条真实 + 1 条模拟 = 2.5 ≥ 2 → red。"""
        items = [
            _item("线程池", topic="线程池", source=ItemSource.SELF_REVIEW),
            _item("线程池2", topic="线程池", source=ItemSource.MOCK_INTERVIEW),
        ]
        with _patch_search(items):
            p = prof.build_profile("default", save=False)
        t = p.weak_topics[0]
        assert t.weighted_fail == pytest.approx(2.5)
        assert t.tier == "red"

    def test_public_jingyan_weight_low(self):
        """网上面经权重 0.5：2 条 public 加权 1.0 < 2 → 不因次数判稳定弱点（gap 中等，不触发快忘了）。"""
        items = [
            # mastery=0.85, days=5 → e^-0.25≈0.78 → eff≈0.66 → gap≈0.34（yellow，且 5<7 不触发快忘了）
            _item("线程池", topic="线程池", source=ItemSource.PUBLIC_JINGYAN, mastery=0.85, days=5),
            _item("线程池2", topic="线程池", source=ItemSource.PUBLIC_JINGYAN, mastery=0.85, days=5),
        ]
        with _patch_search(items):
            p = prof.build_profile("default", save=False)
        assert p.weak_topics and p.weak_topics[0].topic == "线程池"
        assert p.weak_topics[0].weighted_fail == pytest.approx(1.0)
        assert p.weak_topics[0].tier != "red"  # 达不到稳定弱点（加权 1.0 < 2）


class TestAggregation:
    def test_topic_merge_and_representatives(self):
        """同主题合并：avg_gap 正确，代表题取 fail 中 gap 最大的。"""
        items = [
            _item("线程池A", topic="线程池", mastery=0.2, days=30),   # gap 大
            _item("线程池B", topic="线程池", mastery=0.5, days=3),    # gap 小
        ]
        with _patch_search(items):
            p = prof.build_profile("default", save=False)
        t = p.weak_topics[0]
        assert t.raw_fail_count == 2
        assert t.avg_gap == pytest.approx(round((1 - 0.2 * 0.223) + (1 - 0.5 * 0.861), 3) / 2, abs=0.1)
        assert t.representatives and t.representatives[0] == "线程池A"

    def test_behaviors_aggregated(self):
        """行为标签跨题聚合去重。"""
        items = [
            _item("题1", topic="线程池", tags=["表达绕弯"]),
            _item("题2", topic="死锁", tags=["表达绕弯", "回避问题"]),
        ]
        with _patch_search(items):
            p = prof.build_profile("default", save=False)
        assert set(p.behaviors) == {"表达绕弯", "回避问题"}


class TestColdStartAndPersistence:
    def test_empty_profile_cold_start(self):
        """冷启动：无错题 → 空画像，不崩。"""
        with _patch_search([]):
            p = prof.build_profile("default", save=False)
        assert p.empty
        assert p.to_prompt_text() == ""  # 降级：不注入

    def test_persist_and_load_roundtrip(self, tmp_path, monkeypatch):
        """画像落盘 + 读回（space 隔离）。"""
        monkeypatch.setattr(prof, "space_dir", lambda: tmp_path)
        items = [
            _item("线程池", topic="线程池"),
            _item("线程池2", topic="线程池"),
        ]
        with _patch_search(items):
            p = prof.build_profile("测试空间", save=True)
        assert (tmp_path / "profile.json").exists()

        loaded = prof.load_profile("测试空间")
        assert len(loaded.weak_topics) == len(p.weak_topics)
        assert loaded.weak_topics[0].topic == "线程池"
        assert loaded.weak_topics[0].tier == "red"
        assert loaded.behaviors == p.behaviors

    def test_load_corrupted_returns_empty(self, tmp_path, monkeypatch):
        """损坏的 profile.json → 空画像不抛异常。"""
        monkeypatch.setattr(prof, "space_dir", lambda: tmp_path)
        (tmp_path / "profile.json").write_text("{broken", encoding="utf-8")
        p = prof.load_profile("default")
        assert p.empty
