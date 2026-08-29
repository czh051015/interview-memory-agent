"""错题回流 —— 作答即入库（agent 自动采集，非手动录入）。

数据流：用户作答 → 评分传感器(hit/miss) → 结构化入库（answers 表 + 薄弱点档案）。

存储：SQLite（data/shenlun.db），四张表：
  answers      一次作答记录（question_id, answer, hit_ids, miss_ids, ratio, ts
               + rounds 逼近总轮数、initial_hit_ratio 初稿命中率——docs/18 §5）
  answer_rounds 逼近轨迹：一次练习 1 行 answers + N 轮 N 行（初稿 0..N-1）
  weak_points  采分点级薄弱档案（point_key, label, type, miss/hit 计数 + 记忆生命周期字段）
  events       复习/作答事件（供时间序列与诊断）

设计：评分=确定性工具（可 benchmark）；错题回流=纯确定性流水线，不调 LLM。
薄弱点聚合到「采分点」而非「题目」——这是后续 ReAct 推荐和记忆提醒的记忆单元。

记忆生命周期（docs/17）：
  state=active    在提醒池，正常参与 topK 提醒
  state=graduated 毕业：连续命中+间隔验证通过，移出提醒池（档案保留）
  state=stuck     隔离：尝试 ≥ max_attempts 未毕业，防死锁（档案保留）
  state=pinned    用户手动钉住：否决自动毕业，一直留在提醒池
  复活：graduated/stuck 的点再 miss → 回 active（events 记 revive）
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from src.config import DATA_DIR, PROJECT_ROOT
from src.cleaner.schema import utcnow
from src.shenlun.score import Point, ScoreResult, score_answer, from_benchmark

DB_PATH = DATA_DIR / "shenlun.db"

# 题库两个目录（docs/16 §4.1）：官方金标（训练用，不动）+ 用户人审通过题（新增）
BENCHMARK_DIR = PROJECT_ROOT / "benchmark" / "data"
USER_QUESTIONS_DIR = DATA_DIR / "user_questions"

# ── 记忆生命周期状态（docs/17 §3）──
STATE_ACTIVE = "active"
STATE_GRADUATED = "graduated"
STATE_STUCK = "stuck"
STATE_PINNED = "pinned"
_STATES = {STATE_ACTIVE, STATE_GRADUATED, STATE_STUCK, STATE_PINNED}

# 毕业/隔离判定参数（初值待校准：结构先定死，数字跑起来再调）
GRADUATE_CONSECUTIVE_HITS = 3   # 连续命中 ≥ 3 次
GRADUATE_SPACING_DAYS = 7.0     # 距 last_hit_at ≥ 7 天才能安排毕业考（间隔验证）
MAX_ATTEMPTS = 30               # 尝试 ≥ 30 轮仍无法毕业 → stuck（防死锁）

# events.action 枚举：answered=常规作答 / graduation_check=毕业考 / revive=复活
ACTION_ANSWERED = "answered"
ACTION_GRADUATION_CHECK = "graduation_check"
ACTION_REVIVE = "revive"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id TEXT NOT NULL,
    answer TEXT NOT NULL,
    hit_ids TEXT NOT NULL DEFAULT '[]',
    miss_ids TEXT NOT NULL DEFAULT '[]',
    hit_ratio REAL NOT NULL DEFAULT 0,
    ts TEXT NOT NULL,
    rounds INTEGER NOT NULL DEFAULT 1,             -- 逼近总轮数（1=单次作答无逼近，docs/18 §5）
    initial_hit_ratio REAL NOT NULL DEFAULT 0      -- 初稿命中率（算逼近增益用）
);
CREATE TABLE IF NOT EXISTS answer_rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    answer_id INTEGER NOT NULL,                    -- 关联 answers.id
    round_no INTEGER NOT NULL,                     -- 0=初稿, 1..N=每轮逼近
    answer TEXT NOT NULL,                          -- 该轮答案
    hit_ids TEXT NOT NULL DEFAULT '[]',
    miss_ids TEXT NOT NULL DEFAULT '[]',
    hit_ratio REAL NOT NULL DEFAULT 0,
    guided_point_ids TEXT NOT NULL DEFAULT '[]',   -- 该轮 AI 引导了哪些点
    ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS weak_points (
    point_key TEXT PRIMARY KEY,          -- "{question_id}:{point_id}"
    label TEXT NOT NULL,                 -- 采分点名称（如 "设施互通"）
    qtype TEXT NOT NULL DEFAULT '',      -- 题型（归纳概括/综合分析/...）
    point_type TEXT NOT NULL DEFAULT '', -- 采分角度（docs/13 §5.4，拆解时 LLM 标注，展示/诊断用）
    question_id TEXT NOT NULL,
    miss_count INTEGER NOT NULL DEFAULT 0,
    hit_count INTEGER NOT NULL DEFAULT 0,
    last_miss_at TEXT,
    created_at TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'active',         -- active/graduated/stuck/pinned
    consecutive_hits INTEGER NOT NULL DEFAULT 0,  -- 连续命中计数（miss 归零）
    last_practiced_at TEXT,                       -- 每次练习更新（遗忘曲线锚点）
    last_hit_at TEXT,                             -- 仅命中更新（间隔验证锚点）
    graduated_at TEXT,                            -- 毕业时间（复活清空）
    guided_count INTEGER NOT NULL DEFAULT 0,      -- 被引导次数（docs/17 guided_rounds_weight 数据源，先留 0）
    rescue_rounds_sum INTEGER NOT NULL DEFAULT 0  -- 累计补救轮次（同上，先留 0）
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id TEXT NOT NULL,
    answer_id INTEGER NOT NULL,
    action TEXT NOT NULL,                -- answered / graduation_check / revive
    ratio REAL NOT NULL,
    ts TEXT NOT NULL
);
"""

