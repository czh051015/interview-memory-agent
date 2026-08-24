"""Dashboard 聚合端点 —— 首页门面的数据源（第 3 片纵切）。

GET /api/dashboard?space=default →
{
  "spaces": ["default", ...],        # 全部空间（切换器选项）
  "stats": {"total", "by_status", "hot_topics"},   # info 类不计入错题统计
  "remind": {"red": [...], "yellow": [...], "green": N},  # 提醒分层（gap 阈值同 chat）
  "curve": [{"bucket", "count", "avg_mastery"}],   # 遗忘曲线：按距今天数分桶的平均有效掌握度
  "recent": [...]                     # 最近复习事件（review_log 尾部 10 条）
}
"""
from __future__ import annotations

import os
from datetime import datetime

from fastapi import APIRouter, Query

from src.cleaner.schema import utcnow, not_info
from src.memory import knowledge_store as store
from src.memory.mastery import layer, effective_mastery, _elapsed_days
from src.memory import review_log
from src.config import space_dir

router = APIRouter()

# 遗忘曲线分桶（天）：0-1 刚复习 / 1-3 / 3-7 / 7-14 / 14-30 / 30+ 很久没碰
_BUCKETS = [(0, 1), (1, 3), (3, 7), (7, 14), (14, 30), (30, float("inf"))]
_BUCKET_LABELS = ["今天", "1-3天", "3-7天", "7-14天", "14-30天", "30天+"]

def _entry(it, now: datetime) -> dict:
    """提醒分层的展示字段（gap 由 layer 的阈值语义现算，展示时 round 到 3 位）。"""
    return {
        "id": it.id,
        "question": it.question,
        "topic": it.topic,
        "days": int(_elapsed_days(it, now)),  # 未复习过按入库时间算（mastery 语义一致）
        "gap": round(1.0 - effective_mastery(it, now), 3),
    }


def _recent_reviews(limit: int = 10) -> list[dict]:
    """读 review_log 尾部 limit 条（只 append 不分析的日志，Dashboard 只读）。"""
    return review_log.read(limit=limit)


@router.get("/dashboard")
def dashboard(space: str = Query(default="default", description="记忆空间")):
    now = utcnow()

    # 空间列表 = Chroma 有数据的空间 ∪ data/spaces/ 目录存在的空间（CLI 建的空空间也可见）
    all_items = store.search(top_k=1000)
    spaces = sorted({it.space or "default" for it in all_items})
    try:
        spaces_dir = space_dir().parent
        if spaces_dir.exists():
            spaces = sorted(set(spaces) | {d.name for d in spaces_dir.iterdir() if d.is_dir()})
    except OSError:
        pass
    if "default" not in spaces:
        spaces.insert(0, "default")
    if space not in spaces:
        spaces.append(space)
        spaces.sort(key=lambda s: (s != "default", s))

    items = [it for it in all_items if (it.space or "default") == space]
    know = _knowledge_only(items)
    # 提醒与曲线只统计「已判断状态」的题（fail/partial/pass）——unknown 待标注，谈不上遗忘
    judged = [it for it in know if it.status.value in ("fail", "partial", "pass")]

    # 统计（info 类不计入错题统计，与 get_stats 语义一致）
    by_status = {"fail": 0, "partial": 0, "pass": 0, "unknown": 0}
    topic_count: dict[str, int] = {}
    for it in know:
        by_status[it.status.value] = by_status.get(it.status.value, 0) + 1
        if it.topic:
            topic_count[it.topic] = topic_count.get(it.topic, 0) + 1
    hot_topics = sorted(topic_count.items(), key=lambda x: x[1], reverse=True)[:5]

    # 提醒分层：rank 排序 + gap 分档（只对已判断状态的题），再补展示字段
    red_items, yellow_items, _ = layer(judged, now=now)
    red = [_entry(it, now) for it in red_items]
    yellow = [_entry(it, now) for it in yellow_items]
    green = len(judged) - len(red) - len(yellow)

    # 遗忘曲线：按距 anchor 天数分桶，桶内平均有效掌握度
    curve = []
    for (lo, hi), label in zip(_BUCKETS, _BUCKET_LABELS):
        bucket_items = [it for it in judged if lo <= _elapsed_days(it, now) < hi]
        curve.append(
            {
                "bucket": label,
                "count": len(bucket_items),
                "avg_mastery": (
                    round(sum(effective_mastery(it, now) for it in bucket_items) / len(bucket_items), 3)
                    if bucket_items
                    else None  # 空桶前端画断点
                ),
            }
        )

    return {
        "space": space,
        "spaces": spaces,
        "stats": {
            "total": len(items),
            "by_status": by_status,
            "hot_topics": hot_topics,
        },
        "remind": {
            "red": red,
            "yellow": yellow,
            "green": green,
        },
        "curve": curve,
        "recent": _recent_reviews(),
    }
