"""docs/18 §5：answer_rounds 逼近轨迹表 + answers 补列 + 老库迁移。

覆盖：
  · reflow_answer 带 rounds → 1 行 answers（rounds/initial_hit_ratio）+ N 行 answer_rounds
  · 不带 rounds → 单次作答（rounds=1，initial_hit_ratio=终稿命中率），answer_rounds 无行
  · 老库迁移：缺列补齐、旧数据不丢、老作答 initial_hit_ratio 回填 = hit_ratio
  · list_answer_rounds 轨迹读取
"""

import sqlite3

import pytest

from src.shenlun import reflow
from src.shenlun.reflow import reflow_answer, list_answer_rounds

# 单题采分点（3 个，便于分别控制 hit/miss）
REFS = [
    {"id": "c1", "point": "六尺巷·化解纠纷", "keywords": ["六尺巷"], "score": 3},
    {"id": "c2", "point": "河长制·治水", "keywords": ["河长"], "score": 3},
    {"id": "c3", "point": "生态理念·象群", "keywords": ["象群"], "score": 4},
]

# 一次 3 轮逼近的完整轨迹（轮0 初稿 → 轮2 补全）
ROUNDS = [
    {"round_no": 0, "answer": "六尺巷", "hit_ids": ["c1"], "miss_ids": ["c2", "c3"],
     "hit_ratio": 1 / 3, "guided_point_ids": []},
    {"round_no": 1, "answer": "六尺巷 河长", "hit_ids": ["c1", "c2"], "miss_ids": ["c3"],
     "hit_ratio": 2 / 3, "guided_point_ids": ["c2"]},
    {"round_no": 2, "answer": "六尺巷 河长 象群", "hit_ids": ["c1", "c2", "c3"], "miss_ids": [],
     "hit_ratio": 1.0, "guided_point_ids": ["c3"]},
]


@pytest.fixture()
def db(tmp_path):
    """每个测试用独立临时 DB（不污染 data/shenlun.db）。"""
    old_path = reflow.DB_PATH
    reflow.DB_PATH = tmp_path / "test_rounds.db"
    yield tmp_path / "test_rounds.db"
    reflow.DB_PATH = old_path


def _row(conn, sql, args=()):
    conn.row_factory = sqlite3.Row
    r = conn.execute(sql, args).fetchone()
    return dict(r) if r else None


class TestAnswerRounds:
    def test_reflow_with_rounds_writes_trajectory(self, db):
        """带轨迹回流：1 行 answers + 3 行 answer_rounds，rounds/initial_hit_ratio 正确。"""
        r = reflow_answer("jiangsu_2023_a_1", "归纳概括", ROUNDS[2]["answer"], REFS, rounds=ROUNDS)
        assert r.answer_id is not None
        conn = sqlite3.connect(str(db))
        a = _row(conn, "SELECT * FROM answers WHERE id=?", (r.answer_id,))
        assert a["rounds"] == 3
        assert a["initial_hit_ratio"] == pytest.approx(round(1 / 3, 4))  # 初稿命中率（4 位存储）
        assert a["hit_ratio"] == pytest.approx(1.0)  # 终稿命中率
        rows = [dict(x) for x in conn.execute(
            "SELECT * FROM answer_rounds WHERE answer_id=? ORDER BY round_no", (r.answer_id,))]
        conn.close()
        assert [x["round_no"] for x in rows] == [0, 1, 2]
        assert rows[1]["guided_point_ids"] == '["c2"]'   # JSON 存储
        assert rows[2]["miss_ids"] == "[]"

    def test_reflow_without_rounds_is_single_shot(self, db):
        """不带轨迹：单次作答，rounds=1，initial_hit_ratio=终稿命中率，answer_rounds 无行。"""
        r = reflow_answer("jiangsu_2023_a_1", "归纳概括", "六尺巷 河长", REFS)
        conn = sqlite3.connect(str(db))
        a = _row(conn, "SELECT * FROM answers WHERE id=?", (r.answer_id,))
        assert a["rounds"] == 1
        assert a["initial_hit_ratio"] == pytest.approx(round(2 / 3, 4))
        cnt = conn.execute("SELECT COUNT(*) FROM answer_rounds WHERE answer_id=?", (r.answer_id,)).fetchone()[0]
        conn.close()
        assert cnt == 0

    def test_list_answer_rounds_roundtrip(self, db):
        """list_answer_rounds 读出完整轨迹（供诊断/可视化）。"""
        r = reflow_answer("jiangsu_2023_a_1", "归纳概括", ROUNDS[2]["answer"], REFS, rounds=ROUNDS)
        rows = list_answer_rounds(r.answer_id)
        assert [x["round_no"] for x in rows] == [0, 1, 2]
        assert rows[0]["answer"] == "六尺巷"
        assert rows[1]["guided_point_ids"] == '["c2"]'

    def test_weak_points_new_columns_default_zero(self, db):
        """weak_points 补列 guided_count/rescue_rounds_sum 存在且默认 0。"""
        reflow_answer("jiangsu_2023_a_1", "归纳概括", "六尺巷 河长 象群", REFS)
        conn = sqlite3.connect(str(db))
        w = _row(conn, "SELECT * FROM weak_points WHERE point_key=?", ("jiangsu_2023_a_1:c1",))
        conn.close()
        assert w["guided_count"] == 0
        assert w["rescue_rounds_sum"] == 0


