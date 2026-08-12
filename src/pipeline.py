"""OfferLoop 主编排 —— 一键跑通全链路。"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import RUN_DIR, SEED_DIR, CHROMA_DIR
from src.models import (
    RawFeedback,
    CleanedFeedback,
    ScoutOutput,
    EvaluationResult,
    ApprovalRecord,
    Briefing,
    RunStats,
    HypothesisStatus,
)

logger = logging.getLogger(__name__)


class PipelineRun:
    """一次管道运行的上下文。"""

    def __init__(self):
        self.run_id = f"run_{datetime.utcnow():%Y%m%d_%H%M%S}"
        self.started_at = time.time()
        self.tokens_used = 0

        # 运行输出目录
        self.run_dir = RUN_DIR / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

        # 中间结果
        self.raw_feedbacks: list[RawFeedback] = []
        self.cleaned_feedbacks: list[CleanedFeedback] = []
        self.cleaner_report: dict = {}
        self.scout_output: Optional[ScoutOutput] = None
        self.evaluations: list[EvaluationResult] = []
        self.approvals: dict[str, ApprovalRecord] = {}
        self.briefing: Optional[Briefing] = None

        logger.info("Pipeline run started: %s", self.run_id)

    @property
    def duration_s(self) -> float:
        return time.time() - self.started_at

    def stats(self) -> RunStats:
        """汇总运行统计。"""
        return RunStats(
            total_feedback=len(self.raw_feedbacks),
            cleaned=self.cleaner_report.get("cleaned", 0),
            duplicates_removed=self.cleaner_report.get("duplicates", 0),
            clusters_found=len(self.scout_output.clusters) if self.scout_output else 0,
            alerts_generated=len(self.scout_output.alerts) if self.scout_output else 0,
            approved=sum(1 for v in self.approvals.values() if v.status == HypothesisStatus.APPROVED),
            rejected=sum(1 for v in self.approvals.values() if v.status == HypothesisStatus.REJECTED),
            pending=sum(1 for v in self.approvals.values() if v.status == HypothesisStatus.PENDING),
            tokens_used=self.tokens_used,
            total_duration_s=round(self.duration_s, 1),
        )


def run_full_pipeline(
    csv_path: Optional[str | Path] = None,
    *,
    skip_approval: bool = True,
    skip_embedding: bool = False,
) -> PipelineRun:
    """一键运行完整管道。

    Args:
        csv_path: CSV 反馈文件路径（None 则用 seed 数据）
        skip_approval: 是否跳过审批闸门（True = 自动批准所有告警）
        skip_embedding: 是否跳过嵌入生成（使用零向量占位）

    Returns:
        PipelineRun with all results
    """
    run = PipelineRun()

    # ── Step 1: Inbox ──
    logger.info("=" * 50)
    logger.info("Step 1/7: Inbox — 导入反馈")
    _step_inbox(run, csv_path)

    # ── Step 2: Cleaner ──
    logger.info("=" * 50)
    logger.info("Step 2/7: Cleaner — 语义清洗")
    _step_cleaner(run)

    if not run.cleaned_feedbacks:
        logger.warning("No feedbacks after cleaning, pipeline stops")
        return run

    # ── Step 3: Memory ──
    logger.info("=" * 50)
    logger.info("Step 3/7: Memory — 向量存储")
    _step_memory(run, skip_embedding)

    # ── Step 4: Scout ──
    logger.info("=" * 50)
    logger.info("Step 4/7: Scout — 信号探测")
    _step_scout(run)

    if not run.scout_output or not run.scout_output.alerts:
        logger.warning("No alerts generated, pipeline stops")
        return run

    # ── Step 5: Approval ──
    logger.info("=" * 50)
    logger.info("Step 5/7: Approval — 审批闸门")
    _step_approval(run, skip_approval)

    # ── Step 6: Evaluator ──
    logger.info("=" * 50)
    logger.info("Step 6/7: Evaluator — 假设评估")
    _step_evaluator(run)

    # ── Step 7: Output ──
    logger.info("=" * 50)
    logger.info("Step 7/7: Output — 简报生成")
    _step_output(run)

    # ── 持久化运行摘要 ──
    _save_run_summary(run)

    logger.info("=" * 50)
    logger.info("Pipeline complete: %s (%.1fs)", run.run_id, run.duration_s)
    logger.info("Stats: %s", run.stats().model_dump())

    return run


def _step_inbox(run: PipelineRun, csv_path: Optional[str | Path], merge_samples: bool = True) -> None:
    """Step 1: 导入反馈。merge_samples=True 时，CSV 与内置30条合并。"""
    from src.inbox.csv_importer import import_csv

    # 总是加载内置示例作为底料
    base = _get_sample_feedback()
    logger.info("Loaded %d built-in samples", len(base))

    if csv_path and Path(csv_path).exists():
        csv_data = import_csv(csv_path)
        logger.info("Loaded %d from %s", len(csv_data), csv_path)
        if merge_samples:
            # 合并：内置 + CSV，去重由 Cleaner 处理
            run.raw_feedbacks = base + csv_data
            logger.info("Merged: %d total feedbacks", len(run.raw_feedbacks))
        else:
            run.raw_feedbacks = csv_data
    else:
        seed_csv = SEED_DIR / "feedback.csv"
        if seed_csv.exists() and seed_csv != Path(csv_path or ""):
            logger.info("Loading seed data from %s", seed_csv)
            run.raw_feedbacks = base + import_csv(seed_csv)
        else:
            run.raw_feedbacks = base

    logger.info("Inbox: %d feedbacks loaded", len(run.raw_feedbacks))


def _step_cleaner(run: PipelineRun) -> None:
    """Step 2: 清洗反馈。"""
    from src.cleaner.pipeline import run_cleaner_pipeline

    cleaned, stats, report = run_cleaner_pipeline(run.raw_feedbacks)
    run.cleaned_feedbacks = cleaned
    run.cleaner_report = report
    logger.info("Cleaner: %s", report)


def _step_memory(run: PipelineRun, skip_embedding: bool = False) -> None:
    """Step 3: 生成嵌入 + 存入 Chroma。"""
    from src.memory.embedding import embed_texts
    from src.memory.store import store_batch

    # 只存储非重复的反馈
    unique = [f for f in run.cleaned_feedbacks if not f.is_duplicate]
    texts = [f.normalized_text for f in unique]

    if not skip_embedding and texts:
        logger.info("Generating embeddings for %d texts...", len(texts))
        embeddings = embed_texts(texts)
    else:
        logger.warning("Skipping embedding generation")
        embeddings = [None] * len(texts)

    count = store_batch(unique, embeddings)
    logger.info("Memory: %d stored", count)


def _step_scout(run: PipelineRun) -> None:
    """Step 4: 信号探测。"""
    from src.memory.retrieval import get_all_feedback
    from src.memory.embedding import embed_texts
    from src.scout.pipeline import run_scout_pipeline

    # 从记忆库获取所有已存储的反馈
    stored = get_all_feedback()

    if not stored:
        logger.warning("No feedback in memory for scout")
        return

    documents = [item["normalized_text"] for item in stored]
    doc_ids = [item["id"] for item in stored]

    # 确保有嵌入（如果存储时没有嵌入，这里重新生成）
    embeddings = []
    for item in stored:
        emb = item.get("embedding")
        if emb is not None and len(emb) > 0:
            embeddings.append(emb)
        else:
            embeddings.append([])

    if not any(len(e) > 0 for e in embeddings):
        # 全部没有嵌入，重新生成
        logger.info("No embeddings in memory, generating...")
        embeddings = embed_texts(documents)

    # 加载历史信号
    previous_signals = _load_previous_signals(run)

    run.scout_output = run_scout_pipeline(
        documents=documents,
        doc_ids=doc_ids,
        embeddings=embeddings,
        previous_signals=previous_signals,
    )

    # 持久化告警
    alerts_path = RUN_DIR / "latest_alerts.json"
    alerts_path.parent.mkdir(parents=True, exist_ok=True)
    alerts_path.write_text(
        json.dumps(
            [a.model_dump() for a in run.scout_output.alerts],
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )

    logger.info("Scout: %d clusters, %d alerts", len(run.scout_output.clusters), len(run.scout_output.alerts))


def _step_approval(run: PipelineRun, skip_approval: bool) -> None:
    """Step 5: 审批闸门。"""
    from src.approval.app import load_approvals, merge_alerts_to_pending, save_approvals

    if not run.scout_output or not run.scout_output.alerts:
        return

    alerts = run.scout_output.alerts
    approvals = load_approvals()
    approvals = merge_alerts_to_pending(alerts, approvals)

    if skip_approval:
        # 自动批准所有 P0/P1，P2 保持 pending
        for alert in alerts:
            key = alert.cluster_id
            record = approvals.get(key, ApprovalRecord(alert_id=key))
            if record.status == HypothesisStatus.PENDING:
                if alert.suggested_priority.value in ("P0", "P1"):
                    record.status = HypothesisStatus.APPROVED
                    record.approved_priority = alert.suggested_priority
                    record.approved_by = "auto"
                    record.approved_at = datetime.utcnow()
                    record.reason = f"自动批准（skip_approval 模式，优先级 {alert.suggested_priority.value}）"
                # P2 保持 pending —— 不在 skip 模式中自动批准
            approvals[key] = record

    save_approvals(approvals)
    run.approvals = approvals

    pending = sum(1 for v in approvals.values() if v.status == HypothesisStatus.PENDING)
    logger.info("Approval: %d approved, %d rejected, %d pending",
                sum(1 for v in approvals.values() if v.status == HypothesisStatus.APPROVED),
                sum(1 for v in approvals.values() if v.status == HypothesisStatus.REJECTED),
                pending)


def _step_evaluator(run: PipelineRun) -> None:
    """Step 6: 假设评估。"""
    from src.evaluator.pipeline import evaluate_batch
    from src.memory.retrieval import search

    if not run.scout_output or not run.scout_output.alerts:
        return

    # 筛选审批通过的告警
    approved_alerts = [
        a for a in run.scout_output.alerts
        if run.approvals.get(a.cluster_id, ApprovalRecord(alert_id=a.cluster_id)).status == HypothesisStatus.APPROVED
    ]

    if not approved_alerts:
        logger.info("No approved alerts to evaluate")
        return

    # 为每个告警检索相关证据
    evidence_map: dict[str, list[str]] = {}
    for alert in approved_alerts:
        # 用 cluster label 作为查询检索相关反馈
        search_results = search(alert.label, top_k=10)
        evidence_map[alert.cluster_id] = [r["document"] for r in search_results]

    # 内存上下文
    memory_context = {
        "related_feedback_count": sum(len(v) for v in evidence_map.values()),
        "related_company": [],
        "related_roles": [],
    }

    run.evaluations = evaluate_batch(
        alerts=approved_alerts,
        evidence_map=evidence_map,
        memory_context=memory_context,
    )

    logger.info("Evaluator: %d hypotheses evaluated", len(run.evaluations))


def _step_output(run: PipelineRun) -> None:
    """Step 7: 简报生成。"""
    from src.output.generator import generate_briefing, write_briefing

    if not run.scout_output or not run.scout_output.alerts:
        return

    # 筛选已审批的告警及其评估结果
    approved_alerts = [
        a for a in run.scout_output.alerts
        if run.approvals.get(a.cluster_id, ApprovalRecord(alert_id=a.cluster_id)).status == HypothesisStatus.APPROVED
    ]

    approval_records = [
        run.approvals[a.cluster_id]
        for a in approved_alerts
        if a.cluster_id in run.approvals
    ]

    run.briefing = generate_briefing(
        approved_alerts=approved_alerts,
        evaluations=run.evaluations,
        approval_records=approval_records,
        run_stats=run.stats(),
    )

    # 写入文件
    write_briefing(run.briefing, run.run_dir, filename_prefix="briefing")

    logger.info("Output: briefing generated with %d items", len(run.briefing.items))


def _load_previous_signals(run: PipelineRun) -> Optional[list[dict]]:
    """加载上一次运行的 Scout 输出作为历史信号。"""
    latest_scout = RUN_DIR / "latest_scout_output.json"
    if latest_scout.exists():
        try:
            data = json.loads(latest_scout.read_text())
            return data.get("clusters", [])
        except Exception:
            pass
    return None


def _save_run_summary(run: PipelineRun) -> None:
    """持久化运行摘要。"""
    summary = {
        "run_id": run.run_id,
        "started_at": datetime.utcnow().isoformat(),
        "duration_s": run.duration_s,
        "stats": run.stats().model_dump(),
    }

    summary_path = run.run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str))

    # 保存 scout 输出作为下次历史
    if run.scout_output:
        scout_path = RUN_DIR / "latest_scout_output.json"
        scout_path.write_text(
            json.dumps(run.scout_output.model_dump(), ensure_ascii=False, indent=2, default=str)
        )

    # 保存简报路径
    if run.briefing:
        briefing_path = run.run_dir / "briefing.json"
        briefing_path.write_text(
            json.dumps(run.briefing.model_dump(), ensure_ascii=False, indent=2, default=str)
        )

    logger.info("Run summary saved: %s", summary_path)


def _get_sample_feedback() -> list[RawFeedback]:
    """内置示例反馈数据（开发和 smoke test 用）。"""
    from src.models import FeedbackSource

    samples = [
        ("2025-12-03 腾讯AI岗面试，问到了RAG项目的向量检索选型，追问了Chroma和Milvus的区别",
         "other_jingyan"),
        ("13812345678 张三在腾讯面的 AI 岗，问了 RAG 项目是怎么做混合检索的",
         "other_jingyan"),
        ("百度面试问了如何做混合检索，BM25和向量怎么融合",
         "other_jingyan"),
        ("字节面试问到了RRF重排序的原理和实现",
         "other_jingyan"),
        ("RAG项目里问答质量怎么评估，面试官问到了Recall和MRR",
         "other_jingyan"),
        ("面试要求在知识库里做父子分块，解释为什么不用普通分块",
         "other_jingyan"),
        ("今天面字节AI应用岗，主要问了LangGraph的Agent编排原理",
         "other_jingyan"),
        ("百度面试官问到了多Agent协作模式，怎么处理agent间通信",
         "other_jingyan"),
        ("腾讯面试问到了Function Call的实现原理和工具调用链",
         "other_jingyan"),
        ("面试中要求设计一个多智能体系统，问了状态管理和错误恢复",
         "other_jingyan"),
        ("今天面试问了Prompt Engineering的最佳实践",
         "other_jingyan"),
        ("面试官问了如何处理大模型的幻觉问题",
         "other_jingyan"),
        ("面的AI岗问到了向量数据库索引选型，HNSW和IVF的区别",
         "other_jingyan"),
        ("面试要求现场写一个ReAct Agent的简化实现",
         "other_jingyan"),
        ("问了如何评估Agent系统的好坏，用哪些指标",
         "other_jingyan"),
        ("面字节问了知识库分块策略，语义分块和固定分块的优劣",
         "other_jingyan"),
        ("今天面试问了多模态RAG的实现思路",
         "other_jingyan"),
        ("面试官问了对AI应用开发的未来趋势看法",
         "other_jingyan"),
        ("面的AI岗，让设计一个客服机器人的完整架构",
         "other_jingyan"),
        ("问了如何使用LangSmith做Agent trace和调试",
         "other_jingyan"),
        ("面试官问到了流式输出的实现方式和SSE协议",
         "other_jingyan"),
        ("面的岗位问了对开源和闭源模型的选择策略",
         "other_jingyan"),
        ("问了RAG和微调各自的适用场景和优缺点",
         "other_jingyan"),
        ("大厂AI岗面试，问了如何处理长上下文和窗口扩展",
         "other_jingyan"),
        ("面经分享：问到了Agent的安全防护，提示注入的防御",
         "other_jingyan"),
        ("面试问了怎么给大模型做评测，有哪些benchmark",
         "other_jingyan"),
        ("问到了LLM推理加速的几种方案，vLLM和TensorRT",
         "other_jingyan"),
        ("面了字节，问RAG系统在处理实时数据更新时的策略",
         "other_jingyan"),
        ("今天面了腾讯AI应用岗，主要问了Agent框架的设计思路",
         "other_jingyan"),
        ("面的岗位要求设计一个支持多轮对话的面试模拟系统",
         "other_jingyan"),
    ]

    return [
        RawFeedback(
            id=f"raw_{i+1:04d}",
            raw_text=text,
            source=FeedbackSource(source),
            received_at=datetime.utcnow(),
        )
        for i, (text, source) in enumerate(samples)
    ]
