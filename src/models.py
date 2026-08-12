"""全局共享数据模型 —— 对应 data schema v1。"""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class FeedbackSource(str, Enum):
    """反馈来源枚举（决策 Q1/Q8）。"""
    SELF_REVIEW = "self_review"
    OTHER_JINGYAN = "other_jingyan"
    JD = "jd"                # 预留 v2
    MARKET_SIGNAL = "market_signal"  # 预留 v2


class FeedbackStatus(str, Enum):
    RAW = "raw"
    CLEANED = "cleaned"
    DUPLICATE = "duplicate"
    ERROR = "error"


class HypothesisStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Priority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


# ── 反馈原始模型 ──
class RawFeedback(BaseModel):
    id: str = Field(..., description="唯一ID，格式 raw_001")
    raw_text: str = Field(..., description="原始反馈全文")
    source: FeedbackSource
    received_at: datetime = Field(default_factory=datetime.utcnow)


# ── 清洗后模型 ──
class PIIEntry(BaseModel):
    type: str   # phone / email / name
    value: str
    start: int
    end: int


class QualityReport(BaseModel):
    dedup_stage: str = ""       # "hash" | "llm"
    pii_stage: str = ""         # "regex_only" | "regex+llm"
    normalization_ok: bool = True


class CleanedFeedback(BaseModel):
    id: str = Field(..., description="clean_001")
    raw_id: str
    raw_text: str
    normalized_text: str
    dedup_hash: str
    dedup_embedding: Optional[list[float]] = None
    is_duplicate: bool = False
    dup_of: Optional[str] = None
    pii: dict = Field(default_factory=lambda: {"found": [], "masked": False})
    source: FeedbackSource
    cleaned_at: datetime = Field(default_factory=datetime.utcnow)
    quality: QualityReport = Field(default_factory=QualityReport)
    schema_version: str = "v1"


# ── 记忆库模型 ──
class MemoryEntry(BaseModel):
    id: str
    normalized_text: str
    embedding: Optional[list[float]] = None
    source: FeedbackSource
    created_at: datetime
    metadata: dict = Field(default_factory=dict)


# ── Scout 模型 ──
class ClusterInfo(BaseModel):
    cluster_id: str
    label: str
    label_confidence: float
    count: int
    sample_ids: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class AlertType(str, Enum):
    EMERGING = "emerging"
    SURGE = "surge"
    DECAY = "decay"  # v2 启用


class Alert(BaseModel):
    type: AlertType
    cluster_id: str
    label: str
    description: str
    evidence_ids: list[str] = Field(default_factory=list)
    suggested_priority: Priority = Priority.P2


class ScoutOutput(BaseModel):
    run_id: str
    clusters: list[ClusterInfo] = Field(default_factory=list)
    alerts: list[Alert] = Field(default_factory=list)
    cluster_purity: float = 0.0
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# ── Evaluator 模型 ──
class CoverageResult(BaseModel):
    score: int = Field(..., ge=1, le=10)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    evidence_density: float = 0.0


class FalsifiabilityResult(BaseModel):
    score: int = Field(..., ge=1, le=10)
    testable: bool = True
    falsification_conditions: list[str] = Field(default_factory=list)
    counter_example_suggestions: list[str] = Field(default_factory=list)


class HighFreqTopic(BaseModel):
    topic: str = ""
    count: int = 0
    companies: list[str] = Field(default_factory=list)
    has_deep_followup: bool = False


class KnowledgeGap(BaseModel):
    area: str = ""
    evidence: str = ""
    urgency: str = "建议"  # 急需 / 建议 / 了解


class StudyTask(BaseModel):
    priority: int = 1
    task: str = ""
    resource: str = ""
    reason: str = ""


class EvaluationResult(BaseModel):
    evaluation_id: str
    hypothesis_alert_id: str
    coverage: CoverageResult
    falsifiability: FalsifiabilityResult
    overall_confidence: str = "中"  # 高 / 中 / 低
    recommended_action: str = ""
    high_freq_topics: list[HighFreqTopic] = Field(default_factory=list)
    knowledge_gaps: list[KnowledgeGap] = Field(default_factory=list)
    study_plan: list[StudyTask] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)


# ── Approval 模型 ──
class ApprovalRecord(BaseModel):
    alert_id: str
    status: HypothesisStatus = HypothesisStatus.PENDING
    approved_priority: Optional[Priority] = None
    approved_by: str = ""
    approved_at: Optional[datetime] = None
    reason: str = ""


# ── 简报模型 ──
class BriefingItem(BaseModel):
    rank: int
    hypothesis: str
    confidence: str          # 高 / 中 / 低
    priority: Priority
    evidence_count: int
    evidence_ids: list[str] = Field(default_factory=list)
    coverage_score: int
    falsifiability_score: int
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommended_action: str = ""
    high_freq_topics: list[HighFreqTopic] = Field(default_factory=list)
    knowledge_gaps: list[KnowledgeGap] = Field(default_factory=list)
    study_plan: list[StudyTask] = Field(default_factory=list)
    valid_until: datetime = Field(default_factory=datetime.utcnow)


class RunStats(BaseModel):
    total_feedback: int = 0
    cleaned: int = 0
    duplicates_removed: int = 0
    clusters_found: int = 0
    alerts_generated: int = 0
    approved: int = 0
    rejected: int = 0
    pending: int = 0
    tokens_used: int = 0
    total_duration_s: float = 0.0


class Briefing(BaseModel):
    briefing_id: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    valid_until: datetime = Field(default_factory=datetime.utcnow)
    summary: str = ""
    items: list[BriefingItem] = Field(default_factory=list)
    run_stats: RunStats = Field(default_factory=RunStats)
    pipeline_version: str = "v1.0.0"
