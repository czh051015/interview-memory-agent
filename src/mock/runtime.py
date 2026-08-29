"""申论练习运行态（18 计划）：practice_one 逼近循环 + 断点落盘（版本化）+ 恢复。

复用原 mock 的「循环 + 断点 + KeyboardInterrupt 退出保护」骨架（domain 无关资产），
替换判定核心：LLM 面试官（judge_followup）→ 确定性评分（score_answer）+ 逼近引导（LLM 只做提示）。

一次练习 = 一道题的一次完整逼近过程：
  轮0（初稿）：ask_fn 收首答 → score_answer → 达标 → 回流；未达标 → 逼近引导（LLM）→ 用户补充
  轮1..N：累计答案再评分 → 达标 或 轮数上限（不再调 LLM，直接回流）
每轮完成即落盘（断点续练，进度文件显式版本化 v:2，旧文件读失败 → 提示重新开始）。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.config import space_dir
from src.cleaner.schema import utcnow
from src.shenlun.score import from_benchmark, score_answer
from . import MAX_ROUNDS
from .prompts import _APPROACH_PROMPT
# 活引用：LLM 调用一律经包取当前属性（测试 patch 的是 src.mock 命名空间：
# @patch.object(mi, "chat_json")），若缓存为模块全局则 patch 穿透不进来。
import src.mock as _mi

# ── 逼近参数（初值待校准：结构先定死，数字跑起来再调）──
PASS_HIT_RATIO = 0.8      # 达标阈值：命中率 ≥ 0.8（docs/18 §9，与漏点识别语义对齐）
MAX_GUIDED_POINTS = 2     # 一次引导最多 1-2 个漏点（引导太多用户记不住）
PROGRESS_VERSION = 2      # 断点文件版本：不兼容 → 提示重新开始而非静默崩（docs/18 §7）


# ── 逼近循环 ──
@dataclass
class PracticeRound:
    """一轮作答 + 评分结果（round_no 0=初稿，1..N=每轮逼近）。"""
    round_no: int
    answer: str                       # 本轮提交的文本（初稿 / 补充）
    hit_ids: list[str] = field(default_factory=list)
    miss_ids: list[str] = field(default_factory=list)
    hit_ratio: float = 0.0
    guided_point_ids: list[str] = field(default_factory=list)  # 本轮 AI 引导了哪些点
    guidance: str = ""                # 本轮展示给用户的引导文本（round 0 为空）
    full_answer: str = ""             # 累计答案（评分用的是累计，非单轮）

    def to_dict(self) -> dict:
        return {
            "round_no": self.round_no, "answer": self.answer,
            "hit_ids": self.hit_ids, "miss_ids": self.miss_ids,
            "hit_ratio": self.hit_ratio, "guided_point_ids": self.guided_point_ids,
            "guidance": self.guidance, "full_answer": self.full_answer,
        }


@dataclass
class PracticeResult:
    """一次练习的产物：逐轮轨迹 + 是否达标。回流（reflow_answer）由调用方做。"""
    question_id: str
    rounds: list[PracticeRound]
    passed: bool                     # 达标：最后一轮命中率 ≥ 达标阈值

    @property
    def final_answer(self) -> str:
        return self.rounds[-1].full_answer if self.rounds else ""


def _approach_guidance(question: str, material: str, answer: str,
                       miss_ids: list[str], points) -> list[dict]:
    """逼近引导（docs/18 §4.1）：对漏点给 1-2 条「点 + 材料位置」提示。

    只喂漏点的 id/名称/分值（不喂关键词——防 LLM 代写答案）。
    失败返回 []（本轮无引导，练习不阻断）。LLM 输出非法点 id 的条目丢弃。
    """
    miss_points = [p for p in points if p.id in miss_ids]
    if not miss_points:
        return []
    miss_str = "\n".join(f"- [{p.id}] {p.point}（{p.score} 分）" for p in miss_points)
    user_prompt = (
        f"## 题目\n{question}\n\n## 材料\n{material}\n\n"
        f"## 用户最新作答\n{answer}\n\n"
        f"## 漏掉的采分点（只能从这里挑 1-2 个引导）\n{miss_str}"
    )
    try:
        data = _mi.chat_json(_APPROACH_PROMPT, user_prompt, max_tokens=512)
    except Exception as e:
        logging.warning("逼近引导失败，本轮无引导：%s", e)
        return []
    guided: list[dict] = []
    for g in data.get("guidance") or []:
        if not isinstance(g, dict):
            continue
        hint = str(g.get("hint") or "").strip()
        if not hint:
            continue
        pid = str(g.get("point_id") or "")
        p = next((mp for mp in miss_points if mp.id == pid), None)
        if p is None:
            # 兼容只给点名的输出：按名称匹配
            name = str(g.get("point") or "").strip()
            p = next((mp for mp in miss_points if mp.point == name), None)
        if p is None:
            continue
        guided.append({"point_id": p.id, "point": p.point, "hint": hint})
        if len(guided) >= MAX_GUIDED_POINTS:
            break
    return guided


def _format_guidance(guided: list[dict]) -> str:
    """引导列表 → 展示文本（每轮存档 guidance 字段）。"""
    return "\n".join(f"· {g['point']}：{g['hint']}" for g in guided)


def practice_one(
    question_id: str,
    question: str,
    material: str,
    points,
    ask_fn,
    *,
    max_rounds: int = MAX_ROUNDS,
    pass_ratio: float = PASS_HIT_RATIO,
    progress_path: str | None = None,
    resume_rounds: list[dict] | None = None,
) -> PracticeResult:
    """一次练习 = 一道题的一次完整逼近过程（docs/18 §4.2）。

    轮0（初稿）：ask_fn(question, material, None) 收首答 → score_answer →
      达标（命中率 ≥ pass_ratio）→ 回流；未达标 → 逼近引导（LLM）→ ask_fn 收补充
    轮1..N：累计答案再评分 → 达标 或 轮数上限（不再调 LLM，直接回流）。
    每轮完成即落盘（progress_path 给定则存，断点续练）。

    ask_fn(question, material, guidance) -> str：
      guidance=None 表示收初稿；否则 guidance 为引导列表（可能为空=无引导），收补充。
    在 ask_fn 内抛 KeyboardInterrupt/EOFError 会向上传播——已完成轮次已落盘，可续练。

    resume_rounds：断点恢复时传入已完成轮次（PracticeRound.to_dict() 列表），
      从下一轮继续（guidance 按上一轮漏点重新生成）。
    """
    rounds = [PracticeRound(**r) for r in (resume_rounds or [])]
    while len(rounds) < max_rounds:
        round_no = len(rounds)
        if round_no == 0:
            guided: list[dict] = []
            guided_ids: list[str] = []
            guidance_text = ""
            text = ask_fn(question, material, None)
        else:
            last = rounds[-1]
            guided = _approach_guidance(question, material, last.full_answer,
                                        last.miss_ids, points)
            guided_ids = [g["point_id"] for g in guided]
            guidance_text = _format_guidance(guided)
            text = ask_fn(question, material, guided)

        full_answer = "\n".join([r.answer for r in rounds] + [text]).strip("\n")
        sr = score_answer(full_answer, points)
        pr = PracticeRound(
            round_no=round_no, answer=text,
            hit_ids=sr.hit_ids, miss_ids=sr.miss_ids,
            hit_ratio=round(sr.hit_ratio, 4),
            guided_point_ids=guided_ids, guidance=guidance_text,
            full_answer=full_answer,
        )
        rounds.append(pr)
        if progress_path:
            _save_practice(progress_path, question_id=question_id, question=question,
                           material=material, points=points, max_rounds=max_rounds,
                           pass_ratio=pass_ratio, rounds=rounds)
        if sr.hit_ratio >= pass_ratio:
            return PracticeResult(question_id=question_id, rounds=rounds, passed=True)
    return PracticeResult(question_id=question_id, rounds=rounds, passed=False)


# ── 断点保护：边练边落盘 + 版本化恢复 ──
def _progress_file():
    """当前空间的练习进度落盘文件（按空间分目录）。

    文件内容（v:2）：当前题 id + 题目/材料/采分点 + 轮次 + 每轮答案（续练用）。
    """
    return space_dir() / "practice_progress.json"


def _points_to_dicts(points) -> list[dict]:
    """engine Point（或 benchmark 字典）→ reference_points 字典（progress 存档用）。"""
    out = []
    for p in points:
        if isinstance(p, dict):
            out.append({"id": p["id"], "point": p["point"], "keywords": p["keywords"],
                        "score": int(p.get("score", 1))})
        else:
            out.append({"id": p.id, "point": p.point, "keywords": p.keywords, "score": p.score})
    return out


def _save_practice(progress_path: str, *, question_id: str, question: str, material: str,
                   points, max_rounds: int, pass_ratio: float, rounds: list[PracticeRound]) -> None:
    """把当前练习进度落盘。失败不阻断练习（记录 warning）。"""
    try:
        data = {
            "v": PROGRESS_VERSION,
            "ts": utcnow().isoformat(),
            "question_id": question_id,
            "question": question,
            "material": material,
            "points": _points_to_dicts(points),
            "max_rounds": max_rounds,
            "pass_ratio": pass_ratio,
            "rounds": [r.to_dict() for r in rounds],
        }
        Path(progress_path).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logging.warning("练习进度落盘失败：%s", e)


def _load_practice(progress_path: str) -> dict | None:
    """读回上次未完成的练习。文件缺失/损坏/版本不兼容 → None（提示重新开始）。"""
    p = Path(progress_path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("v") != PROGRESS_VERSION:
            logging.warning("练习进度文件版本不兼容（v=%s，期望 v=%s），重新开始",
                            data.get("v"), PROGRESS_VERSION)
            return None
        return data
    except Exception as e:
        logging.warning("练习进度读取失败：%s", e)
        return None


def _clear_practice(progress_path: str) -> None:
    """回流成功后清掉落盘，表示本题已完成。"""
    try:
        Path(progress_path).unlink(missing_ok=True)
    except Exception as e:
        logging.warning("清理练习进度失败：%s", e)
