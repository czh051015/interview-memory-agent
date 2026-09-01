"""LLM-as-a-Judge 评分引擎（docs/26 §6.1，引擎B）——与 score_answer 同签名，可插拔对比。

判定方式：LLM 按 rubric 逐点判定 hit/miss + 强制证据输出（matched_text/material_source）。
fuzzy（同义改写）与 nosource（没结合材料）的区分**全在 rubric 里**——不需要 τ、
不需要分层校准。每题 1 次 LLM 调用（src.llm.chat_json，DeepSeek，temperature=0）。

失败兜底：LLM 挂/超时/解析失败 → 降级回 score_answer（引擎A：kw+语义层），评分永不空转。
命中点 matched_by="llm"（与 "kw"/"semantic" 三方共存，trace 可区分谁判的）。

Return 约定：与 score_answer 不同，返回 (ScoreResult, warnings) 二元组——
LLM 判定质量需要 warnings 审计（未判定点/降级原因），纯 ScoreResult 表达不了。
"""
from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, ValidationError

from src.llm import chat_json
from src.shenlun.score import Point, ScoreResult, _score_answer_kw

logger = logging.getLogger(__name__)

_MATERIAL_MAX = 6000   # 材料截断（doc 26 §6.1：~6000 字）
_ANSWER_MAX = 3000     # 作答截断（防超长跑题答爆 token）
_POINTS_MAX = 20       # 点数上限保护（防 prompt 过长）


class Verdict(BaseModel):
    point_id: str
    verdict: Literal["hit", "miss"]
    cause: Literal["没写", "写模糊", "没结合材料", "套话无具体性", "答非所问", ""] = ""
    matched_text: str = ""
    material_source: str = ""


class JudgeOutput(BaseModel):
    verdicts: list[Verdict]


_JUDGE_SYSTEM = """你是申论阅卷人。评分目标是识别：这个点是不是答到了核心内容；不是用深度不足去硬判 miss。深度不足、套话、空泛属于诊断层标注，不应直接抹掉命中。

判定依据：题干要求 + 材料（给定资料）+ 采分点定义（point 字段为满分对照）。

对每个采分点，按三步执行：
【第1步·作答检查】作答里有没有表达该点的核心内容（原词或同义改写都算）？
  完全没有 → 直接判 miss，cause=没写，两个证据都填空串，跳过第2、3步。

【第2步·材料支撑检查】第1步找到的作答内容，能否在材料中找到语义支撑句？
  支撑句 = 材料中表达同一要点的原句；提出对策题可放宽：能对应到材料里的问题句/原因句也算支撑。
  找到 → 记入 material_source；找不到 → material_source 填空串。

【第3步·按核心内容判定（若本步命中，原则上判 hit；深度不足只是 cause 诊断）】：
  1. 内容方向与题干要求不符（如题干要求"概括举措成效"却写成"建议/对策"）→ miss，cause=答非所问
  2. 无材料支撑（第2步填空串）→ miss，cause=没结合材料
     （内容自创/凭空发挥；阅卷规则：答案70%源自材料，自创不得分）
  3. 只要作答明确写到该点的核心内容（主体/对象/方式/成效中的关键要素），即使语言口语、表达不够丰富，
     也应判 hit。此时若还存在"深度不足、抽象口号、没有具体展开"，将 cause 记为 "套话无具体性"，作为诊断标注，
     但不要因为这类诊断而硬改成 miss。
  4. 表达模糊、意思没到位（沾边但说不清），且没有明确表述核心内容→ miss，cause=写模糊

判定原则：
- 评分层职责：看"有没有提到该点核心内容"（踩点给分）
- 诊断层职责：给出"为什么不够好"（套话无具体性、答非所问等）
- 因此：提到核心内容 = hit；深度不足 = cause 诊断，不得直接改成 miss

输出 JSON（每个点必须包含三步证据，只输出 JSON）：
{"verdicts": [{"point_id": "c1",
               "verdict": "hit"|"miss",
               "cause": "没写"|"写模糊"|"没结合材料"|"套话无具体性"|"答非所问"|"",
               "matched_text": "作答原句（找不到填空串）",
               "material_source": "材料支撑句（找不到填空串）"}]}"""


def _build_user(question: str, material: str, answer: str, points: list[Point]) -> str:
    lines = [f"## 题目\n{question}"] if question else []
    if material:
        lines.append(f"## 材料（给定资料）\n{material[:_MATERIAL_MAX]}")
    pts = "\n".join(
        f"- {p.id} | {p.point} | 关键词: {'、'.join(p.keywords)} | 分值: {p.score}"
        for p in points[:_POINTS_MAX]
    )
    lines.append(f"## 采分点\n{pts}")
    lines.append(f"## 作答\n{answer[:_ANSWER_MAX]}")
    return "\n\n".join(lines)


