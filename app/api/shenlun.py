"""申论工作台 API（docs/22 §3.5）—— 把已存在的申论业务函数封装成无状态 REST 端点。

范式（docs/22）：考你 → 帮你（示证）。practice/submit 只做确定性评分（L1）+ 推 1 个
最该补的漏点；用户点开某漏点才调 practice/guidance 按需生成 L2/L4（旧自动逼问循环已删）。

端点：
  POST /api/shenlun/practice/start     → ReAct 推题（decide 推荐优先，规则回退兜底；题库空 404）
  POST /api/shenlun/practice/parse     → 文字版标准答案 → 采分点（docs/24 §4.2，LLM 拆解 + trace）
  POST /api/shenlun/practice/submit    → 确定性评分（score_answer，L1 命中/漏点 + 材料锚定）+ 推 1 个漏点
  POST /api/shenlun/practice/guidance  → 按需示证：单漏点 L3（材料锚定，0 token）+ L2(DEMO) + L4(CAUSE)
  POST /api/shenlun/practice/complete  → 回流（reflow_answer：answers/weak_points/events + answer_rounds）
  GET  /api/shenlun/remind             → 今日提醒（毕业考候选 ≤2 + 该练 topK ≤3）
  GET  /api/shenlun/weakpoints         → 薄弱点档案全表（state 筛选，档案 tab）

复用（零修改）：src/shenlun/{react.decide, score.score_answer, reflow.{load_question,reflow_answer},
profile.{read_weak_points,read_all_weak_points,graduation_candidates}} + src.mock.runtime.{guidance,pick_leading_point}。
"""
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.cleaner.schema import utcnow
from src.mock.runtime import PASS_HIT_RATIO, guidance, explain_point, pick_leading_point
from src.shenlun.profile import graduation_candidates, read_all_weak_points, read_weak_points
from src.shenlun.react import decide
from src.shenlun.reflow import load_question, reflow_answer
from src.shenlun.score import from_benchmark, score_answer
from src.shenlun.wrongbook import build_wrongbook_item
from src.cleaner.decompose import decompose_points
from src.shenlun.score import _anchor_sentences
from app.utils.decompose_cache import save_trace, load_trace
import uuid
import logging
import time
import os
import json
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
    question_id 仍保留（题库"示例题"模式），两者二选一。
    """
    points: list[dict] = Field(..., description="采分点列表（{id,point,keywords,score,point_type}）")
    material: str = ""
    question: str = ""
    qtype: str = ""


def _resolve(req) -> tuple[list, str, str, str, str, dict | None]:
    """从请求解析评分所需上下文：内联 gold 优先，否则按 question_id 读题库。

    返回 (points, material, question, qtype, qid, ctx)：
      - ctx：错题本入库用的题目载体；题库模式返回 DB item，内联模式返回合成 dict。
    既无 gold 也无 question_id → 400。
    """
    g = getattr(req, "gold", None)
    if g is not None and g.points:
        points = from_benchmark(g.points)
        material = g.material or ""
        question = g.question or ""
        qtype = g.qtype or ""
        ctx = {"id": "inline", "task": {"question": question}, "meta": {"type": qtype}}
        return points, material, question, qtype, "inline", ctx
    if not getattr(req, "question_id", ""):
        raise HTTPException(status_code=400, detail="需提供 question_id 或 gold")
    item = _load_or_404(req.question_id)
    points = from_benchmark(item["gold"]["reference_points"])
    material = item["task"]["material"]
    question = item["task"]["question"]
    qtype = item["meta"]["type"]
    return points, material, question, qtype, req.question_id, item


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


@router.post("/shenlun/practice/submit")
def practice_submit(req: SubmitRequest):
    """评分（L1）+ 推 1 个最该补的漏点（docs/22 §3.5）。

    纯确定性，不调 LLM：hit/miss 判定 + 每漏点挂材料原话（material_source，score 锚定）；
    不再自动逼问（旧 guidance 循环已删）——漏点的 L2/L4 由用户点开
    POST /shenlun/practice/guidance 按需生成。支持题库(question_id)与单题上传(gold)两种来源。
    """
    points, material, question, _, qid, _ = _resolve(req)
    sr = score_answer(req.answer, points, materials=material, question=question)
    passed = sr.hit_ratio >= PASS_HIT_RATIO
    leading = pick_leading_point(sr.miss_points, qid)
    return {
        "hit_ratio": round(sr.hit_ratio, 4),
        "passed": passed,
        "hits": [
            {"id": p.id, "point": p.point, "score": p.score,
             "point_type": p.type, "matched_text": p.matched_text,
             "matched_by": p.matched_by,          # kw / semantic / llm（docs/25/26，trace 可追踪）
             "semantic_score": p.semantic_score}  # 语义命中相似度（kw 命中为 None）
            for p in sr.hit_points
        ],
        "misses": [
            {"id": p.id, "point": p.point, "score": p.score,
             "point_type": p.type, "material_source": p.material_source}
            for p in sr.miss_points
        ],
        "leading": None if leading is None else {
            "point_id": leading.id, "point": leading.point, "score": leading.score,
            "material_source": leading.material_source,
        },
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
    仅 ?dev=1 时前端展示，练习者无感）。评分链路不变——前端拿 points 拼
    InlineGold 后走原 practice/submit。

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


@router.post("/shenlun/practice/guidance")
def get_guidance(req: GuidanceRequest):
    """按需示证：单漏点 L3（材料锚定，0 token）+ L2(DEMO) + L4(CAUSE)（LLM）。

    用户点开某个漏点才调一次；point_id 不在该题采分点集 → 404。
    LLM 失败不阻断：demo/cause 为空串，L3 材料锚定仍返回。
    """
    points, material, _, _, _, _ = _resolve(req)
    g = guidance(material, req.answer, points, req.point_id)
    if g is None:
        raise HTTPException(status_code=404, detail=f"漏点不存在：{req.point_id}")
    return {
        "point_id": g.point_id,
        "point": g.point,
        "material_source": g.material_source,
        "demo": g.demo,
        "cause_type": g.cause_type,
        "cause": g.cause,
        "fix": g.fix,
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
    题库模式 ctx=DB item；单题上传模式 ctx=合成 dict（id=inline）。
    """
    points, material, question, _, _, item = _resolve(req)
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
    points, material, _, _, _, _ = _resolve(req)
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


@router.post("/shenlun/practice/complete")
def practice_complete(req: CompleteRequest):
    """回流：评分 → 写 answers + answer_rounds → 更新薄弱点档案 → 写事件日志。

    纯确定性，不调 LLM。由前端在「达标或轮次上限」时显式调用一次。
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

    docs/20 §3 录入 tab 的数据源。demo 版只返回拆解预览不落库——
    人审闸门（annotate_points）+ user_questions 入库在 CLI 工具
    scripts/run_decompose_question.py（docs/16 §3.4）。
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

    return {"session_id": session_id, "question_id": question_id, "points": points_out}



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
