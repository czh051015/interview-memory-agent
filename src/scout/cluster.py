"""聚类管线 —— HDBSCAN 无监督聚类 + LLM 簇命名。"""

import logging
from typing import Optional

import numpy as np
from hdbscan import HDBSCAN
from sklearn.metrics.pairwise import cosine_distances

from src.llm import chat_json
from src.scout.prompts import CLUSTER_NAMING_SYSTEM, CLUSTER_NAMING_USER
from src.models import ClusterInfo

logger = logging.getLogger(__name__)

# v1 聚类参数（v2 可配置化）
MIN_CLUSTER_SIZE = 3
MIN_SAMPLES = 1
CLUSTER_SELECTION_EPSILON = 0.1

# LLM 命名时采样的样本数（每簇取前 N 条）
NAMING_SAMPLE_COUNT = 5


def run_clustering(
    embeddings: np.ndarray,
    *,
    min_cluster_size: int = MIN_CLUSTER_SIZE,
    min_samples: int = MIN_SAMPLES,
    cluster_selection_epsilon: float = CLUSTER_SELECTION_EPSILON,
) -> tuple[np.ndarray, dict]:
    """HDBSCAN 聚类。

    Args:
        embeddings: shape (n_samples, n_features)

    Returns:
        (labels, cluster_stats) — labels[i] 为簇编号，-1 表示噪声
    """
    if len(embeddings) < MIN_CLUSTER_SIZE:
        logger.warning("Too few samples for clustering: %d", len(embeddings))
        return np.full(len(embeddings), -1), {}

    clusterer = HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="euclidean",  # HDBSCAN 内部使用 euclidean，我们需要 cosine 距离需预处理
        cluster_selection_epsilon=cluster_selection_epsilon,
    )
    labels = clusterer.fit_predict(embeddings)

    # 统计
    stats = {}
    unique_labels = set(labels)
    for label in unique_labels:
        if label == -1:
            continue
        count = int(np.sum(labels == label))
        stats[label] = {"count": count, "indices": np.where(labels == label)[0].tolist()}

    logger.info(
        "Clustering: %d clusters, %d noise points out of %d samples",
        len(stats),
        int(np.sum(labels == -1)),
        len(embeddings),
    )
    return labels, stats


def name_cluster(
    samples: list[str],
    sample_ids: list[str],
    cluster_id: int,
) -> ClusterInfo:
    """LLM 命名一个簇。

    Args:
        samples: 该簇的代表文本（最多 NAMING_SAMPLE_COUNT 条）
        sample_ids: 对应的反馈 ID
        cluster_id: 簇编号（用于生成 cluster_id 字符串）

    Returns:
        ClusterInfo with label, keywords, label_confidence
    """
    samples_for_naming = samples[:NAMING_SAMPLE_COUNT]
    samples_text = "\n".join(
        f"{i+1}. {s}" for i, s in enumerate(samples_for_naming)
    )

    try:
        result = chat_json(
            system_prompt=CLUSTER_NAMING_SYSTEM,
            user_prompt=CLUSTER_NAMING_USER.format(samples=samples_text),
        )
        label = result.get("label", f"cluster_{cluster_id}")
        keywords = result.get("keywords", [])
        confidence = result.get("label_confidence", 0.5)
    except Exception as e:
        logger.warning("Cluster naming failed for cluster %d: %s", cluster_id, e)
        label = f"主题簇_{cluster_id}"
        keywords = []
        confidence = 0.0

    return ClusterInfo(
        cluster_id=f"c{cluster_id}",
        label=label,
        label_confidence=round(confidence, 2),
        count=len(samples),
        sample_ids=sample_ids[:5],  # 保留前 5 个作为证据
        keywords=keywords,
    )


def name_all_clusters(
    labels: np.ndarray,
    documents: list[str],
    doc_ids: list[str],
    cluster_stats: dict,
) -> list[ClusterInfo]:
    """为所有簇命名。

    Returns:
        按簇大小降序排列的 ClusterInfo 列表。
    """
    clusters = []
    # 按簇大小降序
    sorted_clusters = sorted(
        cluster_stats.items(),
        key=lambda x: x[1]["count"],
        reverse=True,
    )

    for label, info in sorted_clusters:
        indices = info["indices"]
        samples = [documents[i] for i in indices]
        ids = [doc_ids[i] for i in indices]
        cluster_info = name_cluster(samples, ids, label)
        clusters.append(cluster_info)

    return clusters


def compute_cluster_purity(
    labels: np.ndarray,
    ground_truth: Optional[list[int]] = None,
) -> float:
    """计算聚类纯度（需要人工标注真值）。

    Args:
        labels: 聚类标签
        ground_truth: 真实主题标签（可选，仅 eval 时提供）

    Returns:
        纯度分数 [0, 1]
    """
    if ground_truth is None:
        return 0.0

    # 简化纯度计算：多数类占比的均值
    purity = 0.0
    unique_labels = set(labels)
    cluster_count = 0

    for label in unique_labels:
        if label == -1:
            continue
        cluster_count += 1
        indices = np.where(labels == label)[0]
        gt_for_cluster = [ground_truth[i] for i in indices]
        if not gt_for_cluster:
            continue
        # 多数类的比例
        from collections import Counter
        majority_count = Counter(gt_for_cluster).most_common(1)[0][1]
        purity += majority_count / len(gt_for_cluster)

    if cluster_count == 0:
        return 0.0
    return purity / cluster_count
