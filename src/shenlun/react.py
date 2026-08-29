"""ReAct 决策层 —— 申论评审 Agent 的主角。

职责：读薄弱点档案 → 检索题库找相关题 → 决定「练哪道 / 补哪个点 / 给什么建议」。
这是「主动性」所在：不是"存了什么给你什么"，而是"根据你的弱点状态决定推什么"。

设计（对齐 memory_keeper 范式）：
  · 确定性工具：read_weak_points（档案）/ search_questions（题库检索）—— 纯函数可测
  · LLM 语义活：读快照 → 输出 {plan:[{question_id, why}], advice, focus} —— 决策
  · 规则回退：LLM 失败 → 按 miss_count 最高的薄弱点直接推其所属题 —— Agent 不会挂

记忆生命周期（docs/17）接入：
  · 决策输入含「毕业考候选」列表（连续命中达标+间隔验证到期）→ 优先安排验证
  · 输出带 action 字段：practice=常规练 / graduation_check=毕业考 / intervene=外部干预
  · stuck 点 → action=intervene：建议先补知识/检查采分点，而非盲目再练（防死锁）

ReAct 循环（本模块实现单轮：观察→决策→输出；多轮 tool use 留待扩展）：
  1. 观察（Observe）  ：读薄弱点档案快照 + 毕业考候选
  2. 检索（Retrieve） ：按薄弱点题型/标签从题库检索候选
  3. 决策（Act）      ：LLM 读快照+候选 → 输出计划/建议；失败回退规则版
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from src.llm import chat_json
from src.shenlun.profile import (
    read_weak_points,
    weakness_snapshot,
    graduation_candidates,
)
from src.shenlun.reflow import list_questions, load_question, STATE_STUCK

logger = logging.getLogger(__name__)

_REACT_PROMPT = (
    "你是申论评审 Agent，负责根据备考者的薄弱点档案规划今天的练习。你会收到：\n"
    "1. 薄弱点档案快照（按题型聚合的采分点：漏了几次、练了几次）\n"
    "2. 题库列表（id + 省份/年份/题型/题干摘要）\n"
    "3. 毕业考候选（连续命中达标、间隔验证到期的采分点——需要安排一次验证作答）\n"
    "任务：从题库挑 1-3 道最该练的题，并给出针对性建议。只输出 JSON：\n"
    '{"focus": "一句话：今天最该补的薄弱环节", '
    '"action": "practice|graduation_check|intervene", '
    '"plan": [{"question_id": "题目id", "why": "为什么练它（引用薄弱点）"}], '
    '"advice": "给备考者的 1-2 句具体建议（如：归纳概括注意先总后分、每个要点先概括后展开）"}\n'
    "要求：\n"
    "- 有毕业考候选时，action=graduation_check，优先安排含这些采分点的题做验证；\n"
    "- 若档案里有 stuck 点（尝试多次仍未掌握），action=intervene，建议先补知识/检查采分点，不要盲目再练同一道题；\n"
    "- 优先选与 red/yellow 薄弱点同题型的题（题单里没有同题型的就选最接近的）；\n"
    "- 不要重复推用户刚做过的同一道题（除非它是唯一候选）；\n"
    "- 只基于快照与题库事实，不要臆造薄弱点或题目。"
)


@dataclass
class ReactOutput:
    focus: str = ""
    plan: list[dict] = field(default_factory=list)
    advice: str = ""
    action: str = "practice"  # practice / graduation_check / intervene（docs/17 §4.3）
    fallback: bool = False    # True = 用了规则回退（LLM 失败）


def search_questions(weak_points: list, limit: int = 8) -> list[dict]:
    """确定性工具：按薄弱点题型/采分角度检索题库候选（docs/13 §6.11，L2 角度过滤，为练同类题铺路）。

    weak_points 是 profile.read_weak_points() 的结果。先按题型过滤；
    薄弱点若标了 point_type，进一步只留含该角度的题（旧题库无标注则保持题型过滤）。
    """
    bank = list_questions()
    # 优先推薄弱点所属题型；没有则全部
    types = list(dict.fromkeys(wp.qtype for wp in weak_points if wp.tier == "red")) or \
            list(dict.fromkeys(wp.qtype for wp in weak_points)) or []
    cands = [q for q in bank if q["type"] in types] if types else bank
    # L2：角度过滤 — 点的 point_type 在拆解时由 LLM 顺手标，看题的金标采分点有没有这个角度
    angles = sorted({wp.point_type for wp in weak_points if wp.point_type})
    if angles and cands:
        def has_angle(q: dict) -> bool:
            item = load_question(q["id"])
            if not item:
                return False
            pts = item["gold"]["reference_points"]
            return any(a in angles for a in (p.get("point_type", "") or "" for p in pts))
        by_angle = [q for q in cands if has_angle(q)]
        if by_angle:  # 没有匹配题就退回题型过滤结果，别把候选清空
            cands = by_angle
    return cands[:limit]


def _rule_fallback(weak_points: list, candidates: list[dict]) -> ReactOutput:
    """规则回退：按 miss_count 最高的薄弱点 → 推它所属题目。不依赖 LLM。"""
    if not weak_points:
        return ReactOutput(focus="暂无薄弱点档案", plan=[], advice="先随便挑一道做，攒数据")
    top = max(weak_points, key=lambda wp: wp.miss_count)
    # 找与 top 同题型的候选（优先不同题，避免刚做过的）
    same_type = [q for q in candidates if q["type"] == top.qtype]
    pick = same_type[0] if same_type else (candidates[0] if candidates else None)
    if pick is None:
        return ReactOutput(focus=f"薄弱点：{top.label}", plan=[], advice="题库为空，先补题")
    return ReactOutput(
        focus=f"薄弱点：{top.qtype} · {top.label}（已漏 {top.miss_count} 次）",
        plan=[{"question_id": pick["id"], "why": f"补薄弱点 {top.label}（漏 {top.miss_count} 次）"}],
        advice="先看材料→列要点→再对照采分点，重点练你漏掉的点。",
        fallback=True,
    )


def decide(*, question_id: str | None = None) -> ReactOutput:
    """ReAct 决策主入口：观察 → 检索 → 决策（LLM 优先，失败规则回退）。

    question_id 传入时，表示"刚才做了这道题"，决策会避开它（推荐下一道）。
    """
    weak_points = read_weak_points(limit=20)
    candidates = search_questions(weak_points)
    snap = weakness_snapshot(limit=12)
    grad_cands = graduation_candidates()

    bank_lines = "\n".join(
        f"- {q['id']} [{q['province']}{q['year']} {q['type']}] {q['question']}"
        for q in candidates
    )
    grad_lines = "\n".join(
        f"- [{wp.qtype}] {wp.label}（{wp.question_id}，连续命中 {wp.consecutive_hits} 次，"
        f"{wp.last_hit_at or '?'} 后未验证）"
        for wp in grad_cands
    ) or "（无）"
    user_prompt = (
        f"## 薄弱点档案快照\n{snap}\n\n"
        f"## 毕业考候选\n{grad_lines}\n\n"
        f"## 题库候选\n{bank_lines}\n\n"
        + (f"## 刚做过的题（尽量别重复推）\n- {question_id}\n" if question_id else "")
    )
    try:
        data = chat_json(_REACT_PROMPT, user_prompt, max_tokens=1024)
        plan = data.get("plan", [])
        if not isinstance(plan, list):
            plan = []
        # 过滤不在题库里的 id
        valid_ids = {q["id"] for q in candidates}
        plan = [p for p in plan if isinstance(p, dict) and p.get("question_id") in valid_ids][:3]
        action = str(data.get("action", "practice"))
        if action not in ("practice", "graduation_check", "intervene"):
            action = "practice"
        return ReactOutput(
            focus=str(data.get("focus", "")),
            plan=plan,
            advice=str(data.get("advice", "")),
            action=action,
        )
    except Exception as e:
        logger.warning("ReAct LLM 决策失败，回退规则版：%s", e)
        return _rule_fallback(weak_points, candidates)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    out = decide()
    print(f"🎯 {out.focus}" + ("  [规则回退]" if out.fallback else ""))
    print(f"⚡ action={out.action}")
    for p in out.plan:
        print(f"  · {p['question_id']} — {p.get('why','')}")
    if out.advice:
        print(f"💡 {out.advice}")
