# -*- coding: utf-8 -*-
"""SAMPLE 三处同源防漂移校验（docs/38 §7 前端清单附录）。

风险点：PracticePanel.tsx 的 SAMPLE（question/material/points/answer）与
eval/calibrate_sample.py 常量、benchmark/data/henan_2025_city_1.json 的
reference_points 三处重复维护——任一处改动都可能导致演示题与库题不一致
（D41 trusted 校验 400，门禁降级失效）或演示稿与实测对不上。

本脚本逐字核对：
  1. TSX SAMPLE ↔ calibrate_sample.py 常量同源（question/material/answer/points）
  2. SAMPLE points ↔ 库题 reference_points 全量一致（normalized：id/point/排序 keywords）
     —— 这是 D41 trusted 通过的前置条件

用法（offerloop 根目录）：
  PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 eval/check_sample_sync.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("cs", str(ROOT / "eval" / "calibrate_sample.py"))
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)

ts = (ROOT / "frontend/components/workbench/PracticePanel.tsx").read_text(encoding="utf-8")
# 声明类型 2026-09-02 扩展为 `InlineGold & { standard_answer_text: string }`（任务三）→ 不再精确匹配
m0 = re.search(r"const SAMPLE: InlineGold[^=]*=\s*\{", ts)
assert m0, "找不到 const SAMPLE 声明（PracticePanel.tsx 结构变了？）"
start = m0.start()
block = ts[start:ts.index("};", start)]


def lit(name: str) -> str | None:
    m = re.search(name + r':\s*"((?:[^"\\]|\\.)*)"', block, re.S)
    return m.group(1) if m else None


def main() -> None:
    q, mat, ans = lit("question"), lit("material"), lit("answer")
    ok = True

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        mark = "✓" if cond else "✗"
        print(f"  {mark} {name} {detail}")
        ok = ok and cond

    print("TSX SAMPLE ↔ eval/calibrate_sample.py 常量同源：")
    check("question", q == cs.QUESTION)
    check("material", mat == cs.MATERIAL, f"(len ts={len(mat or '')} py={len(cs.MATERIAL)})")
    check("answer", ans == cs.ANSWER)

    pts_m = re.search(r"points: \[(.*?)\],\n", block, re.S)
    raw = re.findall(
        r'\{\s*id: "(c\d+)",\s*point: "([^"]+)",\s*keywords: \[([^\]]+)\],\s*score: 1,\s*point_type: "([^"]+)"\s*\}',
        pts_m.group(1),
    )
    ts_kws = {pid: re.findall(r'"([^"]+)"', ks) for pid, _, ks, _ in raw}
    ts_names = {pid: n for pid, n, _, _ in raw}
    py_kws = {p["id"]: list(p["keywords"]) for p in cs.RAW_POINTS}
    py_names = {p["id"]: p["point"] for p in cs.RAW_POINTS}
    check("points 9 点", len(raw) == len(cs.RAW_POINTS) == 9)
    check("points 名称同源", ts_names == py_names)
    check("points kw 同源", ts_kws == py_kws)

    from src.shenlun.reflow import load_question  # noqa: E402

    item = load_question("henan_2025_city_1")
    ref = item["gold"]["reference_points"]

    def norm(p):
        return (p["id"], p["point"], tuple(sorted(p.get("keywords") or [])))

    refd = {n[0]: n for n in map(norm, ref)}
    sampd = {pid: (pid, py_names[pid], tuple(sorted(k))) for pid, k in py_kws.items()}
    same = refd == sampd
    check("SAMPLE ↔ 库题 reference_points 全量一致（D41 trusted 前置）", same,
          f"| 库 {len(refd)} 点")
    if not same:
        for k in sorted(set(refd) | set(sampd)):
            if refd.get(k) != sampd.get(k):
                print(f"    差异点 {k}  库: {refd.get(k)}  声明: {sampd.get(k)}")
    print("\n全部 ✓ → 演示题三处同源，D41 trusted 门禁可过；有 ✗ → 改数据源前先对齐三处。")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
