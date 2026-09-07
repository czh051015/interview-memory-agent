"""docs/37 §5/§6：示证配对器单测 —— align_answer（0 判定 token，纯规则主路）。

覆盖：切句（句号族 + 丢 <6 碎片）、逐点 kw 配对（一句配多点/一点配多句、不消歧）、
gaps（kw 零命中点未见对应候选）、orphans（无 kw 命中句）、material_ref 出处附注
（不进配对主链）、§6 to_dict 契约形状、embedding 语义弱配对第二路（默认关；开启后
用假向量：τ=0.60 边界内的命中/未命中 + 失败静默降级纯 kw）。
"""
import math
from unittest.mock import patch

from src.shenlun.align import (
    ALIGN_SEMANTIC_TAU,
    AlignOfficial,
    AlignOrphan,
    align_answer,
    split_sentences,
)
from src.shenlun.score import Point

M = ("A区与B县开通城际公交，实现高速免费互通，互联互通不断加速，新建提升改造3条道路。"
     "新能源项目相继落地，形成供应链生态圈。两地签署人才协同战略合作协议，互派干部挂职。")

PTS = [
    Point(id="c1", point="设施互通", keywords=["城际公交", "道路", "互通"], score=1, type="对策"),
    Point(id="c2", point="产业协同", keywords=["新兴产业", "供应链"], score=1, type="对策"),
    Point(id="c3", point="人才共育", keywords=["干部互派", "挂职"], score=1, type="对策"),
    Point(id="c4", point="生态保护", keywords=["生态修复", "野生动植物"], score=1, type="对策"),
]

Q = "梳理概括同城化发展的举措和成效"


# ── 切句（§5.1）──────────────────────────────────────────────────

def test_split_sentences_by_punct_family():
    """句号族切分（含 \n）——每段都 ≥6 字符，不触发碎片丢弃规则。"""
    assert split_sentences("第一句内容完整。第二句也完整；第三句内容完整！第四句内容完整？第五句内容完整\n第六句完整内容") == [
        "第一句内容完整", "第二句也完整", "第三句内容完整", "第四句内容完整", "第五句内容完整", "第六句完整内容"]


def test_split_drops_short_fragments():
    """长度 < 6 的碎片丢弃（编号/语气碎片不入句）。"""
    assert split_sentences("第一句完整内容很长。嗯。好！第二句也足够长。") == [
        "第一句完整内容很长", "第二句也足够长"]


def test_split_empty_text():
    assert split_sentences("") == []


# ── 主证据：kw 子串配对（§5.2，0 token）────────────────────────────

def _result(answer):
    return align_answer(answer, PTS, materials=M, question=Q)


def test_kw_pairs_point_to_chunks():
    r = _result("两地开通了城际公交，新建了道路。B县落地了新兴产业项目。")
    by_point = {(a.point_id, a.chunk_id): a.kws_hit for a in r.alignments}
    assert by_point[("c1", 1)] == ["城际公交", "道路"]   # kw 命中如实列出（句内子串）
    assert by_point[("c2", 2)] == ["新兴产业"]          # 不要求整词全中才配对


def test_one_chunk_pairs_many_points_no_disambiguation():
    """一句含多点的 kw → 串点如实呈现（c1/c2 同句），不消歧（docs/37 §5.2）。"""
    r = _result("城际公交与新兴产业共促互联互通与供应链发展。")
    c1 = [a for a in r.alignments if a.point_id == "c1"]
    c2 = [a for a in r.alignments if a.point_id == "c2"]
    assert c1 and c2 and c1[0].chunk_id == c2[0].chunk_id == 1


def test_one_point_pairs_many_chunks():
    r = _result("开通城际公交。随后又新建了道路。互通持续深化。")
    c1s = [a for a in r.alignments if a.point_id == "c1"]
    assert sorted(a.chunk_id for a in c1s) == [1, 2, 3]  # 一个点配多句如实呈现


def test_gaps_and_orphans():
    """kw 零命中点 → gaps（未见对应候选）；无 kw 命中句 → orphans（无对应候选）。"""
    r = _result("两地开通城际公交，实现了道路互通。这句与所有点都无关。")
    assert {g.point_id for g in r.gaps} == {"c2", "c3", "c4"}
    assert [o.chunk_id for o in r.orphans] == [2]
    assert {a.point_id for a in r.alignments} == {"c1"}


def test_material_ref_attached_but_not_in_pairing_chain():
    """official_points 带材料出处附注（§5.4，展示辅助，不进配对主链）。"""
    r = _result("开通了城际公交。")
    c1: AlignOfficial = next(p for p in r.official_points if p.id == "c1")
    assert c1.material_ref and "城际公交" in c1.material_ref   # 出处可溯源
    c4 = next(p for p in r.official_points if p.id == "c4")
    assert c4.material_ref is None                              # 关键词不在材料 → 不硬锚


def test_empty_answer_all_points_gap():
    r = _result("")
    assert len(r.answer_chunks) == 0
    assert {g.point_id for g in r.gaps} == {p.id for p in PTS}
    assert r.orphans == [] and r.alignments == []


