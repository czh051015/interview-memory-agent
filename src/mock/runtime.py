"""申论示证运行态（docs/22 §3.4）：按需示证 guidance(point_id)。

范式转变（docs/22 §0）：考你（题库出题 + 逼问循环）→ 帮你（上传 + 评分 + 示证）。
一次评分出 L1（命中/漏点列表，每漏点挂材料原话），默认只推 1 个最该补的漏点 + 示证；
用户点开某个漏点才调 guidance(point_id) 按需生成 L2(DEMO) + L4(CAUSE)；
L3（材料原话）由 score 锚定，0 token 不调 LLM。
旧 practice_one 逼近循环 / 断点续练 / 伪引导确定性过滤已随范式删除（docs/22 §3.4）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.shenlun.score import score_answer
from .prompts import DEMO_PROMPT, CAUSE_PROMPT, EXPLAIN_PROMPT
# 活引用：LLM 调用一律经包取当前属性（测试 patch 的是 src.mock 命名空间：
# @patch.object(mi, "chat_json")），若缓存为模块全局则 patch 穿透不进来。
import src.mock as _mi

# 达标阈值：命中率 ≥ 0.8（docs/18 §9，评分语义不变，供调用方判「达标→回流」）
PASS_HIT_RATIO = 0.8


@dataclass
class GuidanceResult:
    """单个漏点的示证产物（L2+L3+L4）。

    material_source（L3）由 score 锚定，永远有值或 None（不依赖 LLM）；
    demo/cause（L2/L4）由 LLM 生成，失败或未生成时为空串，调用方按空展示。
    """
    point_id: str
    point: str
    material_source: str | None = None  # L3 材料锚定（「材料第X段：'…'」，0 token）
    demo: str = ""                      # L2 示范表述
    cause_type: str = ""                # L4 错因归类：完全没提 / 写偏 / 太模糊
    cause: str = ""                     # L4 错因说明
    fix: str = ""                       # L4 具体改法


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


def guidance(material: str, answer: str, points, point_id: str) -> GuidanceResult | None:
    """按需生成单个漏点的示证（docs/22 §3.4）：L3 + L2(DEMO) + L4(CAUSE)。

    只生成用户点开的那个点，不自动循环。point_id 不在 points → None。
    LLM 失败不阻断：demo/cause 置空，L3 材料锚定仍可展示。
    调用方（CLI / API）复用同一函数，不另写两套逻辑。
    """
    p = next((x for x in points if x.id == point_id), None)
    if p is None:
        return None
    # L3：材料锚定从本次评卷结果取（与展示给用户的 L1 同源，保证一致）
    sr = score_answer(answer, points, materials=material)
    sp = next((x for x in sr.hit_points + sr.miss_points if x.id == point_id), None)
    material_source = sp.material_source if sp else None

    base = (
        f"## 漏点\n{p.point}（{p.score} 分）\n"
        f"## 材料原话\n{material_source or '（材料中未锚到该点原话）'}\n"
        f"## 该点关键词\n{'、'.join(p.keywords)}"
    )
    out = GuidanceResult(point_id=p.id, point=p.point, material_source=material_source)
    try:
        demo_data = _mi.chat_json(DEMO_PROMPT, f"{base}\n\n请给出示范表述。", max_tokens=256)
        out.demo = str(demo_data.get("demo") or "").strip()
    except Exception as e:
        logging.warning("L2 示范生成失败（point=%s）：%s", p.point, e)
    try:
        cause_data = _mi.chat_json(
            CAUSE_PROMPT, f"{base}\n## 用户作答\n{answer or '（空答）'}", max_tokens=384)
        out.cause_type = str(cause_data.get("cause_type") or "").strip()
        out.cause = str(cause_data.get("cause") or "").strip()
        out.fix = str(cause_data.get("fix") or "").strip()
    except Exception as e:
        logging.warning("L4 错因诊断失败（point=%s）：%s", p.point, e)
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
    sr = score_answer(answer, points, materials=material)
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


def pick_leading_point(miss_points, question_id: str | None = None):
    """推 1 个最该补的漏点（docs/22 §4，Q7b/Q9a 两条分支保证任何阶段都有解）：
    1. 有错题本历史：漏点档案里红档（tier=red，反复漏 ≥2 次，profile 按紧急度降序）优先；
    2. 无历史 / 无红档命中：取 miss_points 中 score 最大者（benchmark 自带 score，天然兜底）。
    """
    if not miss_points:
        return None
    from src.shenlun.profile import read_weak_points  # 延迟导入：仅此分支才碰档案 DB
    reds = [wp for wp in read_weak_points(limit=200) if wp.tier == "red"]
    if reds and question_id:
        miss_by_key = {f"{question_id}:{m.id}": m for m in miss_points}
        for wp in reds:  # read_weak_points 已按紧急度降序 → 最该补的红档优先
            m = miss_by_key.get(wp.point_key)
            if m is not None:
                return m
    return max(miss_points, key=lambda p: p.score)
