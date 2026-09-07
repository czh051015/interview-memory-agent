"""docs/38 §4.1/§6：门禁规则层单测 —— gate_score 三态 + assemble_gate 合并（0 token 确定性）。

判定语义（D42/D43/D44）：每点 kw 全中出现 → hit（绿·关键词）；全缺 → miss（黄·漏答）；
部分出现 → 灰带（交 judge_suspect，本文件不调 LLM——suspects 由调用方传入）。
reason 文案（D47 ①）规则层固定，测试可钉。
"""
from src.shenlun.score import (
    REASON_HIT_LLM,
    REASON_HIT_KW,
    REASON_MISS,
    Point,
    assemble_gate,
    gate_score,
)
from src.shenlun.judge_llm import judge_suspect  # noqa: F401  # 灰带标注的调用方在 api 层

M = ("A区与B县开通城际公交，实现高速免费互通，新建提升改造3条道路，推进互联互通。"
     "新兴产业项目落地B县，物流枢纽成形。两地干部互派、挂职交流常态化。")

PTS = [
    Point(id="c1", point="设施互通", keywords=["城际公交", "高速免费", "道路", "互通"],
          score=1, type="对策"),
    Point(id="c2", point="产业协同", keywords=["新兴产业", "物流枢纽"], score=1, type="对策"),
    Point(id="c3", point="人才共育", keywords=["干部互派", "挂职"], score=1, type="对策"),
]


def _verdict(gv, pid):
    return next(v for v in gv if v.point_id == pid)


# ── gate_score：三态判定 + 规则证据 ────────────────────────────────

def test_gate_full_hit_all_keywords():
    """kw 全中出现 → hit；matched 按关键词原序列全量；missing 空。"""
    gv = gate_score("开通城际公交，高速免费，新建道路，深化互通", PTS, materials=M)
    v = _verdict(gv, "c1")
    assert v.status == "hit"
    assert v.matched == ["城际公交", "高速免费", "道路", "互通"]
    assert v.missing == []


def test_gate_zero_hit_miss():
    """kw 全缺 → miss（黄·漏答）；matched 空。"""
    gv = gate_score("完全无关的内容。", PTS, materials=M)
    v = _verdict(gv, "c3")
    assert v.status == "miss"
    assert v.matched == []
    assert v.missing == ["干部互派", "挂职"]
    assert v.evidence is None                      # §8.1：黄行 evidence 为空


def test_gate_partial_hit_gray():
    """部分命中 → gray（灰带，交 judge_suspect）；命中/缺失按关键词原序。"""
    gv = gate_score("新兴产业项目落地B县。", PTS, materials=M)
    v = _verdict(gv, "c2")
    assert v.status == "gray"
    assert v.matched == ["新兴产业"]
    assert v.missing == ["物流枢纽"]
    assert v.evidence == "新兴产业项目落地B县"


def test_gate_evidence_is_answer_sentence():
    """命中点 evidence = 作答中含 kw 的原句（规则 substring 定位，逐字可复核）。"""
    gv = gate_score("两地开通城际公交，实现高速免费互通。随后新建了3条道路。", PTS, materials=M)
    v = _verdict(gv, "c1")
    assert v.evidence == "两地开通城际公交，实现高速免费互通"
    assert v.evidence and "城际公交" in v.evidence


def test_gate_anchor_material_source():
    """anchor = 材料锚定句（三种状态都下发，docs/36 老缺口修复）。"""
    gv = gate_score("开通城际公交", PTS, materials=M)
    for v in gv:
        assert v.anchor is not None and "材料第" in v.anchor  # 关键词都出现在材料里


def test_gate_anchor_none_when_keyword_not_in_material():
    gv = gate_score("开通城际公交", PTS, materials="材料完全无关。")
    assert _verdict(gv, "c1").anchor is None        # 不硬锚


