"""记错题端点 —— 拆解预览（不入库）+ 确认入库。

对应前端「记错题」页：粘贴面经 → 拆解预览 → 确认入库（IA 定稿第一条主线）。
- POST /api/decompose  {raw_text} → DecomposeResult 预览（不落库，供用户删改）
- POST /api/record     {items, space} → {stored}（预览确认后的条目入库）
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.cleaner.decompose import decompose as run_decompose
from src.cleaner.schema import KnowledgeItem, DecomposeResult
from src.memory import knowledge_store as store

router = APIRouter()


class DecomposeRequest(BaseModel):
    raw_text: str = Field(..., min_length=1, description="粘贴的面试复盘/面经原文")


class RecordRequest(BaseModel):
    items: list[KnowledgeItem] = Field(..., description="拆解预览确认后的条目")
    space: str = Field(default="default", description="目标空间（Q2 拍板：软概念，metadata 过滤）")


class RecordResponse(BaseModel):
    stored: int
    space: str


@router.post("/decompose", response_model=DecomposeResult)
def decompose(req: DecomposeRequest):
    """拆解一篇复盘为结构化 Q&A 列表（预览，不入库）。LLM 调用可能较慢。"""
    try:
        result = run_decompose(req.raw_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"拆解失败：{e}") from e
    if result.total_count == 0:
        raise HTTPException(status_code=422, detail="没拆出任何条目——确认粘贴的是面试复盘原文，不是空文本")
    return result


@router.post("/record", response_model=RecordResponse)
def record(req: RecordRequest):
    """把确认后的条目写入当前空间。"""
    items = req.items
    if not items:
        raise HTTPException(status_code=422, detail="没有可入库的条目")

    # space 覆盖：前端预览阶段不感知空间，入库时统一归入目标空间
    for it in items:
        it.space = req.space

    try:
        stored = store.store_items(items)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"入库失败：{e}") from e
    return RecordResponse(stored=stored, space=req.space)
