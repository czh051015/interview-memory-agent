"""docs/17：memory 记忆生命周期（提醒池/毕业/stuck/pin）测试。

覆盖：
  · 紧急度公式排序（miss_count 相同但更久没练 → 排更前）
  · 提醒池过滤（graduated/stuck 不进池，pinned 进池）
  · 毕业判定 is_graduate_candidate（连续命中 + 间隔）
  · 落库状态流转（consecutive_hits 累计/归零、复活、stuck 触发）
  · 毕业考写库（mark_graduated）+ events action
"""

import sqlite3
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from src.shenlun import reflow
from src.shenlun import profile
from src.shenlun.profile import (
    WeakPoint,
    is_graduate_candidate,
    read_weak_points,
    read_all_weak_points,
)
from src.shenlun.reflow import (
    reflow_answer,
    mark_graduated,
    mark_pinned,
    graduate_hits,
    STATE_ACTIVE,
    STATE_GRADUATED,
    STATE_STUCK,
    STATE_PINNED,
    ACTION_GRADUATION_CHECK,
    ACTION_REVIVE,
)

# 单题采分点（3 个，便于分别控制 hit/miss）
REFS = [
    {"id": "c1", "point": "六尺巷·化解纠纷", "keywords": ["六尺巷"], "score": 3},
    {"id": "c2", "point": "河长制·治水", "keywords": ["河长"], "score": 3},
    {"id": "c3", "point": "生态理念·象群", "keywords": ["象群"], "score": 4},
]


@pytest.fixture()
def db(tmp_path):
    """每个测试用独立临时 DB（不污染 data/shenlun.db）。"""
    old_path = reflow.DB_PATH
    reflow.DB_PATH = tmp_path / "test_shenlun.db"
    profile.DB_PATH = reflow.DB_PATH
    # 清掉 profile 模块缓存引用（_conn 每次现读 DB_PATH）
    yield tmp_path / "test_shenlun.db"
    reflow.DB_PATH = old_path
    profile.DB_PATH = old_path


def _answer(db, text, *, qid="jiangsu_2023_a_1", qtype="归纳概括", action="answered"):
    """一行便捷作答：返回 (ReflowResult, 各点 hit 情况)。"""
    return reflow_answer(qid, qtype, text, REFS, action=action)


