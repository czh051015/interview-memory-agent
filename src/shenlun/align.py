"""示证模式配对器（docs/37 §5，docs/38 吸收为示证档）——0 判定 token。

只做可回溯的文本配对，不做任何好坏判断：
  ① split_sentences 规则切句（0 token）
  ② 逐点 kw 子串配对（主证据：共现词 = 证据，0 token）——一个点可配多个句、
     一个句可配多个点（串点如实呈现，不做消歧，由用户判断）
  ③ kw 零命中点（gap 候选）→ 可选 embedding 语义弱配对（第二路）：
     要点文本 vs 作答各句取 max cosine，≥ τ 记「语义弱对应」，否则留在 gaps 附相似度数字
  ④ 输出 alignments / gaps（未见对应候选）/ orphans（无对应候选）+ meta

embedding 失败/不可用 → 静默降级纯 kw（meta.warnings 说明，不阻塞）。
语义第二路默认关（docs/38 §9 吸收口径：词重叠主证据已够演示，embedding 弱配对默认不调；
use_semantic 仅测试/探索时开启 —— docs/37 §8 草案写的 True 默认被 docs/38 §9 覆盖）。

材料原文只作「出处附注」展示（该点源自材料哪段），不参与配对主链（docs/37 D42）；
找不到出处 → material_ref=None（前端展示「该点非直接摘抄，需自行概括」）。

措辞总则（docs/37 §2.3，前端展示遵守）：禁 漏答/命中/没写上/答非所问/偏离/脱离材料/
套话/宽泛/表述不清/建议你补/你应该写；允许 未见对应句（候选）/有对应/共现词/相似度 X。
本模块只产出结构数据与数字，不含上述词（meta.warnings 面向开发者，不受措辞表约束）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.shenlun import score as _sc  # 活引用 embed_zh（conftest 全局 mock 命中该命名空间）

# 语义弱配对阈值（docs/37 §5.3 经验值 0.60）：校准只改这里，不动接口
ALIGN_SEMANTIC_TAU = 0.60
# 切句规则（docs/37 §5.1）：句号族切分；丢弃长度 < 6 的碎片
_SENT_SPLIT = re.compile(r"[。；!?！？\n]+")
_MIN_CHUNK_LEN = 6


# ── 输出契约（docs/37 §6 jsonc）───────────────────────────────────────
@dataclass
class AlignOfficial:
    """展示锚：标准答案逐点（右栏列表数据源）。"""
    id: str
    point: str
    keywords: list[str]
    official_sentence: str | None  # source_snippet（拆点/录入链路才有，可空）
    material_ref: str | None       # 出处附注（复用 _find_material_source），可空


@dataclass
class AlignChunk:
    id: int
    text: str


@dataclass
class AlignItem:
    """一条配对：kw 行带 kws_hit；semantic 行带 similarity（按 §6 契约输出）。"""
    point_id: str
    chunk_id: int
    method: str = "kw"                 # kw | semantic
    kws_hit: list[str] = field(default_factory=list)
    similarity: float | None = None


@dataclass
class AlignGap:
    point_id: str
    max_similarity: float | None = None  # embedding 可用时才有值，否则 null


@dataclass
class AlignOrphan:
    chunk_id: int
    max_similarity: float | None = None  # 与 gap 组要点 query 的最近相似度，可空


@dataclass
class AlignMeta:
    engine: str = "align"
    semantic_used: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass
class AlignmentResult:
    official_points: list[AlignOfficial]
    answer_chunks: list[AlignChunk]
    alignments: list[AlignItem]
    gaps: list[AlignGap]
    orphans: list[AlignOrphan]
    meta: AlignMeta

    def to_dict(self) -> dict:
        """docs/37 §6 jsonc 契约序列化：kw/semantic 行的字段各自裁剪。"""
        return {
            "official_points": [
                {"id": p.id, "point": p.point, "keywords": p.keywords,
                 "official_sentence": p.official_sentence, "material_ref": p.material_ref}
                for p in self.official_points
            ],
            "answer_chunks": [{"id": c.id, "text": c.text} for c in self.answer_chunks],
            "alignments": [
                ({"point_id": a.point_id, "chunk_id": a.chunk_id,
                  "kws_hit": a.kws_hit, "method": "kw"}
                 if a.method == "kw" else
                 {"point_id": a.point_id, "chunk_id": a.chunk_id,
                  "similarity": a.similarity, "method": "semantic"})
                for a in self.alignments
            ],
            "gaps": [{"point_id": g.point_id, "max_similarity": g.max_similarity}
                     for g in self.gaps],
            "orphans": [{"chunk_id": o.chunk_id, "max_similarity": o.max_similarity}
                        for o in self.orphans],
            "meta": {"engine": self.meta.engine,
                     "semantic_used": self.meta.semantic_used,
                     "warnings": self.meta.warnings},
        }


def split_sentences(text: str) -> list[str]:
    """按句号族切分语义分句（docs/37 §5.1）：[。；!?！？\n]，丢弃长度 < 6 的碎片。"""
    parts = _SENT_SPLIT.split(text or "")
    return [p.strip() for p in parts if len(p.strip()) >= _MIN_CHUNK_LEN]


def _point_query(p) -> str:
    """要点文本（弱配对 query，docs/37 §5.2）：点名称 + 官方原句(若有) + 关键词。"""
    parts = [p.point]
    snippet = (p.source_snippet or "").strip()
    if snippet:
        parts.append(snippet)
    parts.append("、".join(p.keywords))
    return " ".join(parts)


def _cosine(a: list[float], b: list[float]) -> float:
    n = sum(x * x for x in a) ** 0.5 * sum(y * y for y in b) ** 0.5
    return sum(x * y for x, y in zip(a, b)) / n if n else 0.0


def align_answer(answer: str, points: list,
                 materials: str | None = None, question: str | None = None,
                 use_semantic: bool = False) -> AlignmentResult:
    """配对器主入口（docs/37 §5，docs/38 §9 吸收）。

    Args:
        answer: 考生作答全文。
        points: 采分点列表（Point：id/point/keywords/score/type/source_snippet?）。
        materials: 材料原文（只作出处附注，不参与配对主链）。
        question: 题干（当前仅签名兼容，配对不消费）。
        use_semantic: 是否开启 embedding 语义弱配对（默认关，docs/38 §9）。
    """
    material = materials or ""
    chunks = [AlignChunk(id=i, text=t) for i, t in enumerate(split_sentences(answer), 1)]

    official_points = [
        AlignOfficial(
            id=p.id, point=p.point, keywords=list(p.keywords),
            official_sentence=(p.source_snippet or "").strip() or None,
            material_ref=_sc._find_material_source(p.keywords, material),
        )
        for p in points
    ]

    # ── ② kw 子串配对（主证据，0 token；一个点可配多句、一句可配多点，不做消歧）──
    alignments: list[AlignItem] = []
    kw_hit_point_ids: set[str] = set()
    for c in chunks:
        point_hits = [(p, [kw for kw in p.keywords if kw in c.text]) for p in points]
        if any(ph for _, ph in point_hits):
            for p, ph in point_hits:
                if ph:
                    alignments.append(AlignItem(point_id=p.id, chunk_id=c.id,
                                                kws_hit=ph))
                    kw_hit_point_ids.add(p.id)

    gaps = [AlignGap(point_id=p.id) for p in points if p.id not in kw_hit_point_ids]

    meta = AlignMeta()
    if use_semantic and gaps:
        # ── ③ embedding 语义弱配对（只对 kw 零命中点；docs/37 §5.3）──
        gap_points = [p for p in points if p.id in {g.point_id for g in gaps}]
        queries = [_point_query(p) for p in gap_points]
        try:
            embs = _sc.embed_zh(queries + [c.text for c in chunks])  # 一次 batch（每 gap 点 ≤1 次）
        except Exception as e:  # embed_zh 内部已兜底，这里再防一层
            embs = None
            meta.warnings.append(f"embedding 异常：{e}")
        if embs is None:
            meta.warnings.append("embedding 不可用，语义弱配对跳过（纯 kw 结果）")
        else:
            meta.semantic_used = True
            q_embs, c_embs = embs[: len(gap_points)], embs[len(gap_points):]
            # 孤儿句 max_similarity 复用 c_embs（对 gap 组要点 query 的 max，§6 展示数字）
            orphan_sims: dict[int, float] = {}
            for pi, p in enumerate(gap_points):
                best_sim, best_chunk = -1.0, None
                for ci, c in enumerate(chunks):
                    s = _cosine(q_embs[pi], c_embs[ci])
                    if s > best_sim:
                        best_sim, best_chunk = s, c
                    if s > orphan_sims.get(c.id, -1.0):
                        orphan_sims[c.id] = s
                if best_sim >= ALIGN_SEMANTIC_TAU and best_chunk is not None:
                    alignments.append(AlignItem(point_id=p.id, chunk_id=best_chunk.id,
                                                method="semantic",
                                                similarity=round(best_sim, 2)))
                    gaps = [g for g in gaps if g.point_id != p.id]
                else:
                    next(g for g in gaps if g.point_id == p.id).max_similarity = \
                        round(max(best_sim, 0.0), 2)

    # 孤儿 = 无任何配对（kw/semantic 都不沾）的作答句：语义配对完成后才成立
    matched_chunk_ids = {a.chunk_id for a in alignments}
    orphans = [AlignOrphan(chunk_id=c.id) for c in chunks
               if c.id not in matched_chunk_ids]
    if meta.semantic_used:
        for o in orphans:
            o.max_similarity = round(max(orphan_sims.get(o.chunk_id, 0.0), 0.0), 2)

    return AlignmentResult(
        official_points=official_points,
        answer_chunks=chunks,
        alignments=alignments,
        gaps=gaps,
        orphans=orphans,
        meta=meta,
    )
