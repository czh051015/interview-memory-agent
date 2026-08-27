"""动态面试运行态（07 计划 T3）：决策、出题、单题面试、断点恢复、进度落盘。"""

import json
import logging

import src.config as _cfg  # 活引用：CLI --space 在 import 后改 _cfg.SPACE
from src.config import space_dir
from src.cleaner.schema import KnowledgeItem
from . import MAX_ROUNDS, MAX_TOTAL_QUESTIONS, MAX_SECTION_QUESTIONS, MIN_SECTION_QUESTIONS
from .prompts import (
    _DECIDE_NEXT_PROMPT,
    _DYNAMIC_QUESTION_PROMPT,
)
# 活引用：本模块对 judge/LLM 的调用一律经包取当前属性（测试 patch 的是 src.mock 命名空间：
# @patch.object(mi, "chat_json" / "judge_followup" / "get_expected_points" 等），
# 若缓存为模块全局则 patch 穿透不进来。统一经 _mi.xxx 运行时动态查。
import src.mock as _mi

# ── 决策 + 现场出题 ──
def decide_next(
    section: str,
    last_question: str,
    performance: str,
    reason: str,
    section_asked: int,
    remaining_sections: list[str],
    asked_before: list[str],
    weak_topics: list[str] | None = None,
) -> dict:
    """动态循环决策：LLM 输出 {action, guidance, reason}，兜底 switch。"""
    topics_str = "、".join(weak_topics) if weak_topics else "（无）"
    user_prompt = (
        f"当前章节：{section}\n"
        f"刚答完的题：{last_question}\n"
        f"本题表现：{performance}\n"
        f"判断依据：{reason}\n"
        f"本章已问题数：{section_asked}\n"
        f"剩余章节：{remaining_sections or '（无，本章是最后一章）'}\n"
        f"本场已问题目：{asked_before or '（无）'}\n"
        f"画像稳定弱点主题（深挖方向参考）：{topics_str}"
    )
    try:
        data = _mi.chat_json(_DECIDE_NEXT_PROMPT, user_prompt)
        action = data.get("action", "switch")
        if action not in ("deep_dive", "switch", "next_section", "end"):
            action = "switch"
        return {
            "action": action,
            "guidance": str(data.get("guidance", "")),
            "reason": str(data.get("reason", "")),
        }
    except Exception as e:
        logging.warning("下一步决策失败，兜底 switch：%s", e)
        return {"action": "switch", "guidance": "", "reason": "决策失败"}


def generate_dynamic_question(section, guidance, resume, jd, weak_items, asked_before) -> dict:
    """现场出题：deep_dive/switch 时按决策指引生成新题。失败返回 {}（调用方跳过）。"""
    weak_str = "\n".join(f"- [{it.id}] {it.question}" for it in weak_items) if weak_items else "（无）"
    user_prompt = (
        f"当前章节：{section}\n"
        f"出题指引：{guidance or '（无，自行判断）'}\n"
        f"候选人简历：{resume or '（未提供）'}\n"
        f"岗位 JD：{jd or '（未提供）'}\n"
        f"历史薄弱项：{weak_str}\n"
        f"本场已问题目：{asked_before or '（无）'}"
    )
    try:
        data = _mi.chat_json(_DYNAMIC_QUESTION_PROMPT, user_prompt, max_tokens=1024)
        q = str(data.get("question", "")).strip()
        if not q:
            return {}
        return {
            "question": q,
            "source": str(data.get("source", "generic")),
            "topic": str(data.get("topic", "")),
        }
    except Exception as e:
        logging.warning("现场出题失败：%s", e)
        return {}


