"""status 状态机 —— 标注/纠错留痕（2026-08-15 grilling 共识）。

设计原则：
- status = 历史事实（面试那刻的表现），复习不改它；复习走 mastery 连续值（decay/review）
- 唯一硬约束：已判断状态（fail/partial/pass）不许退回 unknown（语义矛盾）
- fail / partial / pass 三者之间自由（学习状态本来就会来回波动）
- 每次变更留痕，证据字段 {time, from, to, reason, actor}，actor ∈ {decompose, annotate, review}

两个入口：
- record_birth：首次赋值留出生记录（from=null），decompose/jingyan 导入时调用
- transition：状态变更留痕 + 校验，annotate 标注时调用
"""

from __future__ import annotations

from datetime import datetime

from src.cleaner.schema import KnowledgeItem, ItemStatus, utcnow

MAX_HISTORY = 50  # 证据链上限，防 metadata 无限膨胀


def _append_history(
    item: KnowledgeItem,
    from_status: ItemStatus | None,
    to_status: ItemStatus,
    reason: str,
    actor: str,
    now: datetime,
) -> list[dict]:
    """追加一条证据并做上限截断（保留最近 MAX_HISTORY 条）。"""
    entry = {
        "time": now.isoformat(),
        "from": from_status.value if from_status else None,
        "to": to_status.value,
        "reason": reason,
        "actor": actor,
    }
    history = list(item.history or [])
    history.append(entry)
    return history[-MAX_HISTORY:]


def record_birth(
    item: KnowledgeItem,
    *,
    reason: str,
    actor: str = "decompose",
    now: datetime | None = None,
) -> KnowledgeItem:
    """首次赋值留出生记录（from=null）。返回新对象，不改原 item。"""
    now = now or utcnow()
    history = _append_history(item, None, item.status, reason, actor, now)
    return item.model_copy(update={"history": history})


def transition(
    item: KnowledgeItem,
    new_status: ItemStatus,
    *,
    reason: str,
    actor: str = "annotate",
    now: datetime | None = None,
) -> KnowledgeItem:
    """状态变更：校验合法 + 留痕。返回新对象，不改原 item。

    Raises:
        ValueError: 已判断状态（fail/partial/pass）试图退回 unknown。
    """
    if new_status == ItemStatus.UNKNOWN and item.status != ItemStatus.UNKNOWN:
        raise ValueError(
            f"非法转换：{item.status.value} → {new_status.value}"
            "（已判断状态不能退回 unknown）"
        )

    now = now or utcnow()
    history = _append_history(item, item.status, new_status, reason, actor, now)
    return item.model_copy(update={"status": new_status, "history": history})
