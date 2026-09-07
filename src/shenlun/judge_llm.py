"""灰色带疑似标注引擎（docs/38 §4.2）——LLM 在门禁模式里唯一的判定职责。

docs/35 的 judge_score（LLM 判 hit/miss + 自由写证据字段）已退役（docs/38 D45/D49）：
命中证据（命中词/缺失词/作答原句/材料锚）全部由规则层 gate_score 生成（0 token）；
LLM 只对「关键词部分命中」的灰带点输出 suspect: null | {"label","reason"}——
**没有证据字段**，docs/36 查出的「材料顶包」（LLM 从材料借句填命中证据）在结构上
不存在。

判据输入面（§4.2 关键）：每个灰带点只给 官方写法（source_snippet ?? 材料锚句）+
全部 kw + 命中的 kw，外加作答全文；**不给材料全文、不给其他点的答案**——
LLM 无材料可借，顶包输入面直接不存在。

安全方向：LLM 挂 / 输出结构坏 / 漏标某点 → 一律按放行（suspect=None）处理，
灰带降级为「绿·语义」；绝不让解析失败误伤成疑似。

Return 约定：judge_suspect 返回 (marks, warnings)，marks = {point_id: None | {"label","reason"}}。
"""
from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, ValidationError

from src.llm import chat_json
from src.shenlun.score import GateVerdict

logger = logging.getLogger(__name__)

_ANSWER_MAX = 3000   # 作答截断（防超长跑题答爆 token）
_POINTS_MAX = 12     # 灰带点一次调用上限保护（§10 注意2：聚合一次喂，勿逐点调）

_SUSPECT_LABELS = ("疑似宽泛", "疑似方向偏离", "疑似表述不清")

# 系统提示 —— 照抄 docs/38 §4.2「Prompt 草案（实现者照抄）」，一字不改。
_SUSPECT_SYSTEM = (
    "你是申论评卷的\"存疑标注员\"。你的任务不是判对错，而是对\"关键词部分命中的\n"
    "采分点\"给出是否存疑的标注。你只标\"疑似\"，从不判\"漏了/错了\"。\n"
    "\n"
    "判定依据只有下面两段输入：\n"
    "【该点官方写法】（标准答案原句或材料对应句——该点\"写到什么程度算够\"的基准）\n"
    "【考生作答】（全文）\n"
    "\n"
    "对每个点，判断：考生作答是否表达出了官方写法的核心内容？\n"
    "- 表达出来了（虽未逐词命中，但语义等价的实质展开，或缺失的关键词被同义覆盖）\n"
    "  → \"suspect\": null（放行，交给规则层显示为命中）\n"
    "- 没表达出来或表达不到位：\n"
    "  → \"suspect\": {\"label\": 三选一, \"reason\": \"一句话，写给考生看\"}\n"
    "\n"
    "label 判定参考：\n"
    "- 疑似宽泛：只写了上位概念/口号/价值，无机制、对象、举措、成效等实质内容\n"
    "- 疑似方向偏离：写的内容与官方写法指向不同的对象/方面（答非所问的更轻表述）\n"
    "- 疑似表述不清：内容沾边但笼统含混，说不清具体是什么\n"
    "\n"
    "硬约束：\n"
    "- 严禁引用、改写、脑补输入中不存在的句子。判定只依据上述输入。\n"
    "- 你不需要给\"证据句\"——证据由系统规则提供。你只给 label 和一句话 reason。\n"
    "- reason 用口语、面向考生，解释\"为什么存疑\"。\n"
    "\n"
    "输出 JSON（只输出 JSON）：\n"
    '{"verdicts":[\n'
    '  {"point_id":"c5","point_name":"民生联动","suspect":null},\n'
    '  {"point_id":"c8","point_name":"民生提质",\n'
    '   "suspect":{"label":"疑似宽泛","reason":"你只写了\'获得感幸福感\'的口号，没写共建共享的具体机制"}}\n'
    "]}"
)


class SuspectRow(BaseModel):
    """灰带点疑似标注行（docs/38 §4.2 输出契约）：无任何证据字段。"""

    point_id: str
    point_name: str = ""
    suspect: dict | None = None  # {"label": 三选一, "reason": 一句话}；null = 放行