class TestOldDbMigration:
    def test_old_db_migrates_without_data_loss(self, tmp_path):
        """docs/17 时代的老库：迁移补齐 4 表 + 新列，旧数据一行不丢。"""
        db = tmp_path / "old.db"
        conn = sqlite3.connect(str(db))
        conn.executescript("""
            CREATE TABLE answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT, question_id TEXT NOT NULL,
                answer TEXT NOT NULL, hit_ids TEXT NOT NULL DEFAULT '[]',
                miss_ids TEXT NOT NULL DEFAULT '[]', hit_ratio REAL NOT NULL DEFAULT 0, ts TEXT NOT NULL);
            CREATE TABLE weak_points (
                point_key TEXT PRIMARY KEY, label TEXT NOT NULL, qtype TEXT NOT NULL DEFAULT '',
                question_id TEXT NOT NULL, miss_count INTEGER NOT NULL DEFAULT 0,
                hit_count INTEGER NOT NULL DEFAULT 0, last_miss_at TEXT, created_at TEXT NOT NULL);
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, question_id TEXT NOT NULL,
                answer_id INTEGER NOT NULL, action TEXT NOT NULL, ratio REAL NOT NULL, ts TEXT NOT NULL);
            INSERT INTO answers(question_id,answer,hit_ids,miss_ids,hit_ratio,ts)
                VALUES('q1','旧作答','["c1"]','[]',0.5,'2026-01-01T00:00:00');
            INSERT INTO weak_points(point_key,label,qtype,question_id,miss_count,hit_count,created_at)
                VALUES('q1:c1','点1','t','q1',0,1,'2026-01-01T00:00:00');
            INSERT INTO events(question_id,answer_id,action,ratio,ts)
                VALUES('q1',1,'answered',0.5,'2026-01-01T00:00:00');
        """)
        conn.commit()
        conn.close()

        old_path = reflow.DB_PATH
        reflow.DB_PATH = db
        try:
            conn = reflow._conn()  # 触发迁移
            conn.row_factory = sqlite3.Row
            # 旧数据不丢
            a = conn.execute("SELECT * FROM answers").fetchone()
            assert a["answer"] == "旧作答"
            w = conn.execute("SELECT * FROM weak_points").fetchone()
            assert w["label"] == "点1"
            e = conn.execute("SELECT * FROM events").fetchone()
            assert e["action"] == "answered"
            # 新列补齐 + 老作答初稿=终稿
            assert a["rounds"] == 1
            assert a["initial_hit_ratio"] == pytest.approx(0.5)
            assert w["state"] == "active"
            assert w["guided_count"] == 0
            assert w["rescue_rounds_sum"] == 0
            # 新表已建
            assert conn.execute("SELECT COUNT(*) FROM answer_rounds").fetchone()[0] == 0
            conn.close()
        finally:
            reflow.DB_PATH = old_path

    def test_migrated_db_still_writeable(self, tmp_path):
        """迁移后的库能正常回流（含带 rounds 的新路径）。"""
        old_path = reflow.DB_PATH
        reflow.DB_PATH = tmp_path / "old2.db"
        try:
            # 先造一个老结构库（只建 answers 老结构）
            conn = sqlite3.connect(str(reflow.DB_PATH))
            conn.execute("CREATE TABLE answers (id INTEGER PRIMARY KEY AUTOINCREMENT, question_id TEXT NOT NULL,"
                         " answer TEXT NOT NULL, hit_ids TEXT NOT NULL DEFAULT '[]',"
                         " miss_ids TEXT NOT NULL DEFAULT '[]', hit_ratio REAL NOT NULL DEFAULT 0, ts TEXT NOT NULL)")
            conn.commit()
            conn.close()
            r = reflow_answer("q1", "t", "六尺巷 河长 象群", REFS, rounds=ROUNDS)
            rows = list_answer_rounds(r.answer_id)
            assert len(rows) == 3
        finally:
            reflow.DB_PATH = old_path
