"""申论工作台 API（docs/22 §3.5 + docs/42 单模式契约）—— 无状态 REST 端点。

范式（docs/22）：考你 → 帮你。docs/42 起评分 = **单引擎 gate 三态**（docs/38 的 trusted
路由退役）：不管题在不在库，都给「有没有命中采分点」的三色判定（绿/黄 + 灰带 LLM 疑似，
judge_suspect 永不硬判）；**可信度从路由模式下沉为数据属性**——采分点来源分层决定回流资格：
  · L1 库题金标：qid 在库 + points 全量一致（_points_equal，D41 防伪语义保留）；
  · L2 用户手填：InlineGold.points 直填（用户即人审），points_source="manual"（缺省）；
  · L3 LLM 拆解草稿：practice/parse / decompose 产物，points_source="llm_parse"，
    判定照给但标「参考 · 未复核」（P-D=① 建议放开 + caveat）。
内联题（L2/L3，P-A=②）漏点只进错题本（wrongbook 通道），不进 weak_points 提醒池。
示证 align 退役：仅 SCORE_FORCE=align（测试/回归锁定）可强制，生产恒 gate（M4）。

端点：
  POST /api/shenlun/practice/start     → ReAct 推题（decide 推荐优先，规则回退兜底；题库空 404）
  POST /api/shenlun/practice/parse     → 文字版标准答案 → 采分点（docs/24 §4.2，LLM 拆解 + trace，points_source=llm_parse）
  POST /api/shenlun/practice/submit    → 单引擎 gate 三色判定（verdicts + 来源分层 tier）
  POST /api/shenlun/practice/guidance  → 单点③改进建议（gap/how/rewrite，1 次 LLM，L1/L2/L3 全放开）
  POST /api/shenlun/practice/complete  → 回流（reflow_answer：answers/weak_points/events + answer_rounds；可带 verdicts 对齐判据）
  GET  /api/shenlun/remind             → 今日提醒（毕业考候选 ≤2 + 该练 topK ≤3）
  GET  /api/shenlun/weakpoints         → 薄弱点档案全表（state 筛选，档案 tab）

复用（零修改）：src/shenlun/{react.decide, reflow.{load_question,reflow_answer},
profile.{read_weak_points,read_all_weak_points,graduation_candidates}} + src.mock.runtime.{guidance,explain_point}。
"""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src import config as _cfg
from src.cleaner.schema import utcnow
from src.mock.runtime import guidance, explain_point
from src.shenlun.align import align_answer
from src.shenlun.judge_llm import judge_suspect
from src.shenlun.profile import graduation_candidates, read_all_weak_points, read_weak_points
from src.shenlun.react import decide
from src.shenlun.question_store import next_user_question_id, save_user_question
from src.shenlun.reflow import load_question, reflow_answer
from src.shenlun.score import from_benchmark, gate_score, assemble_gate, score_answer
from src.shenlun.wrongbook import build_wrongbook_item
from src.cleaner.decompose import decompose_points
from src.shenlun.score import _anchor_sentences
from app.utils.decompose_cache import save_trace, load_trace
import hashlib
import uuid
import logging
import time
import os
from fastapi import Request

logger = logging.getLogger(__name__)


def _fix_mojibake(s: str) -> str:
    """Try to fix common mojibake when UTF-8 bytes were decoded as latin-1.

    If conversion fails, return original string.
    """
    if not isinstance(s, str):
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except Exception:
        return s


def _recursively_fix_strings(obj):
    """Recursively walk obj (dict/list/str) and apply _fix_mojibake to all strings.

    Returns a new object with strings fixed. Non-string leaves are preserved.
    """
    if isinstance(obj, str):
        return _fix_mojibake(obj)
    if isinstance(obj, dict):
        return {k: _recursively_fix_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_recursively_fix_strings(v) for v in obj]
    return obj

router = APIRouter()


# ── 工具 ──────────────────────────────────────────────────────────
def _days_since(iso: str | None) -> int:
    """ISO 时间 → 距今整天数（解析失败/空按 0）。"""
    if not iso:
        return 0
    try:
        return max(0, int((utcnow() - datetime.fromisoformat(iso)).total_seconds() / 86400.0))
    except ValueError:
        return 0


