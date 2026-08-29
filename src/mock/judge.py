"""【已废弃 · docs/18】判卷（07 计划 T4）：期望要点、追问判断、单轮判定。

判定职责已被确定性评分 score_answer（src/shenlun/score.py）+ 逼近引导 prompt
（src/mock/prompts.py._APPROACH_PROMPT，LLM 只做提示不做判断）取代。
本文件保留可导入，仅因 Web 模拟面试（app/api/mock.py）仍在引用；新代码不得使用。
（面试域 prompt 从 prompts.py 内联到本文件，随废弃模块共进退。）
"""

import logging

# 活引用：测试 patch 的是 src.mock 包的命名空间
# （@patch.object(mi, "chat_json")）。函数住在本子模块，若缓存 chat_json 为模块全局，
# 测试 patch 壳属性穿透不进来。统一经 _mi 取壳当前属性，patch 才能生效。
import src.mock as _mi  # 活引用：LLM 调用一律经包取 chat_json（测试 patch 包属性才穿透）

# ── 面试域 prompt（废弃模块自用，从 prompts.py 内联而来）──
_EXPECTED_POINTS_PROMPT = (
    "你是一位严格的面试官。下面是一道面试题，请列出候选人「应该答到的关键点」。\n"
    "要求：只输出 JSON，格式 {\"points\": [\"要点1\", \"要点2\", ...]}，3-5 个要点，每个一句话。"
)

_FOLLOWUP_PROMPT = (
    "你是一位严格的面试官，正在考察候选人。你会收到：面试题、期望要点、候选人的回答。\n"
    "任务：判断是否追问，并评价表现。只输出 JSON：\n"
    "{\"need_followup\": true/false, \"followup_question\": \"追问问题\", "
    "\"reason\": \"判断依据\", \"performance\": \"pass\"|\"partial\"|\"fail\"}\n"
    "标准：覆盖大部分要点且条理清晰→pass 不再追问；漏关键点或含糊→partial 追问；明显不会或跑题→fail。\n"
    "追问要具体、往下钻，围绕候选人回答里的细节/数字/取舍往下问（可追问情境-任务-行动-结果），不要泛泛地问。"
)

_RUBRIC_FOLLOWUP_PROMPT = (
    "你是一位严格的面试官，正在依据固定评分量规考察候选人。你会收到：面试题、期望要点（可能为无）、候选人的回答。\n"
    "评分量规（四个维度，判定必须逐维对照，判断依据必须引用回答原文）：\n"
    "1. 正确性：核心事实与原理是否准确，有无硬伤；\n"
    "2. 完整性：是否覆盖期望要点中的关键点（无期望要点时，自行判断这道题应包含哪些关键点）；\n"
    "3. 深度：是否讲清机制/细节/取舍，而非泛泛而谈；\n"
    "4. 表达：结构是否清晰，是否答非所问。\n"
    "只输出 JSON：\n"
    '{"need_followup": true/false, "followup_question": "追问问题", '
    '"reason": "判断依据（必须引用原文，如：回答只说「…」未提「…」）", "performance": "pass"|"partial"|"fail"}\n'
    "判定标准：四维均达标→pass 不再追问；1-2 个维度不足→partial 追问；存在事实错误或大段缺失→fail。\n"
    "追问要具体、往下钻，围绕回答里的细节/数字/取舍，不要泛泛地问。"
)

_SINGLE_JUDGE_PROMPT = (
    "你是一位严格的面试官，正在考察候选人。你会收到：面试题、候选人的回答。\n"
    "任务：判定回答质量，并给候选人对照。只输出 JSON：\n"
    '{"points": ["应该答到的要点1", "要点2", ...], '
    '"misses": ["回答里漏掉的点1", ...], '
    '"suggested": "pass"|"partial"|"fail", '
    '"reason": "一句判断依据"}\n'
    "标准：覆盖大部分要点且条理清晰→pass；漏关键点或含糊→partial；明显不会或跑题→fail。\n"
    "points 给 3-5 个（这道题应该答到什么），misses 只列确实漏掉/答错的（0-3 个，没有就给空数组）。\n"
    "reason 一句话，指出最致命的差距。"
)

_RUBRIC_SINGLE_PROMPT = (
    "你是一位严格的面试官，正在依据固定评分量规考察候选人。你会收到：面试题、参考答案要点（可能为无）、候选人的回答。\n"
    "评分量规（四个维度，判定必须逐维对照，misses 必须引用回答原文作为证据）：\n"
    "1. 正确性：核心事实与原理是否准确，有无硬伤；\n"
    "2. 完整性：是否覆盖参考答案要点中的关键点（无参考答案时，自行判断这道题应包含哪些关键点）；\n"
    "3. 深度：是否讲清机制/细节/取舍，而非泛泛而谈；\n"
    "4. 表达：结构是否清晰，是否答非所问。\n"
    "只输出 JSON：\n"
    '{"points": ["应该答到的要点1", ...], "misses": ["漏掉/答错的点，必须引用原文，如：回答只说「…」未提「…」", ...], '
    '"suggested": "pass"|"partial"|"fail", "reason": "依据量规的一句判断"}\n'
    "判定标准：四维均达标→pass；1-2 个维度明显不足→partial；存在事实错误或大段缺失→fail。\n"
    "points 给 3-5 个，misses 只列确实漏掉/答错的（0-3 个，没有就给空数组）。"
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