"""Evaluator Agent 单元测试。"""

import pytest

from src.models import Alert, AlertType, Priority
from src.evaluator.pipeline import _clamp_score, _compute_confidence


class TestScoring:
    """评分工具函数测试。"""

    def test_clamp_score_in_range(self):
        assert _clamp_score(5) == 5
        assert _clamp_score(1) == 1
        assert _clamp_score(10) == 10

    def test_clamp_score_below_min(self):
        assert _clamp_score(0) == 1
        assert _clamp_score(-5) == 1

    def test_clamp_score_above_max(self):
        assert _clamp_score(11) == 10
        assert _clamp_score(100) == 10

    def test_compute_confidence_high(self):
        assert _compute_confidence(9, 9) == "高"
        assert _compute_confidence(8, 10) == "高"

    def test_compute_confidence_medium(self):
        assert _compute_confidence(7, 5) == "中"
        assert _compute_confidence(5, 5) == "中"

    def test_compute_confidence_low(self):
        assert _compute_confidence(3, 4) == "低"
        assert _compute_confidence(1, 1) == "低"


class TestFallback:
    """降级结果测试。"""

    def test_fallback_result_structure(self):
        from src.evaluator.pipeline import _fallback_result

        alert = Alert(
            type=AlertType.EMERGING,
            cluster_id="c_test",
            label="测试主题",
            description="一个测试假设",
            evidence_ids=["clean_001"],
        )

        result = _fallback_result("eval_fallback", alert, "测试错误")

        assert result.evaluation_id == "eval_fallback"
        assert result.hypothesis_alert_id == "c_test"
        assert result.coverage.score == 5  # 降级默认值
        assert result.falsifiability.score == 5
        assert "降级" in result.coverage.strengths[0]
        assert result.overall_confidence == "中"
