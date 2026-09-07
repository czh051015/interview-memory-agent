"""docs/38 §4.3 门禁建议区③改进建议 —— runtime.guidance 收敛后测试。

覆盖：
  · guidance 单点懒加载：语境 = 该点门禁事实（官方写法/全部 kw/命中/缺失/材料出处）
    + 作答原文——不判因、不给材料全文（docs/38 §7 runtime 收敛）
  · gap/how/rewrite 单次 LLM 调用；LLM 失败 → 三者置空仍返回（不阻断）
  · guidance 不存在的 point_id → None（不调 LLM）；命中点也可点开
  · GATE_IMPROVE_PROMPT 红线（no_full_answer / 只针对单点）；旧四分支 DEMO 类 prompt 已删
  · 无 SCORE_ENGINE 引擎钉定（docs/38 D49 退役）——guidance 走 gate_score 单点，天然确定性
"""
from unittest.mock import patch

import src.mock as mi
from src.mock.prompts import EXPLAIN_PROMPT, GATE_IMPROVE_PROMPT
from src.mock.runtime import guidance
from src.shenlun.score import from_benchmark

REFS = [
    {"id": "c1", "point": "六尺巷·化解纠纷", "keywords": ["六尺巷"], "score": 3},
    {"id": "c2", "point": "河长制·治水", "keywords": ["河长", "碧水"], "score": 1},
    {"id": "c3", "point": "生态理念·象群", "keywords": ["象群"], "score": 4},
]
Q = "概括基层治理经验"
M = "材料：六尺巷化解邻里纠纷，河长制守护碧水，象群回归印证生态理念深入人心。"


def _suggestion():
    return {"gap": "作答中该点只写了河长，缺少碧水清流的落点",
            "how": "回到材料「河长制守护碧水」句，把治水成效落到碧水清流上",
            "rewrite": "落实河长制，守护碧水清流，让群众共享治水成效"}


class TestGuidanceImprove:
    def test_generate_gap_how_rewrite(self):
        """点开一个点 → ③ 建议三件套单次 LLM 调用；official 由规则层回传（D46）。"""
        points = from_benchmark(REFS)
        with patch.object(mi, "chat_json", return_value=_suggestion()) as llm:
            g = guidance(M, "六尺巷", points, "c2")
        assert g.point_id == "c2"
        assert g.point == "河长制·治水"
        # official = 锚句引文原文（D46：benchmark 无 source_snippet → 兜底锚句，非「材料第X段」包装）
        assert g.official and not g.official.startswith("材料第") and "河长" in g.official
        assert g.gap and g.how and g.rewrite
        assert llm.call_count == 1

    def test_user_prompt_carries_gate_facts_only(self):
        """语境行含 官方写法/关键词/命中/缺失/材料出处；不含材料全文（§7 输入面收紧）。"""
        with patch.object(mi, "chat_json", return_value=_suggestion()) as llm:
            guidance(M, "六尺巷", from_benchmark(REFS), "c2")
        up = llm.call_args.args[1]
        assert llm.call_args.args[0] == GATE_IMPROVE_PROMPT
        assert "## 官方写法" in up and "## 该点关键词" in up
        assert "## 作答中命中/缺失（全部缺失）" in up and "命中：无" in up
        assert "河长、碧水" in up                     # 全部关键词给全
        assert "## 材料出处" in up and "材料第" in up   # how 要结合出处
        assert "## 材料全文" not in up                # 不喂材料全文
        assert "## 用户作答" in up

    def test_hit_point_also_guidable(self):
        """命中点也可点开（语境行标 全部命中，建议核对官方写法）——guidance 不限漏点。"""
        with patch.object(mi, "chat_json", return_value=_suggestion()) as llm:
            g = guidance(M, "六尺巷化解了纠纷", from_benchmark(REFS), "c1")
        assert g.point_id == "c1"
        assert "全部命中" in llm.call_args.args[1]
        assert "缺失：无" in llm.call_args.args[1]

    def test_unknown_point_returns_none_no_llm(self):
        with patch.object(mi, "chat_json") as llm:
            g = guidance(M, "六尺巷", from_benchmark(REFS), "c9")
        assert g is None
        llm.assert_not_called()

    def test_llm_failure_returns_empty_fields(self):
        """LLM 挂了 → gap/how/rewrite 空串仍返回（② 在评分响应里，不重复回放，不阻断）。"""
        with patch.object(mi, "chat_json", side_effect=RuntimeError("network")):
            g = guidance(M, "六尺巷", from_benchmark(REFS), "c2")
        assert g is not None
        assert g.official              # 规则层回传不依赖 LLM
        assert g.gap == "" and g.how == "" and g.rewrite == ""

    def test_gate_facts_come_from_rule_not_llm(self):
        """命中/缺失事实由 gate_score 单点规则算（0 token）——不 patch LLM 也可验证。"""
        g = guidance(M, "六尺巷 河长 碧水", from_benchmark(REFS), "c2", question=Q)
        # 直接断言由规则层算的 official：source_snippet 空 → 材料锚句原文（D46）
        assert g.official and "河长制守护碧水" in g.official


class TestPrompts:
    def test_gate_improve_prompt_redline(self):
        """③ prompt：gap/how/rewrite 三字段，候选措辞 + no_full_answer + 只针对单点。"""
        assert "no_full_answer" in GATE_IMPROVE_PROMPT
        assert '"gap"' in GATE_IMPROVE_PROMPT and '"how"' in GATE_IMPROVE_PROMPT
        assert '"rewrite"' in GATE_IMPROVE_PROMPT
        assert "供参考" in GATE_IMPROVE_PROMPT
        assert "只针对这一个采分点" in GATE_IMPROVE_PROMPT

    def test_explain_prompt_kept(self):
        """L5 讲解 prompt 保留（explain_point 非门禁链路仍用）。"""
        assert "rephrase" in EXPLAIN_PROMPT and "distinguish" in EXPLAIN_PROMPT

    def test_demo_branch_prompts_removed(self):
        """docs/35 四分支判因 prompt 已删（D47：判因由评分响应带回，不再路由）。"""
        import src.mock.prompts as p
        for name in ("DEMO_PROMPT", "DEMO_OFF_DIRECTION_PROMPT",
                     "DEMO_NO_SOURCE_PROMPT", "QUALITY_DEMO_PROMPT", "CAUSE_PROMPT"):
            assert not hasattr(p, name)
