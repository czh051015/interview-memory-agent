"""docs/26 LLM-as-a-Judge 引擎单测 —— mock chat_json，不调真实 LLM。

conftest 全局把 embed_zh mock 成 None（降级），judge_score 的兜底路径（LLM 挂 →
回 score_answer）在这环境下 = 纯 kw 结果，确定性可断言。
"""
from unittest.mock import patch

from src.shenlun.judge_llm import judge_score
from src.shenlun import score as score_mod
from src.shenlun.score import Point

PTS = [
    Point(id="c1", point="推进执法开放", keywords=["开放日"], score=2, type="对策"),
    Point(id="c2", point="强化执法队伍", keywords=["导师帮带"], score=2, type="对策"),
    Point(id="c3", point="增强执法效力", keywords=["迅速响应"], score=1, type="对策"),
]


def _verdicts(vals):
    return {"verdicts": vals}


def test_judge_hit_miss_assembly():
    """正常判定：hit 带证据（matched_by=llm），miss 带 cause，材料证据透传；hit 也可保留诊断型 cause。"""
    with patch("src.shenlun.judge_llm.chat_json", return_value=_verdicts([
        {"point_id": "c1", "verdict": "hit", "cause": "套话无具体性",
         "matched_text": "举办开放日邀请群众参观", "material_source": "材料提到开放日"},
        {"point_id": "c2", "verdict": "miss", "cause": "写模糊",
         "matched_text": "", "material_source": ""},
        {"point_id": "c3", "verdict": "hit", "cause": "",
         "matched_text": "接到举报立即出动", "material_source": ""},
    ])):
        sr, warnings = judge_score("作答文本", PTS, materials="材料文本", question="题干")
    assert warnings == []
    assert [h.id for h in sr.hit_points] == ["c1", "c3"]
    h = sr.hit_points[0]
    assert h.matched_by == "llm"
    assert h.matched_text == "举办开放日邀请群众参观"
    assert h.material_source == "材料提到开放日"
    assert h.quality_cause == "套话无具体性"
    m = sr.miss_points[0]
    assert m.id == "c2"
    assert m.miss_cause == "写模糊"
    assert m.material_source is None  # 空证据 → None（未结合材料）


def test_judge_llm_down_falls_back_to_kw_engine():
    """LLM 挂 → 降级 score_answer（纯 kw），不崩，warnings 说明。"""
    with patch("src.shenlun.judge_llm.chat_json", side_effect=RuntimeError("api down")):
        sr, warnings = judge_score("开放日 导师帮带", PTS, materials="")
    assert [h.id for h in sr.hit_points] == ["c1", "c2"]
    assert sr.hit_points[0].matched_by == "kw"  # 兜底引擎的标记
    assert warnings and "降级" in warnings[0]


def test_judge_missing_point_treated_as_miss():
    """LLM 漏判某点 → 按 miss 处理 + warnings。"""
    with patch("src.shenlun.judge_llm.chat_json", return_value=_verdicts([
        {"point_id": "c1", "verdict": "hit", "cause": "", "matched_text": "x", "material_source": ""},
    ])):
        sr, warnings = judge_score("作答", PTS)
    assert [h.id for h in sr.hit_points] == ["c1"]
    assert [m.id for m in sr.miss_points] == ["c2", "c3"]
    assert warnings and "未判定 c2" in warnings[0]
    assert sr.miss_points[0].miss_cause == "未判定"


def test_judge_bad_verdict_defaults_to_miss():
    """verdict 非 hit（缺/空/乱值）→ miss，cause 缺省"没写"。"""
    with patch("src.shenlun.judge_llm.chat_json", return_value=_verdicts([
        {"point_id": "c1", "verdict": "", "cause": "", "matched_text": "", "material_source": ""},
    ])):
        sr, _ = judge_score("作答", PTS)
    assert sr.hit_ids == []
    assert sr.miss_ids == ["c1", "c2", "c3"]
    assert sr.miss_points[0].miss_cause == "没写"


def test_judge_pydantic_rejects_invalid_schema_and_falls_back_to_miss():
    """schema 语义错误（枚举/类型）被 pydantic 拒绝，按 miss 处理并保留 warnings。"""
    with patch("src.shenlun.judge_llm.chat_json", return_value=_verdicts([
        {"point_id": "c1", "verdict": "yes", "cause": "没写", "matched_text": "x", "material_source": ""},
        {"point_id": "c2", "verdict": "miss", "cause": "没写", "matched_text": "", "material_source": ""},
    ])):
        sr, warnings = judge_score("作答", PTS)
    assert sr.hit_ids == []
    assert sr.miss_ids == ["c1", "c2", "c3"]
    assert any("pydantic" in w.lower() or "校验" in w for w in warnings)
    assert sr.miss_points[0].miss_cause == "没写"


def test_judge_supports_new_nosource_causes():
    """28 号修正：新 cause 枚举应接受 '套话无具体性' 和 '答非所问'，不再误判为 schema 错误。"""
    with patch("src.shenlun.judge_llm.chat_json", return_value=_verdicts([
        {"point_id": "c1", "verdict": "miss", "cause": "套话无具体性", "matched_text": "", "material_source": ""},
        {"point_id": "c2", "verdict": "miss", "cause": "答非所问", "matched_text": "", "material_source": ""},
    ])):
        sr, warnings = judge_score("作答", PTS)
    assert sr.hit_ids == []
    assert [m.id for m in sr.miss_points[:2]] == ["c1", "c2"]
    assert [m.miss_cause for m in sr.miss_points[:2]] == ["套话无具体性", "答非所问"]
    assert not any("pydantic" in w.lower() or "校验" in w.lower() for w in warnings)


def test_score_answer_defaults_to_llm_engine_and_fallback_is_safe():
    """doc 31：默认走 B（LLM），LLM 失败时只回 kw 纯分支，不递归。"""
    original = score_mod.SCORE_ENGINE
    try:
        score_mod.SCORE_ENGINE = "llm"
        with patch("src.shenlun.judge_llm.chat_json", return_value={"verdicts": [{
            "point_id": "c1", "verdict": "hit", "cause": "",
            "matched_text": "开放日", "material_source": "材料提到开放日",
        }]}):
            sr = score_mod.score_answer("开放日", [PTS[0]], materials="材料提到开放日")
            assert [h.id for h in sr.hit_points] == ["c1"]
            assert sr.hit_points[0].matched_by == "llm"

        with patch("src.shenlun.judge_llm.chat_json", side_effect=RuntimeError("api down")):
            sr, warnings = judge_score("开放日", [PTS[0]], materials="材料提到开放日")
            assert [h.id for h in sr.hit_points] == ["c1"]
            assert sr.hit_points[0].matched_by == "kw"
            assert warnings and "降级" in warnings[0]
    finally:
        score_mod.SCORE_ENGINE = original


def test_judge_prompt_build_truncates():
    """超长材料/作答被截断（防爆 token），点数上限保护。"""
    from src.shenlun.judge_llm import _MATERIAL_MAX, _ANSWER_MAX, _build_user
    many = [Point(id=f"c{i}", point="点", keywords=["k"], score=1) for i in range(30)]
    prompt = _build_user("题干", "材" * 10000, "答" * 5000, many)
    assert f"## 材料（给定资料）\n{'材' * _MATERIAL_MAX}" in prompt
    assert f"## 作答\n{'答' * _ANSWER_MAX}" in prompt
    assert prompt.count("- c") == 20  # 点数上限