class SuspectOutput(BaseModel):
    verdicts: list[SuspectRow]


def _build_user(gray: list[GateVerdict], answer: str) -> str:
    """用户消息：灰带点清单（id/名称/官方写法/全部 kw/命中 kw）+ 作答全文。

    不含材料全文、不含其他点的答案原文（§4.2：LLM 无材料可借）。
    """
    lines = ["## 存疑点列表"]
    for v in gray[:_POINTS_MAX]:
        official = v.official or "（未提供官方原句，按采分点名称与关键词判断）"
        lines.append(
            f"- {v.point_id} | {v.point_name} | 官方写法：{official} | "
            f"关键词：{'、'.join(v.keywords)} | 作答中命中：{'、'.join(v.matched) or '无'}"
        )
    lines.append(f"\n## 考生作答\n{answer[:_ANSWER_MAX]}")
    return "\n".join(lines)


def _normalize(raw: object, wanted: set[str]) -> tuple[dict, list[str]]:
    """解析 LLM 输出为 {point_id: None | {"label","reason"}}；坏行/漏标 → 放行 + warnings。

    结构性坏输出（非 dict / 无 verdicts / 全坏）→ 返回 {}（调用方按全放行消化）。
    """
    warnings: list[str] = []
    if not isinstance(raw, dict):
        return {}, ["LLM 输出结构不是 dict，灰带点全部按放行处理（降级绿·语义）"]
    verdicts = raw.get("verdicts")
    if not isinstance(verdicts, list):
        return {}, ["LLM 输出缺少 verdicts 列表，灰带点全部按放行处理（降级绿·语义）"]

    marks: dict = {}
    for i, item in enumerate(verdicts, 1):
        if not isinstance(item, dict):
            warnings.append(f"第 {i} 条标注不是对象，跳过该条")
            continue
        pid = str(item.get("point_id") or "").strip()
        if not pid:
            warnings.append(f"第 {i} 条标注缺少 point_id，已跳过")
            continue
        try:
            row = SuspectRow.model_validate(item)
        except ValidationError as exc:
            msg = exc.errors()[0].get("msg", str(exc)) if exc.errors() else str(exc)
            warnings.append(f"第 {i} 条标注（{pid}）pydantic 校验失败：{msg}，按放行处理")
            marks[pid] = None
            continue
        mark = row.suspect
        if mark is not None:
            label = str(mark.get("label") or "").strip()
            if label not in _SUSPECT_LABELS:
                warnings.append(f"第 {i} 条标注（{pid}）label={label!r} 非法，按放行处理")
                mark = None
            else:
                mark = {"label": label, "reason": str(mark.get("reason") or "").strip()}
        marks[pid] = mark
    # 灰带点没被 LLM 标到 → 放行（安全方向），warnings 留给审计
    for pid in wanted:
        if pid not in marks:
            warnings.append(f"LLM 未标注灰带点 {pid}，按放行处理（降级绿·语义）")
            marks[pid] = None
    return marks, warnings


def judge_suspect(gray: list[GateVerdict], answer: str) -> tuple[dict, list[str]]:
    """灰带点疑似标注（docs/38 §4.2）：一次 LLM 调用处理全部灰带点（§10 注意2）。

    Args:
        gray: gate_score 输出里 status == "gray" 的判定（自带 官方写法/全部kw/命中kw）。
        answer: 作答全文（灰带点不随 LLM 的判据输入面，见模块 docstring）。

    Returns:
        (marks, warnings)：marks = {point_id: None | {"label","reason"}}；
        放行（null/未标/失败）为安全方向，永不出假"疑似"。
    """
    if not gray:
        return {}, []
    try:
        result = chat_json(
            system_prompt=_SUSPECT_SYSTEM,
            user_prompt=_build_user(gray, answer),
            temperature=0.0,
            max_tokens=2048,
        )
    except Exception as e:
        logger.error("judge_suspect LLM call failed, gray points released: %s", e)
        return {}, [f"LLM 不可用，灰带点全部按放行处理（降级绿·语义）: {e}"]

    marks, warnings = _normalize(result, wanted={v.point_id for v in gray})
    if not marks and warnings:
        logger.warning("judge_suspect payload validation failed, all released: %s", warnings)
    return marks, warnings
