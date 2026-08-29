"""模拟面试端点 —— Web 版 v2（对齐 CLI 三源出题：简历 + JD + 错题 + 结构化方法论）。

- POST /api/mock/start    {n, space} → 章节化面试计划
  （读 data/resume.md + jd.md + 错题池 → plan_interview LLM 生成章节；LLM 失败回退只出错题）
- POST /api/mock/verdict  {question, answer} → {points, misses, suggested, reason}（LLM 现场生成）
- POST /api/mock/complete {results, space} → {updated, new, behaviors}
  （weak 题写回 mastery + 新题答差自动采集进错题本，来源可追溯）
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.mock import (
    WEAK_POOL_SIZE,
    get_weak_questions,
    judge_single_round,
    judge_followup,
    plan_interview,
    summarize_behaviors,
    _read_profile,
)
from src.memory import knowledge_store as store
from src.memory import mastery
from src.mock.writeback import apply_verdict

router = APIRouter()


# ── 请求/响应模型 ──
class MockStartRequest(BaseModel):
    n: int = Field(default=5, ge=1, le=20, description="错题候选池大小（v2 起章节化出题，弱项池固定 5，此参数保留兼容）")
    space: str = Field(default="default", description="记忆空间")


class MockQuestion(BaseModel):
    id: str
    question: str
    topic: str
    status: str
    mastery_score: float
    gap: float | None  # 错题来源有值（1 - effective_mastery），现场新题 null
    section: str = ""   # 章节名（自我介绍/项目深挖/技术验证/行为面/动机面）
    source: str = ""    # generic/resume/jd/weak/behavior/motivation
    item_id: str | None = None  # 错题来源填原题 id，其余 null


class MockStartResponse(BaseModel):
    questions: list[MockQuestion]
    focus_topics: list[str] = Field(default_factory=list)  # 画像薄弱主题（前端展示"本场重点"）


class MockVerdictRequest(BaseModel):
    question: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)


class MockVerdictResponse(BaseModel):
    points: list[str]
    misses: list[str]
    suggested: str
    reason: str


class MockFollowupRequest(BaseModel):
    question: str = Field(..., min_length=1)
    points: list[str] = Field(default_factory=list)  # 首答判定的期望要点
    answer: str = Field(..., min_length=1)           # 当前轮回答
    round_num: int = Field(default=1, ge=1, le=3)    # 已答轮数（1=首答）


class MockFollowupResponse(BaseModel):
    need_followup: bool
    followup_question: str
    reason: str
    performance: str


class MockResult(BaseModel):
    question_id: str = ""
    question: str
    verdict: str = Field(..., pattern="^(pass|partial|fail)$")
    answer: str = ""
    source: str = "weak"  # weak 写回错题；其他来源答差 → 自动采集
    topic: str = ""
    # LLM 判定（verdict 阶段的 points/misses/reason），写回 answer 作为答案对照
    points: list[str] = Field(default_factory=list)
    misses: list[str] = Field(default_factory=list)
    reason: str = ""


class MockCompleteRequest(BaseModel):
    results: list[MockResult] = Field(..., min_length=1)
    space: str = Field(default="default")


class MockCompleteResponse(BaseModel):
    updated: int          # weak 题写回数
    new: int              # 新题自动采集数
    behaviors: list[str]


# ── 端点 ──
@router.post("/mock/start", response_model=MockStartResponse)
def mock_start(req: MockStartRequest):
    """出题：简历 + JD + 错题本三源，LLM 生成章节化面试计划（对齐 CLI plan_interview）。

    错题池固定 WEAK_POOL_SIZE 供 LLM 挑「技术验证」章的薄弱项题；
    简历/JD 从 data/ 读取（缺失则对应章节由 LLM 跳过）。LLM 失败回退只出错题。
    """
    try:
        weak_items = get_weak_questions(top_k=WEAK_POOL_SIZE, space=req.space)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取错题本失败：{e}") from e

    if not weak_items:
        raise HTTPException(
            status_code=422,
            detail="错题本是空的——先去「记错题」记几道栽过的题，再来模拟面试。",
        )

    # 三源：简历 + JD（文件）+ 错题池 → 章节化计划
    # 画像（人级记忆）：薄弱主题注入出题 + 前端展示"本场重点验证"
    focus_topics: list[str] = []
    user_profile = None
    try:
        from src.memory import profile as profile_mod
        user_profile = profile_mod.build_profile(req.space, save=True)
        focus_topics = user_profile.weak_topic_names()
    except Exception as e:
        logging.warning("画像读取失败，出题不依赖：%s", e)

    try:
        profile = _read_profile(space=req.space)
        sections = plan_interview(
            profile["resume"], profile["jd"], weak_items,
            focus_topics=focus_topics,
            profile_text=user_profile.to_prompt_text() if user_profile else "",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成面试计划失败：{e}") from e

    if not sections:
        # LLM 回退：只考错题（gap 排序），保证可用
        questions = []
        for it in weak_items:
            questions.append(_to_question(it, section="技术验证", source="weak"))
        return MockStartResponse(questions=questions, focus_topics=focus_topics)

    by_id = {it.id: it for it in weak_items}
    questions = []
    for sec in sections:
        name = (sec.get("name") or "").strip()
        for q in sec.get("questions", []):
            question = (q.get("question") or "").strip()
            if not question:
                continue
            source = (q.get("source") or "generic").strip()
            item_id = q.get("item_id")
            item = by_id.get(item_id) if item_id else None
            if item is not None:
                questions.append(_to_question(item, section=name, source=source))
            else:
                questions.append(
                    MockQuestion(
                        id="",
                        question=question,
                        topic=(q.get("topic") or "").strip(),
                        status="",
                        mastery_score=0.0,
                        gap=None,
                        section=name,
                        source=source,
                        item_id=None,
                    )
                )

    if not questions:
        raise HTTPException(status_code=422, detail="面试计划为空，请重试（可能是简历/JD 格式问题）")
    return MockStartResponse(questions=questions, focus_topics=focus_topics)


def _to_question(item, *, section: str, source: str) -> MockQuestion:
    """错题 → MockQuestion（带遗忘 gap）。"""
    return MockQuestion(
        id=item.id,
        question=item.question,
        topic=item.topic,
        status=item.status.value,
        mastery_score=round(item.mastery_score, 2),
        gap=round(1.0 - mastery.effective_mastery(item), 3),
        section=section,
        source=source,
        item_id=item.id,
    )


@router.post("/mock/verdict", response_model=MockVerdictResponse)
def mock_verdict(req: MockVerdictRequest):
    """单轮判定：LLM 现场生成期望要点 + 差距 + 建议判定。partial 时第二判官复核。"""
    try:
        verdict = judge_single_round(req.question, req.answer, cross_on_partial=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"判定失败：{e}") from e
    return MockVerdictResponse(**verdict)


@router.post("/mock/followup", response_model=MockFollowupResponse)
def mock_followup(req: MockFollowupRequest):
    """追问判断：对齐 CLI MAX_FOLLOWUPS=2，LLM 判断要不要追问 + 给追问问题。

    前端在判定卡点「追问」触发；need_followup=false 时前端提示面试官不再追问。
    partial 时第二判官复核（cross_on_partial）。
    """
    try:
        result = judge_followup(req.question, req.points, req.answer, req.round_num, cross_on_partial=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"追问判断失败：{e}") from e
    return MockFollowupResponse(**result)


@router.post("/mock/complete", response_model=MockCompleteResponse)
def mock_complete(req: MockCompleteRequest):
    """写回：统一委托共享核心 apply_verdict（CLI/Web 单一落点，06 计划方案 A）。

    - weak 题：mastery 涨跌 + 行为标签合并 + feedback 写专用字段（answer 不动）
    - 其他来源答 fail/partial：自动采集（feedback=判定文本，answer 留空）
    - 失败不半写；review_log actor 统一 mock_interview
    """
    if not req.results:
        raise HTTPException(status_code=422, detail="没有要写回的结果")

    # 整场行为特征总结（LLM，失败返回空数组不阻断写回）
    behaviors = []
    try:
        behaviors = summarize_behaviors([
            {"question": r.question, "answer": r.answer, "performance": r.verdict}
            for r in req.results
        ])
    except Exception:
        behaviors = []

    norm = [{
        "question": r.question, "source": r.source, "topic": r.topic,
        "performance": r.verdict, "points": r.points, "misses": r.misses,
        "reason": r.reason, "item": store.get_by_id(r.question_id), "space": req.space,
    } for r in req.results]
    updated, new = apply_verdict(norm, behaviors, space=req.space)
    return MockCompleteResponse(updated=updated, new=new, behaviors=behaviors)