def test_gate_official_falls_back_to_anchor_quote():
    """official = source_snippet ?? 材料锚句原文（D46 兜底）。"""
    p = Point(id="c9", point="无摘录点", keywords=["城际公交"], score=1,
              source_snippet="两地开通城际公交的官方原句")
    v = gate_score("开通了城际公交", [p], materials=M)[0]
    assert v.official == "两地开通城际公交的官方原句"
    p2 = Point(id="c9", point="无摘录点", keywords=["城际公交"], score=1)  # benchmark 无 snippet
    v2 = gate_score("开通了城际公交", [p2], materials=M)[0]
    assert v2.official and "城际公交" in v2.official and "材料" not in v2.official


# ── assemble_gate：规则 + 灰带 LLM 标注合并（0 token，suspects 由调用方给）──

def test_assemble_hit_and_miss_reasons_pinned():
    """绿·关键词 / 黄·漏答的 reason 文案固定（D47 ① 随评分返回）。"""
    vs = assemble_gate("城际公交高速免费道路互通，新兴产业物流枢纽。", PTS, materials=M)
    hit = next(v for v in vs if v.point_id == "c1")
    assert hit.status == "hit" and hit.matched_by == "kw"
    assert hit.reason == REASON_HIT_KW.format(kws="城际公交、高速免费、道路、互通")
    assert hit.evidence and hit.anchor and hit.official
    miss = next(v for v in vs if v.point_id == "c3")
    assert miss.status == "miss" and miss.matched_by == "kw"
    assert miss.reason == REASON_MISS.format(kws="干部互派、挂职")
    assert miss.terms == {"matched": [], "missing": ["干部互派", "挂职"]}


def test_assemble_gray_no_mark_released_green():
    """灰带点无标注（LLM 漏标/整体失败，suspects 缺键）→ 放行 绿·语义。"""
    vs = assemble_gate("新兴产业项目落地。", PTS, materials=M, suspects={})
    v = next(x for x in vs if x.point_id == "c2")
    assert v.status == "hit" and v.matched_by == "llm"
    assert v.suspect is None
    assert v.reason == REASON_HIT_LLM.format(kws="新兴产业")
    assert v.terms == {"matched": ["新兴产业"], "missing": ["物流枢纽"]}


def test_assemble_gray_explicit_null_released():
    """LLM 显式 suspect:null → 放行（与缺键同语义，matched_by=llm）。"""
    vs = assemble_gate("新兴产业项目落地。", PTS, materials=M,
                       suspects={"c2": None})
    v = next(x for x in vs if x.point_id == "c2")
    assert v.status == "hit" and v.matched_by == "llm" and v.suspect is None


def test_assemble_gray_suspect_blue():
    """LLM 标疑似 → status=suspect，reason 透传 LLM reason（D47 ① 蓝行）。"""
    mark = {"label": "疑似宽泛", "reason": "只写了获得感口号，没写就医消费的具体内容"}
    vs = assemble_gate("新兴产业项目落地，群众获得感幸福感提升。", PTS, materials=M,
                       suspects={"c2": mark})
    v = next(x for x in vs if x.point_id == "c2")
    assert v.status == "suspect" and v.matched_by == "llm"
    assert v.suspect == mark
    assert v.reason == mark["reason"]
    assert v.terms == {"matched": ["新兴产业"], "missing": ["物流枢纽"]}  # 疑似行也带规则证据


def test_assemble_verdict_order_follows_points():
    """verdicts 顺序 = points 顺序（§6：按 point_order 逐点）。"""
    vs = assemble_gate("城际公交高速免费道路互通", PTS, materials=M)
    assert [v.point_id for v in vs] == ["c1", "c2", "c3"]


def test_assemble_empty_answer_all_miss():
    vs = assemble_gate("", PTS, materials=M)
    assert [(v.point_id, v.status) for v in vs] == [
        ("c1", "miss"), ("c2", "miss"), ("c3", "miss")]
