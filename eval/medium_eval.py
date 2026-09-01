"""medium 档（中间态）评测 —— 验证评分传感器在真实中间态上的表现。

背景（docs/24 讨论）：baseline 只有 good（满分答）/ bad（跑题答）两档极端，
discrimination 0.899 只证明「极端可区分」，测不到中间态。真实申论阅卷里
「没得满分」主要是三类：没写（bad 已覆盖）、表达模糊（fuzzy）、写了没结合材料（nosource）。

本脚本读 benchmark/medium/*.json（人工按真实阅卷规则标注 expected_hit_ids），
跑 score_answer（纯关键词匹配，与线上一致），对比系统命中 vs 人工期望：
  - fuzzy 样本：期望给分但系统未命中 → 假阴性（漏判）→ 证明「硬匹配对中文同义改写脆弱」
  - nosource 样本：系统命中但期望不给分 → 假阳性（误判）→ 证明「缺材料结合度维度」

用法：
  python eval/medium_eval.py          # 跑全部 medium 样本
  python eval/medium_eval.py --only 归纳概括
  python eval/medium_eval.py --out eval/medium_eval_results.json
输出：medium_eval_results.json（summary 顶层字段供 run_evals extract_summary 扁平化，
  fuzzy_miss_rate / nosource_fp_rate 为 docs/24 接进 HEADLINE 的 2 项指标，方向 ↓）
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, ROOT := os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

from src.shenlun.score import from_benchmark, score_answer

DATA = os.path.join(ROOT, "benchmark", "data")
MEDIUM = os.path.join(ROOT, "benchmark", "medium")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只看某题型，如 归纳概括")
    ap.add_argument("--out",
                    default=os.path.join(ROOT, "eval", "results", "baseline", "medium_eval_results.json"),
                    help="结果 json 路径（run_evals 从 eval/results/baseline/ 拷贝归档）")
    args = ap.parse_args()

    rows = []
    for f in sorted(glob.glob(os.path.join(MEDIUM, "*.json"))):
        m = json.load(open(f, encoding="utf-8"))
        if args.only and m.get("type") != args.only:
            continue
        qf = os.path.join(DATA, f"{m['question_id']}.json")
        if not os.path.exists(qf):
            print(f"  [跳过] 找不到基准题 {m['question_id']}")
            continue
        d = json.load(open(qf, encoding="utf-8"))
        points = from_benchmark(d["gold"]["reference_points"])
        id2point = {p.id: p.point for p in points}
        for s in m["samples"]:
            sr = score_answer(s["text"], points)
            sys_hits = {h.id for h in sr.hit_points}
            exp = set(s["expected_hit_ids"])
            fn = exp - sys_hits          # 该给分但系统没给（漏判）
            fp = sys_hits - exp          # 系统给了但人工不该给（误判）
            rows.append({
                "qid": m["question_id"], "type": m.get("type", "?"),
                "sid": s["id"], "kind": s["kind"],
                "n_points": len(points),
                "exp_hits": len(exp), "sys_hits": len(sys_hits),
                "fn": sorted(fn), "fp": sorted(fp),
                "fn_names": [id2point.get(i, i) for i in sorted(fn)],
                "fp_names": [id2point.get(i, i) for i in sorted(fp)],
                "note": s.get("note", ""),
            })

    # ── 汇总指标（docs/24：fuzzy 漏判率 / nosource 假阳性率，方向 ↓）──
    fuzzy = [r for r in rows if r["kind"] == "fuzzy"]
    nosrc = [r for r in rows if r["kind"] == "nosource"]
    summary = {"sample_count": len(rows), "llm_calls": 0}
    if fuzzy:
        total_fn = sum(len(r["fn"]) for r in fuzzy)
        total_exp = sum(r["exp_hits"] for r in fuzzy)
        summary["fuzzy_n"] = len(fuzzy)
        summary["fuzzy_total_exp"] = total_exp
        summary["fuzzy_total_fn"] = total_fn
        # 期望给分 0 点则比率无定义 → None（对比时显示 N/A）
        summary["fuzzy_miss_rate"] = round(total_fn / total_exp, 4) if total_exp else None
    else:
        summary.update(fuzzy_n=0, fuzzy_total_exp=0, fuzzy_total_fn=0, fuzzy_miss_rate=None)
    if nosrc:
        total_fp = sum(len(r["fp"]) for r in nosrc)
        total_sys = sum(r["sys_hits"] for r in nosrc)
        summary["nosource_n"] = len(nosrc)
        summary["nosource_total_sys"] = total_sys
        summary["nosource_total_fp"] = total_fp
        summary["nosource_fp_rate"] = round(total_fp / total_sys, 4) if total_sys else None
    else:
        summary.update(nosource_n=0, nosource_total_sys=0, nosource_total_fp=0, nosource_fp_rate=None)

    # 归档（默认 eval/results/baseline/medium_eval_results.json，供 run_evals 拷贝）
    out = args.out
    parent = os.path.dirname(out)
    if parent:  # 相对路径无目录（如 ./x.json）时跳过
        os.makedirs(parent, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "rows": rows}, f, ensure_ascii=False, indent=2)

    if not rows:
        print("无样本")
        return

    print("=" * 78)
    print(f"{'样本':<28}{'类':<8}{'期望':<4}{'系统':<4}{'漏判(fuzzy)':<14}{'误判(nosource)'}")
    print("-" * 78)
    for r in rows:
        fn_s = "、".join(r["fn_names"][:3]) or "-"
        fp_s = "、".join(r["fp_names"][:3]) or "-"
        print(f"{r['sid']:<28}{r['kind']:<8}{r['exp_hits']:<4}{r['sys_hits']:<4}"
              f"{fn_s[:13]:<14}{fp_s[:20]}")
        if r["note"]:
            print(f"    └ {r['note'][:70]}")
    print("-" * 78)

    def _pct(v):
        return f"{v:.0%}" if isinstance(v, float) else "N/A"

    if fuzzy:
        print(f"\nfuzzy（表达模糊）: {summary['fuzzy_n']} 条，期望给分 {summary['fuzzy_total_exp']} 点，系统漏判 {summary['fuzzy_total_fn']} 点"
              f"（漏判率 {_pct(summary['fuzzy_miss_rate'])}）→ 漏判率越高，硬匹配对同义改写越脆弱")
    if nosrc:
        print(f"nosource（没结合材料）: {summary['nosource_n']} 条，系统命中 {summary['nosource_total_sys']} 点，人工判定其中 {summary['nosource_total_fp']} 点不该给分"
              f"（假阳性率 {_pct(summary['nosource_fp_rate'])}）→ 假阳性越高，越缺'材料结合度'维度")


if __name__ == "__main__":
    main()
