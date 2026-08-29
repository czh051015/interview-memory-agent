"""交互审核 —— 面试域补标 status + 申论域人审采分点。

面试域（v1.5 ISSUES E1）：decompose 后有 status=unknown 的条目时，让用户逐条补标：
f=不会(fail) / p=半会(partial) / g=会(pass) / x=跳过。
标注走状态机 transition（留痕），并设 last_reviewed_at 作为衰减起点。

申论域（docs/16 §3.4）：decompose_points 拆出的采分点过人工审核闸门：
k=确认 s=改分值 w=改关键词 d=删除 a=新增点 x=跳过，全部通过后才可入库。

prompt_fn 注入便于测试；非交互环境不调用本模块。
"""

import logging
import re
from datetime import datetime
from src.cleaner.schema import (
    KnowledgeItem,
    ItemStatus,
    PointDecomposeResult,
    ReferencePoint,
    append_point_history,
    utcnow,
)
from src.cleaner.state_machine import transition
from src.memory.mastery import INITIAL_MASTERY

logger = logging.getLogger(__name__)

_STATUS_MAP = {
    "f": ItemStatus.FAIL,
    "p": ItemStatus.PARTIAL,
    "g": ItemStatus.PASS,
}

_STATUS_LABEL = {
    ItemStatus.FAIL: "不会",
    ItemStatus.PARTIAL: "半会",
    ItemStatus.PASS: "会",
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
    now = now or utcnow()
    unknown_items = [item for item in items if item.status == ItemStatus.UNKNOWN]
    if not unknown_items:
        return list(items)

    print(f"\n有 {len(unknown_items)} 条 status=unknown，逐条补标（f=不会 p=半会 g=会 x=跳过）:")

    status_updates: dict[int, ItemStatus] = {}
    try:
        for i, item in enumerate(unknown_items):
            print(f"\n  [{i + 1}/{len(unknown_items)}] {item.question}")
            if item.user_note:
                print(f"  备注: {item.user_note}")
            for _ in range(max_retries):
                raw = prompt_fn("  状态 (f/p/g/x): ").strip().lower()
                if raw in ("f", "p", "g"):
                    status_updates[i] = _STATUS_MAP[raw]
                    break
                if raw == "x":
                    break
                print(f"  无效输入 '{raw}'，请输入 f / p / g / x")
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
                annotated = transition(
                    item,
                    new_status,
                    reason=f"人工标注：{_STATUS_LABEL[new_status]}",
                    actor="annotate",
                    now=now,
                )
                # 标注 = 一次判断：更新衰减起点 + 按面试表现设初始掌握度
                annotated = annotated.model_copy(update={
                    "last_reviewed_at": now,
                    "mastery_score": INITIAL_MASTERY[new_status],
                })
                updated.append(annotated)
                continue
        updated.append(item)

    return updated


# ── 申论域：采分点人审闸门（docs/16 §3.4）──────────────────────────────────
# 交互从「标状态 f/p/g/x」变「审采分点 k/s/w/d/a/x」；每步操作走留痕
# （append_point_history，actor="annotate_points"），与状态机同构。
# 防循环论证：LLM 拆的点默认 approved=False，人审通过后才成为可信金标。
def annotate_points(
    result: PointDecomposeResult,
    prompt_fn,
    *,
    max_retries: int = 3,
    now: datetime | None = None,
) -> PointDecomposeResult:
    """对 LLM 拆出的采分点逐条人工审核，返回新结果（不改输入）。

    操作（逐条展示后输入）：
        k=确认（approved=True, source=human_approved）
        s=改分值   w=改关键词   d=删除（不落库）
        a=新增点（人工补漏拆，直接 human_approved）
        x=跳过（保持 approved=False，不通过）

    整批没有一个通过 → 保持草稿（approved=False），不入库。

    Args:
        result: decompose_points() 的输出
        prompt_fn: 输入函数（如 builtins.input），返回用户输入字符串
        max_retries: 非法输入重试次数，超过则该项按跳过处理
        now: 标注时间（留痕用）

    Returns:
        审核后的 PointDecomposeResult
    """
    now = now or utcnow()
    points = list(result.reference_points)

    # LLM 自报的不确定项，人审时优先看
    for w in result.warnings:
        print(f"  ⚠ {w}")

    if not points:
        print("\n没有采分点可审（拆解为空），整批保持草稿")
        return result

    print(f"\n有 {len(points)} 个采分点待审（k=确认 s=改分值 w=改关键词 d=删除 a=新增点 x=跳过）:")
    processed = 0
    try:
        while processed < len(points):
            p = points[processed]
            print(f"\n  [{p.id}] {p.point}  keywords: {'/'.join(p.keywords)}  score: {p.score}"
                  f"  {'✅已通过' if p.approved else '（待审）'}")
            for _ in range(max_retries):
                raw = prompt_fn("  操作 (k/s/w/d/a/x): ").strip().lower()
                if raw == "k":
                    points[processed] = _approve(p, now)
                    break
                if raw == "s":
                    points[processed] = _change_score(p, prompt_fn, result.max_score, now, max_retries)
                    break
                if raw == "w":
                    points[processed] = _change_keywords(p, prompt_fn, now, max_retries)
                    break
                if raw == "d":
                    logger.info("Point %s deleted by annotate_points", p.id)
                    del points[processed]
                    processed -= 1  # 删掉后当前指针回退，下一条顶上
                    break
                if raw == "a":
                    points.insert(processed + 1, _add_point(prompt_fn, points, now, max_retries))
                    processed += 1  # 新增点就地接着审
                    break
                if raw == "x":
                    break
                print(f"  无效输入 '{raw}'，请输入 k / s / w / d / a / x")
            else:
                print("  重试次数用尽，按跳过处理")
            processed += 1
    except (EOFError, KeyboardInterrupt):
        # stdin 不可交互 → 停止审核，已处理的保留，其余保持草稿
        print("\n输入不可用，剩余采分点保持草稿（approved=False）")

    approved = sum(1 for p in points if p.approved)
    print(f"\n审核完成：通过 {approved}/{len(points)} 个采分点")
    if approved == 0:
        print("  整批未通过任何一点 → 保持草稿，不入库。可重新审核或改用更完整的标准答案。")
    elif not all(p.approved for p in points):
        print("  存在未通过的点 → 整批保持草稿，确认所有点后才入库。")

    return result.model_copy(update={"reference_points": points})


def _approve(p: ReferencePoint, now: datetime) -> ReferencePoint:
    """k=确认：approved=True + source=human_approved + 留痕（from=原 source）。"""
    logger.info("Point %s approved by annotate_points", p.id)
    p = append_point_history(
        p, to_source="human_approved", from_source=p.source,
        reason="人工确认通过", actor="annotate_points", now=now,
    )
    return p.model_copy(update={"approved": True})


def _change_score(p: ReferencePoint, prompt_fn, max_score: int, now: datetime, max_retries: int) -> ReferencePoint:
    """s=改分值：改 score + 留痕（不自动 approved，仍需 k 确认）。"""
    print(f"  当前 score: {p.score}{f'（满分 {max_score}）' if max_score else ''}")
    for _ in range(max_retries):
        try:
            new_score = float(prompt_fn("  新分值: ").strip())
            if new_score < 0 or (max_score and new_score > max_score):
                print(f"  分值需在 0 ~ {max_score} 之间")
                continue
            logger.info("Point %s score %s → %s", p.id, p.score, new_score)
            p = append_point_history(
                p, to_source=p.source, from_source=p.source,
                reason=f"人工改分值：{p.score} → {new_score}",
                actor="annotate_points", now=now,
            )
            return p.model_copy(update={"score": new_score})
        except ValueError:
            print("  请输入数字")
    print("  重试次数用尽，分值不变")
    return p


def _change_keywords(p: ReferencePoint, prompt_fn, now: datetime, max_retries: int) -> ReferencePoint:
    """w=改关键词：逗号分隔替换 + 留痕（不自动 approved）。"""
    print(f"  当前 keywords: {'/'.join(p.keywords)}")
    for _ in range(max_retries):
        raw = prompt_fn("  新关键词（逗号分隔）: ").strip()
        new_keywords = [k.strip() for k in re.split(r"[,，]", raw) if k.strip()]
        if not new_keywords:
            print("  关键词不能为空")
            continue
        logger.info("Point %s keywords → %s", p.id, new_keywords)
        p = append_point_history(
            p, to_source=p.source, from_source=p.source,
            reason=f"人工改关键词：{'/'.join(p.keywords)} → {'/'.join(new_keywords)}",
            actor="annotate_points", now=now,
        )
        return p.model_copy(update={"keywords": new_keywords})
    print("  重试次数用尽，关键词不变")
    return p


def _add_point(prompt_fn, points: list[ReferencePoint], now: datetime, max_retries: int) -> ReferencePoint:
    """a=新增点：LLM 漏拆时人工补一个，直接 human_approved。"""
    print("  新增采分点（人工补漏拆）")
    name = prompt_fn("  点名称（≤8字）: ").strip() or "未命名点"
    raw = prompt_fn("  关键词（逗号分隔）: ").strip()
    keywords = [k.strip() for k in re.split(r"[,，]", raw) if k.strip()]
    new_score = 0.0
    try:
        new_score = float(prompt_fn("  分值: ").strip() or 0)
    except ValueError:
        pass
    next_id = f"c{max((int(p.id[1:]) for p in points if p.id.startswith('c')), default=0) + 1}"
    rp = ReferencePoint(id=next_id, point=name, keywords=keywords, score=new_score, created_at=now)
    rp = append_point_history(
        rp, to_source="human_approved", reason="人工新增采分点", actor="annotate_points", now=now,
    )
    logger.info("Point %s added by annotate_points: %s", rp.id, rp.point)
    return rp.model_copy(update={"approved": True})