def _load_or_404(question_id: str) -> dict:
    item = load_question(question_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"题目不存在：{question_id}")
    return item


class InlineGold(BaseModel):
    """前端"单题上传"模式内联的采分点 + 材料（docs/22 §3.5 追加：解题库依赖）。

    points 直接是结构化采分点（0 token 解析，主路径）；material/question/qtype 随题面。
    question_id（docs/42 L1）：声明该题来自题库/benchmark → 全量比对一致即 L1；
    缺省 → 内联题，按 points_source 分层（L2 手填 / L3 LLM 拆解）。
    """
    points: list[dict] = Field(..., description="采分点列表（{id,point,keywords,score,point_type}）")
    material: str = ""
    question: str = ""
    qtype: str = ""
    question_id: str = ""  # docs/42 L1：非空 → 校验在库 + points 一致（_points_equal），通过即 L1
    # docs/42 M2 分层信号：manual=用户手填（L2，用户即人审，缺省兼容旧前端）；
    # llm_parse=LLM 拆解草稿（L3，判定照给但标「参考 · 未复核」，不自动回流）。
    points_source: Literal["manual", "llm_parse"] = "manual"


def _mode() -> str:
    """评分模式（docs/42 单模式化）：生产恒 gate；SCORE_FORCE 仅测试/演示锁定（可强制 align 防回滚）。"""
    return _cfg.SCORE_FORCE or "gate"


def _points_equal(a: list[dict], b: list[dict]) -> str | None:
    """全量比对两套采分点 id/point/keywords（docs/38 D41 / §10 注意3）。

    防"声称 henan 题但塞了自造 points 蹭门禁"——trusted 语义的底线。
    返回 None = 一致；否则返回不一致描述（第一处差异）。
    """
    def norm(pts: list[dict]) -> dict:
        out = {}
        for p in pts or []:
            kws = tuple(sorted(str(k) for k in (p.get("keywords") or [])))
            out[str(p.get("id", ""))] = (str(p.get("point", "")), kws)
        return out

    na, nb = norm(a), norm(b)
    if set(na) != set(nb):
        return f"采分点 id 集不一致（声明 {sorted(na)} vs 库 {sorted(nb)}）"
    for pid in na:
        if na[pid] != nb[pid]:
            return f"采分点 {pid} 与库题不一致（声明 {na[pid][0]!r}/关键词 {list(na[pid][1])} vs 库 {nb[pid][0]!r}/关键词 {list(nb[pid][1])}）"
    return None


def _resolve(req) -> tuple[list, str, str, str, str, dict | None, str]:
    """从请求解析评分所需上下文，并做采分点来源分层（docs/42 §4.0）。

    返回 (points, material, question, qtype, qid, ctx, tier)：
      - tier="L1"：显式声明 question_id 且在库（内容全量比对通过，防伪语义保留）；
        或纯 question_id 命题路径（points 即库题）。
      - tier="L2"/"L3"：内联无 qid，按 gold.points_source 分（manual=L2 / llm_parse=L3，
        缺省 manual 兼容旧前端）。
      - ctx：错题本入库用的题目载体；题库模式返回 DB item，内联模式返回合成 dict。
    既无 gold 也无 question_id → 400；gold 无采分点且无 qid → 400（gate 无输入可判，
    示证档已退役，提示先提供标准答案/采分点，docs/43 §6 用户拍板）。
    """
    g = getattr(req, "gold", None)
    if g is not None and g.points:
        if getattr(g, "question_id", ""):  # L1：声明来自题库 → 必须与库题逐点一致
            item = load_question(g.question_id)  # 查无此题：用 400（防伪造 qid 蹭 L1），不 404
            if item is None:
                raise HTTPException(status_code=400,
                                    detail=f"声明的题目不存在题库中：{g.question_id}（防伪 qid 校验）")
            diff = _points_equal(g.points, item["gold"]["reference_points"])
            if diff:
                raise HTTPException(status_code=400,
                                    detail=f"内联采分点与库题不一致，不能按库题金标（L1）评分：{diff}")
            points = from_benchmark(g.points)
            material = g.material or item["task"]["material"]  # 材料缺失时回退库题（锚定可用）
            question = g.question or item["task"]["question"]
            qtype = g.qtype or item["meta"]["type"]
            return points, material, question, qtype, g.question_id, item, "L1"
        points = from_benchmark(g.points)
        material = g.material or ""
        question = g.question or ""
        qtype = g.qtype or ""
        # docs/39 §7.1：单题 ctx.id 带题面稳定 hash —— 此前恒 "inline"，手动录的不同题
        # 同漏同点会互相覆盖（题面丢失）；hash 后同题同点仍 upsert（保留语义），跨题不再冲突。
        # ctx 目前只被 wrongbook 落库消费（build_wrongbook_item 拼 sl_{id}_{point_id}），
        # 变更前已 grep ctx["id"] 无其他消费点。
        ctx = {"id": f"inline_{hashlib.md5(question.encode('utf-8')).hexdigest()[:8]}",
               "task": {"question": question}, "meta": {"type": qtype}}
        tier = "L3" if g.points_source == "llm_parse" else "L2"
        return points, material, question, qtype, "inline", ctx, tier
    if not getattr(req, "question_id", ""):
        if g is not None:  # gold 在但没采分点：gate 无输入可判（docs/43 §6，不留 align 兜底）
            raise HTTPException(status_code=400,
                                detail="内联题缺少采分点：请先手填结构化采分点（JSON），"
                                       "或粘贴标准答案全文用 LLM 拆解")
        raise HTTPException(status_code=400, detail="需提供 question_id 或 gold")
    item = _load_or_404(req.question_id)  # 纯 question_id（无 gold）：points 即库题 → L1
    points = from_benchmark(item["gold"]["reference_points"])
    material = item["task"]["material"]
    question = item["task"]["question"]
    qtype = item["meta"]["type"]
    return points, material, question, qtype, req.question_id, item, "L1"


