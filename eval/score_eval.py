"""申论评分传感器评测 —— 验证 benchmark 的「漏点识别」可靠性。

不调 LLM，纯确定性，秒级。
指标（对齐 2026-08-28 拍板的评分降级方案）：
  - discrimination = mean(good_ratio - bad_ratio)，越大区分力越强（理想接近 1）
  - no_fool       = 跑题答(bad) 未被误判「全命中」的比例，必须 == 1.0
  - 另报：good 漏点（good_ratio 偏低=采分点标得不够全）、bad 误命中（bad_ratio 偏高=关键词太泛）

输出顶层字段（docs/19 §4.1，供 run_evals extract_summary 扁平化）：
  data_count / n_points / mean_discrimination / no_fool / per_type / rows

用法：
  python eval/score_eval.py
  python eval/score_eval.py --only 提出对策        # 只看某题型
  python eval/score_eval.py --out eval/score_eval_results.json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, ROOT := os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.shenlun.score import from_benchmark, score_answer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "benchmark", "data")


def load_file(path: str):
    d = json.load(open(path, encoding="utf-8"))
    points = from_benchmark(d["gold"]["reference_points"])
    good = d.get("samples", {}).get("good", {}).get("text", "")
    bad = d.get("samples", {}).get("bad", {}).get("text", "")
    return d, points, good, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只看某题型，如 提出对策")
    ap.add_argument("--out", default=os.path.join(ROOT, "eval", "score_eval_results.json"))
    args = ap.parse_args()

    rows = []
    for f in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        try:
            d, points, good, bad = load_file(f)
        except Exception as e:
            print(f"  [跳过] {os.path.basename(f)} 加载失败: {e}")
            continue
        typ = d.get("meta", {}).get("type", "?")
        if args.only and typ != args.only:
            continue
        good_r = score_answer(good, points).hit_ratio if good else 0.0
        bad_r = score_answer(bad, points).hit_ratio if bad else 0.0
        rows.append({
            "id": d["id"], "type": typ,
            "n_points": len(points),
            "good_ratio": round(good_r, 3),
            "bad_ratio": round(bad_r, 3),
            "discrimination": round(good_r - bad_r, 3),
            "bad_fooled": bad_r >= 1.0,        # 跑题答被误判全命中
            "good_leak": good_r < 0.8,         # 满分答都没命中 80% 点
        })

    if not rows:
        print("无数据")
        return

    n = len(rows)
    mean_disc = sum(r["discrimination"] for r in rows) / n
    no_fool = sum(1 for r in rows if not r["bad_fooled"]) / n
    good_leak = sum(1 for r in rows if r["good_leak"])
    fooled = [r["id"] for r in rows if r["bad_fooled"]]
    n_points = sum(r["n_points"] for r in rows)

    by_type = defaultdict(list)
    for r in rows:
        by_type[r["type"]].append(r["discrimination"])
    type_disc = {t: round(sum(v) / len(v), 3) for t, v in by_type.items()}

    # 顶层字段稳定化（docs/19 §4.1 升级点 2）：extract_summary 直接扁平化这些字段
    out = {
        "data_count": n,
        "n_points": n_points,
        "mean_discrimination": round(mean_disc, 3),
        "no_fool": round(no_fool, 3),
        "per_type": type_disc,
        "good_leak_count": good_leak,
        "bad_fooled_ids": fooled,
        "rows": rows,
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(out, open(args.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    print(f"评测题数: {n}")
    print(f"mean discrimination (好答−跑题答命中差): {mean_disc:.3f}  （越接近1越强）")
    print(f"no_fool (跑题答未被误判满分):            {no_fool:.3f}  （必须=1.0）")
    print(f"per-type discrimination: {type_disc}")
    if fooled:
        print(f"  ⚠️ {len(fooled)} 道 bad 被误判全命中(需修关键词): {fooled}")
    else:
        print("  ✅ 无 bad 被误判全命中")
    if good_leak:
        leak_ids = [r["id"] for r in rows if r["good_leak"]]
        print(f"  ⚠️ {good_leak} 道 good 命中<0.8(采分点可能标漏): {leak_ids}")
    print(f"\n明细已写: {args.out}")


if __name__ == "__main__":
    main()
