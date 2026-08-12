"""偏移检测 —— 对比历史信号，发现 emerging / surge / decay。"""

import logging
from typing import Optional

from src.config import SURGE_THRESHOLD, EMERGING_MIN_COUNT
from src.models import Alert, AlertType, ClusterInfo, Priority

logger = logging.getLogger(__name__)


def detect_shifts(
    current_clusters: list[ClusterInfo],
    previous_clusters: Optional[list[ClusterInfo]] = None,
    *,
    surge_threshold: float = SURGE_THRESHOLD,
    emerging_min_count: int = EMERGING_MIN_COUNT,
) -> list[Alert]:
    """对比当前和历史聚类结果，检测趋势偏移。

    Args:
        current_clusters: 当前聚类的簇信息
        previous_clusters: 历史聚类结果（None 表示首次运行）
        surge_threshold: 激增阈值（默认 1.20，即 +20%）
        emerging_min_count: 新主题最少需要多少条才报（默认 3）

    Returns:
        Alert 列表
    """
    alerts: list[Alert] = []

    if not previous_clusters:
        # 首次运行：所有簇都算 "emerging"
        for c in current_clusters:
            if c.count >= emerging_min_count:
                alerts.append(Alert(
                    type=AlertType.EMERGING,
                    cluster_id=c.cluster_id,
                    label=c.label,
                    description=f"新主题出现：{c.count} 条反馈涉及「{c.label}」，此前无此主题",
                    evidence_ids=c.sample_ids,
                    suggested_priority=_suggest_priority(c.count, 0),
                ))
        logger.info("First run: %d emerging alerts", len(alerts))
        return alerts

    # 构建历史映射
    prev_map: dict[str, int] = {}
    for pc in previous_clusters:
        prev_map[pc.cluster_id] = pc.count
        # 也尝试按 label 匹配（同一个 label 可能得到不同的 cluster_id）
        prev_map[pc.label] = pc.count

    for c in current_clusters:
        # 尝试按 cluster_id 匹配，再按 label 匹配
        prev_count = prev_map.get(c.cluster_id, prev_map.get(c.label, 0))

        if prev_count == 0:
            # 新出现的主题
            if c.count >= emerging_min_count:
                alerts.append(Alert(
                    type=AlertType.EMERGING,
                    cluster_id=c.cluster_id,
                    label=c.label,
                    description=f"新主题出现：过去一周 {c.count} 条反馈涉及「{c.label}」，此前无此主题",
                    evidence_ids=c.sample_ids,
                    suggested_priority=_suggest_priority(c.count, 0),
                ))
        elif prev_count > 0 and c.count / prev_count >= surge_threshold:
            # 激增
            pct_increase = (c.count - prev_count) / prev_count * 100
            alerts.append(Alert(
                type=AlertType.SURGE,
                cluster_id=c.cluster_id,
                label=c.label,
                description=f"量级激增：从 {prev_count} 条增至 {c.count} 条，增幅 {pct_increase:.0f}%，超过阈值 {int((surge_threshold - 1) * 100)}%",
                evidence_ids=c.sample_ids,
                suggested_priority=_suggest_priority(c.count, prev_count),
            ))

    logger.info("Detected %d alerts (%d emerging, %d surge)",
                len(alerts),
                sum(1 for a in alerts if a.type == AlertType.EMERGING),
                sum(1 for a in alerts if a.type == AlertType.SURGE))
    return alerts


def _suggest_priority(count: int, prev_count: int) -> Priority:
    """根据簇大小和增幅确定建议优先级。

    - P0: 簇规模 >= 10 或 增幅 >= 100%
    - P1: 簇规模 >= 5 或 增幅 >= 50%
    - P2: 其他
    """
    if count >= 10 or (prev_count > 0 and count / prev_count >= 2.0):
        return Priority.P0
    elif count >= 5 or (prev_count > 0 and count / prev_count >= 1.5):
        return Priority.P1
    return Priority.P2