def _normalize_verdicts(raw: object) -> tuple[dict[str, Verdict], list[str]]:
    """Validate and normalize LLM verdict output. Single invalid rows are downgraded to miss,
    while structurally invalid payloads fall back to the deterministic engine.
    """
    warnings: list[str] = []
    if not isinstance(raw, dict):
        return {}, ["LLM 输出结构不是 dict，pydantic 校验失败，已降级确定性引擎"]

    verdicts = raw.get("verdicts")
    if not isinstance(verdicts, list):
        return {}, ["LLM 输出缺少 verdicts 列表，pydantic 校验失败，已降级确定性引擎"]

    parsed: dict[str, Verdict] = {}
    for i, item in enumerate(verdicts, 1):
        if not isinstance(item, dict):
            warnings.append(f"第 {i} 条判定不是对象，pydantic 校验失败，按 miss 处理")
            continue

        pid = str(item.get("point_id") or "").strip()
        if not pid:
            warnings.append(f"第 {i} 条判定缺少 point_id，已跳过")
            continue

        raw_verdict = item.get("verdict")
        if raw_verdict == "hit":
            try:
                parsed[pid] = Verdict.model_validate(item)
            except ValidationError as exc:
                warnings.append(f"第 {i} 条判定 pydantic 校验失败：{exc.errors()[0].get('msg', str(exc))}，按 miss 处理")
                sanitized = dict(item)
                sanitized["verdict"] = "miss"
                sanitized["cause"] = str(item.get("cause") or "").strip() or "没写"
                parsed[pid] = Verdict.model_validate(sanitized)
            continue

        sanitized = dict(item)
        sanitized["point_id"] = pid
        sanitized["verdict"] = "miss"
        sanitized["cause"] = str(item.get("cause") or "").strip() or "没写"
        try:
            parsed[pid] = Verdict.model_validate(sanitized)
        except ValidationError as exc:
            warnings.append(f"第 {i} 条判定 pydantic 校验失败：{exc.errors()[0].get('msg', str(exc))}，已按 miss 处理")
            # Keep semantic safety fallback even if the raw mix is still invalid.
            parsed[pid] = Verdict(point_id=pid, verdict="miss", cause="没写")
            continue
        if raw_verdict not in ("miss", None, ""):
            warnings.append(f"第 {i} 条判定 verdict={raw_verdict!r} 非法，pydantic 校验后按 miss 处理")
    return parsed, warnings


def judge_score(answer: str, points: list[Point], materials: str = "",
                question: str = "") -> tuple[ScoreResult, list[str]]:
    """LLM 评判引擎。与 score_answer 同签名（多 question，题干语境用于判"答非所问"）。

    Returns:
        (ScoreResult, warnings)：命中点 matched_by="llm"、miss 点带 miss_cause；
        LLM 失败 → 降级 score_answer（kw+语义层），warnings 说明降级原因。
    """
    try:
        result = chat_json(
            system_prompt=_JUDGE_SYSTEM,
            user_prompt=_build_user(question, materials, answer, points),
            temperature=0.0,
            max_tokens=4096,
        )
    except Exception as e:
        logger.error("judge_score LLM call failed, fallback to kw engine: %s", e)
        return _score_answer_kw(answer, points, materials=materials), [f"LLM 不可用，已降级确定性引擎: {e}"]

    by_id, warnings = _normalize_verdicts(result)
    if not by_id and warnings:
        logger.warning("judge_score LLM payload validation failed, fallback to kw engine: %s", warnings)
        return _score_answer_kw(answer, points, materials=materials), warnings

    hits, misses = [], []
    for p in points:
        v = by_id.get(p.id)
        if v is None:
            warnings.append(f"LLM 未判定 {p.id}，按 miss 处理")
            misses.append(Point(id=p.id, point=p.point, keywords=p.keywords,
                                score=p.score, type=p.type, miss_cause="未判定"))
            continue

        if v.verdict == "hit":
            h = Point(id=p.id, point=p.point, keywords=p.keywords, score=p.score, type=p.type,
                      matched_text=(v.matched_text or "").strip() or None, matched_by="llm")
            h.material_source = (v.material_source or "").strip() or None
            cause = (v.cause or "").strip()
            if cause and cause not in {"没写"}:
                h.quality_cause = cause
            hits.append(h)
        else:
            m = Point(id=p.id, point=p.point, keywords=p.keywords, score=p.score, type=p.type,
                      miss_cause=(v.cause or "").strip() or "没写")
            m.material_source = (v.material_source or "").strip() or None
            misses.append(m)
    return ScoreResult(hit_points=hits, miss_points=misses), warnings
