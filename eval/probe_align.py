# -*- coding: utf-8 -*-
"""0 成本配对 demo（纯示证型最小形态验证）。

只做文本配对，不做任何好坏判断（0 token、0 embedding 调用）：
1. 作答按句切分（句号族规则）
2. 每个采分点的 keywords 在作答分句里做子串匹配 → 输出「该点对应哪些作答句 + 共现词」
3. 零命中任何 kw 的点 → [候选]未见对应句
4. 作答句未命中任何点 kw → [候选]无对应（自创/延伸候选）

目的：验证降级后的最小形态能否干净标出 c4/c9（v2 作答已删净的点），
以及词重叠法的局限（串点/同义改写漏配）——后者是 embedding 第二路要补的位置。

用法（offerloop 根目录）：.venv/Scripts/python.exe eval/probe_align.py
数据源：eval/calibrate_sample.py（与前端 SAMPLE v2 同源，仅取常量，不触发评分）。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 只取 calibrate_sample 的常量（模块 import 不执行其 __main__）
import importlib.util

spec = importlib.util.spec_from_file_location("cs", str(ROOT / "eval" / "calibrate_sample.py"))
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)

ANSWER: str = cs.ANSWER
POINTS: list = cs.RAW_POINTS


def split_sentences(text: str) -> list[str]:
    """按句号族切分语义分句（规则，0 token）。"""
    parts = re.split(r"[。；!?！？\n]", text)
    return [p.strip() for p in parts if len(p.strip()) >= 6]


chunks = split_sentences(ANSWER)
print(f"作答切句：{len(chunks)} 句")
for i, c in enumerate(chunks, 1):
    print(f"  [{i}] {c}")
print()

# ── 逐点配对 ──
print("═" * 70)
print("① 逐点配对：每个采分点 × 作答分句（kw 子串命中 → 候选对应）")
print("═" * 70)
gap = []
for p in POINTS:
    pid, pname, kws = p["id"], p["point"], p["keywords"]
    hit_chunks = []
    for i, c in enumerate(chunks, 1):
        hit = [kw for kw in kws if kw in c]
        if hit:
            hit_chunks.append((i, hit, c))
    if hit_chunks:
        print(f"\n[{pid}] {pname}  →  对应作答句:")
        for i, hit, c in hit_chunks:
            print(f"        句[{i}]  共现 {hit}  「{c[:40]}…」")
    else:
        gap.append(p)
        print(f"\n[{pid}] {pname}  →  ★ 作答中未命中任何 kw → [候选]未见对应句")

# ── 孤儿句 ──
print()
print("═" * 70)
print("② 孤儿句：作答句未命中任何点的 kw → [候选]无对应（自创/延伸候选）")
print("═" * 70)
all_kws = [kw for p in POINTS for kw in p["keywords"]]
for i, c in enumerate(chunks, 1):
    hit = [kw for kw in all_kws if kw in c]
    if not hit:
        print(f"  作答句[{i}] 零 kw 命中：{c[:50]}…")
if not any(not [kw for kw in all_kws if kw in c] for c in chunks):
    print("  （无孤儿句）")

# ── gap 汇总 ──
print()
print("═" * 70)
print("③ gap 汇总：作答中零词命中的点（纯规则「未见对应」候选，需你判断）")
print("═" * 70)
for p in gap:
    print(f"  [{p['id']}] {p['point']}  keywords={p['keywords']}")
