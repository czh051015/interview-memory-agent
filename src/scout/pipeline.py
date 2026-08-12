"""Scout 主管线 —— 编排查聚类、命名、偏移检测。"""

import logging
from datetime import datetime
from typing import Optional

import numpy as np

from src.models import ScoutOutput, ClusterInfo, Alert
from src.scout.cluster import run_clustering, name_all_clusters
from src.scout.alerting import detect_shifts

logger = logging.getLogger(__name__)


def run_scout_pipeline(
    documents: list[str],
    doc_ids: list[str],
    embeddings: list[list[float]],
    *,
    previous_signals: Optional[list[dict]] = None,
    ground_truth: Optional[list[int]] = None,
) -> ScoutOutput:
    """运行完整的信号探测管线。

    Args:
        documents: 反馈文本列表
        doc_ids: 对应的反馈 ID 列表
        embeddings: 对应的嵌入向量列表
        previous_signals: 历史信号（用于偏移检测）
        ground_truth: 真实主题标签（仅 eval 用）

    Returns:
        ScoutOutput with clusters, alerts, metadata
    """
    run_id = f"scout_{datetime.utcnow():%Y%m%d_%H%M}"

    if len(embeddings) == 0:
        logger.warning("No embeddings provided, skipping scout")
        return ScoutOutput(run_id=run_id)

    # Step 1: 聚类
    emb_array = np.array(embeddings, dtype=np.float32)
    labels, cluster_stats = run_clustering(emb_array)

    if not cluster_stats:
        logger.info("No clusters found")
        return ScoutOutput(run_id=run_id)

    # Step 2: LLM 簇命名
    clusters = name_all_clusters(labels, documents, doc_ids, cluster_stats)

    # Step 3: 偏移检测
    prev_clusters = None
    if previous_signals:
        prev_clusters = [
            ClusterInfo(
                cluster_id=s["cluster_id"],
                label=s["label"],
                label_confidence=0.8,
                count=s["count"],
                sample_ids=s.get("sample_ids", []),
                keywords=s.get("keywords", []),
            )
            for s in previous_signals
        ]
    alerts = detect_shifts(clusters, prev_clusters)

    # Step 4: 纯度计算（eval 用）
    purity = 0.0
    if ground_truth is not None:
        from src.scout.cluster import compute_cluster_purity
        purity = compute_cluster_purity(labels, ground_truth)

    output = ScoutOutput(
        run_id=run_id,
        clusters=clusters,
        alerts=alerts,
        cluster_purity=purity,
        generated_at=datetime.utcnow(),
    )

    logger.info(
        "Scout done: %d clusters, %d alerts, purity=%.2f",
        len(clusters), len(alerts), purity,
    )
    return output
