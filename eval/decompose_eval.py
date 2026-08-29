"""申论拆解评测 —— decompose_points 金标对照 + 脏标答鲁棒性（docs/19 §4.2）。

评的对象：src.cleaner.decompose.decompose_points（LLM 拆标准答案 → ReferencePoint[]）。
ground truth 零新增成本：benchmark/data/*.json 的 gold.reference_points（official 金标）。
每道题用 samples.good（满分作答，覆盖全部采分点）当标准答案全文喂给 decompose_points，
拿 LLM 拆出的点 vs 官方金标点做对照——docs/16 §5 步 1 验收标准「点覆盖≥80%、无臆造点」的自动化。

指标（门槛为初值，首轮跑完按实际分布校准，docs/19 §9.5）：
  - point_recall      点覆盖率：金标点被 ≥1 个拆出点命中的比例（keywords 子串交集，宽松口径）≥ 0.80
  - fabrication_rate  臆造点率：拆出点中 keywords 对不上任何金标点的比例 ≤ 0.10（人工复核兜底）
  - structural_ok     结构合法性：point≤8字、keywords 1-5 个且均出自原文/材料（程序可验部分）== 1.0
  - score_deviation   分值合理性：拆出点 score 之和 vs max_score 偏差（只报告，不设门槛，提示人审核）
  - over_split_flags  点数量注水标记：拆出点数 > 12 的题（>12 即疑似拆成近义点刷覆盖率）== 0
  - dirty_robustness  脏标答鲁棒性：eval/dirty_gold.json 人工脏标答（残缺/口语化/抄错）
                      断言：拆出点数 < 金标点数一半 且 warnings 含「疑似标答过简」== 1.0（行为验证）
  - LLM-as-judge 抽样复核（漏拆/错拆/臆造）+ 人工校准占位（仿 llm_judge 的 HUMAN_CALIBRATION 骨架）

用法：
  python eval/decompose_eval.py
  python eval/decompose_eval.py --only 归纳概括     # 只看某题型
  python eval/decompose_eval.py --out eval/decompose_eval_results.json
输出：eval/decompose_eval_results.json（顶层字段供 run_evals extract_summary 扁平化）
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

sys.path.insert(0, ROOT := os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cleaner.decompose import decompose_points
from src.llm import chat_json

DATA = os.path.join(ROOT, "benchmark", "data")
DIRTY_SAMPLES = os.path.join(ROOT, "eval", "dirty_gold.json")

# 人工校准结论占位（仿原 llm_judge_eval）：
# 跑完先看 judge 的漏拆/错拆/臆造发现，人工抽 3-4 条核对裁判本身准头，再把结论填进来。
HUMAN_CALIBRATION = {
    "reviewed": 0,
    "category_corrections": {},
    "judge_missed_notes": [],
}

# 门槛初值（docs/19 §4.2，待校准）
THRESHOLDS = {"point_recall": 0.80, "fabrication": 0.10, "structural": 1.0, "dirty_robustness": 1.0}

JUDGE_SYSTEM = (
    "你是「申论采分点拆解」的质检裁判。给你一道申论题、官方金标采分点和 LLM 拆出的采分点。\n"
    "请独立判断拆解质量，不要盲信拆解结果：\n"
    "1. 臆造：LLM 拆出的点，金标里有没有对应内容（名称或关键词对得上就算有）——没有即臆造；\n"
    "2. 漏拆：金标里的点，LLM 一个都没对上的——即漏拆；\n"
    "3. 错拆：拆出的点名称和内容对不上题目语境，或把一个大点拆成多个近义点刷数量。\n\n"
    "只输出 JSON：\n"
    '{"verdicts": [{"decomposed_point": "拆出的点名称", "fabricated": true/false, "issue": "问题说明，无则空字符串"}], '
    '"missed": ["漏拆的金标点名称"], "extra": ["错拆的点名称"]}'
)


def _load_benchmark(path: str) -> dict | None:
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"  [跳过] {os.path.basename(path)} 加载失败: {e}")
        return None


def _kw_hit(dec_keywords: list[str], gold_keywords: list[str]) -> bool:
    """关键词命中判定（宽松口径，docs/19 §10）：任一方向子串重叠即算命中。"""
    for dk in dec_keywords:
        if len(dk) < 2:
            continue
        for gk in gold_keywords:
            if len(gk) < 2:
                continue
            if dk in gk or gk in dk:
                return True
    return False


def _structural_ok(dec_points: list[dict], source_text: str, material: str) -> tuple[bool, list[str]]:
    """结构合法性（程序可验部分）：point≤8字、keywords 1-5 个且均出自原文/材料。"""
    problems: list[str] = []
    ok = True
    for p in dec_points:
        name = str(p.get("point") or "")
        kws = [str(k) for k in (p.get("keywords") or [])]
        if len(name) > 8:
            problems.append(f"「{name}」长度 {len(name)} > 8 字")
            ok = False
        if not (1 <= len(kws) <= 5):
            problems.append(f"「{name}」keywords 数量 {len(kws)} 不在 1-5")
            ok = False
        for kw in kws:
            if kw and kw not in source_text and kw not in material:
                problems.append(f"「{name}」关键词「{kw}」不出自原文/材料")
                ok = False
    return ok, problems


def evaluate_question(d: dict) -> dict:
    """一道题的金标对照：good 作答当标准答案 → decompose → 对照金标。"""
    task, gold = d.get("task", {}), d.get("gold", {})
    gold_points = gold.get("reference_points", [])
    standard_answer = (d.get("samples", {}).get("good", {}).get("text") or "").strip()
    question = str(task.get("question") or "")
    requirements = str(task.get("requirements") or "")
    material = str(task.get("material") or "")
    max_score = int(task.get("max_score") or 0)

    r = decompose_points(
        standard_answer,
        question=question, requirements=requirements, material=material,
        max_score=max_score, question_id=d.get("id", ""),
    )
    dec_points = [p.model_dump() for p in r.reference_points]
    n_gold, n_dec = len(gold_points), len(dec_points)

    # 点覆盖率：金标点被 ≥1 个拆出点命中
    gold_hit = [False] * n_gold
    dec_covered = [False] * n_dec
    for i, g in enumerate(gold_points):
        for j, dp in enumerate(dec_points):
            if _kw_hit(dp.get("keywords") or [], g.get("keywords") or []):
                gold_hit[i] = True
                dec_covered[j] = True
    recall = sum(gold_hit) / n_gold if n_gold else 0.0
    fabrication = sum(1 for c in dec_covered if not c) / n_dec if n_dec else 0.0

    struct_ok, struct_problems = _structural_ok(dec_points, standard_answer, material)
    score_sum = sum(float(p.get("score") or 0) for p in dec_points)
    dev = abs(score_sum - max_score) / max_score if max_score else None

    return {
        "id": d.get("id", ""),
        "type": d.get("meta", {}).get("type", "?"),
        "n_gold": n_gold,
        "n_decomposed": n_dec,
        "point_recall": round(recall, 3),
        "fabrication_rate": round(fabrication, 3),
        "structural_ok": struct_ok,
        "structural_problems": struct_problems,
        "score_deviation": round(dev, 3) if dev is not None else None,
        "over_split": n_dec > 12,
        "warnings": r.warnings,
        "decomposed": [{"point": p.get("point"), "keywords": p.get("keywords")} for p in dec_points],
    }


def evaluate_dirty(qid_gold: dict[str, dict], item: dict) -> dict:
    """一条脏标答的行为验证：拆出点数 < 金标一半 且 warnings 含「疑似标答过简」。"""
    d = qid_gold[item["question_id"]]
    task, gold = d.get("task", {}), d.get("gold", {})
    n_gold = len(gold.get("reference_points", []))
    r = decompose_points(
        item["text"],
        question=str(task.get("question") or ""),
        requirements=str(task.get("requirements") or ""),
        material=str(task.get("material") or ""),
        max_score=int(task.get("max_score") or 0),
        question_id=item["question_id"],
    )
    n_dec = len(r.reference_points)
    warning_hit = any("疑似标答过简" in w for w in r.warnings)
    passed = n_dec < n_gold / 2 and warning_hit
    return {
        "id": item["id"],
        "question_id": item["question_id"],
        "dirty_type": item["dirty_type"],
        "n_gold": n_gold,
        "n_decomposed": n_dec,
        "warning_hit": warning_hit,
        "warnings": r.warnings,
        "pass": passed,
    }


def judge_sample(rows: list[dict], max_samples: int = 10) -> dict:
    """LLM-as-judge 抽样复核（漏拆/错拆/臆造），人工校准占位。"""
    sampled = [r for r in rows if r["n_decomposed"] > 0][:: max(1, len(rows) // max_samples)][:max_samples]
    findings = {"fabricated": [], "missed": [], "extra": []}
    for r in sampled:
        gold_desc = "；".join(f"{g.get('point')}({'/'.join(g.get('keywords', []))})" for g in r.get("_gold", []))
        dec_desc = "；".join(f"{p['point']}({'/'.join(p['keywords'])})" for p in r["decomposed"])
        user_prompt = (
            f"## 题目\n{r.get('_question', '')}\n\n"
            f"## 官方金标采分点\n{gold_desc}\n\n"
            f"## LLM 拆出的采分点\n{dec_desc}"
        )
        try:
            verdict = chat_json(JUDGE_SYSTEM, user_prompt, max_tokens=1024)
        except Exception as e:
            print(f"  [judge] {r['id']} 裁判调用失败: {e}")
            continue
        findings["fabricated"].extend(
            f"{r['id']}: {v.get('decomposed_point')}" for v in verdict.get("verdicts", []) if v.get("fabricated"))
        findings["missed"].extend(f"{r['id']}: {m}" for m in verdict.get("missed", []))
        findings["extra"].extend(f"{r['id']}: {e}" for e in verdict.get("extra", []))
    return {"sample_count": len(sampled), "findings": findings}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只看某题型，如 提出对策")
    ap.add_argument("--out", default=os.path.join(ROOT, "eval", "decompose_eval_results.json"))
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(DATA, "*.json")))
    qid_gold: dict[str, dict] = {}
    rows: list[dict] = []
    for f in files:
        d = _load_benchmark(f)
        if not d:
            continue
        qid_gold[d["id"]] = d
        if args.only and d.get("meta", {}).get("type") != args.only:
            continue
        try:
            r = evaluate_question(d)
        except Exception as e:
            print(f"  [跳过] {d.get('id')} 拆解失败: {e}")
            continue
        rows.append(r)
        flag = " ⚠️注水" if r["over_split"] else ""
        print(f"  {r['id']:<22} {r['type']:<6} 金标{r['n_gold']:>2} 拆出{r['n_decomposed']:>2} "
              f"覆盖{r['point_recall']:.2f} 臆造{r['fabrication_rate']:.2f} 结构{'ok' if r['structural_ok'] else '✗'}{flag}")

    # ── 金标对照指标 ──
    n = len(rows)
    if n:
        mean_recall = sum(r["point_recall"] for r in rows) / n
        all_dec = sum(r["n_decomposed"] for r in rows)
        fab = sum(int(r["fabrication_rate"] * r["n_decomposed"]) for r in rows) / all_dec if all_dec else 0.0
        struct_pts = sum(r["n_decomposed"] for r in rows if r["structural_ok"])
        struct_ok = struct_pts / all_dec if all_dec else 0.0
        devs = [r["score_deviation"] for r in rows if r["score_deviation"] is not None]
        score_dev = {"mean": round(sum(devs) / len(devs), 3), "max": round(max(devs), 3)} if devs else None
        over_split_flags = [r["id"] for r in rows if r["over_split"]]
    else:
        mean_recall = fab = struct_ok = 0.0
        score_dev, over_split_flags = None, []

    # ── 脏标答鲁棒性 ──
    dirty_rows: list[dict] = []
    try:
        dirty_data = json.load(open(DIRTY_SAMPLES, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"  [跳过] 脏标答样本加载失败: {e}")
        dirty_data = {"items": []}
    for item in dirty_data.get("items", []):
        if item["question_id"] not in qid_gold:
            print(f"  [跳过] 脏标答 {item['id']} 找不到基准题 {item['question_id']}")
            continue
        try:
            dr = evaluate_dirty(qid_gold, item)
        except Exception as e:
            print(f"  [跳过] 脏标答 {item['id']} 拆解失败: {e}")
            continue
        dirty_rows.append(dr)
        print(f"  [脏] {dr['dirty_type']} {dr['question_id']:<22} 金标{dr['n_gold']:>2} 拆出{dr['n_decomposed']:>2} "
              f"过简警告{'✓' if dr['warning_hit'] else '✗'} → {'PASS' if dr['pass'] else 'FAIL'}")
    dirty_robustness = round(sum(1 for dr in dirty_rows if dr["pass"]) / len(dirty_rows), 3) if dirty_rows else None

    # ── LLM-as-judge 抽样复核 ──
    print("\n裁判抽样复核（漏拆/错拆/臆造）...")
    for r in rows:
        r["_gold"] = qid_gold[r["id"]].get("gold", {}).get("reference_points", [])
        r["_question"] = qid_gold[r["id"]].get("task", {}).get("question", "")
    judge = judge_sample(rows)
    for k, v in judge["findings"].items():
        print(f"  judge 发现 {k}: {v if v else '无'}")
    calibrated = HUMAN_CALIBRATION["reviewed"] > 0

    llm_calls = len(rows) + len(dirty_rows) + judge["sample_count"]

    summary = {
        "decomposed_count": n,
        "point_recall": round(mean_recall, 3),
        "fabrication_rate": round(fab, 3),
        "structural_ok": round(struct_ok, 3),
        "score_deviation": score_dev,
        "over_split_flags": over_split_flags,
        "dirty_robustness": dirty_robustness,
        "calibrated": calibrated,
        "llm_calls": llm_calls,
        "judge": judge,
        "human_calibration": HUMAN_CALIBRATION,
        "thresholds": THRESHOLDS,
    }
    rows_out = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump({"summary": summary, "rows": rows_out, "dirty_rows": dirty_rows},
              open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # ── 门槛判定（初值）──
    print("\n" + "=" * 60)
    print(f"金标对照题数: {n}")
    print(f"点覆盖率 recall:     {mean_recall:.3f}  （门槛 ≥ {THRESHOLDS['point_recall']}）")
    print(f"臆造点率 fabrication: {fab:.3f}  （门槛 ≤ {THRESHOLDS['fabrication']}）")
    print(f"结构合法性:           {struct_ok:.3f}  （门槛 == 1.0，问题明细见 rows）")
    if score_dev:
        print(f"分值偏差 score 和 vs 满分: mean={score_dev['mean']} max={score_dev['max']}（只报告）")
    if over_split_flags:
        print(f"⚠️ 注水拆分嫌疑: {over_split_flags}")
    if dirty_rows:
        print(f"脏标答鲁棒性: {dirty_robustness}  （门槛 == 1.0，{len(dirty_rows)} 条）")
        for dr in dirty_rows:
            if not dr["pass"]:
                print(f"  ✗ {dr['dirty_type']} {dr['question_id']}: 拆出 {dr['n_decomposed']} 点（金标 {dr['n_gold']}），"
                      f"过简警告={dr['warning_hit']} → {dr['warnings']}")
    print(f"LLM 调用量: {llm_calls}")
    print(f"结果已落盘 → {args.out}")


if __name__ == "__main__":
    main()
