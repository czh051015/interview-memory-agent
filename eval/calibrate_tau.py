"""docs/25 §5 阈值校准 —— 在 medium + bad 样本上扫 τ，输出曲线表，选折中 τ。

不拍脑袋：语义命中阈值 τ 的决定依据是三条曲线的交点——
  - fuzzy 漏判率（↓ 越好）：medium fuzzy 样本「期望给分但系统没给」比例
  - nosource 假阳性率（↑ 越糟）：medium nosource 样本「系统给了但人工不该给」比例
  - bad 误判数（必须 = 0）：全题库跑题答被误判「全命中」的题数（no_fool 红线，硬约束）

指标口径与 medium_eval / score_eval 完全一致（Σfn/Σexp、Σfp/Σsys、hit_ratio≥1.0），
样本直接复用同一批 benchmark 数据。embedding 跨 τ 缓存（同一文本只嵌入一次，
Ollama dmeta 确定性，曲线各点可复现）。embedding 不可用则校准无意义，直接退出。

用法：
  python eval/calibrate_tau.py            # 扫默认 τ∈[0.55, 0.90]，打印曲线表 + 推荐值
  python eval/calibrate_tau.py --start 0.60 --end 0.85 --step 0.025
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

from src.shenlun import score as score_mod
from src.shenlun.score import from_benchmark, score_answer

DATA = os.path.join(ROOT, "benchmark", "data")
MEDIUM = os.path.join(ROOT, "benchmark", "medium")
FUZZY_TARGET = 0.40  # docs/25 §1：漏判率目标 ≤40%（是否可达以校准曲线为准）

# ── embedding 缓存：跨 τ 复用（同文本必同向量），注入方式见 main() ──
_EMB_CACHE: dict[str, list[float]] = {}
_ORIG_EMBED = score_mod.embed_zh


def _cached_embed(texts: list[str]) -> list[list[float]] | None:
    missing = [t for t in texts if t not in _EMB_CACHE]
    if missing:
        embs = _ORIG_EMBED(missing)
        if embs is None:
            return None
        _EMB_CACHE.update(zip(missing, embs))
    return [_EMB_CACHE[t] for t in texts]


def load_medium() -> list[dict]:
    """读 medium 样本（口径同 medium_eval）：{qid, kind, text, exp, points}。"""
    out = []
    for f in sorted(glob.glob(os.path.join(MEDIUM, "*.json"))):
        m = json.load(open(f, encoding="utf-8"))
        qf = os.path.join(DATA, f"{m['question_id']}.json")
        if not os.path.exists(qf):
            continue
        d = json.load(open(qf, encoding="utf-8"))
        points = from_benchmark(d["gold"]["reference_points"])
        for s in m["samples"]:
            out.append({
                "qid": m["question_id"], "kind": s["kind"],
                "text": s["text"], "exp": set(s["expected_hit_ids"]), "points": points,
            })
    return out


def load_bad() -> list[tuple[str, str, list]]:
    """全题库 bad（跑题）样本 → [(qid, bad_text, points)]，no_fool 约束用（口径同 score_eval）。"""
    out = []
    for f in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        bad = (d.get("samples") or {}).get("bad") or {}
        if not bad.get("text"):
            continue
        out.append((d["id"], bad["text"], from_benchmark(d["gold"]["reference_points"])))
    return out


def metrics_at(medium: list[dict], bad: list[tuple[str, str, list]], tau: float,
               use_semantic: bool = True) -> dict:
    """τ 下的指标（口径同 medium/score eval）：
    fuzzy 漏判率 / nosource 假阳性率 / bad 误判数 + 全题库 discrimination。
    discrimination 是语义层的全局副作用雷达：bad 答被语义补命中会推高 bad_ratio、
    缩小区分度——no_fool 只约束「全命中」，管不到这个（2026-08-31 校准发现的盲区）。
    use_semantic=False → 纯硬匹配基线（τ 参数忽略）。
    """
    total_fn = total_exp = 0
    for r in medium:
        if r["kind"] != "fuzzy":
            continue
        hits = {h.id for h in score_answer(r["text"], r["points"], tau=tau,
                                           use_semantic=use_semantic).hit_points}
        total_fn += len(r["exp"] - hits)
        total_exp += len(r["exp"])
    total_fp = total_sys = 0
    for r in medium:
        if r["kind"] != "nosource":
            continue
        hits = {h.id for h in score_answer(r["text"], r["points"], tau=tau,
                                           use_semantic=use_semantic).hit_points}
        total_fp += len(hits - r["exp"])
        total_sys += len(hits)
    bad_fooled = 0
    for _, bad_text, points in bad:
        sr = score_answer(bad_text, points, tau=tau, use_semantic=use_semantic)
        if sr.hit_ratio >= 1.0:
            bad_fooled += 1
    # 全题库 discrimination（口径同 score_eval：mean(good_ratio − bad_ratio)）
    disc, bad_ratios = [], []
    for f in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        s = d.get("samples") or {}
        good, badt = s.get("good", {}).get("text", ""), s.get("bad", {}).get("text", "")
        if not good or not badt:
            continue
        pts = from_benchmark(d["gold"]["reference_points"])
        gr = score_answer(good, pts, tau=tau, use_semantic=use_semantic).hit_ratio
        br = score_answer(badt, pts, tau=tau, use_semantic=use_semantic).hit_ratio
        disc.append(gr - br)
        bad_ratios.append(br)
    return {
        "fuzzy_miss_rate": total_fn / total_exp if total_exp else None,
        "nosource_fp_rate": total_fp / total_sys if total_sys else None,
        "bad_fooled": bad_fooled,
        "discrimination": sum(disc) / len(disc) if disc else None,
        "bad_mean_ratio": sum(bad_ratios) / len(bad_ratios) if bad_ratios else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=float, default=0.55)
    ap.add_argument("--end", type=float, default=0.90)
    ap.add_argument("--step", type=float, default=0.05)
    args = ap.parse_args()

    # embedding 不可用 → 每个 τ 结果都等于纯硬匹配，曲线无意义，直接退出
    if _ORIG_EMBED(["校准探针"]) is None:
        print("embedding 不可用（Ollama/dmeta），校准无意义，退出。")
        return
    score_mod.embed_zh = _cached_embed  # 缓存注入：跨 τ 同一文本只嵌入一次

    medium = load_medium()
    bad_qs = load_bad()
    n_fuzzy = sum(1 for r in medium if r["kind"] == "fuzzy")
    n_nosrc = sum(1 for r in medium if r["kind"] == "nosource")
    print(f"样本：medium fuzzy×{n_fuzzy} / nosource×{n_nosrc}；bad 跑题答×{len(bad_qs)}（全题库）")
    if not medium or not bad_qs:
        print("样本不足，无法校准")
        return

    def _pct(v):
        return f"{v:.0%}" if isinstance(v, float) else "N/A"

    # 基线（纯硬匹配 = use_semantic=False）对照
    base_fn = base_exp = 0
    for r in [m for m in medium if m["kind"] == "fuzzy"]:
        hits = {h.id for h in score_answer(r["text"], r["points"], use_semantic=False).hit_points}
        base_fn += len(r["exp"] - hits)
        base_exp += len(r["exp"])
    base_fp = base_sys = 0
    for r in [m for m in medium if m["kind"] == "nosource"]:
        hits = {h.id for h in score_answer(r["text"], r["points"], use_semantic=False).hit_points}
        base_fp += len(hits - r["exp"])
        base_sys += len(hits)
    base_bad = sum(1 for _, bad_text, points in bad_qs
                   if score_answer(bad_text, points, use_semantic=False).hit_ratio >= 1.0)

    base_disc = metrics_at(medium, bad_qs, tau=0.0, use_semantic=False)["discrimination"]
    print(f"\n基线（纯硬匹配）: fuzzy 漏判率 {_pct(base_fn / base_exp if base_exp else None)} | "
          f"nosource 假阳性率 {_pct(base_fp / base_sys if base_sys else None)} | bad 误判 {base_bad}"
          f" | discrimination {base_disc:.3f}")
    print(f"目标: fuzzy 漏判率 ≤ {FUZZY_TARGET:.0%}，nosource 假阳性可控，bad 误判 = 0（红线），"
          f"discrimination 不显著恶化（基线 {base_disc:.3f}）")
    print(f"\n{'τ':<14}{'fuzzy漏判率':<14}{'nosource假阳性':<16}{'bad误判':<10}{'disc':<8}判定")
    print("-" * 72)

    rows = []
    start_i = round(args.start / args.step)
    end_i = round(args.end / args.step)
    for i in range(start_i, end_i + 1):
        t = round(i * args.step, 4)  # 整数步进，避免浮点累积漂移（round(t+step) 会卡死）
        m = metrics_at(medium, bad_qs, t)
        fuzzy = m["fuzzy_miss_rate"]
        verdict = "❌ no_fool 失守" if m["bad_fooled"] else (
            "✅ 达标" if fuzzy is not None and fuzzy <= FUZZY_TARGET else "⚠️ 未达标")
        print(f"{t:<14.2f}{_pct(fuzzy):<14}{_pct(m['nosource_fp_rate']):<16}{m['bad_fooled']:<10}"
              f"{m['discrimination']:.3f}  {verdict}")
        rows.append({"tau": t, **m})

    # ── bad 语义边界定位 + 细扫 ──
    # no_fool 语义边界：一道 bad 答被语义误判「全命中」iff 每个无 kw 命中的点都被语义命中，
    # 即 τ ≤ 该答所有语义点的最小余弦；全题库边界 = 各答边界的最小值的最大者。
    # （纯 kw 误判与 τ 无关，τ 救不了 → 单独报，需改关键词）
    bad_bound, kw_fooled = 0.0, 0
    for _, bad_text, points in bad_qs:
        sr = score_answer(bad_text, points, tau=0.0)  # τ=0 → 所有语义命中都给出，看上限
        sem = {h.id: h.semantic_score or 0.0 for h in sr.hit_points if h.matched_by == "semantic"}
        kw = {h.id for h in sr.hit_points if h.matched_by == "kw"}
        lims = [sem[p.id] for p in points if p.id not in kw and p.id in sem]
        if not lims and len(kw) == len(points):
            kw_fooled += 1  # 全 kw 命中：任何 τ 都误判，数据问题
        elif lims:
            bad_bound = max(bad_bound, min(lims))
    print(f"\nno_fool 语义边界 = {bad_bound:.4f}（τ 必须超过它；另 {kw_fooled} 道 bad 纯 kw 误判，与 τ 无关）")
    fine = []
    t = round(bad_bound + 0.002, 4)
    while t <= bad_bound + 0.095 + 1e-9:  # 覆盖到 0.80：看 discrimination 随 τ 回升的曲线
        m = metrics_at(medium, bad_qs, t)
        fine.append({"tau": t, **m})
        t = round(t + 0.003, 4)
    print(f"{'τ':<9}{'fuzzy漏判率':<12}{'bad误判':<9}{'disc':<8}{'bad均比':<8}margin(τ−边界)")
    print("-" * 60)
    for r in fine:
        print(f"{r['tau']:<9.3f}{_pct(r['fuzzy_miss_rate']):<12}{r['bad_fooled']:<9}"
              f"{r['discrimination']:.3f}  {r['bad_mean_ratio']:.3f}   {r['tau'] - bad_bound:.4f}")

    # 推荐：bad=0 的候选中，优先「discrimination 不显著恶化（≥ 基线−0.02）」者取 fuzzy 最低；
    # 若所有安全候选都拿不到，则取 fuzzy 最低并在报告里如实标出恶化量。
    cands = [r for r in fine if r["bad_fooled"] == 0 and r["fuzzy_miss_rate"] is not None]
    if not cands:
        cands = [r for r in rows if r["bad_fooled"] == 0 and r["fuzzy_miss_rate"] is not None]
    if cands:
        base_d = base_disc or 0.0
        safe = [r for r in cands if r["discrimination"] is not None
                and r["discrimination"] >= base_d - 0.02]
        pool = safe or cands
        best = min(pool, key=lambda r: (r["fuzzy_miss_rate"], r["nosource_fp_rate"]))
        margin = best["tau"] - bad_bound
        tag = "✓ 区分度不恶化" if best in safe else f"⚠ 区分度恶化 {base_d - best['discrimination']:.3f}"
        print(f"\n推荐 τ = {best['tau']:.3f}（fuzzy 漏判率 {best['fuzzy_miss_rate']:.0%}，"
              f"nosource 假阳性率 {best['nosource_fp_rate']:.0%}，bad 误判 0，"
              f"discrimination {best['discrimination']:.3f}（基线 {base_d:.3f}，{tag}），"
              f"no_fool 余量 {margin:.3f}）")
        print("→ 写入 src/config.py 的 SCORE_SEMANTIC_TAU 默认值（env SCORE_SEMANTIC_TAU 可覆盖）。")
    else:
        print("\n无可选 τ：所有候选都有 bad 误判（no_fool 失守），需降低语义层激进程度或检查 bad 关键词。")


if __name__ == "__main__":
    main()