# ── 练习会话（无状态）──────────────────────────────────────────────
@router.post("/shenlun/practice/start")
def practice_start():
    """ReAct 推题：读薄弱点档案 → 检索候选 → LLM 决策（失败规则回退）。"""
    out = decide()
    if not out.plan:
        raise HTTPException(status_code=404, detail="题库为空——先在「录入」页添加题目")
    qid = out.plan[0]["question_id"]
    item = _load_or_404(qid)
    return {
        "question_id": qid,
        "question": item["task"]["question"],
        "material": item["task"]["material"],
        "max_score": item["task"].get("max_score"),
        "type": item["meta"]["type"],
        "recommend_reason": out.plan[0].get("why", ""),
        "focus": out.focus,
        "action": out.action,
    }


class SubmitRequest(BaseModel):
    question_id: str = Field(default="", description="题目 id（题库模式，来自 practice/start）")
    gold: InlineGold | None = Field(default=None, description="单题上传模式内联采分点+材料")
    answer: str = Field(..., min_length=1, description="作答文本")


def _verdict_dict(v) -> dict:
    """PointVerdict → §6 契约 json（mode 每项带；evidence 契约为 string，null 归一空串）。"""
    return {
        "point_id": v.point_id,
        "point_name": v.point_name,
        "mode": "gate",
        "status": v.status,                       # hit | miss | suspect
        "matched_by": v.matched_by,               # kw（规则绿）| llm（灰带放行绿/疑似）
        "terms": {"matched": list(v.terms.get("matched", [])),
                  "missing": list(v.terms.get("missing", []))},
        "evidence": v.evidence or "",             # 作答原句（规则定位）；黄行空（§8.1）
        "anchor": v.anchor,                       # 「材料第X段：'…'」，hit/miss/suspect 都下发（补老缺口）
        "official": v.official,                   # source_snippet ?? 材料锚句原文（D46 兜底）
        "suspect": v.suspect,                     # 仅 status=suspect 非空
        "reason": v.reason,                       # 为什么标（规则文案或 LLM reason，D47 ①）
    }