# ── 单题面试（可测试纯逻辑） ──
def interview_one(question, answer_fn, answer="", asked_before=None):
    """面试一道题，返回 (最终表现, 全部回答拼接, 逐轮对话记录)。"""
    points = _mi.get_expected_points(question, answer)
    answers = []
    transcript = []
    performance = "partial"

    for round_num in range(1, MAX_ROUNDS + 1):
        answer = answer_fn(round_num).strip()
        if not answer:
            performance = "fail"
            break
        answers.append(answer)

        judge = _mi.judge_followup(question, points, answer, round_num,
                                   cross_on_partial=True, asked_before=asked_before)
        performance = judge.get("performance", "partial")
        transcript.append({
            "round": round_num,
            "answer": answer,
            "points": points,  # 该题期望要点（写回 feedback 用；CLI 追问判官不产出 misses）
            "reason": judge.get("reason", ""),
            "followup_question": judge.get("followup_question", ""),
            "performance": judge.get("performance", "partial"),
        })

        if judge.get("need_followup") and round_num < MAX_ROUNDS:
            fq = judge.get("followup_question", "").strip()
            if fq:
                print(f"\n💬 面试官追问：{fq}")
                continue
        break

    return performance, "\n".join(answers), transcript


# ── 断点保护：边答边落盘 + 写库幂等重跑 ──
def _progress_file():
    """当前空间的面试进度落盘文件（按空间分目录）。"""
    return space_dir() / "interview_progress.json"


def _q_dump(q: dict) -> dict:
    return {
        "question": q.get("question", ""),
        "source": q.get("source", ""),
        "topic": q.get("topic", ""),
        "item_id": q.get("item_id"),
        "section": q.get("section", ""),
        "item": q["item"].model_dump(mode="json") if q.get("item") else None,
    }


def _r_dump(r: dict) -> dict:
    return {
        "question": r.get("question", ""),
        "source": r.get("source", ""),
        "topic": r.get("topic", ""),
        "performance": r.get("performance", ""),
        "answer": r.get("answer", ""),
        "points": r.get("points", []),
        "misses": r.get("misses", []),
        "reason": r.get("reason", ""),
        "item": r["item"].model_dump(mode="json") if r.get("item") else None,
    }


def _save_progress(questions, answered, behaviors):
    """把当前面试进度落盘。item 用快照序列化，None 保持 None。"""
    try:
        data = {
            "questions": [_q_dump(q) for q in questions],
            "answered": [_r_dump(r) for r in answered],
            "behaviors": behaviors,
        }
        _mi._progress_file().write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logging.warning("面试进度落盘失败：%s", e)


def _load_progress():
    """读回上次的面试进度。文件缺失或损坏返回 None。"""
    if not _mi._progress_file().exists():
        return None
    try:
        data = json.loads(_mi._progress_file().read_text(encoding="utf-8"))
        questions = [dict(q) for q in data.get("questions", [])]
        for q in questions:
            q["item"] = KnowledgeItem(**q["item"]) if q.get("item") else None
        answered = [dict(r) for r in data.get("answered", [])]
        for r in answered:
            r["item"] = KnowledgeItem(**r["item"]) if r.get("item") else None
        return {"questions": questions, "answered": answered, "behaviors": data.get("behaviors", [])}
    except Exception as e:
        logging.warning("面试进度读取失败：%s", e)
        return None


def _clear_progress():
    """写库成功后清掉落盘，表示本场面试已完成。"""
    try:
        _mi._progress_file().unlink(missing_ok=True)
    except Exception as e:
        logging.warning("清理面试进度失败：%s", e)


def recover():
    """把上次未写库的面试结果补写进知识库。幂等：可重复执行，不重复涨 mastery。"""
    from .writeback import apply_verdict
    prog = _load_progress()
    if not prog or not prog["answered"]:
        print("没有需要恢复的面试。")
        return
    answered = prog["answered"]
    behaviors = prog.get("behaviors", [])
    print(f"发现上次未完成的面试：已答 {len(answered)} 题，正在补写...")
    updated, new = apply_verdict(answered, behaviors, space=_cfg.SPACE)
    _clear_progress()
    print(f"补写完成（更新 {updated} 题掌握度，新采集 {new} 题进错题本）。")


