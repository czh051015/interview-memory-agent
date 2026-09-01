"""引擎 A/B 对比（docs/26 §4-§6.2）——同一套金标，现有确定性引擎 vs LLM-as-a-Judge。

A: score_answer（kw + 语义层 τ=SCORE_SEMANTIC_TAU，0 token，100% 可复现）
B: judge_score（LLM 按 rubric 逐点判定 + 强制证据输出，每题 1 次 DeepSeek 调用）

指标（同一批 benchmark/medium 金标 + 全题库 good/bad）：
  fuzzy 漏判率 / nosource 假阳性率   口径同 medium_eval（Σfn/Σexp、Σfp/Σsys）
  F1（7 条 medium 样本 macro）        金标 expected_hit_ids 为 ground truth
  no_fool / discrimination          口径同 score_eval（全题库 36 题）
  重跑一致性                         每条 medium 样本判定 runs 次，逐点 verdict 一致比例（LLM 生命线）
  成本                               LLM 调用次数 / 总耗时

决策（§4 规则）：
  1. B 赢（F1≥0.85、重跑一致≥90%、no_fool=1.0、nosource 假阳性大幅降）→ 默认引擎切 LLM
  2. B 不稳（重跑一致<90%）→ 退回 A，再考虑 C（材料锚定，最后手段）
  3. 否则 → A 保持默认，C 待定

用法：
  python eval/compare_engines.py            # medium 跑 3 次一致性，全题库各 1 次
  python eval/compare_engines.py --runs 1   # 跳过重跑一致性（省调用，快速看结果）
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, ROOT := os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

from src.shenlun.score import from_benchmark, score_answer
from src.shenlun.judge_llm import judge_score

DATA = os.path.join(ROOT, "benchmark", "data")
MEDIUM = os.path.join(ROOT, "benchmark", "medium")


def _load_question(qid: str):
    """benchmark/data 的题：points + 题干/材料（task 字段）+ good/bad 样本。"""
    d = json.load(open(os.path.join(DATA, f"{qid}.json"), encoding="utf-8"))
    task = d.get("task") or {}
    return {
        "points": from_benchmark(d["gold"]["reference_points"]),
        "question": task.get("question", ""),
        "material": task.get("material", ""),
        "good": (d.get("samples") or {}).get("good", {}).get("text", ""),
        "bad": (d.get("samples") or {}).get("bad", {}).get("text", ""),
    }


def _engine_a(answer: str, q: dict):
    sr = score_answer(answer, q["points"], materials=q["material"])
    return sr


def _engine_b(answer: str, q: dict):
    sr, _ = judge_score(answer, q["points"], q["material"], q["question"])
    return sr


def _f1(sys_ids: set, exp: set) -> tuple[float, float, float]:
    """per-sample F1：exp 为空集（nosource 判 0）时 recall=1；sys 为空时 precision=1。"""
    tp = len(sys_ids & exp)
    precision = tp / len(sys_ids) if sys_ids else 1.0
    recall = tp / len(exp) if exp else 1.0
    if precision + recall == 0:
        return precision, recall, 0.0
    return precision, recall, 2 * precision * recall / (precision + recall)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3, help="每条 medium 样本跑几次（默认 3，定稿验证用）")
    ap.add_argument("--quick", action="store_true", help="快速反馈：只跑 medium 样本，默认 runs=1，并发 5")
    ap.add_argument("--concurrency", type=int, default=5, help="快速模式的并发 worker 数，默认 5")
    args = ap.parse_args()

    if args.quick:
        args.runs = 1
        print("[quick] 仅跑 medium 样本（1 次 / 样本），并发 = %d" % args.concurrency)

    # ── medium 金标样本 ──
    medium = []  # {sid, kind, qid, q, text, exp}
    for f in sorted(glob.glob(os.path.join(MEDIUM, "*.json"))):
        m = json.load(open(f, encoding="utf-8"))
        q = _load_question(m["question_id"])
        for s in m["samples"]:
            medium.append({
                "sid": s["id"], "kind": s["kind"], "q": q, "text": s["text"],
                "exp": set(s["expected_hit_ids"]),
            })

    # 卖点：快速档只跑 medium；定稿档才继续全题库统计
    bank = []
    if not args.quick:
        for f in sorted(glob.glob(os.path.join(DATA, "*.json"))):
            qid = os.path.basename(f)[:-5]
            q = _load_question(qid)
            if q["good"] and q["bad"]:
                bank.append((qid, q))

    t0 = time.perf_counter()
    n_llm = 0
    llm_falls = 0  # LLM 失败降级次数（指标被 kw 引擎替代，报告里单独标注）

    def judge(engine, answer, q):
        """带调用计数的引擎入口；LLM 失败降级单独计数（docs/26：降级样本不算 LLM 成绩）。"""
        nonlocal n_llm, llm_falls
        if engine == "B":
            n_llm += 1
            sr, warns = judge_score(answer, q["points"], q["material"], q["question"])
            if warns and any("降级" in w for w in warns):
                llm_falls += 1
            return sr
        return _engine_a(answer, q)

    def verdicts_consistent(runs_verdicts: list[list[bool]]) -> float:
        """runs 次逐点判定一致的比例（每个点 N 次 verdict 全同才算一致）。"""
        total, same = 0, 0
        for col in zip(*runs_verdicts):
            total += 1
            if len(set(col)) == 1:
                same += 1
        return same / total if total else 1.0

    stats = {"A": {}, "B": {}}
    for eng in ("A", "B"):
        fn_tot = exp_tot = fp_tot = sys_tot = 0
        f1s = []
        cons = []

        # medium 评测：可并发加速，但保持同一语义与统计口径
        if args.quick and args.concurrency > 1:
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                futures = [pool.submit(lambda s=smp: (s, judge(eng, s["text"], s["q"]), s["exp"])) for smp in medium]
                for future in as_completed(futures):
                    smp, sr, exp = future.result()
                    sys_ids = {h.id for h in sr.hit_points}
                    if smp["kind"] == "fuzzy":
                        fn_tot += len(exp - sys_ids)
                        exp_tot += len(exp)
                    elif smp["kind"] == "nosource":
                        fp_tot += len(sys_ids - exp)
                        sys_tot += len(sys_ids)
                    _, _, f1 = _f1(sys_ids, exp)
                    f1s.append(f1)
                    cons.append(1.0)
        else:
            for smp in medium:
                verdicts_runs = []
                for _ in range(args.runs):
                    sr = judge(eng, smp["text"], smp["q"])
                    sys_ids = {h.id for h in sr.hit_points}
                    verdicts_runs.append([p.id in sys_ids for p in smp["q"]["points"]])
                    if smp["kind"] == "fuzzy":
                        fn_tot += len(smp["exp"] - sys_ids)
                        exp_tot += len(smp["exp"])
                    elif smp["kind"] == "nosource":
                        fp_tot += len(sys_ids - smp["exp"])
                        sys_tot += len(sys_ids)
                    _, _, f1 = _f1(sys_ids, smp["exp"])
                    f1s.append(f1)
                cons.append(verdicts_consistent(verdicts_runs))

        # nosource_fp_rate 是点级误判率：误判点数 / 系统命中点数（doc 30 口径确认；金标全 0 时数学上恒等于 1.0，不能误判为“指标有问题”）
        stats[eng]["fuzzy_miss_rate"] = fn_tot / exp_tot if exp_tot else None
        stats[eng]["nosource_fp_rate"] = fp_tot / sys_tot if sys_tot else None
        stats[eng]["f1_medium"] = sum(f1s) / len(f1s) if f1s else None
        stats[eng]["consistency"] = sum(cons) / len(cons) if cons else None

        if not args.quick:
            disc, fooled, n = [], 0, 0
            for qid, q in bank:
                gr = judge(eng, q["good"], q).hit_ratio
                br = judge(eng, q["bad"], q).hit_ratio
                disc.append(gr - br)
                n += 1
                if br >= 1.0:
                    fooled += 1
            stats[eng]["no_fool"] = (n - fooled) / n
            stats[eng]["discrimination"] = sum(disc) / n if n else None
            stats[eng]["llm_calls"] = n_llm if eng == "B" else 0
        else:
            stats[eng]["no_fool"] = None
            stats[eng]["discrimination"] = None
            stats[eng]["llm_calls"] = n_llm if eng == "B" else 0

    stats["B"]["llm_falls"] = llm_falls

    elapsed = time.perf_counter() - t0

    def _pct(v):
        return f"{v:.0%}" if isinstance(v, float) else "N/A"

    print("=" * 74)
    print(f"{'指标':<22}{'A 现有(kw+语义)':<20}{'B LLM-as-a-Judge'}")
    print("-" * 74)
    rows = [
        ("fuzzy 漏判率（↓）", stats["A"]["fuzzy_miss_rate"], stats["B"]["fuzzy_miss_rate"]),
        ("nosource 假阳性率（↓）", stats["A"]["nosource_fp_rate"], stats["B"]["nosource_fp_rate"]),
        ("F1（7 条 medium 金标）", stats["A"]["f1_medium"], stats["B"]["f1_medium"]),
        ("no_fool（↑，必须=1.0）", stats["A"]["no_fool"], stats["B"]["no_fool"]),
        ("discrimination（↑）", stats["A"]["discrimination"], stats["B"]["discrimination"]),
        ("重跑一致性（≥90% 生命线）", 1.0, stats["B"]["consistency"]),
        ("LLM 调用次数", 0, stats["B"]["llm_calls"]),
    ]
    for name, a, b in rows:
        print(f"{name:<22}{_pct(a) if name != 'LLM 调用次数' else a:<20}"
              f"{_pct(b) if name != 'LLM 调用次数' else b}")
    if llm_falls:
        print(f"{'降级样本数（LLM失败→kw）':<22}{'-':<20}{llm_falls}（这些样本 B 列实为 A 引擎）")
    print(f"{'总耗时':<22}{'秒级':<20}{elapsed/60:.1f} 分钟")
    print("-" * 74)

    if not args.quick:
        b = stats["B"]
        win = (b["f1_medium"] is not None and b["f1_medium"] >= 0.85
               and b["consistency"] is not None and b["consistency"] >= 0.90
               and b["no_fool"] == 1.0
               and b["nosource_fp_rate"] is not None and b["nosource_fp_rate"] < 0.5)
        print("\n决策（docs/26 §4）：")
        if win:
            print("  ✅ B 赢（F1≥0.85、重跑一致≥90%、no_fool=1.0、nosource 假阳性大幅降）")
            print("     → 默认引擎切 LLM，确定性引擎留作兜底；接入 SCORE_ENGINE + 四维评测进回归")
        elif b["consistency"] is not None and b["consistency"] < 0.90:
            print("  ⚠️ B 不稳（重跑一致性 <90%）→ 退回 A，再考虑 C（材料锚定，最后手段）")
        else:
            print("  ⚠️ B 未全面达标 → A 保持默认引擎；是否回头做 C（材料锚定）待议")

    out = os.path.join(ROOT, "eval", "results", "baseline", "engine_compare.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "elapsed_s": round(elapsed, 1), "runs": args.runs, "quick": args.quick},
                  f, ensure_ascii=False, indent=2)
    print(f"\n明细已写: {out}")


if __name__ == "__main__":
    main()