@router.post("/shenlun/practice/submit")
def practice_submit(req: SubmitRequest):
    """评分（docs/42 单引擎）：恒 gate 三色判定 + 来源分层 tier。

    单模式化（docs/42 M1）：库内/内联统一走 gate——对每点规则绿/黄 + 灰带点聚合一次
    judge_suspect（§10 注意2），合并成 verdicts（含 anchor 全量下发）；LLM 挂 → 灰带
    全放行（安全方向），响应仍完整。tier 标注采分点来源（L1 库题金标 / L2 手填 /
    L3 LLM 拆解「参考 · 未复核」）——判定逻辑三者一致，分层只决定回流资格与展示标记。
    SCORE_FORCE=align 可强制示证对照（仅测试/回归锁定，M4 退役保底）。
    """
    points, material, question, _, _, _, tier = _resolve(req)
    if _mode() == "align":  # 仅 SCORE_FORCE=align（测试/演示锁定）可达
        ar = align_answer(req.answer, points, materials=material, question=question)
        return {"mode": "align", **ar.to_dict()}
    gray = [v for v in gate_score(req.answer, points, materials=material) if v.status == "gray"]
    marks, warnings = judge_suspect(gray, req.answer)  # 灰带为空/LLM 不可用 → 不阻塞
    verdicts = assemble_gate(req.answer, points, materials=material, suspects=marks)
    return {
        "mode": "gate",
        "tier": tier,  # docs/42 §4.0：L1 库题 / L2 手填 / L3 LLM 拆解（参考 · 未复核）
        "verdicts": [_verdict_dict(v) for v in verdicts],  # 顺序 = 采分点顺序
        "warnings": warnings,
    }


class ParseRequest(BaseModel):
    standard_answer: str = Field(..., min_length=1, description="标准答案全文（文字版，自动拆采分点）")
    question: str = Field(default="", description="题干（语境，防拆出答非所问的点）")
    material: str = Field(default="", description="给定材料（语境）")
    max_score: int = Field(default=0, ge=0, description="题目满分（0=不指定，LLM 按重要性分配）")


@router.post("/shenlun/practice/parse")
def practice_parse(req: ParseRequest):
    """文字版标准答案 → 采分点（docs/24 §4.2）。

    练习者贴纯文字标准答案时前端调用：内部走 decompose_points（LLM 温度 0），
    补 p1/p2… 编号，返回 points + warnings + trace（trace 含 source_snippet，
    仅 ?dev=1 时前端展示，练习者无感）。响应带 points_source="llm_parse"（docs/42 M2）：
    前端拼 InlineGold 时原样回传 → 服务端按 L3（参考 · 未复核）分层。
    评分链路不变——前端拿 points 拼 InlineGold 后走原 practice/submit。

    错误处理（docs/24 §8 失败策略）：
      - LLM 调用失败（decompose_points 吞异常返回空结果，空点且无 warnings）→ 400，提示切回 JSON 手填
      - 拆点不完整/有不确定项 → 200 + warnings（不阻断练习）
    """
    r = decompose_points(
        req.standard_answer,
        question=req.question,
        material=req.material,
        max_score=req.max_score,
        question_id="__parse__",
    )
    if not r.reference_points and not r.warnings:
        raise HTTPException(status_code=400, detail="解析失败，可切回 JSON 模式手填")

    points = [
        {
            "id": f"p{i}",
            "point": p.point,
            "keywords": p.keywords,
            "score": p.score,
            "point_type": p.point_type,
            "source_snippet": p.source_snippet,
        }
        for i, p in enumerate(r.reference_points, 1)
    ]
    return {
        "points": points,
        "points_source": "llm_parse",  # docs/42 M2：LLM 拆解产物 → 前端回传 InlineGold.points_source
        "warnings": r.warnings,
        "trace": {
            "standard_answer": req.standard_answer,
            "points": points,
            "warnings": r.warnings,
        },
    }


class GuidanceRequest(BaseModel):
    question_id: str = Field(default="", description="题目 id（题库模式）")
    gold: InlineGold | None = Field(default=None, description="单题上传模式内联采分点+材料")
    point_id: str = Field(..., description="漏点 id（来自 practice/submit 的 misses/leading）")
    answer: str = Field(..., description="本次作答全文（L4 错因诊断对照用）")


GUIDANCE_CAVEAT_L3 = "本建议基于 LLM 拆解的未复核采分点（参考 · 未人工复核），请以官方答案为准"


