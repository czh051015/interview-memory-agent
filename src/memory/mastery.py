"""掌握度衰减 / 复习重置 / 双因子召回排序（phase-2-plan §3.3，v2.0 记忆层）。

三个核心函数：
- decay   掌握度衰减：mastery(t) = mastery × e^(-λt)，λ=0.05（艾宾浩斯遗忘曲线）
- review  复习重置：mastery = min(1.0, 上次 × 1.2)，review_count +1，更新复习时间
- rank    双因子召回排序：relevance×0.5 + importance×0.5

设计约定：
- 衰减是「读取时计算」的纯函数，不写回数据库；库里存的 mastery_score
  永远是「最近一次复习时的值」，有效掌握度用 effective_mastery 现算。
- importance = status 权重 × 掌握度缺口(1 - effective_mastery)。
  掌握度缺口即遗忘程度，同时含「时间衰减」和「复习后 mastery 回升」，
  故原「时间衰减量」独立项已并入 importance（不再单列 recency）。
- status 权重（fail 最该复习）与各项权重均待攒够数据后校准（计划书 §6 风险）。
"""

from __future__ import annotations

import math
from datetime import datetime

from src.cleaner.schema import KnowledgeItem, ItemStatus

# 遗忘速率（每天衰减比例），phase-2-plan §3.3：λ=0.05
LAMBDA = 0.05

# 双因子权重，初值待校准
W_RELEVANCE = 0.5
W_IMPORTANCE = 0.5

# status → 重要性（初值待校准）：答错的题最该复习
STATUS_IMPORTANCE = {
    ItemStatus.FAIL: 1.0,
    ItemStatus.PARTIAL: 0.6,
    ItemStatus.PASS: 0.2,
    ItemStatus.UNKNOWN: 0.0,
}


def decay(mastery: float, days: float, *, lam: float = LAMBDA) -> float:
    """掌握度衰减：mastery × e^(-λ·days)。

    days ≤ 0 时不衰减（返回原值）；结果始终落在 [0, mastery]。
    验收 1：1.0 分 30 天后 ≈ 0.2231（e^(-1.5)）。
    """
    if days <= 0:
        return mastery
    return mastery * math.exp(-lam * days)


def _elapsed_days(item: KnowledgeItem, now: datetime) -> float:
    """距最近一次复习的天数；没复习过按入库时间算；未来时间戳当 0。"""
    anchor = item.last_reviewed_at or item.created_at
    if anchor is None:
        return 0.0
    return max(0.0, (now - anchor).total_seconds() / 86400.0)


def effective_mastery(item: KnowledgeItem, now: datetime | None = None) -> float:
    """当前有效掌握度 = 存储值按距上次复习天数衰减。"""
    return decay(item.mastery_score, _elapsed_days(item, now or datetime.utcnow()))


def review(item: KnowledgeItem, now: datetime | None = None) -> KnowledgeItem:
    """复习重置：mastery = min(1.0, 上次 × 1.2)，review_count +1，更新复习时间。

    返回新对象，不改动原 item。衰减只在读取时算，这里不把已衰减值写回。
    """
    bumped = min(1.0, item.mastery_score * 1.2)
    return item.model_copy(
        update={
            "mastery_score": round(bumped, 4),
            "review_count": item.review_count + 1,
            "last_reviewed_at": now or datetime.utcnow(),
        }
    )


def rank(
    items: list[KnowledgeItem],
    *,
    relevances: dict[str, float] | None = None,
    now: datetime | None = None,
) -> list[KnowledgeItem]:
    """双因子召回排序：relevance×0.5 + importance×0.5，按分降序。

    - relevance：relevances 字典按 id 提供（语义搜索相似度）；缺省时取
      item 上的 _similarity（search 结果自带），再缺省按 0。
    - importance = status 权重 × 掌握度缺口(1 - effective_mastery)。
      掌握度缺口 = 遗忘程度，同时反映「越久没复习」和「复习后 mastery 回升」，
      让复习成果回流排序（复习到会的 fail 题不再被高优先级推）。

    排序结果附在每个 item 的 _recall_score 上（与 _similarity 同款模式），
    排序稳定：同分保持原顺序。
    """
    when = now or datetime.utcnow()
    relevances = relevances or {}

    for item in items:
        relevance = relevances.get(
            item.id, getattr(item, "_similarity", 0.0) or 0.0
        )
        status_weight = STATUS_IMPORTANCE.get(item.status, 0.0)
        gap = 1.0 - effective_mastery(item, when)  # 掌握度缺口 = 遗忘程度
        importance = status_weight * gap
        score = (
            W_RELEVANCE * relevance
            + W_IMPORTANCE * importance
        )
        setattr(item, "_recall_score", round(score, 4))

    return sorted(items, key=lambda it: -getattr(it, "_recall_score", 0.0))
