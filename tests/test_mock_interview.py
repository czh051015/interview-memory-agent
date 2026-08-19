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
        mock_judge.side_effect = lambda q, p, a, r, **kw: {
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
        mock_judge.side_effect = lambda q, p, a, r, **kw: {
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
        mock_judge.side_effect = lambda q, p, a, r, **kw: {
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


class TestCrossOnPartial:
    """边界判定触发第二判官复核（cross_on_partial）。"""

    @patch.object(mi, "chat_json")
    def test_partial_triggers_cross_and_adopts(self, mock_chat_json):
        """主判 partial → 第二判官判 pass → 采纳复核结果并标注。"""
        mock_chat_json.side_effect = [
            {"points": ["p"], "misses": [], "suggested": "partial", "reason": "主判含糊"},
            {"points": ["p"], "misses": [], "suggested": "pass", "reason": "复核认为到位"},
        ]
        r = mi.judge_single_round("题", "答", cross_on_partial=True)
        assert r["suggested"] == "pass"
        assert r["cross_reviewed"] is True
        assert "第二判官复核" in r["reason"]
        assert mock_chat_json.call_count == 2
        # 第二次调用走了 cross 通道
        assert mock_chat_json.call_args[1]["cross"] is True

    @patch.object(mi, "chat_json")
    def test_partial_cross_still_partial_keeps(self, mock_chat_json):
        """第二判官也判 partial → 保留主判结果，不标注。"""
        mock_chat_json.side_effect = [
            {"points": ["p"], "misses": [], "suggested": "partial", "reason": "主判含糊"},
            {"points": ["p"], "misses": [], "suggested": "partial", "reason": "复核也含糊"},
        ]
        r = mi.judge_single_round("题", "答", cross_on_partial=True)
        assert r["suggested"] == "partial"
        assert "cross_reviewed" not in r
        assert mock_chat_json.call_count == 2

    @patch.object(mi, "chat_json")
    def test_non_partial_no_cross(self, mock_chat_json):
        """pass/fail 明确判定 → 不触发复核，只调一次。"""
        mock_chat_json.return_value = {"points": ["p"], "misses": [], "suggested": "pass", "reason": "清楚"}
        r = mi.judge_single_round("题", "答", cross_on_partial=True)
        assert r["suggested"] == "pass"
        assert mock_chat_json.call_count == 1

    @patch.object(mi, "chat_json")
    def test_followup_cross_on_partial(self, mock_chat_json):
        """追问判断同样支持：partial → 复核 fail → 采纳。"""
        mock_chat_json.side_effect = [
            {"need_followup": True, "followup_question": "追", "reason": "含糊", "performance": "partial"},
            {"need_followup": False, "followup_question": "", "reason": "复核判定不会", "performance": "fail"},
        ]
        r = mi.judge_followup("题", ["p"], "答", 1, cross_on_partial=True)
        assert r["performance"] == "fail"
        assert r["cross_reviewed"] is True


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


class TestSessionContext:
    """session 级上下文（短期记忆最小版）：已问题目注入追问判断。"""

    @patch.object(mi, "chat_json")
    def test_asked_before_injected_into_prompt(self, mock_chat_json):
        """已问题目列表应出现在 judge_followup 的 user prompt 里。"""
        mock_chat_json.return_value = {
            "need_followup": False, "followup_question": "", "reason": "ok", "performance": "pass",
        }
        mi.judge_followup("新题", ["点1"], "答", 1, asked_before=["旧题A", "旧题B"])
        user_prompt = mock_chat_json.call_args[0][1]
        assert "旧题A" in user_prompt
        assert "旧题B" in user_prompt
        assert "本场已问过的题目" in user_prompt

    @patch.object(mi, "chat_json")
    def test_no_asked_before_clean_prompt(self, mock_chat_json):
        """无历史时不注入上下文段。"""
        mock_chat_json.return_value = {
            "need_followup": False, "followup_question": "", "reason": "ok", "performance": "pass",
        }
        mi.judge_followup("题", ["点1"], "答", 1)
        user_prompt = mock_chat_json.call_args[0][1]
        assert "本场已问过的题目" not in user_prompt

    @patch.object(mi, "get_expected_points", return_value=["点1"])
    @patch.object(mi, "judge_followup")
    def test_interview_one_passes_history(self, mock_judge, mock_points):
        """interview_one 应把 asked_before 透传给 judge_followup。"""
        mock_judge.return_value = {
            "need_followup": False, "followup_question": "", "reason": "ok", "performance": "pass",
        }
        answers = iter(["答"])
        mi.interview_one("题", lambda r: next(answers), asked_before=["历史题"])
        assert mock_judge.call_args[1]["asked_before"] == ["历史题"]


