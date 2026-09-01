"""申论示证评测 —— 示证 eval（docs/22 §6，替代旧 guidance_eval）。

评的对象：docs/22 新范式后端（score L1 材料锚定 + guidance 单点示证）。
⚠️ 旧 guidance_eval.py 测旧 _APPROACH_PROMPT（苏格拉底逼问），其红线（no_position /
no_overcopy / no_keyword_spoiler / no_spoiler / evidence_spoiler）设计意图是「引导但不
泄露」，与示证「直接给关键词/示范表述/材料原话」哲学相反，不能复用测新后端（会系统性红失败）。

红线重新定义（docs/22 §6）：
  - no_fabrication     示证点必须真在漏点集 + 材料原话真出自材料（material_source 可溯源，不能编）
  - no_full_answer     示范表述禁止替用户写完整作答段落（新红线；允许含关键词/材料原话/骨架）
  - material_anchored  L3 材料锚定必须真有出处（引号内原话确实是材料句子）
  另报告（不设门槛）：anchored_coverage（漏点锚定覆盖率）、hit_snippet（命中片段覆盖率）、
  leading_ok（推 1 个 = score 最大漏点，eval 无档案走确定性分支）。

保留不重跑：score_eval（判定区分力）+ decompose_eval（散文式拆解兜底质量，Q6 主路径 0 token）。

用法：
  python eval/demo_eval.py
  python eval/demo_eval.py --only 归纳概括
  python eval/demo_eval.py --out eval/demo_eval_results.json
输出：demo_eval_results.json（summary 顶层字段供 run_evals extract_summary 扁平化）
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

from src.shenlun.score import _anchor_sentences, from_benchmark, score_answer
from src.mock.runtime import guidance, pick_leading_point

# eval 必须无档案可复现：pick_leading_point 会读 reflow.DB_PATH 的 weak_points，
# 本机开发期留下的练习档案会让红档优先分支介入（推的 1 个 ≠ score 最大），
# 污染 leading_ok 判定 → 隔离到临时 DB（docs/22 §6「eval 无档案走确定性分支」）。
import tempfile

from src.shenlun import reflow

reflow.DB_PATH = os.path.join(tempfile.mkdtemp(prefix="demo_eval_"), "shenlun.db")

DATA = os.path.join(ROOT, "benchmark", "data")

BAD_PER_TYPE = 4          # 跑题答每题型抽样数（提出对策只有 3 题）
HALF_DONE_PER_TYPE = 1    # 半吊子答每题型 1 条（good 截断派生，docs/19 §9.3 推荐 C）

THRESHOLDS = {
    "no_fabrication": 1.0,   # 示证点∈漏点集 + 材料原话真出自材料（确定性为主，门槛 1.0）
    "no_full_answer": 1.0,   # 示范不代写完整作答段落（LLM 产物，门槛 1.0，违规人工复核）
    "material_anchored": 1.0,  # L3 材料锚定有真出处（确定性，必须 1.0）
}

# 停用字（归一化用，只影响比较）：标点 + 高频虚词
_STOP = r"[，。、；：？！（）()“”\"'《》\s]+|的|与|了|并|等|和|及|还|在|为|是|中|有|不|也|就|都|对|从|由|被"
_FULL_ANSWER_MIN = 20   # 去停用字后与参考答案的最长公共子串 ≥ 20 字 → 视为代写整句（初值待校准）


def _norm(s: str) -> str:
    return re.sub(_STOP, "", s)


def _lcs_substring(a: str, b: str) -> str:
    """最长公共子串（DP，材料 ≤2k 字量级可接受）。"""
    n, m = len(a), len(b)
    if n == 0 or m == 0:
        return ""
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    best = (0, 0, 0)  # (len, i, j)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
                if dp[i][j] > best[0]:
                    best = (dp[i][j], i, j)
    ln, i, _j = best
    return a[i - ln:i]


def _quote_anchored(source: str | None, material: str) -> bool:
    """L3 材料锚定校验：source 非空时，引号内原话（去尾部省略号）确实是材料某句的内容。"""
    if not source:
        return True  # 未锚到不算失败（锚不到是材料没覆盖该点），由 anchored_coverage 报告
    m = re.search(r"'([^']+)'", source)
    if not m:
        return False
    quote = m.group(1).rstrip("…").strip()
    if not quote:
        return False
    return any(quote in sent for _pno, sent in _anchor_sentences(material))


def _full_answer_ok(demo: str, good_text: str, material: str) -> bool:
    """新红线 no_full_answer（docs/22 §6）：demo 不得替用户写完整作答段落。

    判定：demo 与参考答案（good_text）去停用字归一化后，最长公共子串 ≥ 20 字
    且该子串不是材料原话 → 写出了参考答案独有的组织句 = 代写。
    材料引用放行（示证哲学允许给材料原话）；示范含关键词/骨架放行。
    （阈值初值待校准，违规条目进 flags 人工复核）
    """
    if not demo:
        return True
    sub = _lcs_substring(_norm(demo), _norm(good_text))
    if len(sub) >= _FULL_ANSWER_MIN and sub not in _norm(material):
        return False
    return True


def _half_done(good_text: str) -> str:
    """半吊子答：good 截断至 60% 派生（模拟「时间不够，写了一半没写完」），漏点由评分器实测。"""
    cut = int(len(good_text) * 0.6)
    return good_text[:cut].rstrip() + "……（时间不够，先写到这里）"


def run_sample(d: dict, answer: str, kind: str) -> dict:
    """跑一个样本：L1（确定性）→ 推 1 个 → 示证（LLM），返回指标原始值。"""
    task, gold = d.get("task", {}), d.get("gold", {})
    material = str(task.get("material") or "")
    good_text = (d.get("samples", {}).get("good", {}).get("text") or "")
    points = from_benchmark(gold.get("reference_points", []))
    sr = score_answer(answer, points, materials=material)

    # L1 材料锚定（确定性）：非空 source 必须真有出处
    anchored_total = sum(1 for p in sr.miss_points if p.material_source)
    anchor_fails = [p.point for p in sr.miss_points
                    if p.material_source and not _quote_anchored(p.material_source, material)]
    hit_missing_snippet = [p.point for p in sr.hit_points if not p.matched_text]

    # 推 1 个：eval 无档案 → 确定性分支（score 最大）
    leading = pick_leading_point(sr.miss_points, d.get("id"))
    leading_by_score = max(sr.miss_points, key=lambda p: p.score).id if sr.miss_points else None
    leading_ok = leading is not None and leading.id == leading_by_score

    # 示证（LLM，只推的那 1 个）
    g = None
    err = None
    if leading is not None:
        try:
            g = guidance(material, answer, points, leading.id)
        except Exception as e:  # 调用失败记 err，不算红线失败
            err = str(e)

    row = {
        "id": d.get("id", ""),
        "type": d.get("meta", {}).get("type", "?"),
        "kind": kind,
        "n_miss": len(sr.miss_points),
        "anchored_total": anchored_total,
        "anchor_fails": anchor_fails,
        "hit_missing_snippet": hit_missing_snippet,
        "leading_ok": leading_ok,
    }
    if g is None:
        row.update({"error": err, "demo": None, "full_answer_flags": [],
                    "fabrication_flags": []})
        return row

    # no_fabrication：示证点∈漏点集（构造上保证）+ 材料原话真出自材料
    fab_flags = []
    if g.material_source and not _quote_anchored(g.material_source, material):
        fab_flags.append(g.material_source)
    # no_full_answer：示范不代写完整作答段落
    full_flags = [g.demo] if g.demo and not _full_answer_ok(g.demo, good_text, material) else []
    row.update({
        "demo": g.demo,
        "cause_type": g.cause_type,
        "full_answer_flags": full_flags,
        "fabrication_flags": fab_flags,
        "material_source": g.material_source,
    })
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只看某题型，如 归纳概括")
    ap.add_argument("--out", default=os.path.join(ROOT, "eval", "results", "baseline", "demo_eval_results.json"))
    args = ap.parse_args()

    by_type: dict[str, list[dict]] = defaultdict(list)
    for f in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        by_type[d.get("meta", {}).get("type", "?")].append(d)

    samples: list[tuple[dict, str, str]] = []
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
    n_anchored_pts = n_anchor_ok = 0
    n_leading_ok = n_demo_generated = n_cause_generated = 0
    n_full = n_fab = n_empty_demo = n_err = 0
    for d, answer, kind in samples:
        r = run_sample(d, answer, kind)
        r["type"] = d.get("meta", {}).get("type", "?")
        rows.append(r)
        n_anchored_pts += r["anchored_total"]
        n_anchor_ok += r["anchored_total"] - len(r["anchor_fails"])
        n_leading_ok += int(r["leading_ok"])
        if "error" in r:
            n_err += 1
            print(f"  [✗] {r['id']} {r['kind']}: 示证调用失败 {r['error']}")
            continue
        if r["demo"]:
            n_demo_generated += 1
        else:
            n_empty_demo += 1
        if r["cause_type"]:
            n_cause_generated += 1
        n_full += len(r["full_answer_flags"])
        n_fab += len(r["fabrication_flags"])
        flags = r["full_answer_flags"] or r["fabrication_flags"] or r["anchor_fails"]
        print(f"  {r['id']:<22} {r['type']:<6} {r['kind']:<9} 漏点{r['n_miss']:>2} "
              f"锚定{r['anchored_total']} 示证{'✓' if r['demo'] else '空'} "
              f"{'⚠️' if flags else ''}")

    n_demo = n_demo_generated
    material_anchored = round(n_anchor_ok / n_anchored_pts, 3) if n_anchored_pts else None
    anchored_coverage = round(n_anchored_pts / sum(r["n_miss"] for r in rows), 3) if rows else None
    no_full_answer = round(1 - n_full / n_demo, 3) if n_demo else None
    no_fabrication = round(1 - n_fab / n_demo, 3) if n_demo else None
    leading_ok = round(n_leading_ok / len(rows), 3) if rows else None
    hit_snippet = round(
        sum(1 for r in rows if not r["hit_missing_snippet"]) / len(rows), 3) if rows else None

    summary = {
        "sample_count": len(rows),
        "material_anchored": material_anchored,     # 红线：非空锚定必须真有出处 == 1.0
        "anchored_coverage": anchored_coverage,     # 报告项：漏点锚到材料原话的比例
        "no_full_answer": no_full_answer,           # 红线：示范不代写完整作答段落
        "no_fabrication": no_fabrication,           # 红线：示证不臆造
        "leading_ok": leading_ok,                   # 报告项：推 1 个 = score 最大漏点
        "hit_snippet_ok": hit_snippet,              # 报告项：命中点带作答片段
        "demo_generated": n_demo_generated,
        "cause_generated": n_cause_generated,
        "empty_demo_count": n_empty_demo,
        "error_count": n_err,
        "llm_calls": 2 * n_demo,                    # demo + cause 各一次
        "thresholds": THRESHOLDS,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump({"summary": summary, "rows": rows}, open(args.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"样本数: {len(rows)}（bad {sum(1 for r in rows if r.get('kind') == 'bad')} "
          f"+ half_done {sum(1 for r in rows if r.get('kind') == 'half_done')}）")
    print(f"material_anchored（L3 锚定有真出处）:  {material_anchored}  （红线 == 1.0，"
          f"{n_anchor_ok}/{n_anchored_pts}）")
    print(f"anchored_coverage（漏点锚定覆盖率）:    {anchored_coverage}  （报告项）")
    print(f"no_full_answer（示范不代写整段）:       {no_full_answer}  （红线 == 1.0，"
          f"违规 {n_full} 条）")
    print(f"no_fabrication（示证不臆造）:           {no_fabrication}  （红线 == 1.0，"
          f"违规 {n_fab} 条）")
    print(f"leading_ok（推 1 个 = score 最大）:      {leading_ok}  （报告项）")
    print(f"hit_snippet_ok（命中点带作答片段）:      {hit_snippet}  （报告项）")
    print(f"示证生成: demo {n_demo_generated} / cause {n_cause_generated} / 空 {n_empty_demo} / 失败 {n_err}")
    print(f"LLM 调用量: {summary['llm_calls']}")
    print(f"结果已落盘 → {args.out}")


if __name__ == "__main__":
    main()
