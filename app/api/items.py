"""错题本端点 —— 列表读 + 三态标注写（第 2 片纵切）。

- GET  /api/items             列表（按遗忘 gap 降序，越该复习越靠前）
- POST /api/items/{id}/status 标注三态 fail/partial/pass（可互相切换，不许退回 unknown）

标注逻辑复用 CLI 的 annotate 语义：transition 留痕 + last_reviewed_at 衰减起点 + 初始掌握度。
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.cleaner.schema import KnowledgeItem, ItemStatus, ItemCategory, utcnow
from src.cleaner.state_machine import transition
from src.memory import knowledge_store as store
from src.memory.mastery import INITIAL_MASTERY, rank, effective_mastery, _elapsed_days

router = APIRouter()

_STATUS_LABEL = {
    ItemStatus.FAIL: "没答上",
    ItemStatus.PARTIAL: "答了一半",
    ItemStatus.PASS: "答上了",
}


def mark_item(item: KnowledgeItem, new_status: ItemStatus, *, reason: str = "") -> KnowledgeItem:
    """标注一条题：状态机留痕 + 衰减起点 + 初始掌握度。返回新对象。

    供 API 端点和 chat 的自然语言入口共用（Web 版标注 = CLI annotate 的语义）。
    """
    now = utcnow()
    label = _STATUS_LABEL.get(new_status, new_status.value)
    why = reason.strip() or f"人工标注：{label}"
    marked = transition(item, new_status, reason=why, actor="annotate", now=now)
    # 标注 = 一次判断：更新衰减起点 + 按表现设初始掌握度（与 annotate.py 一致）
    return marked.model_copy(
        update={"last_reviewed_at": now, "mastery_score": INITIAL_MASTERY[new_status]}
    )


# ── 列表读 ──
class ItemListParams(BaseModel):
    status: str = Query(default="", description="过滤状态 fail/partial/pass/unknown，空=全部")
    space: str = Query(default="default", description="记忆空间")
    category: str = Query(default="", description="过滤类别 knowledge/info")
    source: str = Query(default="", description="过滤来源 self_review/public_jingyan/mock_interview")
    limit: int = Query(default=200, ge=1, le=500)


@router.get("/items", response_model=list[KnowledgeItem])
def list_items(
    status: str = "",
    space: str = "default",
    category: str = "",
    source: str = "",
    limit: int = 200,
):
    """错题本/知识库列表，按遗忘 gap 降序（快忘了的排最前）。"""
    items = store.search(
        status=status or None,
        space=space or None,
        top_k=limit,
    )
    if category:
        try:
            cat = ItemCategory(category)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"非法 category: {category}")
        items = [it for it in items if it.category == cat]
    if source:
        items = [it for it in items if it.source.value == source]

    now = utcnow()
    # gap = 1 - effective_mastery，越大越该复习；同 gap 按最近复习时间旧者优先
    items.sort(
        key=lambda it: (effective_mastery(it, now) - 1.0, -(it.last_reviewed_at or now).timestamp()),
        reverse=False,
    )
    # 展示语义：mastery_score 覆盖为「当前有效掌握度」（衰减后），前端直接显示
    for it in items:
        it.mastery_score = effective_mastery(it, now)
    return items[:limit]


# ── 语义检索（CLI search.py 的 Web 版）──
@router.get("/search", response_model=list[KnowledgeItem])
def search_items(q: str = Query(..., min_length=1, description="检索词"), space: str = "default", limit: int = 20):
    """按语义检索错题本（cosine 相似度，similarity 字段供前端展示命中程度）。"""
    items = store.search(query=q, space=space, top_k=limit)
    now = utcnow()
    for it in items:
        it.mastery_score = effective_mastery(it, now)
        it.similarity = it._similarity  # 下划线字段不序列化，复制到正式字段
    return items


# ── 标注写 ──
class MarkRequest(BaseModel):
    status: ItemStatus = Field(..., description="目标状态 fail/partial/pass（不许退回 unknown）")
    reason: str = Field(default="", max_length=200, description="标注理由，留痕用")
    space: str = Field(default="default", description="记忆空间（严格隔离：只标本空间条目）")


@router.post("/items/{item_id}/status", response_model=KnowledgeItem)
def mark_status(item_id: str, req: MarkRequest):
    if req.status == ItemStatus.UNKNOWN:
        raise HTTPException(status_code=422, detail="不能标回 unknown")
    item = store.get_by_id(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"找不到题目 {item_id}")
    if (item.space or "default") != req.space:
        raise HTTPException(
            status_code=422,
            detail=f"题目属于「{item.space or 'default'}」空间，不能从「{req.space}」空间标注（空间隔离）",
        )
    try:
        updated = mark_item(item, req.status, reason=req.reason)
        store.store_items([updated])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"标注写库失败：{e}") from e
    return updated


# ── 编辑 / 删除 ──
class EditRequest(BaseModel):
    space: str = Field(default="default", description="记忆空间（严格隔离：只改本空间条目）")
    question: str | None = Field(default=None, min_length=1, max_length=300)
    topic: str = Field(default="", max_length=50)
    answer: str = Field(default="", max_length=4000)


def _get_item_in_space(item_id: str, space: str) -> KnowledgeItem:
    item = store.get_by_id(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"找不到题目 {item_id}")
    if (item.space or "default") != space:
        raise HTTPException(
            status_code=422,
            detail=f"题目属于「{item.space or 'default'}」空间，不能从「{space}」空间操作（空间隔离）",
        )
    return item


@router.put("/items/{item_id}", response_model=KnowledgeItem)
def edit_item(item_id: str, req: EditRequest):
    """编辑题目：question/topic/answer 覆盖，重新嵌入（store_items upsert）。"""
    item = _get_item_in_space(item_id, req.space)
    updates: dict = {}
    if req.question is not None and req.question.strip():
        updates["question"] = req.question.strip()
    updates["topic"] = req.topic.strip()
    updates["answer"] = req.answer.strip()
    updated = item.model_copy(update=updates)
    try:
        store.store_items([updated])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存失败：{e}") from e
    return updated


@router.delete("/items/{item_id}")
def delete_item(item_id: str, space: str = "default"):
    """删除错题（幂等：不存在也返回 ok，供前端刷新列表）。"""
    item = store.get_by_id(item_id)
    if item is None:
        return {"ok": True, "deleted": False}
    if (item.space or "default") != space:
        raise HTTPException(
            status_code=422,
            detail=f"题目属于「{item.space or 'default'}」空间，不能从「{space}」空间删除（空间隔离）",
        )
    store.delete_by_ids([item_id])
    return {"ok": True, "deleted": True}