# 老库升级：为新表补缺失列（CREATE TABLE IF NOT EXISTS 不会改已存在的表）。
# 按表分组：answers 补 rounds/initial_hit_ratio，weak_points 补记忆生命周期列 + 逼近统计列。
_MIGRATION_COLUMNS = {
    "weak_points": [
        ("point_type", "TEXT NOT NULL DEFAULT ''"),  # docs/13 §5.4：老库补列，默认未分类
        ("state", "TEXT NOT NULL DEFAULT 'active'"),
        ("consecutive_hits", "INTEGER NOT NULL DEFAULT 0"),
        ("last_practiced_at", "TEXT"),
        ("last_hit_at", "TEXT"),
        ("graduated_at", "TEXT"),
        ("guided_count", "INTEGER NOT NULL DEFAULT 0"),
        ("rescue_rounds_sum", "INTEGER NOT NULL DEFAULT 0"),
    ],
    "answers": [
        ("rounds", "INTEGER NOT NULL DEFAULT 1"),
        ("initial_hit_ratio", "REAL NOT NULL DEFAULT 0"),
    ],
}


def _migrate(conn: sqlite3.Connection) -> None:
    """老库平滑升级：缺列则 ALTER TABLE 补上（数据不丢）。"""
    for table, cols in _MIGRATION_COLUMNS.items():
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, decl in cols:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
                if table == "answers" and name == "initial_hit_ratio":
                    # 老作答没有逼近轮次：初稿命中率回填为终稿命中率（初稿=终稿）
                    conn.execute("UPDATE answers SET initial_hit_ratio = hit_ratio")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    _migrate(conn)
    return conn


@dataclass
class ReflowResult:
    """一次错题回流的产物：评分 + 入库 + 薄弱点更新。"""
    question_id: str
    result: ScoreResult
    answer_id: int | None = None
    weak_points_updated: int = 0
    new_weak_points: int = 0
    revived: bool = False  # 本次是否有 graduated/stuck 点复活回 active


def _key(qid: str, pid: str) -> str:
    return f"{qid}:{pid}"