def _row(db, key):
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        r = conn.execute("SELECT * FROM weak_points WHERE point_key=?", (key,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


# ── 紧急度公式 + 提醒池 ──────────────────────────────────────────
class TestUrgency:
    def test_miss_count_same_older_practiced_ranks_first(self, db):
        """同样漏 1 次：8 天没练的点应排 2 天没练的点前面（遗忘程度更高）。"""
        _answer(db, "有六尺巷但没河长没象群")          # c1 hit, c2/c3 miss
        row = _row(db, "jiangsu_2023_a_1:c2")
        # 手动把 c2 的 last_practiced_at 改到 8 天前，c3 保持现在
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        conn.execute(
            "UPDATE weak_points SET last_practiced_at=? WHERE point_key=?",
            ((datetime.utcnow() - timedelta(days=8)).isoformat(), "jiangsu_2023_a_1:c2"),
        )
        conn.commit()
        conn.close()

        pts = read_weak_points()
        keys = [wp.point_key for wp in pts]
        assert keys.index("jiangsu_2023_a_1:c2") < keys.index("jiangsu_2023_a_1:c3")

    def test_forgetting_formula(self, db):
        """遗忘程度 = 1 - e^(-0.05·days)：0 天≈0，14 天≈0.5。"""
        wp = WeakPoint(point_key="k", label="l", qtype="t", question_id="q",
                       miss_count=1, hit_count=0, last_miss_at=None)
        assert wp.forgetting() < 0.01  # 没练过按 created_at=None → 0 天
        wp2 = WeakPoint(point_key="k2", label="l", qtype="t", question_id="q",
                        miss_count=1, hit_count=0, last_miss_at=None,
                        last_practiced_at=(datetime.utcnow() - timedelta(days=14)).isoformat())
        assert abs(wp2.forgetting() - (1 - __import__("math").exp(-0.05 * 14))) < 1e-6

    def test_graduated_not_in_reminder_pool(self, db):
        """毕业点不进提醒池；stuck 点也不进；pinned 点进。"""
        _answer(db, "六尺巷河长象群")  # 全命中
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE weak_points SET state=? WHERE point_key=?",
                     (STATE_GRADUATED, "jiangsu_2023_a_1:c1"))
        conn.execute("UPDATE weak_points SET state=? WHERE point_key=?",
                     (STATE_STUCK, "jiangsu_2023_a_1:c2"))
        conn.execute("UPDATE weak_points SET state=? WHERE point_key=?",
                     (STATE_PINNED, "jiangsu_2023_a_1:c3"))
        conn.commit()
        conn.close()

        keys = {wp.point_key for wp in read_weak_points()}
        assert "jiangsu_2023_a_1:c1" not in keys
        assert "jiangsu_2023_a_1:c2" not in keys
        assert "jiangsu_2023_a_1:c3" in keys  # pinned 在提醒池（用户想一直练）
        # 完整档案全在
        all_keys = {wp.point_key for wp in read_all_weak_points()}
        assert all_keys == {"jiangsu_2023_a_1:c1", "jiangsu_2023_a_1:c2", "jiangsu_2023_a_1:c3"}


# ── 毕业判定 ─────────────────────────────────────────────────────
class TestGraduation:
    def _wp(self, consec=3, last_hit_days_ago=7, state=STATE_ACTIVE):
        return WeakPoint(
            point_key="k", label="l", qtype="t", question_id="q",
            miss_count=1, hit_count=3, last_miss_at=None,
            state=state, consecutive_hits=consec,
            last_hit_at=(datetime.utcnow() - timedelta(days=last_hit_days_ago)).isoformat(),
        )

    def test_candidate_when_consecutive_and_spacing_met(self):
        assert is_graduate_candidate(self._wp(consec=3, last_hit_days_ago=7))

    def test_not_candidate_when_consecutive_short(self):
        assert not is_graduate_candidate(self._wp(consec=2, last_hit_days_ago=7))

    def test_not_candidate_when_spacing_not_met(self):
        assert not is_graduate_candidate(self._wp(consec=3, last_hit_days_ago=1))

    def test_not_candidate_when_graduated(self):
        assert not is_graduate_candidate(self._wp(state=STATE_GRADUATED))

    def test_graduation_candidates_lists_only_eligible(self, db):
        """真实库：c1 连续 3 命中 + 7 天未验证 → 候选；c2 刚命中 → 非候选。"""
        _answer(db, "六尺巷 河长")  # c1/c2 hit, c3 miss
        _answer(db, "六尺巷 河长")
        _answer(db, "六尺巷 河长")
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE weak_points SET last_hit_at=?, last_practiced_at=? WHERE point_key=?",
                     ((datetime.utcnow() - timedelta(days=8)).isoformat(),
                      (datetime.utcnow() - timedelta(days=8)).isoformat(),
                      "jiangsu_2023_a_1:c1"))
        conn.commit()
        conn.close()
        cands = profile.graduation_candidates()
        keys = [wp.point_key for wp in cands]
        assert "jiangsu_2023_a_1:c1" in keys
        assert "jiangsu_2023_a_1:c2" not in keys  # 刚命中，间隔未到


