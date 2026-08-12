"""Scout Agent 单元测试。"""

import numpy as np
import pytest

from src.models import ClusterInfo
from src.scout.alerting import detect_shifts, _suggest_priority
from src.models import AlertType, Priority


class TestAlerting:
    """偏移检测测试。"""

    def test_first_run_all_emerging(self):
        clusters = [
            ClusterInfo(cluster_id="c1", label="RAG检索", label_confidence=0.9, count=5),
            ClusterInfo(cluster_id="c2", label="Agent框架", label_confidence=0.85, count=3),
        ]
        alerts = detect_shifts(clusters, previous_clusters=None)

        assert len(alerts) == 2
        assert all(a.type == AlertType.EMERGING for a in alerts)

    def test_first_run_below_min_count(self):
        clusters = [
            ClusterInfo(cluster_id="c1", label="小主题", label_confidence=0.5, count=2),
        ]
        alerts = detect_shifts(clusters, previous_clusters=None, emerging_min_count=3)

        assert len(alerts) == 0  # count=2 < emerging_min_count=3

    def test_surge_detection(self):
        current = [
            ClusterInfo(cluster_id="c1", label="RAG检索", label_confidence=0.9, count=20),
        ]
        previous = [
            ClusterInfo(cluster_id="c1", label="RAG检索", label_confidence=0.9, count=10),
        ]
        alerts = detect_shifts(current, previous, surge_threshold=1.2)

        assert len(alerts) == 1
        assert alerts[0].type == AlertType.SURGE

    def test_no_alert_for_stable(self):
        current = [
            ClusterInfo(cluster_id="c1", label="RAG检索", label_confidence=0.9, count=11),
        ]
        previous = [
            ClusterInfo(cluster_id="c1", label="RAG检索", label_confidence=0.9, count=10),
        ]
        alerts = detect_shifts(current, previous, surge_threshold=1.2)

        # 11/10 = 1.10 < 1.20, 不触发
        assert len(alerts) == 0

    def test_mix_emerging_and_surge(self):
        current = [
            ClusterInfo(cluster_id="c1", label="RAG检索", label_confidence=0.9, count=20),
            ClusterInfo(cluster_id="c2", label="新主题", label_confidence=0.7, count=5),
        ]
        previous = [
            ClusterInfo(cluster_id="c1", label="RAG检索", label_confidence=0.9, count=10),
        ]
        alerts = detect_shifts(current, previous, surge_threshold=1.2)

        assert len(alerts) == 2
        types = {a.type for a in alerts}
        assert AlertType.SURGE in types
        assert AlertType.EMERGING in types


class TestPriority:
    """优先级判定测试。"""

    def test_p0_large_cluster(self):
        assert _suggest_priority(10, 0) == Priority.P0

    def test_p0_high_growth(self):
        assert _suggest_priority(5, 2) == Priority.P0  # 2.5x growth

    def test_p1_medium_cluster(self):
        assert _suggest_priority(5, 0) == Priority.P1

    def test_p2_small_cluster(self):
        assert _suggest_priority(3, 0) == Priority.P2