@router.post("/shenlun/practice/guidance")
def get_guidance(req: GuidanceRequest):
    """建议区③改进建议（docs/42 P-D=①）：单点懒加载，1 次 LLM，L1/L2/L3 全放开。

    建议区 ①②（为什么标 / 标准答案原文）随评分响应回放（0 token），前端点开某点
    才调本端点生成 ③ gap/how/rewrite（候选，措辞带"（供参考，以官方答案为准）"）。
    单模式化后无"仅门禁"限制；L3（LLM 拆解采分点）caveat 带「基于未复核采分点」措辞。
    LLM 失败不阻断：gap/how/rewrite 置空仍返回（②已在评分响应里，不重复回放）。
    """
    points, material, question, _, _, _, tier = _resolve(req)
    g = guidance(material, req.answer, points, req.point_id, question=question)
    if g is None:
        raise HTTPException(status_code=404, detail=f"采分点不存在：{req.point_id}")
    return {
        "point_id": g.point_id,
        "point": g.point,
        "official": g.official,
        "gap": g.gap,
        "how": g.how,
        "rewrite": g.rewrite,
        "caveat": GUIDANCE_CAVEAT_L3 if tier == "L3" else "",
    }


class WrongbookRequest(BaseModel):
    question_id: str = Field(default="", description="题目 id（题库模式）")
    gold: InlineGold | None = Field(default=None, description="单题上传模式内联采分点+材料")
    point_id: str = Field(..., description="漏点 id（来自 submit 的 misses/leading）")
    answer: str = Field("", description="用户作答全文（服务端用它重算 material_source，保证材料原话真出自材料）")
    answer_snippet: str = Field("", description="用户作答片段（matched_text；漏点未命中则传空）")
    demo: str = Field("", description="L2 示范表述（guidance 返回的 demo，回传免重复调 LLM）")
    cause_type: str = Field("", description="L4 错因归类（完全没提/写偏/太模糊）")
    cause: str = Field("", description="L4 错因说明")


@router.post("/shenlun/wrongbook")
def add_wrongbook(req: WrongbookRequest):
    """加入错题本：按「每个漏点一条」快照入库（docs/22 §3.6）。

    material_source 由服务端用 score 材料锚定重算（0 token，锚定可溯源）；
    LLM 产物（demo/cause）由前端回传（示证时已生成，不重复调 LLM）。
    落库走 knowledge_store.store_items（与面试域错题本同库；延迟 import 避免 pytest
    环境 chromadb 链路，同 test_shenlun_api 注释）。
    题库模式 ctx=DB item；单题上传模式 ctx=合成 dict（id=inline_{hash}，docs/39 §7.1）。
    """
    points, material, question, _, _, item, _tier = _resolve(req)
    p = next((x for x in points if x.id == req.point_id), None)
    if p is None:
        raise HTTPException(status_code=404, detail=f"采分点不存在：{req.point_id}")
    sr = score_answer(req.answer, points, materials=material, question=question)
    sp = next((x for x in sr.hit_points + sr.miss_points if x.id == req.point_id), None)
    ki = build_wrongbook_item(
        item, p,
        material_source=sp.material_source if sp else None,
        answer_snippet=req.answer_snippet,
        demo=req.demo, cause=req.cause, cause_type=req.cause_type,
    )
    try:
        from src.memory import knowledge_store as store
        stored = store.store_items([ki])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"入库失败：{e}") from e
    return {"stored": stored, "item_id": ki.id, "point": p.point}


class ExplainRequest(BaseModel):
    question_id: str = Field(default="", description="题目 id（题库模式）")
    gold: InlineGold | None = Field(default=None, description="单题上传模式内联采分点+材料")
    point_id: str = Field(..., description="漏点 id（来自 submit 的 misses/leading）")
    answer: str = Field(..., description="本次作答全文（讲解对照用）")


@router.post("/shenlun/practice/explain")
def get_explain(req: ExplainRequest):
    """按需讲解：单漏点有界讲解（L5，docs/22 §3.4 追加）：换说法 + 为什么 + 与邻点辨析。

    与「自由聊天」划清边界：只围绕用户点开的这一个漏点，绝不生成完整作答（no_full_answer）。
    用户想"换个说法 / 为什么这样写 / 和邻点啥区别"时的安全回应；point_id 不在集 → 404。
    LLM 失败不阻断：rephrase/why/distinguish 置空，L3 材料锚定仍返回。
    """
    points, material, _, _, _, _, _tier = _resolve(req)
    e = explain_point(material, req.answer, points, req.point_id)
    if e is None:
        raise HTTPException(status_code=404, detail=f"漏点不存在：{req.point_id}")
    return {
        "point_id": e.point_id,
        "point": e.point,
        "material_source": e.material_source,
        "rephrase": e.rephrase,
        "why": e.why,
        "distinguish": e.distinguish,
    }


