"""docs/22 §3.4/§4：示证运行态测试 —— guidance 按需示证 + pick_leading_point 推 1 个。

覆盖：
  · guidance 单点生成 L2(DEMO) + L4(CAUSE)，L3 材料锚定来自 score（与 L1 同源）
  · guidance 不存在的 point_id → None（不调 LLM）
  · guidance LLM 失败 → demo/cause 置空，L3 仍可展示（不阻断）
  · pick_leading_point 无档案 → miss 中 score 最大者
  · pick_leading_point 有红档（漏 ≥2 次）→ 红档点优先（即使 score 更小）；非本题红档不干扰
  · DEMO/CAUSE prompt 红线文案在位
"""

import pytest
from unittest.mock import patch

import src.mock as mi
from src.shenlun.score import from_benchmark
from src.mock.runtime import guidance, pick_leading_point
from src.shenlun import reflow

REFS = [
    {"id": "c1", "point": "六尺巷·化解纠纷", "keywords": ["六尺巷"], "score": 3},
    {"id": "c2", "point": "河长制·治水", "keywords": ["河长"], "score": 1},
    {"id": "c3", "point": "生态理念·象群", "keywords": ["象群"], "score": 4},
]
Q = "概括基层治理经验"
M = "材料：六尺巷化解邻里纠纷，河长制守护碧水，象群回归印证生态理念深入人心。"


class TestGuidance:
    def test_single_point_l2_l3_l4(self):
        """点开一个漏点 → L3 材料锚定 + L2 示范 + L4 错因（LLM mock）。"""
        points = from_benchmark(REFS)
        with patch.object(mi, "chat_json", side_effect=[
            {"demo": "写到治水时可表述为：落实河长制，守护碧水清流。"},
            {"cause_type": "完全没提", "cause": "作答只写了纠纷调解。", "fix": "回材料抓河长制。"},
        ]) as llm:
            g = guidance(M, "六尺巷", points, "c2")
        assert g.point_id == "c2"
        assert g.point == "河长制·治水"
        assert g.material_source and "河长制守护碧水" in g.material_source  # L3 锚定来自 score
        assert "河长制" in g.demo
        assert g.cause_type == "完全没提"
        assert llm.call_count == 2

    def test_unknown_point_returns_none_no_llm(self):
        with patch.object(mi, "chat_json") as llm:
            g = guidance(M, "六尺巷", from_benchmark(REFS), "c9")
        assert g is None
        assert llm.call_count == 0

    def test_llm_failure_keeps_l3(self):
        """LLM 挂了 → demo/cause 空，L3 材料锚定仍返回（示证不阻断）。"""
        with patch.object(mi, "chat_json", side_effect=RuntimeError("network")):
            g = guidance(M, "六尺巷", from_benchmark(REFS), "c2")
        assert g is not None
        assert g.material_source and "河长制" in g.material_source
        assert g.demo == ""
        assert g.cause == "" and g.fix == ""

    def test_hit_point_also_guidable(self):
        """命中点也可点开示证（L3 锚定 + L2/L4），guidance 不限制只能引导漏点。"""
        with patch.object(mi, "chat_json", return_value={"demo": "示范"}):
            g = guidance(M, "六尺巷 河长 象群", from_benchmark(REFS), "c1")
        assert g.point_id == "c1"
        assert g.material_source and "六尺巷" in g.material_source


class TestPickLeading:
    def test_no_archive_max_score(self):
        """无错题本历史（首 session）→ 取 score 最大者（Q9a 兜底）。"""
        pts = from_benchmark(REFS)
        from src.shenlun.score import score_answer
        sr = score_answer("六尺巷", pts, materials=M)
        lead = pick_leading_point(sr.miss_points, "q1")
        assert lead.id == "c3"  # score 4 > c2 的 1

    def test_empty_returns_none(self):
        assert pick_leading_point([], "q1") is None

    def test_red_tier_archive_wins(self, tmp_path):
        """有错题本历史：红档（漏 ≥2 次）优先——即使 score 比别的漏点小。"""
        old_path = reflow.DB_PATH
        reflow.DB_PATH = tmp_path / "test_guidance.db"
        try:
            # 造档案：c2（score 1）漏 2 次 → 红档；c3（score 4）漏 1 次 → 黄档
            for _ in range(2):
                reflow.reflow_answer("q1", "归纳概括", "不相关", REFS)
            reflow.reflow_answer("q2", "归纳概括", "六尺巷 河长", REFS)  # c3 miss ×1（另一题）
            from src.shenlun.score import score_answer
            sr = score_answer("六尺巷", from_benchmark(REFS), materials=M)
            lead = pick_leading_point(sr.miss_points, "q1")
            assert lead.id == "c2"  # 红档（q1:c2）优先于 score 最大的 c3
        finally:
            reflow.DB_PATH = old_path

    def test_other_question_red_ignored(self, tmp_path):
        """别题的红档不干扰本题推 1（红档匹配按 question_id:point_id）。"""
        old_path = reflow.DB_PATH
        reflow.DB_PATH = tmp_path / "test_guidance2.db"
        try:
            reflow.reflow_answer("q9", "归纳概括", "不相关", REFS)  # q9 全漏 1 次 → 非红档
            reflow.reflow_answer("q9", "归纳概括", "不相关", REFS)  # q9 全漏 2 次 → q9 全红档
            from src.shenlun.score import score_answer
            sr = score_answer("六尺巷", from_benchmark(REFS), materials=M)
            lead = pick_leading_point(sr.miss_points, "q1")
            assert lead.id == "c3"  # q1 无红档 → 回落 score 最大
        finally:
            reflow.DB_PATH = old_path


class TestPrompts:
    def test_demo_prompt_redline(self):
        """L2 prompt 红线：只给骨架/关键词，不代写完整作答段落（no_full_answer）。"""
        from src.mock.prompts import DEMO_PROMPT
        assert "no_full_answer" in DEMO_PROMPT
        assert "示范" in DEMO_PROMPT
        assert "60 字" in DEMO_PROMPT

    def test_cause_prompt_redline(self):
        """L4 prompt：错因三类 + 具体改法，同样禁代写。"""
        from src.mock.prompts import CAUSE_PROMPT
        assert "完全没提" in CAUSE_PROMPT and "写偏" in CAUSE_PROMPT and "太模糊" in CAUSE_PROMPT
        assert "no_full_answer" in CAUSE_PROMPT

    def test_old_approach_prompt_gone(self):
        """旧苏格拉底逼近 prompt 已删除（docs/22 §3.3）。"""
        import src.mock.prompts as p
        assert not hasattr(p, "_APPROACH_PROMPT")
