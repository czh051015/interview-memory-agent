"""场景构造器 —— 把一道题展开成「练习场景」（纯数据，无 DB/IO）。

输入：题目 dict（gold.reference_points）+ random.Random
输出：Scenario —— 该题练几次、每次距今几天、命中 / 漏哪些点。

规则（docs/40 §4.1 Step2）：
 · 每道题抽 2–5 个采分点做漏点（点多取 5，点少至少留 1 个命中）
 · 约半数题练 2 次：第一次更老、第二次较近（间隔 3–7 天）；
   老一次漏全部目标点 → miss_count=2 红档；第二次漏其中一部分 → 其余点「补过一次」
 · 练习日散布在过去 1–28 天（>14 天自然形成 stale 红档）
 · 关键词重叠/互为子串的点不拆进不同桶（防作答无意命中漏点）
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

MIN_MISS = 2       # 每道题最少漏点数
MAX_MISS = 5       # 每道题最多漏点数
MAX_DAYS = 28      # 最后练习日距今上限（stale 阈值 14 天在其中）
TWO_ATTEMPT_P = 0.5


@dataclass(frozen=True)
class Attempt:
    """一次作答：落在 days_ago 天前，命中 hit_ids，其余为漏点。"""
    days_ago: int
    hit_ids: tuple[str, ...]
    miss_ids: tuple[str, ...]


@dataclass(frozen=True)
class Scenario:
    """一道题的完整练习场景（老 → 新的尝试序列）。"""
    question_id: str
    question_type: str
    points: tuple[dict, ...] = field(default_factory=tuple)  # reference_points 原文
    attempts: tuple[Attempt, ...] = field(default_factory=tuple)

    @property
    def weak_point_ids(self) -> set[str]:
        """该题会新增的薄弱点 = 各次作答漏点的并集。"""
        out: set[str] = set()
        for a in self.attempts:
            out.update(a.miss_ids)
        return out

    @property
    def weak_points(self) -> tuple[dict, ...]:
        return tuple(p for p in self.points if p["id"] in self.weak_point_ids)


def build_scenario(question: dict, rng: random.Random) -> Scenario:
    """从一道题生成练习场景；同 seed 可复现，纯函数无副作用。"""
    points = tuple(question["gold"]["reference_points"])
    ids = [p["id"] for p in points]
    n = len(ids)
    miss = _miss_target(n, rng)
    if n < 3 or rng.random() >= TWO_ATTEMPT_P:
        days = rng.randint(1, MAX_DAYS)
        old_miss = _pick_miss(ids, ids, points, miss, rng)
        return Scenario(
            question_id=question["id"], question_type=question["meta"]["type"],
            points=points, attempts=(_attempt(days, old_miss, ids),),
        )
    final_days = rng.randint(1, MAX_DAYS)
    older_days = final_days + rng.randint(3, 7)
    old_miss = _pick_miss(ids, ids, points, miss, rng)
    new_count = rng.randint(1, max(1, miss - 1))
    new_miss = _pick_miss(old_miss, ids, points, new_count, rng)
    return Scenario(
        question_id=question["id"], question_type=question["meta"]["type"],
        points=points,
        attempts=(_attempt(older_days, old_miss, ids), _attempt(final_days, new_miss, ids)),
    )


def _miss_target(n: int, rng: random.Random) -> int:
    lo = min(MIN_MISS, n - 1)
    hi = min(MAX_MISS, n - 1)
    return rng.randint(lo, max(lo, hi))


def _pick_miss(pool_ids: list[str], all_ids: list[str], points: tuple[dict, ...],
               target: int, rng: random.Random) -> list[str]:
    """抽 target 个漏点并过冲突清洗；不足则重抽（最多 24 次，返回最接近的一次）。"""
    best: list[str] = []
    for _ in range(24):
        resolved = _resolve(rng.sample(pool_ids, target), all_ids, points)
        if len(resolved) >= target:
            return resolved
        if len(resolved) > len(best):
            best = resolved
    return best


def _attempt(days_ago: int, miss_ids: list[str], all_ids: list[str]) -> Attempt:
    miss = tuple(m for m in all_ids if m in miss_ids)
    return Attempt(days_ago=days_ago, miss_ids=miss,
                   hit_ids=tuple(i for i in all_ids if i not in miss_ids))


def _resolve(candidate: list[str], all_ids: list[str], points: tuple[dict, ...]) -> list[str]:
    """从漏点候选里剔除「与命中点关键词冲突」的点（防无意命中），其余原样保留。"""
    by_id = {p["id"]: p for p in points}
    miss = list(candidate)
    changed = True
    while changed:
        changed = False
        for m in list(miss):
            if any(_kw_conflict(by_id[m], by_id[h]) for h in all_ids if h not in miss):
                miss.remove(m)
                changed = True
    return miss


def _kw_conflict(a: dict, b: dict) -> bool:
    """两个点的 keywords 是否有包含/被包含/相等关系（命中会互相带出）。"""
    return any(x == y or x in y or y in x for x in a["keywords"] for y in b["keywords"])
