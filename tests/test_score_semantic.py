"""docs/25 语义匹配层单测 —— 不依赖 Ollama，手造向量精确控制相似度。

conftest 全局把 embed_zh mock 成 None（降级），本文件测试内再 patch 成假嵌入，
用手造 2 维向量让 cosine 值精确可算：
  Q    = [1, 0]
  V_HI = [0.9, √(1−0.9²)]      → cos(Q, V_HI) = 0.9
  V_ABOVE = [0.75, √(1−0.75²)] → cos = 0.75（> 默认 τ=0.71）
  V_BELOW = [0.7, √(1−0.7²)]   → cos = 0.70（< 默认 τ=0.71）
  V_LO = [0.2, √(1−0.04)]      → cos = 0.2
"""
import math
from unittest.mock import patch

from src.shenlun.score import Point, _cosine, _semantic_match, score_answer

Q = [1.0, 0.0]
V_HI = [0.9, math.sqrt(1 - 0.9 ** 2)]
V_ABOVE = [0.75, math.sqrt(1 - 0.75 ** 2)]
V_BELOW = [0.7, math.sqrt(1 - 0.7 ** 2)]
V_LO = [0.2, math.sqrt(1 - 0.2 ** 2)]


def _point(keywords=None):
    return Point(id="p1", point="测试采分点", keywords=keywords or ["绝不出现的词"], score=2, type="对策")


def _fake_embed(sent_vecs: dict[str, list[float]]):
    """构造假 embed_zh：第一个文本是 query（返回 Q），其余按句查表，缺省 V_LO。"""
    def fake(texts: list[str]) -> list[list[float]]:
        return [Q if i == 0 else sent_vecs.get(t, V_LO) for i, t in enumerate(texts)]
    return fake


# ── 阶段2 基本判定 ──────────────────────────────────────────────

def test_semantic_hit_fields():
    """相似句 ≥ τ → 语义命中：matched_by/semantic_score/matched_text 全带。"""
    answer = "推动产业协同发展。完全无关的废话。"
    with patch("src.shenlun.score.embed_zh", _fake_embed({"推动产业协同发展": V_HI})):
        sr = score_answer(answer, [_point()], tau=0.71)
    assert sr.hit_ids == ["p1"]
    h = sr.hit_points[0]
    assert h.matched_by == "semantic"
    assert h.semantic_score == 0.9
    assert h.matched_text == "推动产业协同发展"  # 相似句原文（≤100 截断）
    assert sr.miss_points == []


def test_semantic_below_tau_misses():
    """相似度 < τ → 漏点，miss 侧与语义无关字段保持。"""
    answer = "推动产业协同发展。"
    with patch("src.shenlun.score.embed_zh", _fake_embed({"推动产业协同发展": V_HI})):
        sr = score_answer(answer, [_point()], tau=0.95)
    assert sr.hit_ids == []
    assert [m.id for m in sr.miss_points] == ["p1"]
    assert sr.hit_ratio == 0.0


def test_default_tau_uses_config():
    """默认 τ 读 SCORE_SEMANTIC_TAU（config 校准值 0.71）：0.75 命中、0.70 漏。"""
    answer = "A句。B句。"
    with patch("src.shenlun.score.embed_zh",
               _fake_embed({"A句": V_ABOVE, "B句": V_BELOW})):
        sr = score_answer(answer, [_point()])
    assert sr.hit_ids == ["p1"]
    assert sr.hit_points[0].semantic_score == 0.75


# ── 阶段1 优先 / 阶段2 开关 ─────────────────────────────────────

def test_kw_hit_skips_semantic():
    """关键词命中 → matched_by="kw"，不调 embedding（semantic_score 为 None）。"""
    answer = "关键词甲出现了。"
    with patch("src.shenlun.score.embed_zh") as m:
        sr = score_answer(answer, [_point(keywords=["关键词甲"])])
    m.assert_not_called()
    h = sr.hit_points[0]
    assert h.matched_by == "kw"
    assert h.semantic_score is None


def test_use_semantic_false_skips_phase2():
    """use_semantic=False → 纯硬匹配，不调 embedding。"""
    with patch("src.shenlun.score.embed_zh") as m:
        sr = score_answer("相似表达而已。", [_point()], use_semantic=False)
    m.assert_not_called()
    assert sr.hit_ids == []


def test_embed_unavailable_degrades():
    """embedding 不可用（None）→ 语义阶段降级，结果等同纯硬匹配，不崩。"""
    with patch("src.shenlun.score.embed_zh", lambda texts: None):
        sr = score_answer("相似表达而已。", [_point()], tau=0.5)
    assert sr.hit_ids == []
    assert [m.id for m in sr.miss_points] == ["p1"]


def test_empty_answer_all_miss():
    """空作答 → 不调 embedding，全漏。"""
    with patch("src.shenlun.score.embed_zh") as m:
        sr = score_answer("", [_point()])
    m.assert_not_called()
    assert sr.miss_ids == ["p1"]


# ── 与材料锚定（L3）共存 ────────────────────────────────────────

def test_semantic_hit_keeps_material_source():
    """语义命中的点照样锚材料（keywords 回材料句重叠度），与命中来源正交。"""
    answer = "不出现锚定词的相似表达。"
    with patch("src.shenlun.score.embed_zh",
               _fake_embed({"不出现锚定词的相似表达": V_HI})):
        sr = score_answer(answer, [_point(keywords=["锚定词"])],
                          materials="材料句里有锚定词。", tau=0.71)
    assert sr.hit_ids == ["p1"]
    assert sr.hit_points[0].material_source == "材料第1段：'材料句里有锚定词'"


# ── 底层函数直接测 ──────────────────────────────────────────────

def test_cosine_zero_vector_guard():
    assert _cosine([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert _cosine([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_semantic_match_empty_sents_no_embed():
    with patch("src.shenlun.score.embed_zh") as m:
        hit, sim, sent = _semantic_match("q", [], 0.71)
    m.assert_not_called()
    assert (hit, sim, sent) == (False, 0.0, None)