def test_to_dict_contract_shape():
    """§6 jsonc：kw 行无 similarity、semantic 行无 kws_hit；meta 带 semantic_used。"""
    d = _result("开通城际公交。落地新能源项目。").to_dict()
    assert set(d) == {"official_points", "answer_chunks", "alignments",
                      "gaps", "orphans", "meta"}
    assert d["meta"] == {"engine": "align", "semantic_used": False, "warnings": []}
    kw_row = d["alignments"][0]
    assert kw_row["method"] == "kw" and "similarity" not in kw_row and "kws_hit" in kw_row
    assert set(d["official_points"][0]) == {"id", "point", "keywords",
                                            "official_sentence", "material_ref"}
    assert d["official_points"][0]["official_sentence"] is None   # benchmark 无 source_snippet


# ── 第二路：embedding 语义弱配对（默认关，§5.3 / docs/38 §9）────────

Q_VEC = [1.0, 0.0]
V_ABOVE = [0.65, math.sqrt(1 - 0.65 ** 2)]     # cos = 0.65 ≥ τ=0.60
V_BELOW = [0.5, math.sqrt(1 - 0.5 ** 2)]       # cos = 0.50 < τ
V_LO = [0.1, math.sqrt(1 - 0.1 ** 2)]


def _patch_embed(fake):
    """patch align 经活引用的 embed_zh（score 模块属性；与 conftest 同构）。"""
    from src.shenlun import score as score_mod
    return patch.object(score_mod, "embed_zh", fake)


# 语义路径的前提：只 c4 是 kw 零命中点（唯一 gap）→ texts = [c4 query] + chunks。
# c1/c2/c3 用 kw 命中句占位，chunk 向量按切句顺序给。
_ANS_SEM = ("开通城际公交，互通加深。新兴产业落地形成供应链。干部互派挂职进行中。"
            "{extra}")


def test_semantic_off_by_default_no_embed_call():
    """use_semantic=False（默认）→ 不调 embed（0 token 主路，docs/38 §9）。"""

    def fake(texts):  # noqa: ARG001
        raise AssertionError("use_semantic=False 不该调 embedding")

    with _patch_embed(fake):
        r = _result("开通了城际公交。")
    assert not r.meta.semantic_used
    assert r.meta.warnings == []


def test_semantic_pair_moves_gap_to_alignment():
    """gap 点（kw 零命中）的 query vs 某句 ≥ τ → 移到语义弱对应（method=semantic）。"""

    def fake(texts):
        assert len(texts) == 1 + 4             # [c4 query] + 4 个作答句
        return [Q_VEC, V_LO, V_LO, V_LO, V_ABOVE]   # 第 4 句（extra）语义对应 0.65

    with _patch_embed(fake):
        r = align_answer(_ANS_SEM.format(extra="能对应生态保护的表述句"), PTS,
                         materials=M, use_semantic=True)
    assert r.meta.semantic_used
    c4s = [a for a in r.alignments if a.point_id == "c4"]
    assert len(c4s) == 1
    assert c4s[0].method == "semantic" and c4s[0].similarity == 0.65
    assert c4s[0].kws_hit == []
    assert "c4" not in {g.point_id for g in r.gaps}


def test_semantic_below_tau_keeps_gap_with_max_similarity():
    """全部 < τ → 保持 gap 并附 max_similarity 数字（如实，不装懂）。"""

    def fake(texts):
        return [Q_VEC, V_LO, V_LO, V_LO, V_BELOW]  # 第 4 句也只有 0.50

    with _patch_embed(fake):
        r = align_answer(_ANS_SEM.format(extra="有点沾边但不够的句子"), PTS,
                         materials=M, use_semantic=True)
    g = next(g for g in r.gaps if g.point_id == "c4")
    assert g.max_similarity == 0.5             # 四舍五入两位
    assert not any(a.point_id == "c4" for a in r.alignments)


def test_semantic_unavailable_silently_degrades():
    """embedding 不可用（conftest 全局 None / 抛异常）→ 静默降级纯 kw + meta 说明。"""
    with _patch_embed(lambda texts: None):
        r = align_answer("无关句。", PTS, materials=M, use_semantic=True)
    assert r.meta.semantic_used is False
    assert r.meta.warnings                        # 降级有据可查
    assert {g.point_id for g in r.gaps} == {"c1", "c2", "c3", "c4"}  # 纯 kw 结果照常


def test_orphan_max_similarity_when_semantic_on():
    """语义开启时孤儿句（无 kw 命中句）附与 gap 点 query 的最近相似度（§6 数字）。"""

    def fake(texts):
        # 两 extra 句都无 kw → orphan；c4 与两句 cosine 均 < τ → c4 仍在 gaps
        return [Q_VEC, V_LO, V_LO, V_LO, V_LO, V_BELOW]

    with _patch_embed(fake):
        r = align_answer(_ANS_SEM.format(extra="第一句与所有要点都无关。第二句有点沾边。"),
                         PTS, materials=M, use_semantic=True)
    assert "c4" in {g.point_id for g in r.gaps}     # 0.5/0.1 都 < τ，不装懂
    sims = {o.chunk_id: o.max_similarity for o in r.orphans}
    assert sims == {4: 0.1, 5: 0.5}


def test_align_tau_constant_exposed():
    assert ALIGN_SEMANTIC_TAU == 0.60          # 校准只改常量（docs/37 §5.3 经验值）