# ── 动态智能体循环 ──
def run_dynamic_session(
    section_order,
    pool_by_section,
    resume,
    jd,
    weak_items,
    *,
    ask_fn,
    on_save=None,
    interrupted=False,
    weak_topics=None,
):
    """动态面试状态机：选下一题 → 出题 → 等回答 → 追问 → 决策 → 循环。"""
    questions: list[dict] = []
    results = []
    asked_before: list[str] = []
    sec_idx = 0
    sec_asked: dict[str, int] = {}
    next_action: str | None = None
    next_guidance: str = ""          # 新增：决策给出的出题指引，供下轮 deep_dive 消费

    while sec_idx < len(section_order):
        if len(questions) >= MAX_TOTAL_QUESTIONS:
            print("\n（达到整场题数上限，面试结束）")
            break
        section = section_order[sec_idx]
        if sec_asked.get(section, 0) >= MAX_SECTION_QUESTIONS:
            print(f"\n（{section} 已达章节上限，进入下一章）")
            sec_idx += 1
            continue
        if sec_asked.get(section, 0) == 0:
            print(f"\n{'=' * 50}\n【{section}】\n{'=' * 50}")

        if sec_asked.get(section, 0) == 0:
            q = pool_by_section[section].pop(0) if pool_by_section.get(section) else {}
            if not q:
                q = _mi.generate_dynamic_question(section, "", resume, jd, weak_items, asked_before)
        elif next_action == "deep_dive":
            q = _mi.generate_dynamic_question(section, next_guidance or "深挖上一题主题", resume, jd, weak_items, asked_before)
        else:
            q = pool_by_section[section].pop(0) if pool_by_section.get(section) else {}
            if not q:
                q = _mi.generate_dynamic_question(section, "", resume, jd, weak_items, asked_before)

        if not q or not q.get("question"):
            print(f"\n⚠️ 出题失败，{section} 章节结束。")
            sec_idx += 1
            continue
        q["section"] = section
        q.setdefault("source", "generic")
        q.setdefault("topic", "")
        q.setdefault("item", None)
        questions.append(q)

        print(f"\n[第 {len(questions)}/{MAX_TOTAL_QUESTIONS} 题 · {section}] {q['question']}")

        try:
            ref_answer = q["item"].answer if q["item"] else ""
            performance, answer_text, transcript = _mi.interview_one(
                q["question"], ask_fn, ref_answer, asked_before=asked_before
            )
        except (KeyboardInterrupt, EOFError):
            if not interrupted:
                raise
            print("\n\n已退出模拟面试（已答的题会保存）。")
            break

        asked_before.append(q["question"])
        last_judge = (transcript or [{}])[-1]
        results.append({
            "question": q["question"], "source": q.get("source", ""),
            "topic": q.get("topic", ""), "item": q.get("item"),
            "performance": performance, "answer": answer_text,
            "transcript": transcript,
            "points": last_judge.get("points", []),
            "misses": [],
            "reason": last_judge.get("reason", ""),
        })
        sec_asked[section] = sec_asked.get(section, 0) + 1
        if on_save:
            on_save(questions, results)

        emoji = {"pass": "✅", "partial": "⚠️", "fail": "❌"}.get(performance, "❓")
        print(f"\n{emoji} 本题表现：{performance.upper()}")

        last_judge = (transcript or [{}])[-1]
        remaining = section_order[sec_idx + 1:]
        if sec_idx == len(section_order) - 1 and sec_asked.get(section, 0) >= MIN_SECTION_QUESTIONS:
            decision = {"action": "end", "guidance": "", "reason": "最后一章已问，面试结束"}
        else:
            decision = _mi.decide_next(
                section, q["question"], performance, last_judge.get("reason", ""),
                sec_asked.get(section, 0), remaining, asked_before,
                weak_topics=weak_topics,
            )
        next_action = decision["action"]
        next_guidance = decision.get("guidance", "")   # 新增：取出题指引
        if decision.get("reason"):
            print(f"      → 面试官决策：{next_action}（{decision['reason'][:60]}）")

        if next_action == "end" and sec_asked.get(section, 0) >= MIN_SECTION_QUESTIONS:
            break
        if next_action == "next_section" and sec_asked.get(section, 0) >= MIN_SECTION_QUESTIONS:
            sec_idx += 1
        elif next_action == "deep_dive" and sec_asked.get(section, 0) >= MAX_SECTION_QUESTIONS:
            sec_idx += 1

    return questions, results