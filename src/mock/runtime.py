"""申论门禁运行态（docs/22 §3.4 + 38 §4.3）：按需改进建议 guidance(point_id)。

docs/38 收敛：判因层退役（D47/D49）——「为什么标」由门禁评分响应带回（verdict.reason，
0 token），建议区只有 ③ 需要懒加载 1 次 LLM；用户点开某采分点才调 guidance(point_id)：
  · 语境 = 该点的门禁事实（gate_score 单点，0 token）：官方写法 + 命中/缺失关键词 +
    材料出处 + 作答原文——不判因、不喂材料全文（docs/38 §7 runtime 收敛）
  · 输出 gap / how / rewrite（候选草稿，前端固定带"（供参考，以官方答案为准）"）
示证档（align）无判定无建议：guidance 不路由（API 400 明确提示）。
explain_point（L5 有界讲解）保留：非门禁语境，围绕单点换说法/为什么/辨析。
旧 docs/35 四分支判因路由 / text_compare_cause / pick_leading_point（推 1 个漏点）
随 L1 响应形态（misses/leading → verdicts）退役，已在 docs/38 §8.2 失效声明区。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.shenlun import score as _sc  # 活引用 gate_score（单点规则判定，0 token）
from .prompts import EXPLAIN_PROMPT, GATE_IMPROVE_PROMPT
# 活引用：LLM 调用一律经包取当前属性（测试 patch 的是 src.mock 命名空间：
# @patch.object(mi, "chat_json")），若缓存为模块全局则 patch 穿透不进来。
import src.mock as _mi

# 作答截断（防超长作答爆 token，与 judge_llm 同量级）
_ANSWER_MAX = 3000

# 门禁单点状态的中文名（guidance 语境行，只陈述命中事实）
_STATUS_WORD = {"hit": "全部命中", "miss": "全部缺失", "gray": "部分命中"}


@dataclass
class GuidanceResult:
    """门禁模式建议区③改进建议（docs/38 §4.3）：单采分点懒加载产物。

    official（建议区② 同源回放）：source_snippet ?? 材料锚句原文（D46，0 数据工程兜底）；
    gap/how/rewrite 由 LLM 生成（GATE_IMPROVE_PROMPT，单次调用），失败置空；
    三者都是候选草稿——展示方固定带"（供参考，以官方答案为准）"。
    """
    point_id: str
    point: str
    official: str = ""   # ② 标准答案原文（与评分响应同值，③ 语境展示用）
    gap: str = ""        # 差距在哪（与官方写法的差距，只陈述可验证事实）
    how: str = ""        # 怎么补（结合官方写法与材料出处）
    rewrite: str = ""    # 示范句（整点没写到 → 全新示范；已沾边 → 改写示范）


@dataclass
class ExplainResult:
    """单个漏点的有界讲解产物（L5，docs/22 §3.4 追加）：换说法 / 为什么 / 辨析。

    围绕用户点开的这一个漏点，绝不生成完整作答（no_full_answer）。
    material_source 取自 score 锚定（0 token）；rephrase/why/distinguish 由 LLM 生成，
    失败置空，调用方按空展示。
    """
    point_id: str
    point: str
    material_source: str | None = None  # L3 材料锚定（「材料第X段：'…'」，0 token）
    rephrase: str = ""                  # 换一种更口语/更易懂的说法
    why: str = ""                       # 为什么材料这句话能支撑这个点
    distinguish: str = ""               # 与相邻点的辨析（无相邻点则空串）


def guidance(material: str, answer: str, points, point_id: str,
             question: str = "") -> GuidanceResult | None:
    """生成单个采分点的改进建议（docs/38 §4.3 ③，仅门禁模式由 API 调用）。

    语境 = 该点的门禁规则事实（gate_score 单点，0 token）：官方写法（source_snippet ??
    材料锚句，D46）+ 全部关键词 + 命中/缺失事实 + 材料出处 + 作答原文。
    不判因（为什么标在评分响应的 verdict.reason，D47 ①）、不喂材料全文——
    输入面收紧，LLM 只产建议不产证据。point_id 不在 points → None。
    LLM 失败不阻断：gap/how/rewrite 置空仍返回（② 在评分响应里，不重复回放）。
    """
    p = next((x for x in points if x.id == point_id), None)
    if p is None:
        return None
    v = _sc.gate_score(answer, [p], materials=material)[0]  # 单点规则判定（0 token）
    base = (
        f"## 采分点\n{p.point}（{p.score} 分）\n"
        f"## 官方写法\n{v.official or '（未提供官方原句，按采分点名称与关键词判断）'}\n"
        f"## 该点关键词\n{'、'.join(p.keywords)}\n"
        f"## 作答中命中/缺失（{_STATUS_WORD.get(v.status, v.status)}）\n"
        f"命中：{'、'.join(v.matched) or '无'}；缺失：{'、'.join(v.missing) or '无'}\n"
        f"## 材料出处\n{v.anchor or '（未锚到该点材料原话）'}"
    )
    out = GuidanceResult(point_id=p.id, point=p.point, official=v.official)
    try:
        # ③ 改进建议：单点候选草稿（一次 LLM 调用；失败置空不阻断）
        data = _mi.chat_json(
            GATE_IMPROVE_PROMPT,
            f"{base}\n## 用户作答\n{(answer or '（空答）')[: _ANSWER_MAX]}",
            max_tokens=512,
        )
        out.gap = str(data.get("gap") or "").strip()
        out.how = str(data.get("how") or "").strip()
        out.rewrite = str(data.get("rewrite") or "").strip()
    except Exception as e:
        logging.warning("改进建议生成失败（point=%s）：%s", p.point, e)
    return out


def explain_point(material: str, answer: str, points, point_id: str) -> ExplainResult | None:
    """按需生成单个漏点的有界讲解（docs/22 §3.4 追加）：L3 + 换说法/为什么/辨析。

    与 guidance 同源：只生成用户点开的那个点，不自动循环。point_id 不在 points → None。
    LLM 失败不阻断：rephrase/why/distinguish 置空，L3 材料锚定仍可展示。
    红线：绝不生成完整作答段落（no_full_answer）——这是「用户想换个说法/为什么」的安全回应，
    不重新打开自由聊天 / 逼问那团坑。
    """
    p = next((x for x in points if x.id == point_id), None)
    if p is None:
        return None
    sr = _sc.score_answer(answer, points, materials=material)
    sp = next((x for x in sr.hit_points + sr.miss_points if x.id == point_id), None)
    material_source = sp.material_source if sp else None

    base = (
        f"## 漏点\n{p.point}（{p.score} 分）\n"
        f"## 材料原话\n{material_source or '（材料中未锚到该点原话）'}\n"
        f"## 该点关键词\n{'、'.join(p.keywords)}"
    )
    out = ExplainResult(point_id=p.id, point=p.point, material_source=material_source)
    try:
        data = _mi.chat_json(
            EXPLAIN_PROMPT, f"{base}\n## 用户作答\n{answer or '（空答）'}", max_tokens=512)
        out.rephrase = str(data.get("rephrase") or "").strip()
        out.why = str(data.get("why") or "").strip()
        out.distinguish = str(data.get("distinguish") or "").strip()
    except Exception as e:
        logging.warning("L5 讲解生成失败（point=%s）：%s", p.point, e)
    return out
