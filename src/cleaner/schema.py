"""KnowledgeItem —— 核心实体（product-plan §8.1）。"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


def utcnow() -> datetime:
    """当前 UTC 时间（naive）。等价于弃用的 datetime.utcnow()，避免 DeprecationWarning。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ItemStatus(str, Enum):
    FAIL = "fail"          # 忘了/不会/没答上
    PARTIAL = "partial"    # 答了一半/漏了/追问没接住
    PASS = "pass"          # 答了/过了/完整
    UNKNOWN = "unknown"    # 备注为空或不可识别


class ItemCategory(str, Enum):
    KNOWLEDGE = "knowledge"  # 知识点考察（Agent设计、线程池原理）
    INFO = "info"            # 信息性问题（自我介绍、有实习过吗）


class ItemSource(str, Enum):
    """数据来源枚举：自己的复盘 / 网上面经 / 模拟面试自动采集。"""
    SELF_REVIEW = "self_review"          # 自己的面试复盘
    PUBLIC_JINGYAN = "public_jingyan"    # 网上面经（只有题目，无自评）
    MOCK_INTERVIEW = "mock_interview"    # 模拟面试答差自动采集的新弱点


class KnowledgeItem(BaseModel):
    """一条拆解后的面试 Q&A 记录。"""
    id: str = Field(default="", description="ki_20260815_001")
    question: str = Field(..., description="面试题原文")
    answer: str = Field(default="", description="参考答案（面经里自带的「回答：XXX」，没有则为空）")
    question_type: str = Field(default="", description="题型：八股文/项目/场景/行为，没有则为空")
    topic: str = Field(default="", description="主题标签，如'混合检索'")
    category: ItemCategory = ItemCategory.KNOWLEDGE  # ISSUES F2
    company: str = Field(default="")
    role: str = Field(default="AI应用开发")
    round: str = Field(default="", description="技术一面/二面/HR面")
    date: str = Field(default="", description="面试日期 YYYY-MM-DD")
    space: str = Field(default="default", description="空间标识（IA 全局空间切换），软概念按 metadata 过滤，默认 default")
    status: ItemStatus = ItemStatus.UNKNOWN
    history: list[dict] = Field(default_factory=list, description="状态变更证据链 [{time,from,to,reason,actor}]")
    user_note: str = Field(default="", description="用户原始备注")
    feedback: str = Field(default="", description="模拟面试面试官反馈（单题：要点+漏答+评语），来源可追溯，不复用 answer")
    mastery_score: float = Field(default=1.0, ge=0.0, le=1.0)
    last_reviewed_at: Optional[datetime] = None
    review_count: int = 0
    source: ItemSource = ItemSource.SELF_REVIEW  # phase-2-plan §2.3
    behavior_tags: list[str] = Field(
        default_factory=list,
        description="行为特征标签（人级画像），如 ['表达绕弯','回避问题']，模拟面试结束统一写入",
    )
    created_at: datetime = Field(default_factory=utcnow)
    _similarity: float = 0.0  # 内部使用，不入库（下划线字段 pydantic 不序列化）
    similarity: float = 0.0  # 语义检索相似度，API 展示用（search 端点从 _similarity 复制）


# ── 拆解结果 ──
def not_info(items):
    """过滤信息性问题（自我介绍/薪酬/哪里人），只留知识类（ISSUES F2）。"""
    return [it for it in items if it.category != ItemCategory.INFO]


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
    suspected_fail: bool = False  # 整篇"明说栽过"→疑似错题，需用户确认后才标 fail


# ── 申论域：标准答案 → 采分点（docs/16 §3.2）──────────────────────────────
# KnowledgeItem/状态机原样保留服务面试域，申论走新模型（平行新增，不删不改面试代码）。
# approved 默认 false 是防循环论证的关键：LLM 拆的点 → LLM 判的分，必须人审后才成为可信金标。
class ReferencePoint(BaseModel):
    """一个采分点：评分传感器 score_answer() 的比对单元。"""
    id: str = Field(default="", description="c1/c2/...，入库时按序编号")
    point: str = Field(..., description="采分点名称，≤8字，如「设施互通」")
    keywords: list[str] = Field(..., description="比对关键词，须出自标准答案原文/材料原词，2-5 个")
    score: float = Field(default=0, description="该点分值，人审时可按分比值核对")
    point_type: str = Field(default="", description="采分角度：问题/原因/影响/对策/意义/危害/其他（docs/13 §5.3，拆解时 LLM 顺手标注，不参与 hit/miss）")
    approved: bool = Field(default=False, description="人审闸门，默认不通过")
    source: str = Field(default="llm_draft", description="llm_draft / human_approved / official")
    history: list[dict] = Field(default_factory=list, description="证据链 [{time,from,to,reason,actor}]，与状态机同构")
    created_at: datetime = Field(default_factory=utcnow)


class PointDecomposeResult(BaseModel):
    """一次「标准答案 → 采分点」拆解的完整输出。"""
    question_id: str = Field(default="", description="题目 id（入库时用）")
    question: str = ""
    requirements: str = ""
    material: str = ""
    max_score: int = 0
    reference_points: list[ReferencePoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list, description="LLM 自报的不确定项，人审时优先看")

    @property
    def approved_count(self) -> int:
        return sum(1 for p in self.reference_points if p.approved)

    @property
    def all_approved(self) -> bool:
        """全部通过 = 整批可入库（任何一条未通过则整批保持草稿）。"""
        return bool(self.reference_points) and all(p.approved for p in self.reference_points)


MAX_POINT_HISTORY = 50  # 证据链上限，与状态机同规格


def append_point_history(
    point: ReferencePoint,
    *,
    to_source: str,
    reason: str,
    actor: str,
    from_source: str | None = None,
    now: datetime | None = None,
) -> ReferencePoint:
    """ReferencePoint 留痕（docs/16 §3.5 方案 A：不动 state_machine.py，申论侧小函数）。

    与 KnowledgeItem 状态机同构：证据 {time, from, to, reason, actor}；
    from/to 存 source（llm_draft → human_approved），出生记录 from=None。
    返回新对象，不改原 point。
    """
    now = now or utcnow()
    entry = {
        "time": now.isoformat(),
        "from": from_source,
        "to": to_source,
        "reason": reason,
        "actor": actor,
    }
    history = list(point.history or [])[-(MAX_POINT_HISTORY - 1):]
    history.append(entry)
    return point.model_copy(update={"source": to_source, "history": history})