# ── 落库状态流转 ─────────────────────────────────────────────────
class TestReflowLifecycle:
    def test_consecutive_hits_accumulate_and_reset(self, db):
        """连续命中累计；漏一次归零。"""
        _answer(db, "六尺巷 河长")   # c1 hit
        _answer(db, "六尺巷 河长")   # c1 hit
        assert _row(db, "jiangsu_2023_a_1:c1")["consecutive_hits"] == 2
        _answer(db, "河长 象群")      # c1 miss（不含六尺巷），c2/c3 hit
        assert _row(db, "jiangsu_2023_a_1:c1")["consecutive_hits"] == 0
        assert _row(db, "jiangsu_2023_a_1:c1")["hit_count"] == 2

    def test_graduated_revives_on_miss(self, db):
        """毕业点再 miss → 复活回 active，events 记 revive。"""
        _answer(db, "六尺巷 河长")
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE weak_points SET state=? WHERE point_key=?",
                     (STATE_GRADUATED, "jiangsu_2023_a_1:c1"))
        conn.commit()
        conn.close()
        result = _answer(db, "什么都没有")  # c1 miss
        row = _row(db, "jiangsu_2023_a_1:c1")
        assert row["state"] == STATE_ACTIVE
        assert result.revived is True
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        actions = [r["action"] for r in conn.execute("SELECT action FROM events").fetchall()]
        conn.close()
        assert ACTION_REVIVE in actions

    def test_stuck_triggered_after_max_attempts(self, db):
        """尝试 ≥ MAX_ATTEMPTS 仍未毕业（连续命中不达标）→ 自动 stuck。"""
        # 用很小阈值避免真的练 30 轮
        old = reflow.MAX_ATTEMPTS
        reflow.MAX_ATTEMPTS = 3
        try:
            _answer(db, "六尺巷")   # 全 miss（故意不含关键词）
            _answer(db, "六尺巷")
            _answer(db, "六尺巷")
            assert _row(db, "jiangsu_2023_a_1:c2")["state"] == STATE_STUCK
        finally:
            reflow.MAX_ATTEMPTS = old

    def test_stuck_not_triggered_when_on_graduation_track(self, db):
        """attempts 达标但连续命中达标（在毕业轨道）→ 不 stuck。"""
        old = reflow.MAX_ATTEMPTS
        reflow.MAX_ATTEMPTS = 2
        try:
            _answer(db, "六尺巷 河长 象群")
            _answer(db, "六尺巷 河长 象群")
            assert _row(db, "jiangsu_2023_a_1:c1")["state"] == STATE_ACTIVE
        finally:
            reflow.MAX_ATTEMPTS = old

    def test_mark_graduated_and_pinned(self, db):
        """mark_graduated/mark_pinned 状态写回。"""
        _answer(db, "六尺巷 河长")
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        assert mark_graduated(conn, "jiangsu_2023_a_1", "c1") is True
        assert mark_pinned(conn, "jiangsu_2023_a_1", "c2", pinned=True) is True
        conn.commit()
        conn.close()
        assert _row(db, "jiangsu_2023_a_1:c1")["state"] == STATE_GRADUATED
        assert _row(db, "jiangsu_2023_a_1:c2")["state"] == STATE_PINNED
        # 毕业的点不在提醒池
        keys = {wp.point_key for wp in read_weak_points()}
        assert "jiangsu_2023_a_1:c1" not in keys
        assert "jiangsu_2023_a_1:c2" in keys  # pinned 还在提醒池

    def test_graduation_check_event_action(self, db):
        """action=graduation_check 的作答 → events 记 graduation_check。"""
        _answer(db, "六尺巷 河长 象群", action=ACTION_GRADUATION_CHECK)
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        actions = [r["action"] for r in conn.execute("SELECT action FROM events").fetchall()]
        conn.close()
        assert ACTION_GRADUATION_CHECK in actions

    def test_graduate_hits_only_candidates(self, db):
        """毕业考命中即毕业：作答前是候选且本次命中 → graduated；非候选不动。"""
        # 先攒候选：c1/c2 连续命中 3 次，再把 c1 的 last_hit_at 拨到 8 天前（满足间隔）
        for _ in range(3):
            _answer(db, "六尺巷 河长")
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        conn.execute(
            "UPDATE weak_points SET last_hit_at=? WHERE point_key=?",
            ((datetime.utcnow() - timedelta(days=8)).isoformat(), "jiangsu_2023_a_1:c1"),
        )
        conn.commit()
        conn.close()

        from src.shenlun.profile import graduation_candidates
        cand_keys = {wp.point_key for wp in graduation_candidates()}
        assert "jiangsu_2023_a_1:c1" in cand_keys   # c1 达标（连续3+间隔8天）
        assert "jiangsu_2023_a_1:c2" not in cand_keys  # c2 刚命中，间隔未到

        # 毕业考作答：c1/c2 都命中 → 只 c1 毕业
        r = _answer(db, "六尺巷 河长", action=ACTION_GRADUATION_CHECK)
        graduated = graduate_hits("jiangsu_2023_a_1", r.result.hit_ids, cand_keys)
        assert graduated == ["c1"]
        assert _row(db, "jiangsu_2023_a_1:c1")["state"] == STATE_GRADUATED
        assert _row(db, "jiangsu_2023_a_1:c2")["state"] == STATE_ACTIVE

    def test_graduate_hits_miss_keeps_active(self, db):
        """毕业考 miss → 不毕业，consecutive_hits 归零重来（可再攒）。"""
        for _ in range(3):
            _answer(db, "六尺巷 河长")
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        conn.execute(
            "UPDATE weak_points SET last_hit_at=? WHERE point_key=?",
            ((datetime.utcnow() - timedelta(days=8)).isoformat(), "jiangsu_2023_a_1:c1"),
        )
        conn.commit()
        conn.close()
        cand_keys = {wp.point_key for wp in profile.graduation_candidates()}

        r = _answer(db, "河长 象群")  # c1 miss（毕业考失败）
        graduated = graduate_hits("jiangsu_2023_a_1", r.result.hit_ids, cand_keys)
        assert graduated == []
        row = _row(db, "jiangsu_2023_a_1:c1")
        assert row["state"] == STATE_ACTIVE
        assert row["consecutive_hits"] == 0  # 归零，重来
