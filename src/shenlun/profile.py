"""薄弱点档案 —— 从错题回流自动聚合的「采分点级弱点画像」。

记忆单元 = 采分点（而非整道题）："归纳概括题连续3次漏'对策可行性'类点"
这一层是 ReAct 推荐和记忆提醒的数据源。复用 mastery.py 的遗忘分层做动态分层。

工具（全部确定性，可测）：
  · read_weak_points(limit)   → 提醒池（仅 state=active），按紧急度公式排序
  · read_all_weak_points()    → 全部档案（含 graduated/stuck，诊断/统计用）
  · weakness_snapshot()       → ReAct 读取的快照文本（谁弱、弱多久、什么题型）
  · is_graduate_candidate()   → 毕业判定纯函数（docs/17 §3 出口1）
  · graduation_candidates()   → 当前可安排「毕业考」的候选列表

紧急度公式（docs/17 §4.2，替代 ORDER BY miss_count）：
  紧急度(point) = (miss_count + guided_rounds_weight) × 遗忘程度(1 - e^(-0.05·days))
  guided_rounds_weight 来自答案逼近（引导 3 轮才补上 > 引导 1 轮就会），
  逼近未落地前为 0，公式骨架预留。
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from src.shenlun.reflow import (
    _conn,
    DB_PATH,
    STATE_ACTIVE,
    STATE_GRADUATED,
    STATE_STUCK,
    STATE_PINNED,
    GRADUATE_CONSECUTIVE_HITS,
    GRADUATE_SPACING_DAYS,
)
from src.cleaner.schema import utcnow

# 薄弱分层阈值：miss_count 与 最近漏题天数
MISS_RED = 2       # 累计漏 ≥2 次 → 稳定弱点
MISS_YELLOW = 1    # 漏过 1 次 → 需关注
STALE_DAYS = 14    # 超过 N 天没再练这道题 → 遗忘风险（复用遗忘曲线的思想）

# 遗忘速率（对齐 mastery.py 的 λ=0.05，艾宾浩斯）
LAMBDA = 0.05


@dataclass
class WeakPoint:
    point_key: str
    label: str
    qtype: str
    question_id: str
    miss_count: int
    hit_count: int
    last_miss_at: str | None
    point_type: str = ""   # 采分角度（docs/13 §5.5，聚合 L2 诊断的维度；放默认区，不破坏 dataclass 顺序）
    created_at: str | None = None
    state: str = STATE_ACTIVE
    consecutive_hits: int = 0
    last_practiced_at: str | None = None
    last_hit_at: str | None = None
    graduated_at: str | None = None
    guided_count: int = 0          # 被 AI 引导过的次数（答案逼近，未落地前为 0）
    rescue_rounds_sum: int = 0     # 补上它累计用的轮次（答案逼近，未落地前为 0）
    tier: str = ""                 # red/yellow/green（遗忘分层，展示用）
    urgency: float = 0.0           # 紧急度得分（排序用，docs/17 §4.2）

    @property
    def miss_ratio(self) -> float:
        total = self.miss_count + self.hit_count
        return self.miss_count / total if total else 0.0

    @property
    def attempts(self) -> int:
        """尝试轮次 = 练过几次（miss + hit），无需单独字段。"""
        return self.miss_count + self.hit_count

    @property
    def guided_rounds_weight(self) -> float:
        """引导难度权重：平均几轮补上 → 权重（记忆问题低、理解问题高）。"""
        if not self.guided_count:
            return 0.0
        avg = self.rescue_rounds_sum / self.guided_count
        if avg >= 3:
            return 1.0
        if avg >= 2:
            return 0.5
        return 0.0

    def forgetting(self, now: datetime | None = None) -> float:
        """遗忘程度 = 1 - e^(-0.05·距上次练习天数)；没练过按入库时间（created_at 缺失按 0）。"""
        anchor = self.last_practiced_at or self.created_at
        days = _elapsed_days(anchor, now or utcnow())
        return 1.0 - math.exp(-LAMBDA * days)

    def score(self, now: datetime | None = None) -> float:
        """紧急度 = 弱点权重 × 遗忘程度。排序的唯一来源。"""
        weakness = self.miss_count + self.guided_rounds_weight
        return round(weakness * self.forgetting(now), 4)


def _tier(miss_count: int, stale: bool) -> str:
    """分层：稳定弱点(红) / 需关注(黄) / 巩固(绿)。stale=太久没练有遗忘风险。"""
    if miss_count >= MISS_RED or (miss_count >= MISS_YELLOW and stale):
        return "red"
    if miss_count >= MISS_YELLOW:
        return "yellow"
    return "green"


def _elapsed_days(anchor: str | None, now: datetime) -> float:
    """ISO 时间字符串 → 距今的天数（解析失败按 0）。"""
    if not anchor:
        return 0.0
    try:
        last = datetime.fromisoformat(anchor)
    except ValueError:
        return 0.0
    return max(0.0, (now - last).total_seconds() / 86400.0)


def _row_to_weak(r: sqlite3.Row, now: datetime) -> WeakPoint:
    """sqlite 行 → WeakPoint（补 tier/urgency 展示与排序字段）。"""
    wp = WeakPoint(
        point_key=r["point_key"],
        label=r["label"],
        qtype=r["qtype"],
        point_type=r["point_type"] if "point_type" in r.keys() else "",
        question_id=r["question_id"],
        miss_count=r["miss_count"],
        hit_count=r["hit_count"],
        last_miss_at=r["last_miss_at"],
        state=r["state"] if "state" in r.keys() else STATE_ACTIVE,
        consecutive_hits=r["consecutive_hits"] if "consecutive_hits" in r.keys() else 0,
        last_practiced_at=r["last_practiced_at"],
        last_hit_at=r["last_hit_at"],
        graduated_at=r["graduated_at"],
        created_at=r["created_at"] if "created_at" in r.keys() else None,
    )
    stale = _elapsed_days(wp.last_practiced_at or wp.last_miss_at, now) > STALE_DAYS
    wp.tier = _tier(wp.miss_count, stale)
    wp.urgency = wp.score(now)
    return wp


def read_weak_points(limit: int = 100) -> list[WeakPoint]:
    """读「提醒池」：state=active + pinned，按紧急度降序（docs/17 §4.2）。

    graduated/stuck 不进提醒池；pinned 一直在池里（用户否决自动毕业，docs/17 §3 出口3）；
    完整档案用 read_all_weak_points()。确定性，不调 LLM。
    """
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM weak_points WHERE state IN (?,?) "
            "ORDER BY miss_count DESC, last_miss_at DESC LIMIT ?",
            (STATE_ACTIVE, STATE_PINNED, limit),
        ).fetchall()
    finally:
        conn.close()
    return sorted((_row_to_weak(r, utcnow()) for r in rows), key=lambda wp: -wp.urgency)[:limit]


def read_all_weak_points(limit: int = 500) -> list[WeakPoint]:
    """读完整档案（含 graduated/stuck/pinned）——统计/诊断用，不进提醒池。"""
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM weak_points ORDER BY miss_count DESC LIMIT ?", (limit,),
        ).fetchall()
    finally:
        conn.close()
    return sorted((_row_to_weak(r, utcnow()) for r in rows), key=lambda wp: -wp.urgency)


def is_graduate_candidate(wp: WeakPoint, now: datetime | None = None) -> bool:
    """毕业判定（docs/17 §3 出口1）：连续命中达标 + 距 last_hit_at ≥ 间隔天数。

    满足 = 该点可安排「毕业考」（系统主动推题验证），不是直接毕业——
    毕业考命中才真正 graduated（reflow.mark_graduated）。
    """
    now = now or utcnow()
    if wp.state != STATE_ACTIVE:
        return False
    if wp.consecutive_hits < GRADUATE_CONSECUTIVE_HITS:
        return False
    return _elapsed_days(wp.last_hit_at, now) >= GRADUATE_SPACING_DAYS


def graduation_candidates(now: datetime | None = None) -> list[WeakPoint]:
    """当前可安排毕业考的点（提醒池内满足毕业判定的子集）。"""
    return [wp for wp in read_weak_points(limit=200) if is_graduate_candidate(wp, now)]


def weakness_snapshot(limit: int = 12) -> str:
    """生成 ReAct 读取的薄弱点快照文本（谁弱、弱多久、什么题型）。"""
    pts = read_weak_points(limit=limit)
    if not pts:
        return "（暂无薄弱点档案，先做几道题吧）"
    lines = []
    for wp in pts:
        icon = {"red": "🔴", "yellow": "🟡", "green": "🟢"}[wp.tier]
        days = int(_elapsed_days(wp.last_practiced_at or wp.last_miss_at, utcnow()))
        tag = f"{wp.qtype}/{wp.point_type}" if wp.point_type else wp.qtype  # docs/13 §6.10：角度入快照
        lines.append(
            f"{icon} [{tag}] {wp.label} — 漏 {wp.miss_count} 次 / 练 {wp.attempts} 次"
            f"（{wp.question_id}，{days} 天未练）"
        )
    return "\n".join(lines)


def stats() -> dict:
    """档案统计：按题型聚合薄弱点分布（能力诊断的雏形）。"""
    pts = read_all_weak_points()
    by_type: dict[str, dict] = {}
    for wp in pts:
        d = by_type.setdefault(wp.qtype, {"total": 0, "red": 0, "miss_sum": 0})
        d["total"] += 1
        d["miss_sum"] += wp.miss_count
        if wp.tier == "red":
            d["red"] += 1
    return {"by_type": by_type, "total_points": len(pts)}


def stats_by_angle() -> dict:
    """按采分角度聚合薄弱点（L2，docs/13 §6.9）：跨题型揭示"总漏哪类角度"。

    未标注（point_type=""）的并入"未分类"，不丢弃。结构与 stats() 对齐。
    """
    pts = read_all_weak_points()
    by_angle: dict[str, dict] = {}
    for wp in pts:
        a = by_angle.setdefault(wp.point_type or "未分类", {"total": 0, "red": 0, "miss_sum": 0})
        a["total"] += 1
        a["miss_sum"] += wp.miss_count
        if wp.tier == "red":
            a["red"] += 1
    return {"by_angle": by_angle, "total_points": len(pts)}


def diagnose() -> dict:
    """三层诊断聚合（docs/13 §7，确定性，复用 weak_points，不调 LLM）。

    题型 → 角度 → 薄弱点，供前端诊断页与 ReAct 共用。
    """
    pts = read_all_weak_points()
    by_type: dict[str, dict] = {}
    by_angle: dict[str, dict] = {}
    for wp in pts:
        t = by_type.setdefault(wp.qtype, {"total": 0, "red": 0, "miss_sum": 0})
        t["total"] += 1
        t["miss_sum"] += wp.miss_count
        if wp.tier == "red":
            t["red"] += 1
        a = by_angle.setdefault(wp.point_type or "未分类", {"total": 0, "red": 0, "miss_sum": 0})
        a["total"] += 1
        a["miss_sum"] += wp.miss_count
        if wp.tier == "red":
            a["red"] += 1
    return {"by_type": by_type, "by_angle": by_angle, "total_points": len(pts)}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print("=== 薄弱点档案 ===")
    print(weakness_snapshot())
    print("\n=== 按题型聚合 ===")
    import json
    print(json.dumps(stats(), ensure_ascii=False, indent=2))
    print("\n=== 三层诊断（题型→角度）===")
    print(json.dumps(diagnose(), ensure_ascii=False, indent=2))
