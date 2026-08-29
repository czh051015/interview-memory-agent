"""docs/13：采分点角度维度（point_type）与跨题型诊断测试。

覆盖：
  · score.Point 新增 type 字段 + from_benchmark 读取 point_type（§6.1）
  · cleaner decompose 透传 point_type 到 ReferencePoint（§6.2–6.4）
  · reflow 入库写 weak_points.point_type（§6.5–6.7）+ 老库迁移幂等
  · profile.stats_by_angle / diagnose 跨题型按角度聚合（§6.9 + §7）
  · react.search_questions 角度过滤（§6.11，为"练同类题"铺路）
"""

import sqlite3
from datetime import datetime
from unittest.mock import patch

import pytest

from src.cleaner.decompose import decompose_points
from src.shenlun.score import Point, from_benchmark
from src.shenlun import reflow
from src.shenlun import react
from src.shenlun.profile import WeakPoint, stats_by_angle, diagnose, stats
from src.shenlun.reflow import reflow_answer, STATE_ACTIVE

# 带 point_type 的采分点（模拟 LLM 拆解标注）
REFS = [
    {"id": "c1", "point": "对策可行性", "keywords": ["配套", "落地"], "score": 3, "point_type": "对策"},
    {"id": "c2", "point": "现状问题", "keywords": ["短板"], "score": 3, "point_type": "问题"},
]


@pytest.fixture()
def db(tmp_path):
    """每个测试用独立临时 DB（不污染 data/shenlun.db）。"""
    old_path = reflow.DB_PATH
    reflow.DB_PATH = tmp_path / "test_point_type.db"
    yield
    reflow.DB_PATH = old_path  # profile 读同一库（profile 复用 reflow._conn，无需单独改）


def make_wp(label="对策可行性", qtype="提出对策", point_type="对策", miss=2, question_id="q_test"):
    return WeakPoint(
        point_key=f"{question_id}:c1", label=label, qtype=qtype, point_type=point_type,
        question_id=question_id, miss_count=miss, hit_count=1, last_miss_at=None,
        state=STATE_ACTIVE, tier="red" if miss >= 2 else "yellow",
        created_at=datetime.utcnow().isoformat(),
        last_practiced_at=datetime.utcnow().isoformat(),
    )


# ── §6.1–6.2 评分引擎 ───────────────────────────────────
class TestPointTypeScore:
    def test_point_has_type_field(self):
        assert Point(id="c1", point="x", keywords=["k"], type="对策").type == "对策"

    def test_from_benchmark_carries_type(self):
        pts = from_benchmark(REFS)
        assert pts[0].type == "对策"
        assert pts[1].type == "问题"

    def test_from_benchmark_defaults_empty(self):
        pts = from_benchmark([{"id": "c1", "point": "x", "keywords": ["k"]}])
        assert pts[0].type == ""


# ── §6.2–6.4 拆解透传 ─────────────────────────────────────
class TestDecomposeCarriesType:
    def test_decompose_points_passes_point_type(self):
        llm_out = {
            "reference_points": [
                {"point": "对策可行性", "keywords": ["配套"], "score": 3, "point_type": "对策"},
            ],
        }
        with patch("src.cleaner.decompose.chat_json", return_value=llm_out):
            result = decompose_points("标答", question="题")
        assert result.reference_points[0].point_type == "对策"


# ── §6.5–6.7 入库写库 + 迁移 ──────────────────────────────
class TestUpsertAndMigration:
    def test_reflow_stores_point_type(self, db):
        reflow_answer("q_test", "提出对策", "加强设施配套", REFS)
        conn = reflow._conn()
        try:
            row = conn.execute(
                "SELECT point_type FROM weak_points WHERE point_key=?",
                ("q_test:c1",),
            ).fetchone()
        finally:
            conn.close()
        assert row["point_type"] == "对策"

    def test_migration_idempotent(self, db):
        # 模拟老库（无 point_type 列），_conn 迁移自动补列且二次连接幂等
        conn = sqlite3.connect(str(reflow.DB_PATH))
        conn.executescript(
            "CREATE TABLE weak_points (point_key TEXT PRIMARY KEY, label TEXT, qtype TEXT,"
            " question_id TEXT, miss_count INTEGER, hit_count INTEGER, created_at TEXT, state TEXT);"
        )
        conn.commit()
        conn.close()
        conn = reflow._conn()
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(weak_points)").fetchall()}
        finally:
            conn.close()
        assert "point_type" in cols
        reflow._conn().close()  # 再连一次不报错，幂等


# ── §6.9 + §7 聚合诊断 ────────────────────────────────────
class TestAggregation:
    @patch("src.shenlun.profile.read_all_weak_points", return_value=[
        make_wp(point_type="对策"), make_wp(point_type="对策"), make_wp(point_type="问题"),
    ])
    def test_stats_by_angle(self, _):
        out = stats_by_angle()
        assert out["by_angle"]["对策"]["total"] == 2
        assert out["by_angle"]["问题"]["total"] == 1
        assert out["total_points"] == 3

    @patch("src.shenlun.profile.read_all_weak_points", return_value=[])
    def test_diagnose_empty(self, _):
        out = diagnose()
        assert out == {"by_type": {}, "by_angle": {}, "total_points": 0}

    @patch("src.shenlun.profile.read_all_weak_points", return_value=[
        make_wp(qtype="提出对策", point_type="对策", miss=3),
        make_wp(qtype="提出对策", point_type="对策", miss=2),
        make_wp(qtype="归纳概括", point_type="问题", miss=2),
    ])
    def test_diagnose_has_both_layers(self, _):
        out = diagnose()
        assert out["by_type"]["提出对策"]["total"] == 2
        assert out["by_type"]["归纳概括"]["total"] == 1
        assert out["by_angle"]["对策"]["total"] == 2
        assert out["by_angle"]["问题"]["total"] == 1
        assert out["total_points"] == 3


# ── §6.11 角度过滤 ─────────────────────────────────────────
class TestSearchByAngle:
    BANK = [
        {"id": "q1", "type": "提出对策", "province": "X", "year": 2023, "question": "提对策"},
        {"id": "q2", "type": "提出对策", "province": "Y", "year": 2024, "question": "提对策"},
    ]
    GOLD = {
        "q1": {"gold": {"reference_points": [{"point_type": "对策"}]}},
        "q2": {"gold": {"reference_points": [{"point_type": "问题"}]}},
    }

    @patch("src.shenlun.react.list_questions", return_value=BANK)
    @patch("src.shenlun.react.load_question", side_effect=lambda qid: TestSearchByAngle.GOLD[qid])
    def test_filters_by_angle(self, _load, _list):
        cands = react.search_questions([make_wp(point_type="对策")])
        assert [q["id"] for q in cands] == ["q1"]

    @patch("src.shenlun.react.list_questions", return_value=[
        {"id": "q1", "type": "归纳概括", "province": "X", "year": 2023, "question": "概括"},
    ])
    @patch("src.shenlun.react.load_question",
           return_value={"gold": {"reference_points": []}})
    def test_no_angle_match_keeps_type_filter(self, _load, _list):
        # 库题无 point_type → 退回题型过滤，不丢候选
        cands = react.search_questions([make_wp(qtype="归纳概括", point_type="对策")])
        assert [q["id"] for q in cands] == ["q1"]