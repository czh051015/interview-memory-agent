"""Evaluator 主管线 —— 单轮 LLM 结构化输出，温度 0 保复现。"""

import logging
from datetime import datetime
from typing import Optional

from src.llm import chat_json
from src.evaluator.prompts import EVALUATOR_SYSTEM, EVALUATOR_USER
from src.models import (
    Alert,
    EvaluationResult,
    CoverageResult,
    FalsifiabilityResult,
    HighFreqTopic,
    KnowledgeGap,
    StudyTask,
)

logger = logging.getLogger(__name__)

# 综合评分的加权系数
COVERAGE_WEIGHT = 0.6
FALSIFIABILITY_WEIGHT = 0.4


def evaluate_single(
    alert: Alert,
    evidence_texts: list[str],
    *,
    memory_context: Optional[dict] = None,
) -> EvaluationResult:
    """评估单条假设的信号强度。

    Args:
        alert: 来自 Scout 的告警信号
        evidence_texts: 证据原文列表（已经脱敏的 normalized_text）
        memory_context: 记忆库背景信息（相关反馈数、公司列表等）

    Returns:
        EvaluationResult with coverage, falsifiability, overall_confidence
    """
    eval_id = f"eval_{datetime.utcnow():%Y%m%d_%H%M}"

    # 拼装证据文本
    evidence_str = "\n\n".join(
        f"[{i+1}] {t}" for i, t in enumerate(evidence_texts[:10])  # 最多 10 条证据
    )

    # 拼装背景信息
    ctx = memory_context or {}
    ctx_str = (
        f"相关反馈总数: {ctx.get('related_feedback_count', 0)}\n"
        f"涉及公司: {', '.join(ctx.get('related_company', [])) or '未知'}\n"
        f"涉及岗位: {', '.join(ctx.get('related_roles', [])) or '未知'}"
    )

    user_prompt = EVALUATOR_USER.format(
        hypothesis_description=alert.description,
        n_evidence=len(evidence_texts),
        evidence_fulltext=evidence_str,
        memory_context=ctx_str,
    )

    try:
        result = chat_json(
            system_prompt=EVALUATOR_SYSTEM,
            user_prompt=user_prompt,
            temperature=0.0,
            max_tokens=2048,
        )
    except Exception as e:
        logger.error("Evaluator LLM call failed: %s", e)
        # 降级返回默认结果
        return _fallback_result(eval_id, alert, str(e))

    # 解析并校验
    try:
        coverage_raw = result.get("coverage", {})
        falsifiability_raw = result.get("falsifiability", {})

        coverage = CoverageResult(
            score=_clamp_score(coverage_raw.get("score", 5)),
            strengths=coverage_raw.get("strengths", []),
            gaps=coverage_raw.get("gaps", []),
            evidence_density=min(max(float(coverage_raw.get("evidence_density", 0)), 0), 1),
        )

        falsifiability = FalsifiabilityResult(
            score=_clamp_score(falsifiability_raw.get("score", 5)),
            testable=bool(falsifiability_raw.get("testable", True)),
            falsification_conditions=falsifiability_raw.get("falsification_conditions", []),
            counter_example_suggestions=falsifiability_raw.get("counter_example_suggestions", []),
        )

        # 校验 overall_confidence
        confidence = result.get("overall_confidence", "中")
        if confidence not in ("高", "中", "低"):
            confidence = _compute_confidence(coverage.score, falsifiability.score)

        # 新增：高频考点、知识缺口、学习计划
        high_freq = [_parse_topic(t) for t in result.get("high_freq_topics", [])]
        gaps = [_parse_gap(g) for g in result.get("knowledge_gaps", [])]
        plan = [_parse_task(s) for s in result.get("study_plan", [])]

        return EvaluationResult(
            evaluation_id=eval_id,
            hypothesis_alert_id=alert.cluster_id,
            coverage=coverage,
            falsifiability=falsifiability,
            overall_confidence=confidence,
            recommended_action=result.get("recommended_action", ""),
            high_freq_topics=high_freq,
            knowledge_gaps=gaps,
            study_plan=plan,
            evaluated_at=datetime.utcnow(),
        )

    except Exception as e:
        logger.warning("Evaluator result parsing failed: %s", e)
        return _fallback_result(eval_id, alert, str(e))