def _upsert_weak(conn: sqlite3.Connection, qid: str, p: Point, qtype: str, *, hit: bool, now: str, ptype: str = "") -> tuple[int, bool]:
    """更新单个采分点的累计统计 + 记忆生命周期字段。

    Returns:
        (1=新增 / 0=更新, revived=本次是否从 graduated/stuck 复活回 active)
    """
    key = _key(qid, p.id)
    row = conn.execute("SELECT * FROM weak_points WHERE point_key=?", (key,)).fetchone()

    # 复活判定：非 active（graduated/stuck）的点，只要再被练到（无论 hit/miss）→ 回 active
    revived = False
    if row is None:
        conn.execute(
            "INSERT INTO weak_points(point_key,label,qtype,point_type,question_id,miss_count,hit_count,"
            "last_miss_at,created_at,state,consecutive_hits,last_practiced_at,last_hit_at,graduated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (key, p.point, qtype, ptype, qid, 0 if hit else 1, 1 if hit else 0,
             None if hit else now, now, STATE_ACTIVE,
             1 if hit else 0, now, now if hit else None, None),
        )
        return 1, False

    miss = row["miss_count"] + (0 if hit else 1)
    hitc = row["hit_count"] + (1 if hit else 0)
    consec = row["consecutive_hits"] + 1 if hit else 0
    last_hit = now if hit else row["last_hit_at"]

    state = row["state"]
    if state != STATE_ACTIVE:
        if state in (STATE_GRADUATED, STATE_STUCK):
            # 再被练到 → 复活（档案还在，只是状态回 active）
            state = STATE_ACTIVE
            revived = True
        # STATE_PINNED 保持不动（用户钉住，一直留提醒池）
    conn.execute(
        "UPDATE weak_points SET miss_count=?, hit_count=?, last_miss_at=?, state=?, "
        "consecutive_hits=?, last_practiced_at=?, last_hit_at=?, graduated_at=?, point_type=? WHERE point_key=?",
        (miss, hitc, row["last_miss_at"] if hit else now,
         state, consec, now, last_hit,
         None if revived else row["graduated_at"], ptype, key),
    )
    # 防死锁（docs/17 §3 出口2）：尝试 ≥ MAX_ATTEMPTS 仍未毕业 → 自动转 stuck，移出提醒池。
    # 判据：consec == 0（上一次练习仍在漏）才算死锁；consec ≥ 1 即在毕业轨道上
    # （刚命中过，差几次就达标），不隔离。参数初值待校准。
    if (
        state == STATE_ACTIVE
        and not revived
        and miss + hitc >= MAX_ATTEMPTS
        and consec == 0
    ):
        conn.execute(
            "UPDATE weak_points SET state=? WHERE point_key=?",
            (STATE_STUCK, key),
        )
    return 0, revived


def mark_graduated(conn: sqlite3.Connection, qid: str, pid: str, *, now: str | None = None) -> bool:
    """毕业考命中 → 该点 graduated（移出提醒池，档案保留）。返回是否真的改了状态。

    仅在 state=active 且已满足毕业判定时调用（调用方用 profile.is_graduate_candidate 先判）。
    """
    key = _key(qid, pid)
    row = conn.execute("SELECT * FROM weak_points WHERE point_key=?", (key,)).fetchone()
    if row is None or row["state"] != STATE_ACTIVE:
        return False
    conn.execute(
        "UPDATE weak_points SET state=?, graduated_at=? WHERE point_key=?",
        (STATE_GRADUATED, now or utcnow().isoformat(), key),
    )
    return True


def mark_stuck(conn: sqlite3.Connection, qid: str, pid: str, *, now: str | None = None) -> bool:
    """尝试 ≥ MAX_ATTEMPTS 未毕业 → stuck（防死锁，docs/17 §3 出口2）。"""
    key = _key(qid, pid)
    row = conn.execute("SELECT * FROM weak_points WHERE point_key=?", (key,)).fetchone()
    if row is None or row["state"] != STATE_ACTIVE:
        return False
    conn.execute(
        "UPDATE weak_points SET state=? WHERE point_key=?",
        (STATE_STUCK, key),
    )
    return True


def graduate_hits(question_id: str, hit_ids: list[str], candidate_keys: set[str]) -> list[str]:
    """毕业考命中即毕业（docs/17 §3 出口1 收尾）。

    candidate_keys 由调用方在作答前用 profile.graduation_candidates() 采集
    （作答会更新 last_hit_at，事后采集会漏判）——毕业考命中且作答前是候选 → graduated。
    返回实际毕业的 point_id 列表。
    """
    conn = _conn()
    try:
        done = []
        for pid in hit_ids:
            if _key(question_id, pid) in candidate_keys and mark_graduated(conn, question_id, pid):
                done.append(pid)
        conn.commit()
        return done
    finally:
        conn.close()


def mark_pinned(conn: sqlite3.Connection, qid: str, pid: str, *, pinned: bool = True) -> bool:
    """用户手动钉住/取消钉住（docs/17 §3 出口3）：否决自动毕业，一直留提醒池。"""
    key = _key(qid, pid)
    row = conn.execute("SELECT * FROM weak_points WHERE point_key=?", (key,)).fetchone()
    if row is None:
        return False
    conn.execute(
        "UPDATE weak_points SET state=? WHERE point_key=?",
        (STATE_PINNED if pinned else STATE_ACTIVE, key),
    )
    return True


