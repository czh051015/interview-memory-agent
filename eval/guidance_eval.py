"""申论逼近引导评测 —— _APPROACH_PROMPT 红线 + 质量（docs/19 §4.3）。

评的对象：src.mock.prompts._APPROACH_PROMPT（逼近引导，LLM 只提示「漏了什么 + 去哪里找」，不代写）。
样本：benchmark/data 的 samples.bad（跑题答，漏点已知）+ 少量「半吊子答」（good 截断派生，部分命中）。
每样本：score_answer(作答) → 真实漏点集 → 按 src/mock/runtime.py `_approach_guidance` 的 user_prompt
格式调 _APPROACH_PROMPT（user_prompt 与运行时保持一致，改格式需同步 runtime）→ 校验引导输出。

红线（必须，门槛 == 1.0，docs/18 §7 风险 1 的自动化）：
  - no_spoiler     hint 不含参考答案独有整句（good-text 的 ≥14 字连续子串、去停用字归一化后
                    仍不在材料里）→ 代写。校准记录（2026-08-29 首轮）：初值「≥6字子串或 ≥2 个
                    关键词」在 20/20 误报——hint 引用材料术语/叙述是产品标准引导（材料第X段有X），
                    材料与满分作答大量重合（江苏材料为摘要版），子串与关键词口径无法区分「引用材料」
                    vs「代写」；人工复核 20 条后改为「答案独有整句」口径（≥14 字实质整句；
                    12 字内短引与合格引导重叠，交给 judge + 人工层），docs/19 §10
  - no_fabrication LLM 返回的 point_id ∈ 该题真实漏点集（不引导已命中的点、不引导金标没有的点）
质量（门槛初值，待校准）：
  - hint_grounded  hint 提到材料位置/事例/材料短语（≥4字锚点词 或 ≥5字材料子串），而非空话 ≥ 0.8
  - judge_score    LLM-as-judge 对「引导有用性」打分 1-5，人工抽验裁判，只报告

用法：
  python eval/guidance_eval.py
  python eval/guidance_eval.py --only 归纳概括
  python eval/guidance_eval.py --out eval/guidance_eval_results.json
输出：eval/guidance_eval_results.json（顶层字段供 run_evals extract_summary 扁平化）
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

sys.path.insert(0, ROOT := os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.llm import chat_json
from src.mock.prompts import _APPROACH_PROMPT
from src.shenlun.score import from_benchmark, score_answer

DATA = os.path.join(ROOT, "benchmark", "data")

BAD_PER_TYPE = 4          # 跑题答每题型抽样数（提出对策只有 3 题）
HALF_DONE_PER_TYPE = 1    # 半吊子答每题型 1 条（good 截断派生，docs/19 §9.3 推荐 C）
MAX_GUIDED_POINTS = 2     # 与 runtime 一致：一次最多引导 1-2 个漏点
JUDGE_MAX_SAMPLES = 8

# 门槛初值（docs/19 §4.3，待校准）
THRESHOLDS = {"no_spoiler": 1.0, "no_fabrication": 1.0, "hint_grounded": 0.8}

JUDGE_SYSTEM = (
    "你是「申论逼近引导」的质检裁判。用户写申论作答漏了若干采分点，陪练 LLM 给出引导提示"
    "（只允许提示「漏了什么 + 去哪里找」，不得代写答案）。\n"
    "对每条 hint 独立判断：\n"
    "1. 有用性打分 1-5：1-2 空话（没指向材料位置/事例，用户不知道去哪找）；"
    "3 一般（有方向但不够具体）；4-5 有用（指出材料具体位置/事例/名词，能帮用户回忆起漏点）。\n"
    "2. spoiler：hint 是否直接写出了参考答案原句或关键词串（代写红线），写了一个以上完整关键词即视为 spoiler。\n"
    "只输出 JSON：\n"
    '{"scores": [{"hint": "引导提示原文", "score": 1-5, "spoiler": true/false, "note": "一句评价"}]}'
)


def _half_done(good_text: str) -> str:
    """半吊子答：good 截断至 60% 派生（模拟「时间不够，写了一半没写完」），漏点由评分器实测。"""
    cut = int(len(good_text) * 0.6)
    return good_text[:cut].rstrip() + "……（时间不够，先写到这里）"


def _gold_anchors(d: dict) -> tuple[list[str], list[str]]:
    """材料锚点：金标关键词里同时出现在材料中的（hint 提到它们 = 指向具体事例）。
    另返回金标全部关键词（原句/关键词串比对用）。"""
    material = d.get("task", {}).get("material", "")
    all_kws: list[str] = []
    anchors: list[str] = []
    for g in d.get("gold", {}).get("reference_points", []):
        for kw in g.get("keywords", []):
            kw = str(kw)
            if len(kw) >= 2:
                all_kws.append(kw)
            if len(kw) >= 3 and kw in material:
                anchors.append(kw)
    return anchors, all_kws


# 停用字（归一化用，只影响比较）：标点 + 虚词，消除「相关的」vs「息息相关」这类措辞差异
_SPOILER_STOP = r"[，。、；：？！（）()“”\"'《》\s]+|的|与|了|并|等|和|及|还"


def _is_spoiler(hint: str, good_text: str, material: str) -> bool:
    """代写红线判定（2026-08-29 校准后口径，docs/19 §10）：答案独有整句。

    规则：hint 含 good-text（参考答案全文）的 ≥14 字连续子串，且该子串去停用字归一化后
    不在材料里 → 代写（写出了参考答案独有的组织句/概括语）。
    材料引用（含材料叙述转述、引号短引、12 字内短串）放行——产品标准引导「材料第X段有X」。
    校准依据：首轮 20/20 误报人工复核，全部为合格引导；真代写反例
    「把骂声当作改进工作的动力」可被 ≥14 字规则命中。
    """
    nm = re.sub(_SPOILER_STOP, "", material)
    for i in range(max(0, len(good_text) - 13)):
        seg = good_text[i:i + 14]
        if seg in hint and re.sub(_SPOILER_STOP, "", seg) not in nm:
            return True
    return False


def _is_grounded(hint: str, anchors: list[str], material: str) -> bool:
    """hint 是否指向材料位置/事例（非空话）：材料锚点名词、第X段/事例/案例 标记，
    或 ≥5 字材料子串重叠（校准：首轮 6 条空话误报全部为材料具体内容复述，补 5-gram 口径）。"""
    if any(a in hint for a in anchors):
        return True
    if re.search(r"第\s*\d*\s*段", hint) or "事例" in hint or "案例" in hint:
        return True
    return any(material[i:i + 5] in hint for i in range(max(0, len(material) - 4)))


def run_guidance(d: dict, answer: str) -> dict:
    """复刻 runtime._approach_guidance 的调用与过滤（docs/18 §4.1），返回引导 + 红线原始值。"""
    task, gold = d.get("task", {}), d.get("gold", {})
    points = from_benchmark(gold.get("reference_points", []))
    question = str(task.get("question") or "")
    material = str(task.get("material") or "")
    good_text = (d.get("samples", {}).get("good", {}).get("text") or "")

    miss_ids = score_answer(answer, points).miss_ids
    miss_points = [p for p in points if p.id in miss_ids]
    if not miss_points:
        return {"id": d.get("id", ""), "miss_ids": [], "guided": [], "raw": []}

    miss_str = "\n".join(f"- [{p.id}] {p.point}（{p.score} 分）" for p in miss_points)
    user_prompt = (
        f"## 题目\n{question}\n\n## 材料\n{material}\n\n"
        f"## 用户最新作答\n{answer}\n\n"
        f"## 漏掉的采分点（只能从这里挑 1-2 个引导）\n{miss_str}"
    )
    try:
        data = chat_json(_APPROACH_PROMPT, user_prompt, max_tokens=512)
    except Exception as e:
        print(f"  [失败] {d.get('id')} 引导调用失败: {e}")
        return {"id": d.get("id", ""), "error": str(e), "miss_ids": miss_ids,
                "guided": [], "raw": []}

    # 过滤逻辑与 runtime 一致：id 匹配 → 名称匹配 → 丢弃；上限 1-2 条
    raw: list[dict] = []
    guided: list[dict] = []
    fabricated = 0  # 红线：raw 条目指向漏点集之外（已命中的点或金标没有的点）
    for g in data.get("guidance") or []:
        if not isinstance(g, dict):
            continue
        hint = str(g.get("hint") or "").strip()
        if not hint:
            continue
        raw.append(g)
        pid = str(g.get("point_id") or "")
        p = next((mp for mp in miss_points if mp.id == pid), None)
        if p is None:
            name = str(g.get("point") or "").strip()
            p = next((mp for mp in miss_points if mp.point == name), None)
        if p is None:
            fabricated += 1
            continue
        guided.append({"point_id": p.id, "point": p.point, "hint": hint})
        if len(guided) >= MAX_GUIDED_POINTS:
            break

    anchors, _all_kws = _gold_anchors(d)
    return {
        "id": d.get("id", ""),
        "miss_ids": miss_ids,
        "raw": raw,               # LLM 原始返回（含 hint 的条目）
        "guided": guided,         # 过滤后的有效引导（产品实际展示）
        "fabricated": fabricated,
        "spoiler_flags": [g["hint"] for g in guided if _is_spoiler(g["hint"], good_text, material)],
        "ungrounded_flags": [g["hint"] for g in guided if not _is_grounded(g["hint"], anchors, material)],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只看某题型，如 提出对策")
    ap.add_argument("--out", default=os.path.join(ROOT, "eval", "results", "baseline", "guidance_eval_results.json"))
    args = ap.parse_args()

    # 样本选型（docs/19 §9.3 推荐 C）：跑题答每题型 BAD_PER_TYPE 条 + 半吊子答每题型 1 条
    by_type: dict[str, list[dict]] = defaultdict(list)
    for f in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        by_type[d.get("meta", {}).get("type", "?")].append(d)

    samples: list[tuple[dict, str, str]] = []  # (benchmark, answer, kind)
    for typ, files in sorted(by_type.items()):
        if args.only and typ != args.only:
            continue
        for d in files[:BAD_PER_TYPE]:
            bad = d.get("samples", {}).get("bad", {}).get("text", "")
            if bad:
                samples.append((d, bad, "bad"))
        for d in files[:HALF_DONE_PER_TYPE]:
            good = d.get("samples", {}).get("good", {}).get("text", "")
            if good:
                samples.append((d, _half_done(good), "half_done"))

    rows: list[dict] = []
    n_guidance = n_spoiler_ok = n_grounded_ok = n_fabricated = n_returned = n_empty = 0
    flagged: list[dict] = []
    for d, answer, kind in samples:
        r = run_guidance(d, answer)
        r["answer_kind"] = kind
        r["type"] = d.get("meta", {}).get("type", "?")
        if "error" in r:
            print(f"  [✗] {r['id']} {kind}: 调用失败")
            rows.append(r)
            continue
        guided = r["guided"]
        n_returned += len(r["raw"])
        n_fabricated += r["fabricated"]
        if not guided:
            n_empty += 1
        else:
            n_guidance += 1
            spoiler_ok = not r["spoiler_flags"]
            grounded_ok = not r["ungrounded_flags"]
            n_spoiler_ok += int(spoiler_ok)
            n_grounded_ok += int(grounded_ok)
            if not spoiler_ok or not grounded_ok:
                flagged.append({"id": r["id"], "kind": kind,
                                "spoiler": r["spoiler_flags"], "ungrounded": r["ungrounded_flags"]})
        print(f"  {r['id']:<22} {r['type']:<6} {kind:<9} 漏点{len(r['miss_ids']):>2} "
              f"引导{len(guided)}/返回{len(r['raw'])} "
              f"{'⚠️代写' if r['spoiler_flags'] else ''}{'⚠️空话' if r['ungrounded_flags'] else ''}")
        rows.append(r)

    no_spoiler = round(n_spoiler_ok / n_guidance, 3) if n_guidance else None
    hint_grounded = round(n_grounded_ok / n_guidance, 3) if n_guidance else None
    no_fabrication = round(1 - n_fabricated / n_returned, 3) if n_returned else None

    # ── LLM-as-judge：引导有用性打分（抽样 ≤8 条，附题目/作答上下文）──
    judge_samples = [s for s, r in zip(samples, rows) if r.get("guided")][:JUDGE_MAX_SAMPLES]
    scores: list[int] = []
    judge_spoilers: list[dict] = []
    for d, answer, _kind in judge_samples:
        r = next(x for x in rows if x["id"] == d["id"])
        hints = "；".join(f"[{g['point']}] {g['hint']}" for g in r["guided"])
        user_prompt = (f"## 题目\n{d.get('task', {}).get('question', '')}\n\n"
                       f"## 用户作答（片段）\n{answer[:300]}\n\n"
                       f"## 引导提示\n{hints}")
        try:
            verdict = chat_json(JUDGE_SYSTEM, user_prompt, max_tokens=1024)
        except Exception as e:
            print(f"  [judge] {d['id']} 裁判调用失败: {e}")
            continue
        for s in verdict.get("scores", []):
            try:
                scores.append(int(s.get("score")))
            except (TypeError, ValueError):
                continue
            if s.get("spoiler"):
                judge_spoilers.append({"id": d["id"], "hint": s.get("hint"), "note": s.get("note")})
    judge_score = {"mean": round(sum(scores) / len(scores), 2), "samples": len(scores)} if scores else None

    llm_calls = len(samples) + len(judge_samples)

    summary = {
        "sample_count": len(samples),
        "no_spoiler": no_spoiler,
        "no_fabrication": no_fabrication,
        "hint_grounded": hint_grounded,
        "judge_score": judge_score,
        "judge_spoiler_flags": judge_spoilers,
        "empty_guidance_count": n_empty,
        "llm_calls": llm_calls,
        "thresholds": THRESHOLDS,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump({"summary": summary, "rows": rows, "flagged": flagged},
              open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"样本数: {len(samples)}（bad {sum(1 for r in rows if r.get('answer_kind') == 'bad')} "
          f"+ half_done {sum(1 for r in rows if r.get('answer_kind') == 'half_done')}）")
    print(f"no_spoiler（无代写）:      {no_spoiler}  （门槛 == 1.0，{n_spoiler_ok}/{n_guidance} 有引导样本通过）")
    print(f"no_fabrication（漏点集内）: {no_fabrication}  （门槛 == 1.0，臆造 {n_fabricated}/{n_returned} 条返回）")
    print(f"hint_grounded（非空话）:   {hint_grounded}  （门槛 ≥ {THRESHOLDS['hint_grounded']}）")
    if judge_score:
        print(f"judge 有用性打分: {judge_score['mean']}/5（抽样 {judge_score['samples']} 条，人工抽验裁判）")
    if judge_spoilers:
        print(f"⚠️ judge 认为代写: {judge_spoilers}")
    if n_empty:
        print(f"⚠️ 空引导样本: {n_empty} 条（LLM 没给任何提示）")
    if flagged:
        print(f"⚠️ 需人工复核 {len(flagged)} 条（明细见 flagged 字段）")
    print(f"LLM 调用量: {llm_calls}")
    print(f"结果已落盘 → {args.out}")


if __name__ == "__main__":
    main()
