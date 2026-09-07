"""题目采样器 —— 抽题并保证题型多样（纯函数，无 DB/IO）。

输入：候选题目元数据（含 id/type）+ 排除 id（已练 / 已 seed）+ 数量 + 种子
输出：同 seed 可复现的 question_id 列表。
方法：按题型分组后随机轮转 —— 第一轮每类抽 1 道、第二轮再回头，
抽到的题天然跨题型（归纳概括 / 综合分析 / 应用文 / 提出对策）。
"""

from __future__ import annotations

import random
from collections.abc import Iterable


def pick_question_ids(
    candidates: Iterable[dict],
    exclude_ids: Iterable[str],
    count: int,
    seed: int,
) -> list[str]:
    """从候选题中按题型轮转抽 count 道；排除后不足则全部返回。"""
    excluded = set(exclude_ids)
    pool = [c for c in candidates if c["id"] not in excluded]
    by_type: dict[str, list[str]] = {}
    for c in pool:
        by_type.setdefault(c["type"], []).append(c["id"])
    rng = random.Random(seed)
    types = list(by_type)
    rng.shuffle(types)
    for ids in by_type.values():
        rng.shuffle(ids)

    chosen: list[str] = []
    while len(chosen) < count and any(by_type[t] for t in types):
        for t in types:
            if len(chosen) >= count:
                break
            if by_type[t]:
                chosen.append(by_type[t].pop(0))
    return chosen