class RoundModel(BaseModel):
    round_no: int
    answer: str
    hit_ids: list[str] = Field(default_factory=list)
    miss_ids: list[str] = Field(default_factory=list)
    hit_ratio: float = 0.0
    guided_point_ids: list[str] = Field(default_factory=list)


class CompleteRequest(BaseModel):
    question_id: str
    rounds: list[RoundModel] = Field(min_length=1, description="前端累积的逐轮轨迹（0=初稿）")
    action: str = Field(default="answered", description="answered / graduation_check")
    # docs/42 M5（P-B=B1）：practice/submit 返回的 verdicts 原样透传 → 入库判据与展示
    # 判据统一（hit=绿含 LLM 放行 / miss=黄 / suspect 记 miss + events 标注）；
    # 缺省 [] = 回退 score_answer 旧口径（历史调用方不变）。
    verdicts: list[dict] = Field(default_factory=list, description="submit 的三色判定（判据对齐用，可省略）")


@router.post("/shenlun/practice/complete")
def practice_complete(req: CompleteRequest):
    """回流：评分 → 写 answers + answer_rounds → 更新薄弱点档案 → 写事件日志。

    纯确定性，不调 LLM。由前端在「达标或轮次上限」时显式调用一次。
    带 verdicts（推荐，docs/42 B1）→ 按 gate 三态语义入库；不带 → 旧口径兼容。
    仅库内题（qid 在库）——内联题无题库载体，漏点走 wrongbook 通道（P-A=②）。
    """
    item = _load_or_404(req.question_id)
    last = req.rounds[-1]
    r = reflow_answer(
        req.question_id,
        item["meta"]["type"],
        last.answer,
        item["gold"]["reference_points"],
        action=req.action,
        rounds=[x.model_dump() for x in req.rounds],
        verdicts=req.verdicts or None,
    )
    return {"ok": True, "weak_added": r.new_weak_points, "answer_id": r.answer_id}


# ── 录入 ──────────────────────────────────────────────────────────
class RecordRequest(BaseModel):
    question: str = Field(..., min_length=1, description="题目（题干）")
    standard_answer: str = Field(..., min_length=1, description="标准答案全文")
    requirements: str = Field(default="", description="作答要求（如字数限制）")
    material: str = Field(default="", description="给定材料（可空，拆点最好有）")
    max_score: int = Field(default=20, ge=1, description="题目满分")


@router.post("/shenlun/record")
def shenlun_record(req: RecordRequest):
    """录入预览：标准答案 → 拆采分点（LLM，温度 0）。

    docs/20 §3 录入 tab 的数据源。只拆解不落库——页面在预览上逐点编辑
    （改分/改词/删点/加点）后点「确认入库」走 POST /shenlun/questions
    （docs/实施计划 任务一：入库唯一实现 src/shenlun/question_store.py，
    与 CLI run_decompose_question.py 同源）。
    """
    from src.cleaner.decompose import decompose_points

    try:
        r = decompose_points(
            req.standard_answer,
            question=req.question,
            requirements=req.requirements,
            material=req.material,
            max_score=req.max_score,
            question_id="__preview__",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"拆解失败：{e}") from e
    return {
        "points": [
            {"id": p.id, "point": p.point, "score": p.score, "keywords": p.keywords,
             "point_type": p.point_type}
            for p in r.reference_points
        ],
        "warnings": r.warnings,
    }


class UserQuestionRequest(BaseModel):
    """用户题入库请求（docs/实施计划 任务一）：页面编辑确认后的最终采分点直接写库。

    question_id 可选注入（CLI/测试用）；缺省自动 user_YYYYMMDD_NN。
    点「确认入库」= 全部采分点人工通过（等价 CLI annotate_points 全 k）。
    """
    question: str = Field(..., min_length=1, description="题干")
    requirements: str = Field(default="", description="作答要求")
    material: str = Field(default="", description="给定材料")
    max_score: int = Field(default=20, description="题目满分（手动校验 ≥1，统一 400）")
    points: list[dict] = Field(..., description="采分点列表（{id,point,keywords,score,point_type}）")
    question_id: str = Field(default="", description="入库 id（缺省自动生成）")


