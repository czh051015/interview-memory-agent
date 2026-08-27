"""判卷（07 计划 T4）：期望要点、追问判断、单轮判定。从 scripts 原样搬迁。"""

import logging

# 活引用：测试 patch 的是 src.mock 包的命名空间
# （@patch.object(mi, "chat_json")）。函数住在本子模块，若缓存 chat_json 为模块全局，
# 测试 patch 壳属性穿透不进来。统一经 _mi 取壳当前属性，patch 才能生效。
import src.mock as _mi  # 活引用：LLM 调用一律经包取 chat_json（测试 patch 包属性才穿透）

from .prompts import (
    _EXPECTED_POINTS_PROMPT,
    _FOLLOWUP_PROMPT,
    _RUBRIC_FOLLOWUP_PROMPT,
    _SINGLE_JUDGE_PROMPT,
    _RUBRIC_SINGLE_PROMPT,
)


def get_expected_points(question: str, answer: str = "") -> list[str]:
    """期望要点：有参考答案就用参考答案，否则 LLM 现场生成。"""
    if answer.strip():
        return [answer.strip()]
    try:
        data = _mi.chat_json(_EXPECTED_POINTS_PROMPT, f"面试题：{question}")
        return data.get("points", [])
    except Exception as e:
        logging.warning("生成期望要点失败，跳过对照：%s", e)
        return []


def judge_followup(
    question: str,
    points: list[str],
    answer: str,
    round_num: int,
    *,
    use_rubric: bool = True,
    cross_on_partial: bool = False,
    asked_before: list[str] | None = None,
) -> dict:
    """追问判断：LLM 输出结构化判断，兜底为 partial。

    cross_on_partial=True 时：主判官判 partial（拿不准）→ 第二判官复核，
    复核给出明确判定（pass/fail）则采纳并标注；复核仍 partial 则保留。
    """
    prompt = _RUBRIC_FOLLOWUP_PROMPT if use_rubric else _FOLLOWUP_PROMPT
    ctx = ""
    if asked_before:
        ctx = "\n本场已问过的题目（面试官记忆，追问可参考、请勿重复提问）：\n" + "\n".join(
            f"- {q[:80]}" for q in asked_before
        ) + "\n"
    user_prompt = (
        f"面试题：{question}\n"
        f"期望要点：{points}\n"
        f"候选人回答（第{round_num}轮）：{answer}"
        f"{ctx}"
    )
    try:
        result = _mi.chat_json(prompt, user_prompt)
    except Exception as e:
        logging.warning("追问判断失败，兜底 partial：%s", e)
        return {"need_followup": False, "followup_question": "", "reason": "判断失败", "performance": "partial"}

    if cross_on_partial and result.get("performance") == "partial":
        try:
            review = _mi.chat_json(prompt, user_prompt, cross=True)
            if review.get("performance") in ("pass", "fail"):
                result = review
                result["reason"] = f"【第二判官复核】{result.get('reason', '')}"
                result["cross_reviewed"] = True
        except Exception as e:
            logging.warning("第二判官复核失败，保留主判官 partial：%s", e)
    return result


def judge_single_round(
    question: str,
    answer: str,
    *,
    expected_points: list[str] | None = None,
    use_rubric: bool = True,
    cross: bool = False,
    cross_on_partial: bool = False,
) -> dict:
    """单轮判定（Web 版）：LLM 生成期望要点 + 差距 + 建议判定。失败兜底 partial。"""
    points_section = ""
    if expected_points:
        points_section = "参考答案要点：\n" + "\n".join(f"- {p}" for p in expected_points) + "\n"
    user_prompt = f"面试题：{question}\n{points_section}候选人回答：{answer}"

    def _judge(cross_call: bool) -> dict:
        data = _mi.chat_json(
            _RUBRIC_SINGLE_PROMPT if use_rubric else _SINGLE_JUDGE_PROMPT,
            user_prompt,
            cross=cross_call,
        )
        if not isinstance(data.get("points"), list) or not isinstance(data.get("misses"), list):
            raise ValueError("points/misses 必须为数组")
        suggested = data.get("suggested", "partial")
        if suggested not in ("pass", "partial", "fail"):
            suggested = "partial"
        return {
            "points": [str(p) for p in data["points"]],
            "misses": [str(m) for m in data["misses"]],
            "suggested": suggested,
            "reason": str(data.get("reason", "")),
        }

    try:
        result = _judge(cross)
        if cross_on_partial and not cross and result["suggested"] == "partial":
            try:
                review = _judge(cross_call=True)
                if review["suggested"] in ("pass", "fail"):
                    result = review
                    result["reason"] = f"【第二判官复核】{result['reason']}"
                    result["cross_reviewed"] = True
            except Exception as e:
                logging.warning("第二判官复核失败，保留主判官 partial：%s", e)
        return result
    except Exception as e:
        logging.warning("单轮判定失败，兜底 partial：%s", e)
        return {"points": [], "misses": [], "suggested": "partial", "reason": "LLM 判定失败"}