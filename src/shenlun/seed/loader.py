"""落库器 —— 时间回拨 + 语义禁用，逐场景调 reflow_answer（唯一写库 IO 面）。

不做的事：不含抽题 / 场景构造 / 文本组织逻辑；
只把已构造好的 Scenario 灌进 data/shenlun.db：
 1) 先本地评分断言「作答命中 == 场景预期命中」（不一致即中止，防数据脏）
 2) 每题每次作答：patch reflow.utcnow → 过去第 days_ago 天、patch score.embed_zh
    → None（纯关键词硬匹配，毫秒级、无外部调用），调 reflow_answer 落库后恢复
 3) seed 幂等（docs/40 §5.4）：data/seed/weak_history_seed.json 记录已用 seed 与
    已 seed 的 question_id —— 同一 seed 只跑一次（不重复写库）；换 seed 换一批，
    已 seed 的题自动排除（档案不重复膨胀）
"""

from __future__ import annotations

import json
import random
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from src.config import DATA_DIR
from src.shenlun import reflow, score
from src.shenlun.reflow import reflow_answer
from src.shenlun.score import from_benchmark, score_answer

from .builder import build_answer
from .scenario import Scenario, build_scenario

_MANIFEST = DATA_DIR / "seed" / "weak_history_seed.json"
_KIND = "shenlun_weak_history_seed"


@dataclass
class SeedReport:
    written: list[str] = field(default_factory=list)   # 本次实际写库的 question_id
    skipped: list[str] = field(default_factory=list)   # 已在清单 / seed 已用过 → 跳过
    answers_written: int = 0                           # 新增 answers 行数（含每题多轮）
    already_applied: bool = False                      # 该 seed 之前已跑过（本轮 0 写库）


def _load_manifest() -> dict:
    if not _MANIFEST.exists():
        return {"kind": _KIND, "seeds": [], "question_ids": []}
    return json.loads(_MANIFEST.read_text(encoding="utf-8"))


def load_seeded_ids() -> list[str]:
    """已 seed 的 question_id（抽题排除用；无清单返回空列表）。"""
    return list(_load_manifest().get("question_ids", []))


def is_seed_applied(seed: int) -> bool:
    """该 seed 是否已落过库（同一 seed 重跑 = 幂等跳过）。"""
    return seed in _load_manifest().get("seeds", [])


def prepare_scenarios(questions: list[dict], seed: int) -> list[Scenario]:
    """纯构造：question dicts + seed → Scenario 列表（不写库，dry-run 可打印）。"""
    out = []
    for q in questions:
        out.append(build_scenario(q, random.Random(f"{seed}:{q['id']}")))
    return out


def seed_scenarios(scenarios: list[Scenario], *, seed: int) -> SeedReport:
    """把场景灌进真实库；返回写库 / 跳过统计。"""
    manifest = _load_manifest()
    report = SeedReport(skipped=[s.question_id for s in scenarios])
    if seed in manifest.get("seeds", []):
        report.already_applied = True
        return report
    already = set(manifest.get("question_ids", []))
    todo = [s for s in scenarios if s.question_id not in already]
    report.skipped = [s.question_id for s in scenarios if s.question_id in already]
    if not todo:
        return report
    _verify_all(todo)
    for s in todo:
        for a in s.attempts:  # scenario 内 attempts 已按老 → 新排序
            with _time_back(a.days_ago), _semantic_off():
                reflow_answer(s.question_id, s.question_type,
                              build_answer(list(s.points), list(a.hit_ids)),
                              list(s.points))
                report.answers_written += 1
        report.written.append(s.question_id)
    _save_manifest(seed, sorted(already | set(report.written)))
    return report


def _verify_all(scenarios: list[Scenario]) -> None:
    """写库前本地评分校验：任何一次作答命中与场景预期不符 → 中止整个批次。"""
    with _semantic_off():
        for s in scenarios:
            for a in s.attempts:
                expected = set(a.hit_ids)
                result = score_answer(build_answer(list(s.points), list(a.hit_ids)),
                                      from_benchmark(list(s.points)))
                if set(result.hit_ids) != expected:
                    raise RuntimeError(
                        f"seed 评分校验失败 {s.question_id}（days_ago={a.days_ago}）："
                        f"期望命中 {sorted(expected)}，实际 {sorted(result.hit_ids)} —— 已中止，未写库"
                    )


def _save_manifest(seed: int, ids: list[str]) -> None:
    _MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    data = _load_manifest()
    data.update(kind=_KIND, seeds=sorted(set(data.get("seeds", [])) | {seed}),
                question_ids=ids, updated_at=reflow.utcnow().isoformat())
    _MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@contextmanager
def _time_back(days_ago: int):
    """把 reflow 模块的 utcnow 拨回 days_ago 天前（naive UTC，与 schema.utcnow 同口径）。"""
    fake = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days_ago)
    original = reflow.utcnow
    reflow.utcnow = lambda: fake
    try:
        yield
    finally:
        reflow.utcnow = original


@contextmanager
def _semantic_off():
    """禁用评分语义层（embed_zh → None = 自动降级纯关键词硬匹配）。"""
    original = score.embed_zh
    score.embed_zh = lambda texts: None
    try:
        yield
    finally:
        score.embed_zh = original
