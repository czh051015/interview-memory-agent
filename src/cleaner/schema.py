"""KnowledgeItem —— 核心实体（product-plan §8.1）。"""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ItemStatus(str, Enum):
    FAIL = "fail"          # 忘了/不会/没答上
    PARTIAL = "partial"    # 答了一半/漏了/追问没接住
    PASS = "pass"          # 答了/过了/完整
    UNKNOWN = "unknown"    # 备注为空或不可识别


class ItemCategory(str, Enum):
    KNOWLEDGE = "knowledge"  # 知识点考察（Agent设计、线程池原理）
    INFO = "info"            # 信息性问题（自我介绍、有实习过吗）


class ItemSource(str, Enum):
    """数据来源二枚举：自己的复盘 / 网上面经。"""
    SELF_REVIEW = "self_review"          # 自己的面试复盘
    PUBLIC_JINGYAN = "public_jingyan"    # 网上面经（只有题目，无自评）


class KnowledgeItem(BaseModel):
    """一条拆解后的面试 Q&A 记录。"""
    id: str = Field(default="", description="ki_20260815_001")
    question: str = Field(..., description="面试题原文")
    topic: str = Field(default="", description="主题标签，如'混合检索'")
    category: ItemCategory = ItemCategory.KNOWLEDGE  # ISSUES F2
    company: str = Field(default="")
    role: str = Field(default="AI应用开发")
    round: str = Field(default="", description="技术一面/二面/HR面")
    date: str = Field(default="", description="面试日期 YYYY-MM-DD")
    status: ItemStatus = ItemStatus.UNKNOWN
    user_note: str = Field(default="", description="用户原始备注")
    mastery_score: float = Field(default=1.0, ge=0.0, le=1.0)
    last_reviewed_at: Optional[datetime] = None
    review_count: int = 0
    related_items: list[str] = Field(default_factory=list)
    source: ItemSource = ItemSource.SELF_REVIEW  # phase-2-plan §2.3
    priority: float = Field(default=1.0, ge=0.0)  # 交叉验证修正的复习优先级
    created_at: datetime = Field(default_factory=datetime.utcnow)
    _similarity: float = 0.0  # 内部使用，不入库


# ── 拆解结果 ──
class DecomposeResult(BaseModel):
    """面经消化 Agent 的完整输出。"""
    company: str = ""
    role: str = ""
    round: str = ""
    date: str = ""
    items: list[KnowledgeItem] = Field(default_factory=list)
    raw_text: str = ""
    unknown_count: int = 0  # status=unknown 的条目数
    total_count: int = 0
