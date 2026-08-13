"""unknown 条目交互补标 —— ISSUES E1（v1.5）。

decompose 后有 status=unknown 的条目时，让用户逐条补标：
f=不会(fail) / p=半会(partial) / x=跳过。
prompt_fn 注入便于测试；非交互环境不调用本模块。
"""

import logging
from datetime import datetime
from src.cleaner.schema import KnowledgeItem, ItemStatus

logger = logging.getLogger(__name__)

_STATUS_MAP = {
    "f": ItemStatus.FAIL,
    "p": ItemStatus.PARTIAL,
}


def annotate_unknown(
    items: list[KnowledgeItem],
    prompt_fn,
    *,
    max_retries: int = 3,
    now: datetime | None = None,
) -> list[KnowledgeItem]:
    """对 status=unknown 的条目逐条补标，返回新列表（不改输入）。

    Args:
        items: 拆解结果
        prompt_fn: 输入函数（如 builtins.input），返回用户输入字符串
        max_retries: 非法输入重试次数，超过则保持 unknown
        now: 标注时间（标 fail/partial 时写入 last_reviewed_at，作为衰减起点）

    Returns:
        补标后的 KnowledgeItem 列表
    """
    now = now or datetime.utcnow()
    unknown_items = [item for item in items if item.status == ItemStatus.UNKNOWN]
    if not unknown_items:
        return list(items)

    print(f"\n有 {len(unknown_items)} 条 status=unknown，逐条补标（f=不会 p=半会 x=跳过）:")

    status_updates: dict[int, ItemStatus] = {}
    try:
        for i, item in enumerate(unknown_items):
            print(f"\n  [{i + 1}/{len(unknown_items)}] {item.question}")
            if item.user_note:
                print(f"  备注: {item.user_note}")
            for _ in range(max_retries):
                raw = prompt_fn("  状态 (f/p/x): ").strip().lower()
                if raw in ("f", "p"):
                    status_updates[i] = _STATUS_MAP[raw]
                    break
                if raw == "x":
                    break
                print(f"  无效输入 '{raw}'，请输入 f / p / x")
            else:
                print("  重试次数用尽，保持 unknown")
    except (EOFError, KeyboardInterrupt):
        # stdin 不可交互（如管道/CI 环境 isatty 误报）→ 停止补标，保持 unknown
        print("\n输入不可用，剩余条目保持 unknown")

    updated = []
    for item in items:
        if item.status == ItemStatus.UNKNOWN:
            idx = unknown_items.index(item)
            new_status = status_updates.get(idx)
            if new_status is not None:
                logger.info("Annotated %s: unknown → %s", item.id, new_status.value)
                updated.append(item.model_copy(update={
                    "status": new_status,
                    "last_reviewed_at": now,  # 标记不会/半会 = 新的衰减起点
                }))
                continue
        updated.append(item)

    return updated
