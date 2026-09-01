"""评分传感器 —— 把 benchmark 的 hit/miss 逻辑做成可复用引擎层。

domain 无关：输入「采分点列表 + 作答文本」，输出「命中/漏掉哪些点」。
换壳时不需要改这里，只需换 reference_points 的来源（benchmark/data 或产品题库）。

docs/22 §3.2 升级：命中/漏点除 id/名称外，每个点携带
  - matched_text    命中关键词在作答中的片段（L1 标红定位，0 token 纯字符串）
  - material_source 材料锚定句（keywords 回材料句子做重叠度取最相关一句，L3 溯源，0 token）
docs/25 升级（语义匹配层）：关键词硬匹配未中的点，进阶段2 语义匹配——
  点 query（名称+关键词）vs 作答分句取 max cosine，≥ τ 判命中（matched_by="semantic"）。
  仍 0 LLM token（本地 dmeta embedding，确定性）；embedding 不可用则自动降级回纯硬匹配。
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field

from src.config import SCORE_EMBED_BACKEND, SCORE_ENGINE, SCORE_SEMANTIC_TAU

logger = logging.getLogger(__name__)


@dataclass
class Point:
    id: str
    point: str
    keywords: list[str]
    score: int = 1
    type: str = ""   # 采分角度（问题/原因/影响/对策/意义/危害/其他），docs/13 §5.1
    # 以下三个字段评卷时动态算，默认 None = 未评卷/未锚到
    matched_text: str | None = None      # 命中片段（仅 hit 点有值）：kw=含词句子，semantic=相似句
    material_source: str | None = None   # 材料锚定句，如「材料第1段：'…'」
    matched_by: str = "kw"               # 命中来源：kw / semantic（docs/25）/ llm（docs/26 judge 引擎）
    semantic_score: float | None = None  # 语义命中相似度（matched_by="semantic" 时有值，trace 用）
    miss_cause: str = ""                 # 漏点原因（judge 引擎诊断用）：没写/写模糊/没结合材料，docs/26
    quality_cause: str | None = None      # 诊断层标注：套话无具体性/答非所问 等，仅对命中点保留，docs/29


@dataclass
class ScoreResult:
    """一次作答的评分结果：只报 hit/miss，不报精确分数。"""
    hit_points: list[Point] = field(default_factory=list)
    miss_points: list[Point] = field(default_factory=list)

    @property
    def hit_ratio(self) -> float:
        total = len(self.hit_points) + len(self.miss_points)
        return len(self.hit_points) / total if total else 0.0

    @property
    def hit_ids(self) -> list[str]:
        return [p.id for p in self.hit_points]

    @property
    def miss_ids(self) -> list[str]:
        return [p.id for p in self.miss_points]


_SENT_SPLIT = re.compile(r"[。；;！？!?\n]+")   # 句级切分（与 runtime._segment_material 同口径）
_MAX_SNIPPET = 100      # matched_text 截断上限（展示用，够定位即可）
_MAX_QUOTE = 60         # 材料原话截断上限（L3 展示用）


def _matched_snippet(answer: str, keywords: list[str]) -> str | None:
    """命中关键词在作答中的片段：取包含命中词的句子（句级切分），截断到 ≤100 字。

    命中多个词时取最长的（更长 = 更特指，片段更可信）。0 token。
    """
    if not answer:
        return None
    hit_kw = next((kw for kw in sorted(keywords, key=len, reverse=True) if kw in answer), None)
    if hit_kw is None:
        return None
    for chunk in _SENT_SPLIT.split(answer):
        chunk = chunk.strip()
        if chunk and hit_kw in chunk:
            return chunk if len(chunk) <= _MAX_SNIPPET else chunk[:_MAX_SNIPPET] + "…"
    return hit_kw


# ── docs/25 语义匹配层：关键词硬匹配之后的阶段2 ──────────────────────
_SEM_SENT_SPLIT = re.compile(r"[。；;！？!?，,、\n]+")  # 语义匹配专用切句：含逗号（比 _SENT_SPLIT 更细）


def embed_zh(texts: list[str]) -> list[list[float]] | None:
    """评分语义层 embedding：按后端优先级走 api→ollama→None。

    docs/27 §2.2：本地 dmeta 保持记忆检索，评分语义层改为云端 bge-m3，失败后回降本地 dmeta，
    再失败则返回 None，整个语义阶段退回纯硬匹配，不崩。
    """
    if not texts:
        return []
    try:
        if SCORE_EMBED_BACKEND == "api":
            from src.memory.embedding import embed_api

            return embed_api(texts)
        from src.memory.embedding import embed_ollama

        return embed_ollama(texts)
    except Exception as e:
        logger.warning("embedding %s 失败，回退本地 dmeta: %s", SCORE_EMBED_BACKEND, e)
        try:
            from src.memory.embedding import embed_ollama

            return embed_ollama(texts)
        except Exception as e2:
            logger.warning("本地 embedding 也失败，语义匹配阶段跳过（回退硬匹配）: %s", e2)
            return None


def _cosine(a: list[float], b: list[float]) -> float:
    n = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    if not n:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / n


def _semantic_match(query: str, answer_sents: list[str], tau: float) -> tuple[bool, float, str | None]:
    """未命中点的语义判定（docs/25 §3 阶段2）：点 query vs 作答分句取 max cosine。

    Returns:
        (是否命中, 最大相似度, 命中的作答句)
    embedding 失败（embed_zh 返回 None）→ (False, 0.0, None)，语义阶段降级。
    """
    if not answer_sents:
        return False, 0.0, None
    embs = embed_zh([query] + answer_sents)
    if embs is None:
        return False, 0.0, None
    q = embs[0]
    best_sim, best_sent = -1.0, None
    for sent, e in zip(answer_sents, embs[1:]):
        sim = _cosine(q, e)
        if sim > best_sim:
            best_sim, best_sent = sim, sent
    return best_sim >= tau, best_sim, best_sent


def _anchor_sentences(material: str) -> list[tuple[int, str]]:
    """材料 → [(段落号(1-based), 句子)]，段落按换行分。基准材料多无段落，退化为 1 段。"""
    out: list[tuple[int, str]] = []
    for pno, para in enumerate((material or "").split("\n"), start=1):
        for chunk in _SENT_SPLIT.split(para):
            chunk = chunk.strip()
            if chunk:
                out.append((pno, chunk))
    return out


def _find_material_source(keywords: list[str], material: str) -> str | None:
    """材料锚定（docs/22 §3.2 L3）：把采分点关键词回材料句子做重叠度，取最相关一句。

    重叠度 = 句内命中的关键词字符数之和；没有句子命中任何关键词 → None（不硬锚）。
    输出格式：「材料第X段：'原话'」，锚定可溯源，不依赖预标注行号。0 token。
    """
    if not material or not keywords:
        return None
    best: tuple[int, str] | None = None
    best_score = 0
    for pno, sent in _anchor_sentences(material):
        s = sum(len(kw) for kw in keywords if kw in sent)
        if s > best_score:
            best_score, best = s, (pno, sent)
    if best is None or best_score == 0:
        return None
    quote = best[1] if len(best[1]) <= _MAX_QUOTE else best[1][:_MAX_QUOTE] + "…"
    return f"材料第{best[0]}段：'{quote}'"


def _score_answer_kw(answer: str, points: list[Point], materials: str = "",
                    use_semantic: bool = True, tau: float | None = None) -> ScoreResult:
    """确定性评分引擎：关键词 + 语义两阶段，LLM 分发时作为安全兜底。"""
    if tau is None:
        tau = SCORE_SEMANTIC_TAU
    answer_sents = [c.strip() for c in _SEM_SENT_SPLIT.split(answer) if c.strip()] if use_semantic else []

    result = ScoreResult()
    for p in points:
        if any(kw in answer for kw in p.keywords):
            hit = Point(id=p.id, point=p.point, keywords=p.keywords, score=p.score, type=p.type,
                        matched_text=_matched_snippet(answer, p.keywords), matched_by="kw")
            hit.material_source = _find_material_source(p.keywords, materials)
            result.hit_points.append(hit)
        elif use_semantic:
            hit_flag, sim, sent = _semantic_match(
                f"{p.point} {' '.join(p.keywords)}", answer_sents, tau)
            if hit_flag:
                snippet = sent if sent is None or len(sent) <= _MAX_SNIPPET else sent[:_MAX_SNIPPET] + "…"
                hit = Point(id=p.id, point=p.point, keywords=p.keywords, score=p.score, type=p.type,
                            matched_text=snippet, matched_by="semantic", semantic_score=round(sim, 4))
                hit.material_source = _find_material_source(p.keywords, materials)
                result.hit_points.append(hit)
            else:
                miss = Point(id=p.id, point=p.point, keywords=p.keywords, score=p.score, type=p.type)
                miss.material_source = _find_material_source(p.keywords, materials)
                result.miss_points.append(miss)
        else:
            miss = Point(id=p.id, point=p.point, keywords=p.keywords, score=p.score, type=p.type)
            miss.material_source = _find_material_source(p.keywords, materials)
            result.miss_points.append(miss)
    return result


def score_answer(answer: str, points: list[Point], materials: str = "",
                 question: str = "", use_semantic: bool = True,
                 tau: float | None = None) -> ScoreResult:
    """评分入口：docs/31 默认切 LLM，失败时安全回退到确定性 kw+语义引擎。

    question 为题干（LLM 判"答非所问"用，docs/31 §3.2 显式传入，勿再从 points 取——
    Point 无 question 字段）。kw 引擎不需要 question，传了也忽略。
    """
    if SCORE_ENGINE == "llm":
        from src.shenlun.judge_llm import judge_score

        result, _ = judge_score(answer, points, materials=materials, question=question)
        return result

    return _score_answer_kw(answer, points, materials=materials, use_semantic=use_semantic, tau=tau)


def from_benchmark(reference_points: list[dict]) -> list[Point]:
    """把 benchmark JSON 的 reference_points 转成引擎 Point。"""
    return [
        Point(
            id=p["id"],
            point=p["point"],
            keywords=p["keywords"],
            score=int(p.get("score", 1)),
            type=p.get("point_type", ""),
        )
        for p in reference_points
    ]
