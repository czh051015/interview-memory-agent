"""统一面试写回核心 —— CLI 与 Web 共享（06 计划 §3.3 方案 A）。

消除 scripts/run_mock_interview.py 与 app/api/mock.py 的写回逻辑重复 + 行为分叉：
一次判定（weak 涨跌 / 新题采集 / 行为标签合并 / review_log）抽成单一 apply_verdict 落点。
反馈写进专用 feedback 字段，不复用 answer（answer 定义为面经自带参考答案）。
"""

from src.cleaner.schema import KnowledgeItem, ItemSource, ItemStatus, utcnow
from src.memory import knowledge_store as store
from src.memory import mastery
from src.memory import review_log
from src.cleaner.state_machine import record_birth

_ACTION_OF = {"pass": "review", "fail": "review_fail", "partial": "review_partial"}


def _feedback_text(performance: str, judge: dict) -> str:
    """把 LLM 判定拼成可读反馈文本（作为 feedback 字段内容）。"""
    from datetime import datetime

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    parts = [f"【模拟面试 {ts} · {performance}】"]
    points = judge.get("points") or []
    misses = judge.get("misses") or []
    if points:
        parts.append("应该答到：\n" + "\n".join(f"- {p}" for p in points))
    if misses:
        parts.append("漏掉的：\n" + "\n".join(f"- {m}" for m in misses))
    if judge.get("reason"):
        parts.append(f"面试官的话：{judge['reason']}")
    return "\n".join(parts)


def _record_result(item, performance: str, behaviors: list[str], judge: dict):
    """weak 题：mastery 涨跌 + 合并行为标签 + 写 feedback（不改 answer）。"""
    if performance == "pass":
        updated = mastery.review(item)
    elif performance == "fail":
        updated = mastery.review_fail(item)
    else:
        updated = mastery.review_partial(item)
    merged = list(set(updated.behavior_tags + behaviors))
    # 只对 fail/partial 写 feedback（对齐旧 Web「pass 不进 answer」行为裁决：pass 无需对照）
    feedback = _feedback_text(performance, judge) if (
        performance in ("fail", "partial") and (judge.get("points") or judge.get("misses") or judge.get("reason"))
    ) else ""
    return updated.model_copy(update={"behavior_tags": merged, "feedback": feedback})


def _collect_new_item(r: dict) -> KnowledgeItem:
    """面试答差的新题自动采集进错题本（feedback 填判定文本，answer 留空）。"""
    import uuid
    import src.config as _cfg  # 活引用：CLI --space 在 import 后改 _cfg.SPACE

    status = ItemStatus.FAIL if r["performance"] == "fail" else ItemStatus.PARTIAL
    ki = KnowledgeItem(
        id=f"ki_{utcnow():%Y%m%d}_{uuid.uuid4().hex[:6]}_{r.get('source', 'mock')[:3]}",
        question=r["question"],
        answer="",  # 方案 A：answer 留空，反馈进 feedback
        topic=r.get("topic", ""),
        feedback=r.get("feedback") or "",
        status=status,
        source=ItemSource.MOCK_INTERVIEW,
        mastery_score=mastery.INITIAL_MASTERY[status],
        created_at=utcnow(),
        space=r.get("space") or _cfg.SPACE,
    )
    return record_birth(ki, reason=f"模拟面试表现 {r['performance']}", actor="mock_interview")


def _build_writeback_items(results: list[dict], behaviors: list[str]) -> tuple[list[KnowledgeItem], list[KnowledgeItem]]:
    """把归一化结果拆成 (updated, new)——纯函数，不落库。

    归一化 result 字段：question/source/topic/performance/points/misses/reason/item/space。
    - source=="weak" 且 item 有值 → updated（record_result 逻辑）
    - 否则 performance∈{fail,partial} → new（_collect_new_item）
    """
    updated, new = [], []
    for r in results:
        if r.get("source") == "weak" and r.get("item") is not None:
            updated.append(_record_result(r["item"], r["performance"], behaviors, r))
        elif r.get("performance") in ("fail", "partial"):
            r2 = dict(r)
            if not r2.get("feedback"):  # 归一化结果没带 feedback → 由 points/misses/reason 现拼
                r2["feedback"] = _feedback_text(r["performance"], r2)
            new.append(_collect_new_item(r2))
    return updated, new


def apply_verdict(results: list[dict], behaviors: list[str], space: str = "default") -> tuple[int, int]:
    """统一写回核心：一次判定完成 weak mastery 涨跌 + 新题采集 + 行为标签合并 + review_log。

    结果元素（归一化）：question/source/topic/performance/points/misses/reason/item/space。
    return (updated_count, new_count)。写失败抛异常（调用方回滚），不半写。
    """
    updated, new = _build_writeback_items(results, behaviors)

    # 原子写库（"失败不半写"）
    all_to_store = updated + new
    if all_to_store:
        store.store_items(all_to_store)

    # 只有写库成功后，才记 weak 题的 mastery 变化进 review_log（actor 统一 mock_interview）
    if updated:
        after_by_id = {u.id: u for u in updated}
        for r in results:
            it = r.get("item")
            if it is not None and it.id in after_by_id:
                u = after_by_id[it.id]
                review_log.append(
                    item_id=it.id, question=it.question,
                    before=it.mastery_score, after=u.mastery_score,
                    action=_ACTION_OF.get(r["performance"], "review_partial"),
                    actor="mock_interview",
                )

    return len(updated), len(new)


def _write_back(results: list[dict], behaviors: list[str]):
    """兼容旧测试/中断流程：纯计算返回 (updated, new)，不落库。"""
    return _build_writeback_items(results, behaviors)


def record_result(item, performance: str, behaviors: list[str]):
    """兼容旧签名（3 参，无 judge）：单题写回判定文本为空（不发 feedback）。

    新路径统一走 apply_verdict（结果归一化带 points/misses/reason）。
    """
    return _record_result(item, performance, behaviors, {})