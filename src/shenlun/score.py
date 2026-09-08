"""评分传感器 —— 把 benchmark 的 hit/miss 逻辑做成可复用引擎层。

domain 无关：输入「采分点列表 + 作答文本」，输出「命中/漏掉哪些点」。
换壳时不需要改这里，只需换 reference_points 的来源（benchmark/data 或产品题库）。

docs/22 §3.2 升级：命中/漏点除 id/名称外，每个点携带
  - matched_text    命中关键词在作答中的片段（L1 标红定位，0 token 纯字符串）
  - material_source 材料锚定句（keywords 回材料句子做重叠度取最相关一句，L3 溯源，0 token）
docs/25 升级（语义匹配层）：关键词硬匹配未中的点，进阶段2 语义匹配——
  点 query（名称+关键词）vs 作答分句取 max cosine，≥ τ 判命中（matched_by="semantic"）。
  仍 0 LLM token（本地 dmeta embedding，确定性）；embedding 不可用则自动降级回纯硬匹配。

docs/38（2026-09-02）双模式改造：LLM 判定分发（SCORE_ENGINE=llm）退役（D49）——
评分路由改为「门禁 gate / 示证 align」双模式（trusted 信号在 app/api/shenlun.py 判定）：
  · gate_score（本文件）：规则门禁，每点 all/partial/none 三态（D42/D43/D44），0 token；
    灰带（partial）点由 src/shenlun/judge_llm.judge_suspect 做疑似标注（D45），永不定性硬判。
  · align 配对器（src/shenlun/align.py）：不可信题只摆差异（docs/37 形态）。
score_answer / _score_answer_kw **保留不删**（docs/38 §10 注意1）：旧评测对照、reflow、
explain 等非门禁链路继续用确定性两段式，仅去掉 llm 分发分支。
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field

from src.config import SCORE_EMBED_BACKEND, SCORE_SEMANTIC_TAU

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
    source_snippet: str = ""              # 拆点时从标准答案一字摘录的原句（范本对照，docs/35 D25）


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
                        matched_text=_matched_snippet(answer, p.keywords), matched_by="kw",
                        source_snippet=p.source_snippet)
            hit.material_source = _find_material_source(p.keywords, materials)
            result.hit_points.append(hit)
        elif use_semantic:
            hit_flag, sim, sent = _semantic_match(
                f"{p.point} {' '.join(p.keywords)}", answer_sents, tau)
            if hit_flag:
                snippet = sent if sent is None or len(sent) <= _MAX_SNIPPET else sent[:_MAX_SNIPPET] + "…"
                hit = Point(id=p.id, point=p.point, keywords=p.keywords, score=p.score, type=p.type,
                            matched_text=snippet, matched_by="semantic", semantic_score=round(sim, 4),
                            source_snippet=p.source_snippet)
                hit.material_source = _find_material_source(p.keywords, materials)
                result.hit_points.append(hit)
            else:
                miss = Point(id=p.id, point=p.point, keywords=p.keywords, score=p.score, type=p.type,
                             source_snippet=p.source_snippet)
                miss.material_source = _find_material_source(p.keywords, materials)
                result.miss_points.append(miss)
        else:
            miss = Point(id=p.id, point=p.point, keywords=p.keywords, score=p.score, type=p.type,
                         source_snippet=p.source_snippet)
            miss.material_source = _find_material_source(p.keywords, materials)
            result.miss_points.append(miss)
    return result


def score_answer(answer: str, points: list[Point], materials: str = "",
                 question: str = "", use_semantic: bool = True,
                 tau: float | None = None) -> ScoreResult:
    """确定性评分（kw 两段式 + 语义层）入口 —— 旧评测对照 / reflow / explain 等非门禁链路用。

    docs/38 D49：LLM 判定分发已退役（judge_score 改造为 judge_suspect），本函数恒走
    确定性引擎（不调 LLM、秒级、可复现）。门禁模式请用 gate_score（all/partial/none
    三态），示证模式用 align.py —— score_answer 保留只为旧口径兼容（§10 注意1）。
    question 传了也忽略（kw 引擎不需要题干）。
    """
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
            source_snippet=p.get("source_snippet", ""),  # 库题 benchmark 无此键 → 空；文字版拆点有
        )
        for p in reference_points
    ]


# ── docs/38 门禁模式规则层（D42/D43/D44，0 token）────────────────────────
# 判定语义：每点 kw 全中出现 → hit（绿·关键词）；全缺 → miss（黄·漏答）；
# 部分出现 → 灰带，交 judge_suspect 做疑似标注（D44/D45，不进本文件）。
# 证据全部由规则生成（命中词/缺失词/作答原句/材料锚），LLM 输出面没有证据字段。
# 本层不复用 _score_answer_kw（any 命中即 hit 的两段式）——全/缺/部分三态是新判据。

_ANCHOR_QUOTE = re.compile(r"材料第\d+段：'([^']*)'")  # _find_material_source 输出里取原句


def _anchor_quote(anchor: str | None) -> str:
    """从锚「材料第X段：'…'」取引号内原句（D46 兜底展示用）；取不到原样返回。"""
    if not anchor:
        return ""
    m = _ANCHOR_QUOTE.search(anchor)
    return m.group(1) if m else anchor


@dataclass
class GateVerdict:
    """门禁规则层逐点判定（gate_score 输出；0 token，逐字可复核）。

    status: hit（kw 全中）/ miss（kw 全缺）/ gray（部分命中 → 灰带，待 LLM 疑似标注）。
    evidence: 作答中含命中词的整句（规则 substring 定位，miss 恒 None）。
    anchor: 「材料第X段：'…'」（_find_material_source，三种状态下发，D51）。
    official: 标准答案原文 = source_snippet ?? 材料锚句原文（D46，0 数据工程兜底）。
    """
    point_id: str
    point_name: str
    score: int
    point_type: str
    keywords: list[str]
    status: str            # hit | miss | gray
    matched: list[str]     # 命中的 kw（按 keywords 原序）
    missing: list[str]     # 缺失的 kw
    evidence: str | None = None
    anchor: str | None = None
    official: str = ""


def gate_score(answer: str, points: list[Point], materials: str = "") -> list[GateVerdict]:
    """门禁规则层（docs/38 §4.1）：对每点做 all/partial/none 三态判定，0 token。

    输出顺序 = points 顺序（响应按此序列化，替代旧 point_order）。灰带点由调用方
    聚合喂 judge_suspect（§10 注意2：一次 LLM 调用，勿逐点调）。
    """
    ans = answer or ""
    out: list[GateVerdict] = []
    for p in points:
        matched = [kw for kw in p.keywords if kw in ans]
        missing = [kw for kw in p.keywords if kw not in ans]
        status = "hit" if not missing else ("miss" if not matched else "gray")
        v = GateVerdict(
            point_id=p.id, point_name=p.point, score=p.score, point_type=p.type,
            keywords=p.keywords, status=status, matched=matched, missing=missing,
        )
        if matched:  # 证据：作答中含命中词的整句（规则定位，截断仅展示）
            for chunk in _SENT_SPLIT.split(ans):
                chunk = chunk.strip()
                if chunk and any(kw in chunk for kw in matched):
                    v.evidence = chunk if len(chunk) <= _MAX_SNIPPET else chunk[:_MAX_SNIPPET] + "…"
                    break
        v.anchor = _find_material_source(p.keywords, materials)
        v.official = (p.source_snippet or "").strip() or _anchor_quote(v.anchor)
        out.append(v)
    return out


def result_from_verdicts(points: list[Point], verdicts: list[dict]) -> ScoreResult:
    """gate verdicts（JSON 形态，docs/42 §4.0）→ ScoreResult：入库判据与展示判据统一。

    docs/42 M5（P-B=B1）：reflow 入库改按 submit 展示的 gate 三态语义——
    hit = 绿（规则 kw ∪ LLM 放行绿）；miss = 黄；suspect = 灰带疑似（记 miss，
    suspect 标注由调用方在 events 落）。verdicts 与 points 同源（submit 响应原样回传），
    个别点缺失时按 miss 兜底（不臆造命中）。evidence/anchor 回填作答原句与材料锚，
    保持入库记录可溯源。纯函数，0 token。
    """
    by_id = {str(v.get("point_id")): v for v in verdicts or []}
    result = ScoreResult()
    for p in points:
        v = by_id.get(p.id) or {}
        if v.get("status") == "hit":
            hit = Point(id=p.id, point=p.point, keywords=p.keywords, score=p.score, type=p.type,
                        matched_text=v.get("evidence") or None,
                        matched_by=str(v.get("matched_by") or "kw"),
                        source_snippet=p.source_snippet)
            hit.material_source = v.get("anchor")
            result.hit_points.append(hit)
        else:
            miss = Point(id=p.id, point=p.point, keywords=p.keywords, score=p.score, type=p.type,
                         source_snippet=p.source_snippet)
            miss.material_source = v.get("anchor")
            result.miss_points.append(miss)
    return result


# ── 响应契约（docs/38 §6）：PointVerdict —— 每条含 reason（为什么标，随评分返回）──
# reason 文案（规则层固定，测试可钉；蓝行由 LLM reason 透传）：
REASON_HIT_KW = "该点得分关键词均已出现：{kws}"      # 绿·关键词
REASON_MISS = "作答中未找到关键词：{kws}"            # 黄·漏答（D43 候选措辞，用户可复核自判）
REASON_HIT_LLM = "该点关键词部分出现（{kws}），比对官方写法无存疑，放行命中"  # 绿·语义


@dataclass
class PointVerdict:
    """门禁模式的逐点最终判定（规则 + LLM 灰带标注合并后，docs/38 §6）。"""
    point_id: str
    point_name: str
    status: str                                   # hit | miss | suspect
    matched_by: str                               # kw（规则绿）| llm（灰带放行绿 / 疑似）
    terms: dict                                   # {"matched": [...], "missing": [...]}
    evidence: str | None
    anchor: str | None
    official: str
    suspect: dict | None                          # {"label","reason"}，仅 status=suspect 非空
    reason: str                                   # 为什么标（规则文案或 LLM reason，D47 ①）


def assemble_gate(answer: str, points: list[Point], materials: str = "",
                  suspects: dict | None = None) -> list[PointVerdict]:
    """把规则层判定 + 灰带 LLM 标注合并成 docs/38 §6 的 PointVerdict 列表。

    suspects: judge_suspect 的产出 {point_id: None | {"label","reason"}}；点不在表内
    （LLM 漏标/整体失败）→ 放行绿·语义，不误伤成疑似（D45 安全方向）。
    本函数不调 LLM（0 token 合并），LLM 标注由调用方先做好再传入。
    """
    verdicts: list[PointVerdict] = []
    for v in gate_score(answer, points, materials=materials):
        if v.status == "hit":
            verdicts.append(PointVerdict(
                point_id=v.point_id, point_name=v.point_name, status="hit", matched_by="kw",
                terms={"matched": v.matched, "missing": []},
                evidence=v.evidence, anchor=v.anchor, official=v.official,
                suspect=None,
                reason=REASON_HIT_KW.format(kws="、".join(v.matched)) if v.matched
                       else "该点无得分关键词（按全中出现计）",
            ))
        elif v.status == "miss":
            verdicts.append(PointVerdict(
                point_id=v.point_id, point_name=v.point_name, status="miss", matched_by="kw",
                terms={"matched": [], "missing": v.missing},
                evidence=None, anchor=v.anchor, official=v.official,
                suspect=None,
                reason=REASON_MISS.format(kws="、".join(v.missing)) if v.missing
                       else "该点无得分关键词",
            ))
        else:  # gray：LLM 疑似标注（suspects dict 由 judge_suspect 产出）
            mark = (suspects or {}).get(v.point_id)  # 不在表内 / 显式 null → 都放行
            if mark is None:
                verdicts.append(PointVerdict(
                    point_id=v.point_id, point_name=v.point_name, status="hit", matched_by="llm",
                    terms={"matched": v.matched, "missing": v.missing},
                    evidence=v.evidence, anchor=v.anchor, official=v.official,
                    suspect=None,
                    reason=REASON_HIT_LLM.format(kws="、".join(v.matched)) if v.matched
                           else "灰带点无命中关键词（比对官方写法后放行）",
                ))
            else:
                verdicts.append(PointVerdict(
                    point_id=v.point_id, point_name=v.point_name, status="suspect", matched_by="llm",
                    terms={"matched": v.matched, "missing": v.missing},
                    evidence=v.evidence, anchor=v.anchor, official=v.official,
                    suspect={"label": mark["label"], "reason": mark["reason"]},
                    reason=mark["reason"],
                ))
    return verdicts
