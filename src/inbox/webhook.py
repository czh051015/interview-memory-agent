"""FastAPI Webhook 实时接入 (US-02)。"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.models import FeedbackSource, RawFeedback

logger = logging.getLogger(__name__)

# 内存缓冲（v1 单用户，无需持久化队列）
_feedback_buffer: list[RawFeedback] = []


class WebhookPayload(BaseModel):
    raw_text: str = Field(..., min_length=1, description="反馈原文")
    source: str = Field(..., description="self_review | other_jingyan")
    received_at: Optional[datetime] = None


def create_app() -> FastAPI:
    """创建 FastAPI 应用。"""
    app = FastAPI(title="OfferLoop Inbox", version="1.0.0")

    @app.post("/feedback")
    async def ingest(payload: WebhookPayload) -> dict:
        """接收单条反馈。"""
        if payload.source not in {s.value for s in FeedbackSource}:
            raise HTTPException(
                status_code=400,
                detail=f"非法 source: {payload.source}，允许: {[s.value for s in FeedbackSource]}",
            )

        feedback = RawFeedback(
            id=f"raw_{len(_feedback_buffer) + 1:04d}",
            raw_text=payload.raw_text.strip(),
            source=FeedbackSource(payload.source),
            received_at=payload.received_at or datetime.utcnow(),
        )
        _feedback_buffer.append(feedback)
        logger.info("Webhook ingested: %s", feedback.id)
        return {"status": "ok", "id": feedback.id}

    @app.get("/feedback/buffer")
    async def get_buffer() -> dict:
        """查看缓冲中的反馈列表。"""
        return {"count": len(_feedback_buffer), "items": [f.model_dump() for f in _feedback_buffer]}

    @app.post("/feedback/buffer/flush")
    async def flush_buffer() -> dict:
        """清空缓冲，返回所有待处理反馈。"""
        global _feedback_buffer
        items = _feedback_buffer.copy()
        _feedback_buffer = []
        logger.info("Flushed %d items from buffer", len(items))
        return {"count": len(items), "items": [f.model_dump() for f in items]}

    return app


def get_buffer() -> list[RawFeedback]:
    """获取当前缓冲（非 HTTP 调用方式）。"""
    return list(_feedback_buffer)


def clear_buffer() -> list[RawFeedback]:
    """清空并返回缓冲。"""
    global _feedback_buffer
    items = _feedback_buffer.copy()
    _feedback_buffer = []
    return items