@router.post("/shenlun/questions")
def save_user_question_api(req: UserQuestionRequest):
    """用户题入库（docs/实施计划 任务一）：拆解预览 → 页面编辑 → 确认入库 → 进题库。

    纯写库（0 LLM）。写库唯一实现在 src/shenlun/question_store.py（与 CLI 同源，
    防两份实现漂移）；doc 结构与 CLI 逐字段一致 → load_question/推题/门禁全链路
    立即可用（load_question 已覆盖 USER_QUESTIONS_DIR，reflow.py）。
    """
    # 手动语义校验（统一 400 便于前端直接展示 detail；pydantic 只挡类型/缺字段）
    if not req.points:
        raise HTTPException(status_code=400, detail="采分点不能为空")
    seen_ids: set[str] = set()
    normalized = []
    for i, p in enumerate(req.points, 1):
        raw_id = str(p.get("id") or "").strip()
        point = str(p.get("point") or "").strip()
        kws = [str(k).strip() for k in (p.get("keywords") or []) if str(k).strip()]
        if not point:
            raise HTTPException(status_code=400, detail=f"第 {i} 个采分点名称为空")
        if not kws:
            raise HTTPException(status_code=400, detail=f"采分点「{point}」未填关键词")
        try:
            score = int(p.get("score") or 0)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"采分点「{point}」分值不是整数") from None
        if score < 0:
            raise HTTPException(status_code=400, detail=f"采分点「{point}」分值不能为负")
        # id 归一：空/重复 → 补 p{N}（LLM 拆点习惯 p1/p2…，保持同风格）
        if not raw_id or raw_id in seen_ids:
            n = 1
            while f"p{n}" in seen_ids:
                n += 1
            raw_id = f"p{n}"
        seen_ids.add(raw_id)
        normalized.append({
            "id": raw_id, "point": point, "keywords": kws, "score": score,
            "point_type": str(p.get("point_type") or "").strip(),
        })
    if req.max_score < 1:
        raise HTTPException(status_code=400, detail="满分需 ≥ 1")
    qid = req.question_id.strip() or next_user_question_id()
    save_user_question(
        question_id=qid,
        question=req.question,
        requirements=req.requirements,
        material=req.material,
        max_score=req.max_score,
        points=normalized,
    )
    return {"question_id": qid, "stored": len(normalized)}



class DecomposeCacheRequest(RecordRequest):
    question_id: str = Field(default="", description="题目 id（可选）")


