"""docs/17 §4.3：ReAct 决策接入（毕业考候选入 prompt + action 字段 + 规则回退）测试。"""

from datetime import datetime, timedelta
from unittest.mock import patch

from src.shenlun.react import ReactOutput, decide, search_questions, _rule_fallback
from src.shenlun.profile import WeakPoint
from src.shenlun.reflow import STATE_ACTIVE

# 题库候选（与真实题单同形状）
BANK = [
    {"id": "jiangsu_2023_a_1", "authority": "training", "province": "江苏", "year": 2023,
     "type": "归纳概括", "question": "用一段话归纳概括……"},
    {"id": "henan_2025_city_1", "authority": "training", "province": "河南", "year": 2025,
     "type": "归纳概括", "question": "概括……"},
    {"id": "henan_2025_city_2", "authority": "training", "province": "河南", "year": 2025,
     "type": "综合分析", "question": "谈谈对……的理解"},
]


def make_wp(label="设施互通", qtype="归纳概括", miss=2, question_id="jiangsu_2023_a_1",
            consec=0, last_hit_days_ago=0):
    return WeakPoint(
        point_key=f"{question_id}:c1", label=label, qtype=qtype, question_id=question_id,
        miss_count=miss, hit_count=3, last_miss_at=None, state=STATE_ACTIVE,
        consecutive_hits=consec, tier="red" if miss >= 2 else "yellow",
        last_practiced_at=(datetime.utcnow() - timedelta(days=1)).isoformat(),
        last_hit_at=(datetime.utcnow() - timedelta(days=last_hit_days_ago)).isoformat(),
    )


class TestSearchQuestions:
    @patch("src.shenlun.react.list_questions", return_value=BANK)
    def test_prefers_red_point_types(self, _):
        wps = [make_wp(qtype="综合分析", miss=3)]
        cands = search_questions(wps, limit=8)
        assert cands and all(q["type"] == "综合分析" for q in cands)

    @patch("src.shenlun.react.list_questions", return_value=BANK)
    def test_falls_back_to_full_bank(self, _):
        cands = search_questions([], limit=8)
        assert len(cands) == len(BANK)


class TestRuleFallback:
    def test_fallback_picks_top_miss_point_question(self):
        out = _rule_fallback([make_wp(label="设施互通", miss=5)], BANK)
        assert out.fallback is True
        assert out.plan and out.plan[0]["question_id"] == "jiangsu_2023_a_1"
        assert "设施互通" in out.focus

    def test_fallback_empty_profile(self):
        out = _rule_fallback([], BANK)
        assert out.focus == "暂无薄弱点档案"
        assert out.plan == []


class TestDecide:
    def test_action_parsed_from_llm(self):
        """LLM 决策输出带 action；毕业考候选进 prompt；无效 id 被过滤。"""
        llm_out = {
            "focus": "今天安排毕业考验证设施互通",
            "action": "graduation_check",
            "plan": [{"question_id": "jiangsu_2023_a_1", "why": "验证设施互通"}],
            "advice": "按材料要点逐条核对",
        }
        captured = {}

        def fake_chat_json(system_prompt, user_prompt, **kw):
            captured["prompt"] = user_prompt
            return llm_out

        with patch("src.shenlun.react.chat_json", fake_chat_json), \
             patch("src.shenlun.react.list_questions", return_value=BANK), \
             patch("src.shenlun.profile.read_weak_points",
                   return_value=[make_wp(consec=3, last_hit_days_ago=8)]), \
             patch("src.shenlun.profile.graduation_candidates",
                   return_value=[make_wp(consec=3, last_hit_days_ago=8)]):
            out = decide()
        assert out.action == "graduation_check"
        assert out.fallback is False
        assert out.plan[0]["question_id"] == "jiangsu_2023_a_1"
        # 毕业考候选已进决策输入
        assert "## 毕业考候选" in captured["prompt"]
        assert "设施互通" in captured["prompt"]

    def test_invalid_action_forced_to_practice(self):
        llm_out = {"focus": "f", "action": "bogus", "plan": [], "advice": "a"}
        with patch("src.shenlun.react.chat_json", return_value=llm_out), \
             patch("src.shenlun.react.list_questions", return_value=BANK), \
             patch("src.shenlun.profile.read_weak_points", return_value=[]), \
             patch("src.shenlun.profile.graduation_candidates", return_value=[]):
            out = decide()
        assert out.action == "practice"

    def test_llm_failure_falls_back_to_rules(self):
        """LLM 挂了 → 规则回退不崩，产出仍可用。"""
        with patch("src.shenlun.react.chat_json", side_effect=Exception("API down")), \
             patch("src.shenlun.react.list_questions", return_value=BANK), \
             patch("src.shenlun.profile.read_weak_points",
                   return_value=[make_wp(label="设施互通", miss=4)]), \
             patch("src.shenlun.profile.graduation_candidates", return_value=[]):
            out = decide()
        assert out.fallback is True
        assert out.focus
        assert out.plan  # 规则版也有计划
        assert out.action == "practice"
