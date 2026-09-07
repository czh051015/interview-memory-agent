"""docs/38 §4.2 灰色带疑似标注引擎单测 —— judge_suspect，mock chat_json 不调真实 LLM。

（docs/26 judge_score 全量套件已随退役删除，见 38 D45/D49。）

安全方向（D45，每条都断言）：LLM 挂 / 输出结构坏 / 漏标某点 → 一律按放行
（suspect=None）处理，灰带降级为「绿·语义」；绝不让解析失败误伤成疑似。
结构约束（§4.2）：输出 schema 无任何证据字段（matched_text/material_source 类槽位
不存在），命中证据全部由规则层 gate_score 生成。
"""
import json
from unittest.mock import patch

from src.shenlun.judge_llm import (
    SuspectRow,
    _ANSWER_MAX,
    _POINTS_MAX,
    _SUSPECT_SYSTEM,
    _build_user,
    judge_suspect,
)
from src.shenlun.score import GateVerdict


def _gray(pid="c8", point_name="民生提质", keywords=("就医", "消费", "就业", "幸福感"),
          matched=("就业", "幸福感")):
    return GateVerdict(
        point_id=pid, point_name=point_name, score=1, point_type="影响",
        keywords=list(keywords), status="gray",
        matched=list(matched), missing=[k for k in keywords if k not in matched],
        evidence="作答句：增强了群众的获得感幸福感", anchor="材料第1段：'…'",
        official="官方原句：优化就业服务、方便群众就医消费…")


def _rows(rows):
    return {"verdicts": rows}


def _call(gray, rows=None, side_effect=None):
    kw = {}
    if rows is not None:
        kw["return_value"] = rows
    if side_effect is not None:
        kw["side_effect"] = side_effect
    with patch("src.shenlun.judge_llm.chat_json", **kw) as llm:
        return judge_suspect(gray, "作答全文：…"), llm


# ── 输出 schema 无证据字段（docs/36 顶包在结构上不存在）──────────────

def test_suspect_schema_has_no_evidence_fields():
    """SuspectRow 只含 point_id/point_name/suspect —— 没有可放伪造句的证据槽位。"""
    assert set(SuspectRow.model_fields) == {"point_id", "point_name", "suspect"}


def test_system_prompt_markers():
    """§4.2 prompt 照抄：只标疑似不判漏/错；无证据要求；suspect 三选一。"""
    assert "存疑标注员" in _SUSPECT_SYSTEM
    assert "suspect" in _SUSPECT_SYSTEM
    assert "你不需要给\"证据句\"" in _SUSPECT_SYSTEM
    for label in ("疑似宽泛", "疑似方向偏离", "疑似表述不清"):
        assert label in _SUSPECT_SYSTEM


def test_build_user_no_material_full_text():
    """灰带点消息：含 官方写法/关键词/命中，但不含材料全文与证据（§4.2 输入面）。"""
    up = _build_user([_gray("c8"), _gray("c5")], "作答正文")
    assert "官方写法：官方原句" in up
    assert "关键词：就医、消费、就业、幸福感" in up
    assert "作答中命中：就业、幸福感" in up
    assert "## 考生作答\n作答正文" in up
    assert "材料全文" not in up  # LLM 无材料可借 → 顶包输入面不存在


def test_build_user_truncates_long_answer():
    up = _build_user([_gray()], "答" * 5000)
    assert "答" * _ANSWER_MAX in up
    assert "答" * (_ANSWER_MAX + 1) not in up


def test_build_user_caps_gray_points():
    many = [_gray(pid=f"c{i}") for i in range(20)]
    up = _build_user(many, "答")
    assert up.count("- c") == _POINTS_MAX  # 一次调用保护上限（§10 注意2 反逐点调）


# ── 正常标注 ────────────────────────────────────────────────────

def test_marks_mixed_release_and_suspect():
    """suspect 有值/无值混合 → marks 如实；warnings 为空。"""
    (marks, warnings), _ = _call(
        [_gray("c5"), _gray("c8")],
        _rows([
            {"point_id": "c5", "point_name": "民生联动", "suspect": None},
            {"point_id": "c8", "point_name": "民生提质",
             "suspect": {"label": "疑似宽泛", "reason": "只写了获得感幸福感口号，没写就医消费机制"}},
        ]))
    assert warnings == []
    assert marks["c5"] is None                       # 放行（绿·语义）
    assert marks["c8"] == {"label": "疑似宽泛",
                           "reason": "只写了获得感幸福感口号，没写就医消费机制"}


def test_mark_extra_point_ignored_but_kept():
    """LLM 多标了不在灰带集里的点 → 保留无妨（assemble 只查 wanted）。"""
    (marks, _), _ = _call([_gray("c8")], _rows([
        {"point_id": "c99", "point_name": "多余", "suspect": {"label": "疑似宽泛", "reason": "x"}},
        {"point_id": "c8", "suspect": None},
    ]))
    assert marks["c8"] is None
    assert marks["c99"] == {"label": "疑似宽泛", "reason": "x"}


# ── 安全方向：坏输出 → 放行 + warnings ───────────────────────────

def test_illegal_label_releases_with_warning():
    """label 不在三选一内 → 该点放行 + warning（不误伤成疑似）。"""
    (marks, warnings), _ = _call([_gray()], _rows([
        {"point_id": "c8", "suspect": {"label": "疑似瞎编", "reason": "x"}},
    ]))
    assert marks["c8"] is None
    assert any("label" in w and "非法" in w for w in warnings)


def test_bad_suspect_shape_releases_with_warning():
    """suspect 非对象（pydantic 校验失败）→ 放行 + warning。"""
    (marks, warnings), _ = _call([_gray()], _rows([
        {"point_id": "c8", "suspect": "疑似宽泛"},
    ]))
    assert marks["c8"] is None
    assert any("校验失败" in w for w in warnings)


def test_missing_point_id_row_skipped():
    """缺 point_id 的行 → 跳过（不计入 marks），不崩。"""
    (marks, warnings), _ = _call([_gray("c8")], _rows([
        {"point_name": "没id", "suspect": None},
    ]))
    assert "c8" in marks and marks["c8"] is None    # wanted 兜底补放行
    assert any("point_id" in w for w in warnings)


def test_missing_verdicts_key_all_released():
    """无 verdicts 键 / 非 dict → 全放行 + 说明 warning（不误伤）。"""
    for raw in ("not-a-dict", {"other": 1}, []):
        (marks, warnings), _ = _call([_gray()], raw)
        assert marks.get("c8") is None
        assert warnings  # 全放行有据可查


def test_llm_down_all_released():
    """LLM 调用异常 → 灰带点全放行 + warnings（安全方向，演示不崩）。"""
    (marks, warnings), _ = _call([_gray("c8"), _gray("c5")],
                                 side_effect=RuntimeError("api down"))
    assert marks == {}
    assert warnings and "放行" in warnings[0]


def test_omitted_point_released_with_warning():
    """灰带点漏标 → 该点放行（安全方向）+ warnings 供审计。"""
    (marks, warnings), _ = _call([_gray("c8")], _rows([
        {"point_id": "c5", "suspect": None},  # 标了别的点，c8 漏标
    ]))
    assert marks["c8"] is None
    assert any("未标注" in w and "c8" in w for w in warnings)


def test_empty_gray_no_llm_call():
    """无灰带点（全绿全黄）→ 不调 LLM，直接空结果（0 token 路径）。"""
    with patch("src.shenlun.judge_llm.chat_json") as llm:
        marks, warnings = judge_suspect([], "作答")
    assert marks == {} and warnings == []
    llm.assert_not_called()