@router.post("/shenlun/decompose_and_cache")
def decompose_and_cache(req: DecomposeCacheRequest, request: Request):
    """拆解标准答案、按材料句映射并把完整 trace 缓存到 space_dir/decompose_cache/ 。

    返回精简的 points（供前端直接用于评分）和 session_id。
    """
    session_id = uuid.uuid4().hex
    question_id = req.question_id or "inline"
    ts = time.time()
    trace: dict = {
        "question_id": question_id,
        "session_id": session_id,
        "timestamp": ts,
        "question": req.question,
        "material": req.material,
        "max_score": req.max_score,
        "reference_points_raw": None,
        "mapped_points": [],
        "llm_calls": [],
        "errors": [],
        "meta": {},
    }
    try:
        r = decompose_points(
            req.standard_answer,
            question=req.question,
            requirements=req.requirements,
            material=req.material,
            max_score=req.max_score,
            question_id=question_id,
        )
    except Exception as e:
        logger.exception("decompose_points failed")
        trace["errors"].append(str(e))
        # save trace with error
        try:
            save_trace(trace, question_id, session_id)
        except Exception as e2:
            logger.exception("save_trace failed: %s", e2)
        raise HTTPException(status_code=500, detail=f"拆点失败：{e}") from e

    trace["reference_points_raw"] = [p.model_dump() for p in r.reference_points]

    # 分句并做关键词覆盖度打分，选最优句
    sents = _anchor_sentences(req.material)
    for p in r.reference_points:
        best = None
        best_score = 0
        best_pno = None
        for pno, sent in sents:
            # keywords may contain mojibake; attempt fix
            kws = [(_fix_mojibake(kw) if isinstance(kw, str) else kw) for kw in (p.keywords or [])]
            s = sum(len(kw) for kw in kws if kw in sent)
            if s > best_score:
                best_score = s
                best = sent
                best_pno = pno
        quote = None
        if best is not None:
            quote = best if len(best) <= 60 else best[:60] + "…"
            material_sentence = f"材料第{best_pno}段：'{quote}'"
        else:
            material_sentence = None
        mapped = {
            "id": _fix_mojibake(p.id),
            "point": _fix_mojibake(p.point),
            "keywords": [(_fix_mojibake(kw) if isinstance(kw, str) else kw) for kw in (p.keywords or [])],
            "score": p.score,
            "material_sentence": material_sentence,
            "material_pno": best_pno,
            "anchor_score": best_score,
            "decompose_raw": p.model_dump(),
        }
        trace["mapped_points"].append(mapped)

    # meta
    try:
        trace["meta"]["client_host"] = request.client.host
    except Exception:
        pass

    # preserve original raw decompose data for debugging, then fix strings in trace
    trace["decompose_raw_original"] = trace.get("reference_points_raw")
    try:
        trace_fixed = _recursively_fix_strings(trace)
    except Exception:
        trace_fixed = trace

    try:
        path = save_trace(trace_fixed, question_id, session_id)
        logger.info("Saved decompose trace: %s", path)
    except Exception as e:
        logger.exception("Failed to save trace: %s", e)

    # build compact points for frontend
    # ensure returned points are mojibake-fixed
    pts_src = trace_fixed["mapped_points"] if "trace_fixed" in locals() else trace["mapped_points"]
    points_out = [
        {
            "id": _fix_mojibake(m.get("id")),
            "point": _fix_mojibake(m.get("point")),
            "keywords": [(_fix_mojibake(kw) if isinstance(kw, str) else kw) for kw in (m.get("keywords") or [])],
            "score": m.get("score"),
            "material_sentence": _fix_mojibake(m.get("material_sentence")) if m.get("material_sentence") else None,
        }
        for m in pts_src
    ]

    # docs/42 M2：LLM 拆解产物 → 前端拼 InlineGold 时回传 points_source（按 L3 分层）
    return {"session_id": session_id, "question_id": question_id,
            "points": points_out, "points_source": "llm_parse"}



@router.get("/shenlun/dev/decompose_trace")
def dev_decompose_trace(question_id: str, session_id: str):
    """Dev-only: 返回完整的 decompose trace（仅开发/DEBUG 环境下可用）。"""
    if not os.getenv("OFFERLOOP_DEBUG"):
        raise HTTPException(status_code=403, detail="dev endpoint disabled")
    t = load_trace(question_id or "inline", session_id)
    if t is None:
        raise HTTPException(status_code=404, detail="trace not found")
    return t


# ── 工作台 / 档案 ─────────────────────────────────────────────────
@router.get("/shenlun/remind")
def get_remind():
    """今日提醒：毕业考候选（≤2，间隔验证到期）+ 该练 topK（≤3，按紧急度）。"""
    grads = graduation_candidates()[:2]
    top = read_weak_points(limit=20)[:3]
    return {
        "graduation_candidates": [
            {"point": wp.label, "qtype": wp.qtype, "days": _days_since(wp.last_hit_at or wp.last_practiced_at)}
            for wp in grads
        ],
        "to_practice": [
            {"point": wp.label, "qtype": wp.qtype, "days": _days_since(wp.last_practiced_at or wp.last_miss_at)}
            for wp in top
        ],
    }


@router.get("/shenlun/weakpoints")
def get_weakpoints(state: str | None = None):
    """薄弱点档案全表（档案 tab）：默认全部，state 筛选 active/graduated/stuck/pinned。"""
    pts = read_all_weak_points(limit=500)
    if state:
        pts = [p for p in pts if p.state == state]
    return {
        "items": [
            {
                "point_key": p.point_key,
                "label": p.label,
                "qtype": p.qtype,
                "point_type": p.point_type,
                "question_id": p.question_id,
                "miss_count": p.miss_count,
                "hit_count": p.hit_count,
                "consecutive_hits": p.consecutive_hits,
                "tier": p.tier,
                "urgency": p.urgency,
                "state": p.state,
                "last_miss_at": p.last_miss_at,
            }
            for p in pts
        ]
    }
