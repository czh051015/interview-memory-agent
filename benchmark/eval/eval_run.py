# -*- coding: utf-8 -*-
"""
benchmark eval 引擎（domain 无关，换壳零改动）
===============================================
读 benchmark/data/*.json → 对每个 item 的 good/bad 作答做"采分点命中"匹配
→ 输出两个指标：
  1. discrimination : good 命中数 > bad 命中数（能区分好坏）
  2. no_fool        : bad 命中率 < 50%（跑题档不得高分，防流畅/长度误导）
匹配方式：纯关键词（A 模式）—— 引擎骨架，后续可替换为语义/混合。
"""
import json, glob, os, re, sys

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
MISS_THRESHOLD = 0.5  # bad 命中率低于该值才算"没被 fool"

def hit_ratio(answer: str, point) -> float:
    """一个采分点的命中判定：任意关键词出现在作答中即命中（1.0），否则 0.0"""
    for kw in point["keywords"]:
        if kw in answer:
            return 1.0
    return 0.0

def score_answer(answer: str, points) -> tuple:
    """返回 (命中点数, 命中率, 命中的 point id 列表)"""
    hits = [p for p in points if hit_ratio(answer, p) > 0]
    ratio = len(hits) / len(points) if points else 0.0
    return len(hits), ratio, [p["id"] for p in hits]

def main():
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*.json")))
    if not files:
        print("!! data 目录为空，请先运行生成脚本")
        sys.exit(1)

    rows = []
    disc_fail, fool_fail = [], []

    for f in files:
        item = json.load(open(f, encoding="utf-8"))
        points = item["gold"]["reference_points"]
        g = item["samples"]["good"]["text"]
        b = item["samples"]["bad"]["text"]

        g_hits, g_ratio, g_ids = score_answer(g, points)
        b_hits, b_ratio, b_ids = score_answer(b, points)

        disc_ok = g_hits > b_hits
        fool_ok = b_ratio < MISS_THRESHOLD

        if not disc_ok: disc_fail.append(item["id"])
        if not fool_ok: fool_fail.append(item["id"])

        rows.append((item["id"], item["meta"]["province"], item["meta"]["type"],
                     len(points), g_hits, round(g_ratio,2), b_hits, round(b_ratio,2),
                     "✓" if disc_ok else "✗", "✓" if fool_ok else "✗"))

    # 输出表
    print(f"{'id':<22}{'省':<4}{'题型':<6}{'点数':<4}{'good命中':<8}{'g比率':<6}{'bad命中':<8}{'b比率':<6}{'区分':<4}{'防fool':<4}")
    print("-" * 78)
    for r in rows:
        print(f"{r[0]:<22}{r[1]:<4}{r[2]:<6}{r[3]:<4}{r[4]:<8}{r[5]:<6}{r[6]:<8}{r[7]:<6}{r[8]:<4}{r[9]:<4}")

    n = len(rows)
    disc_pass = n - len(disc_fail)
    fool_pass = n - len(fool_fail)
    print("-" * 78)
    print(f"\n总 item: {n}  |  discrimination 通过: {disc_pass}/{n}  |  no_fool 通过: {fool_pass}/{n}")
    if disc_fail: print("✗ 区分失败:", disc_fail)
    if fool_fail: print("✗ 防fool失败:", fool_fail)

    # good 平均命中率（recall 代理）
    avg_g = sum(r[5] for r in rows) / n
    print(f"good 平均命中率（recall 代理）: {avg_g:.2f}  → 目标 ≥0.90")

    ok = (not disc_fail) and (not fool_fail) and avg_g >= 0.90
    print("\n✅ 全部通过，漏点识别可靠" if ok else "\n❌ 存在失败项，需检查")

if __name__ == "__main__":
    main()