def evaluate_batch(
    alerts: list[Alert],
    evidence_map: dict[str, list[str]],  # alert_id → 证据文本列表
    *,
    memory_context: Optional[dict] = None,
) -> list[EvaluationResult]:
    """批量评估多条假设。

    Args:
        alerts: Scout 告警列表
        evidence_map: alert_id → 证据文本列表的映射
        memory_context: 全局记忆库背景信息

    Returns:
        评估结果列表
    """
    results = []
    for alert in alerts:
        evidence = evidence_map.get(alert.cluster_id, evidence_map.get(alert.label, []))
        if not evidence:
            # 从 alert 自己的 evidence_ids 构建（需要外部注入原文）
            evidence = [f"证据ID: {eid}" for eid in alert.evidence_ids]

        result = evaluate_single(alert, evidence, memory_context=memory_context)
        results.append(result)

    return results


def check_consistency(
    hypothesis_description: str,
    evidence_texts: list[str],
    n_runs: int = 3,
) -> dict:
    """评估一致性检验：同一假设重复评估 n 次，计算分差。

    Returns:
        {"scores": [[c1, f1], ...], "max_diff_coverage": 0, "max_diff_falsifiability": 0, "pass": true/false}
    """
    scores = []
    for _ in range(n_runs):
        # 创建临时 alert
        alert = Alert(
            type="surge",
            cluster_id="consistency_test",
            label="一致性检验",
            description=hypothesis_description,
            evidence_ids=[],
        )
        result = evaluate_single(alert, evidence_texts)
        scores.append([result.coverage.score, result.falsifiability.score])

    max_diff_c = max(s[0] for s in scores) - min(s[0] for s in scores)
    max_diff_f = max(s[1] for s in scores) - min(s[1] for s in scores)

    return {
        "scores": scores,
        "max_diff_coverage": max_diff_c,
        "max_diff_falsifiability": max_diff_f,
        "pass": max_diff_c <= 1 and max_diff_f <= 1,
    }


def _parse_topic(data: dict) -> HighFreqTopic:
    return HighFreqTopic(
        topic=data.get("topic", ""),
        count=data.get("count", 0),
        companies=data.get("companies", []),
        has_deep_followup=data.get("has_deep_followup", False),
    )


def _parse_gap(data: dict) -> KnowledgeGap:
    return KnowledgeGap(
        area=data.get("area", ""),
        evidence=data.get("evidence", ""),
        urgency=data.get("urgency", "建议"),
    )


def _parse_task(data: dict) -> StudyTask:
    return StudyTask(
        priority=data.get("priority", 1),
        task=data.get("task", ""),
        resource=data.get("resource", ""),
        reason=data.get("reason", ""),
    )


def _clamp_score(score: int) -> int:
    """将分数限制在 1-10。"""
    return max(1, min(10, int(score)))


def _compute_confidence(coverage_score: int, falsifiability_score: int) -> str:
    """根据加权分计算置信度标签。"""
    weighted = coverage_score * COVERAGE_WEIGHT + falsifiability_score * FALSIFIABILITY_WEIGHT
    if weighted >= 8:
        return "高"
    elif weighted >= 5:
        return "中"
    return "低"


def _fallback_result(eval_id: str, alert: Alert, error: str) -> EvaluationResult:
    """LLM 调用失败时的降级评估结果。"""
    return EvaluationResult(
        evaluation_id=eval_id,
        hypothesis_alert_id=alert.cluster_id,
        coverage=CoverageResult(
            score=5,
            strengths=["评估自动降级"],
            gaps=[f"LLM 调用失败: {error}"],
            evidence_density=0.0,
        ),
        falsifiability=FalsifiabilityResult(
            score=5,
            testable=True,
            falsification_conditions=["评估降级，需人工复查"],
            counter_example_suggestions=[],
        ),
        overall_confidence="中",
        recommended_action=f"LLM 评估失败，建议人工复查: {error}",
    )