def reflow_answer(
    question_id: str,
    question_type: str,
    answer: str,
    reference_points: list[dict],
    *,
    action: str = ACTION_ANSWERED,
    rounds: list[dict] | None = None,
) -> ReflowResult:
    """作答即入库：评分 → 写 answers → 更新薄弱点档案 → 写事件日志。

    action 传 graduation_check 表示这是一次毕业考作答（docs/17 §3 出口1），
    事件流里能区分"常规练习"与"毕业验证"。

    rounds：逼近轨迹（docs/18 §5，practice_one 的每轮记录），
      [{round_no, answer, hit_ids, miss_ids, hit_ratio, guided_point_ids}, ...]，
      round_no 0=初稿，1..N=每轮逼近。传入 → 同一事务写 N 行 answer_rounds +
      answers 补 rounds（总轮数）/ initial_hit_ratio（初稿命中率，算逼近增益）。
      不传 → 单次作答（rounds=1，initial_hit_ratio=终稿命中率）。
    """
    points = from_benchmark(reference_points)
    result = score_answer(answer, points)
    now = utcnow().isoformat()

    rounds = list(rounds or [])
    initial_hit_ratio = rounds[0]["hit_ratio"] if rounds else result.hit_ratio
    total_rounds = len(rounds) if rounds else 1  # 无轨迹 = 单次作答 1 轮
    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT INTO answers(question_id,answer,hit_ids,miss_ids,hit_ratio,ts,rounds,initial_hit_ratio)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (question_id, answer, json.dumps(result.hit_ids, ensure_ascii=False),
             json.dumps(result.miss_ids, ensure_ascii=False), round(result.hit_ratio, 4), now,
             total_rounds, round(initial_hit_ratio, 4)),
        )
        answer_id = cur.lastrowid
        for rd in rounds:
            conn.execute(
                "INSERT INTO answer_rounds(answer_id,round_no,answer,hit_ids,miss_ids,hit_ratio,"
                "guided_point_ids,ts) VALUES(?,?,?,?,?,?,?,?)",
                (answer_id, int(rd.get("round_no", 0)), rd.get("answer", ""),
                 json.dumps(rd.get("hit_ids") or [], ensure_ascii=False),
                 json.dumps(rd.get("miss_ids") or [], ensure_ascii=False),
                 round(float(rd.get("hit_ratio") or 0), 4),
                 json.dumps(rd.get("guided_point_ids") or [], ensure_ascii=False), now),
            )
        new_cnt = upd_cnt = revived_cnt = 0
        for p in points:
            hit = p.id in result.hit_ids
            n, revived = _upsert_weak(conn, question_id, p, question_type,
                                      hit=hit, now=now, ptype=p.type)
            new_cnt += n
            upd_cnt += 1 - n
            revived_cnt += 1 if revived else 0
        conn.execute(
            "INSERT INTO events(question_id,answer_id,action,ratio,ts) VALUES(?,?,?,?,?)",
            (question_id, answer_id, action, round(result.hit_ratio, 4), now),
        )
        if revived_cnt:
            conn.execute(
                "INSERT INTO events(question_id,answer_id,action,ratio,ts) VALUES(?,?,?,?,?)",
                (question_id, answer_id, ACTION_REVIVE, round(result.hit_ratio, 4), now),
            )
        conn.commit()
        return ReflowResult(question_id=question_id, result=result,
                            answer_id=answer_id, weak_points_updated=upd_cnt,
                            new_weak_points=new_cnt, revived=revived_cnt > 0)
    finally:
        conn.close()


def _question_dirs() -> list[Path]:
    """题库目录：官方金标优先，用户人审题其次（官方 id 不与用户题冲突）。"""
    return [BENCHMARK_DIR, USER_QUESTIONS_DIR]


def load_question(question_id: str) -> dict | None:
    """按 id 加载题目（带材料+得分点），官方金标与用户题库都找。"""
    for d in _question_dirs():
        path = d / f"{question_id}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return None


def list_questions() -> list[dict]:
    """列出题库全部题目（官方 + 用户，含 authority 标记）。"""
    out = []
    for d in _question_dirs():
        if not d.exists():
            continue
        for f in sorted(d.glob("*.json")):
            item = json.loads(f.read_text(encoding="utf-8"))
            out.append({
                "id": item["id"],
                "authority": item.get("meta", {}).get("authority", "training"),
                "province": item["meta"]["province"],
                "year": item["meta"]["year"],
                "type": item["meta"]["type"],
                "question": item["task"]["question"][:60],
            })
    return out


def recent_answers(limit: int = 10) -> list[dict]:
    """最近作答记录（诊断/可视化用）。"""
    conn = _conn()
    try:
        rows = conn.execute("SELECT * FROM answers ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_answer_rounds(answer_id: int) -> list[dict]:
    """读一次练习的逼近轨迹（answer_rounds 按轮次排序）。"""
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT round_no,answer,hit_ids,miss_ids,hit_ratio,guided_point_ids,ts "
            "FROM answer_rounds WHERE answer_id=? ORDER BY round_no",
            (answer_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
