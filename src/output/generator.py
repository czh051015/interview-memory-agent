"""简报生成器 —— 纯规则引擎 + Jinja2 模板渲染。"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.config import BRIEFING_VALIDITY_DAYS
from src.models import (
    Alert,
    EvaluationResult,
    ApprovalRecord,
    Briefing,
    BriefingItem,
    RunStats,
    Priority,
)

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_JINJA_ENV = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(),
)


def generate_briefing(
    approved_alerts: list[Alert],
    evaluations: list[EvaluationResult],
    approval_records: list[ApprovalRecord],
    run_stats: RunStats,
    *,
    valid_days: int = BRIEFING_VALIDITY_DAYS,
) -> Briefing:
    """生成简报对象（JSON 结构 + Markdown 渲染）。

    流程：
    1. 按审批优先级排序（P0 > P1 > P2）
    2. 组装每个 briefing item（八字段）
    3. 计算有效期
    4. 渲染 Markdown + JSON

    Args:
        approved_alerts: 审批通过的告警
        evaluations: 对应的评估结果
        approval_records: 审批记录
        run_stats: 运行统计
        valid_days: 有效期天数

    Returns:
        Briefing 对象（含 JSON 和 Markdown）
    """
    now = datetime.utcnow()
    briefing_id = f"brief_{now:%Y%m%d_%H%M}"

    # 构建 alert_id → (alert, evaluation, approval) 映射
    eval_map: dict[str, EvaluationResult] = {}
    for ev in evaluations:
        eval_map[ev.hypothesis_alert_id] = ev

    approval_map: dict[str, ApprovalRecord] = {}
    for ar in approval_records:
        approval_map[ar.alert_id] = ar

    # 组装 items
    items: list[BriefingItem] = []
    for rank, alert in enumerate(approved_alerts, start=1):
        evaluation = eval_map.get(alert.cluster_id)
        approval = approval_map.get(alert.cluster_id)

        priority = alert.suggested_priority
        if approval and approval.approved_priority:
            priority = approval.approved_priority

        if evaluation:
            coverage_score = evaluation.coverage.score
            falsifiability_score = evaluation.falsifiability.score
            confidence = evaluation.overall_confidence
            strengths = evaluation.coverage.strengths
            gaps = evaluation.coverage.gaps
            recommended_action = evaluation.recommended_action
            risks = evaluation.coverage.gaps[:3] + (
                evaluation.falsifiability.counter_example_suggestions[:2] or []
            )
        else:
            coverage_score = 0
            falsifiability_score = 0
            confidence = "未评估"
            strengths = []
            gaps = ["未经评估器处理"]
            recommended_action = ""
            risks = ["未经评估，风险未知"]

        items.append(BriefingItem(
            rank=rank,
            hypothesis=alert.label,
            confidence=confidence,
            priority=priority,
            evidence_count=len(alert.evidence_ids),
            evidence_ids=alert.evidence_ids,
            coverage_score=coverage_score,
            falsifiability_score=falsifiability_score,
            strengths=strengths,
            gaps=gaps,
            risks=risks,
            recommended_action=recommended_action,
            high_freq_topics=evaluation.high_freq_topics if evaluation else [],
            knowledge_gaps=evaluation.knowledge_gaps if evaluation else [],
            study_plan=evaluation.study_plan if evaluation else [],
            valid_until=now + timedelta(days=valid_days),
        ))

    # 按优先级排序
    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    items.sort(key=lambda x: (priority_order.get(x.priority.value, 99), x.rank))

    # 重设 rank
    for i, item in enumerate(items, 1):
        item.rank = i

    summary = _generate_summary(items, run_stats)

    briefing = Briefing(
        briefing_id=briefing_id,
        generated_at=now,
        valid_until=now + timedelta(days=valid_days),
        summary=summary,
        items=items,
        run_stats=run_stats,
        pipeline_version="v1.0.0",
    )

    logger.info("Briefing generated: %d items", len(items))
    return briefing


def render_markdown(briefing: Briefing) -> str:
    """将简报渲染为 Markdown 字符串。"""
    template = _JINJA_ENV.get_template("briefing.md.j2")
    return template.render(
        generated_at=briefing.generated_at.isoformat(),
        valid_until=briefing.valid_until.isoformat(),
        items=[it.model_dump() for it in briefing.items],
        run_stats=briefing.run_stats.model_dump(),
        briefing_id=briefing.briefing_id,
        pipeline_version=briefing.pipeline_version,
    )


def render_json(briefing: Briefing) -> str:
    """将简报序列化为 JSON 字符串。"""
    return json.dumps(briefing.model_dump(), ensure_ascii=False, indent=2, default=str)


def write_briefing(
    briefing: Briefing,
    output_dir: str | Path,
    *,
    filename_prefix: str = "",
) -> tuple[Path, Path]:
    """将简报写入文件（Markdown + JSON）。

    Returns:
        (md_path, json_path)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    prefix = filename_prefix or briefing.briefing_id

    md_path = output_dir / f"{prefix}.md"
    json_path = output_dir / f"{prefix}.json"

    md_path.write_text(render_markdown(briefing), encoding="utf-8")
    json_path.write_text(render_json(briefing), encoding="utf-8")

    logger.info("Briefing written: %s, %s", md_path, json_path)
    return md_path, json_path


def _generate_summary(items: list[BriefingItem], stats: RunStats) -> str:
    """生成简报摘要文本。"""
    p0_count = sum(1 for it in items if it.priority == Priority.P0)
    p1_count = sum(1 for it in items if it.priority == Priority.P1)

    if not items:
        return f"本期基于 {stats.total_feedback} 条面试反馈，未识别出值得关注的求职信号。"

    parts = [f"本期基于 {stats.total_feedback} 条面试反馈"]

    if p0_count > 0:
        parts.append(f"识别出 {p0_count} 条 P0 级高优先级信号")
    if p1_count > 0:
        parts.append(f"{p1_count} 条 P1 级信号")

    parts.append("值得关注。")
    return "，".join(parts)
