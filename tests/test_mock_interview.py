"""面试官状态机核心逻辑测试（mock LLM）。"""

import pytest
from unittest.mock import patch

import run_mock_interview as mi
from src.cleaner.schema import KnowledgeItem, ItemStatus


class TestInterviewOne:
    """单题面试的追问循环。"""

    @patch.object(mi, "get_expected_points", return_value=["点1", "点2"])
    @patch.object(mi, "judge_followup")
    def test_answer_well_one_round(self, mock_judge, mock_points):
        """答到位：1 轮结束，performance=pass，只判断一次。"""
        mock_judge.side_effect = lambda q, p, a, r: {
            "need_followup": False, "followup_question": "", "reason": "答到位", "performance": "pass",
        }
        answers = iter(["完整回答"])
        performance, text, transcript = mi.interview_one("题", lambda r: next(answers))
        assert performance == "pass"
        assert mock_judge.call_count == 1

    @patch.object(mi, "get_expected_points", return_value=["点1"])
    @patch.object(mi, "judge_followup")
    def test_followup_until_max_rounds(self, mock_judge, mock_points):
        """一直追问：追满 3 轮（首答+2 追问）后强制结束。"""
        mock_judge.side_effect = lambda q, p, a, r: {
            "need_followup": True, "followup_question": "追问", "reason": "没答到点", "performance": "partial",
        }
        answers = iter(["答1", "答2", "答3"])
        performance, text, transcript = mi.interview_one("题", lambda r: next(answers))
        assert performance == "partial"
        assert mock_judge.call_count == 3  # 硬约束：不会无限追问

    @patch.object(mi, "get_expected_points", return_value=["点1"])
    @patch.object(mi, "judge_followup")
    def test_empty_answer_marks_fail(self, mock_judge, mock_points):
        """空回答：视为不会，直接 fail，不调 judge。"""
        performance, text, transcript = mi.interview_one("题", lambda r: "")
        assert performance == "fail"
        mock_judge.assert_not_called()

    @patch.object(mi, "get_expected_points", return_value=["点1"])
    @patch.object(mi, "judge_followup")
    def test_transcript_records_each_round(self, mock_judge, mock_points):
        """transcript 逐轮记录回答/判断理由/追问，供复盘报告用。"""
        mock_judge.side_effect = lambda q, p, a, r: {
            "need_followup": True, "followup_question": f"追问{r}", "reason": f"理由{r}", "performance": "partial",
        }
        answers = iter(["答1", "答2", "答3"])
        performance, text, transcript = mi.interview_one("题", lambda r: next(answers))
        assert len(transcript) == 3
        assert transcript[0]["round"] == 1
        assert transcript[0]["answer"] == "答1"
        assert transcript[0]["reason"] == "理由1"
        assert transcript[0]["followup_question"] == "追问1"


class TestRecordResult:
    """写回逻辑。"""

    def test_pass_boost(self):
        item = KnowledgeItem(id="ki_1", question="Q", status=ItemStatus.FAIL, mastery_score=0.3)
        updated = mi.record_result(item, "pass", [])
        assert updated.mastery_score == pytest.approx(0.45)  # 0.3 × 1.5

    def test_fail_cap(self):
        item = KnowledgeItem(id="ki_1", question="Q", status=ItemStatus.PARTIAL, mastery_score=0.6)
        updated = mi.record_result(item, "fail", [])
        assert updated.mastery_score == pytest.approx(0.5)  # min(0.6, 0.5)

    def test_partial_keep_mastery(self):
        """partial：mastery 保持不动，但重置遗忘时钟（review_count+1、last_reviewed_at 更新）。"""
        item = KnowledgeItem(id="ki_1", question="Q", status=ItemStatus.PARTIAL, mastery_score=0.6)
        updated = mi.record_result(item, "partial", [])
        assert updated.mastery_score == pytest.approx(0.6)  # 保持
        assert updated.review_count == 1
        assert updated.last_reviewed_at is not None

    def test_behavior_merge(self):
        item = KnowledgeItem(id="ki_1", question="Q", status=ItemStatus.FAIL,
                             mastery_score=0.3, behavior_tags=["旧标签"])
        updated = mi.record_result(item, "fail", ["表达绕弯", "旧标签"])
        assert set(updated.behavior_tags) == {"旧标签", "表达绕弯"}


class TestGetExpectedPoints:
    @patch.object(mi, "chat_json")
    def test_uses_answer_when_present(self, mock_chat_json):
        """有参考答案就直接用，不调 LLM 现编。"""
        points = mi.get_expected_points("题", "参考答案内容")
        assert points == ["参考答案内容"]
        mock_chat_json.assert_not_called()

    @patch.object(mi, "chat_json", return_value={"points": ["点1", "点2"]})
    def test_llm_when_no_answer(self, mock_chat_json):
        points = mi.get_expected_points("题", "")
        assert points == ["点1", "点2"]


class TestReviewReport:
    @patch.object(
        mi, "chat_json",
        return_value={"overall": "整体评价", "items": [], "common": "共性建议"},
    )
    def test_generate_review_report(self, mock_chat_json):
        records = [{
            "question": "题", "performance": "fail", "answer": "答",
            "transcript": [{
                "round": 1, "answer": "答", "reason": "没答到点",
                "followup_question": "追问", "performance": "fail",
            }],
        }]
        report = mi.generate_review_report(records, ["回避问题"])
        assert report["overall"] == "整体评价"
        assert report["common"] == "共性建议"

    @patch.object(mi, "chat_json", side_effect=RuntimeError("no llm"))
    def test_generate_review_report_fails_gracefully(self, mock_chat_json):
        report = mi.generate_review_report([], [])
        assert report is None

