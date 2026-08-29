"""R1 backfill：给 benchmark 金标补 point_type（docs/13 §10 R1）。

背景：point_type 在拆解阶段由 LLM 顺手标注（docs/13 §4 D1），但 benchmark/data
的 36 道金标是人工/早期标注的，没有 point_type 字段 → 真实库 weak_points 全部
"未分类"，L2 跨题型诊断（stats_by_angle/diagnose）没有真实信号。

本脚本做两件事（都幂等，可重跑）：
  1. 遍历 benchmark/data/*.json，对缺 point_type 的 reference_points 批量送 LLM
     分类角度（问题/原因/影响/对策/意义/危害/其他），只加字段、不动 id/point/
     keywords/score —— 金标评分内容零改动，仅补诊断元数据。
  2. 真实库 data/shenlun.db 的 weak_points 老行：按 point_key("{qid}:{pid}")
     从题目 JSON 回填 point_type。

LLM 失败 → 跳过该批并警告（不破坏金标）；未标到的点保持 "" = "未分类"。
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_DIR = PROJECT_ROOT / "benchmark" / "data"
DB_PATH = PROJECT_ROOT / "data" / "shenlun.db"

sys.path.insert(0, str(PROJECT_ROOT))
from src.llm import chat_json

ANGLES = ["问题", "原因", "影响", "对策", "意义", "危害", "其他"]
BATCH_SIZE = 30  # 每个 LLM 调用批量分类的点数

_SYSTEM = f"""你是申论采分点角度标注器。给你一批采分点（来自不同题型的标准答案拆解），
把每个点标为它回答的是哪一类角度。角度只能取：{"/".join(ANGLES)}，只能选其一；
无法确定用"其他"。输出 JSON：{{"points": [{{"id": "<原样回显id>", "point_type": "<角度>"}}]}}，
必须与输入 id 一一对应、不增不减。只输出 JSON。"""


def _loads_points() -> list[tuple[Path, list[dict]]]:
    """(文件, 缺 point_type 的点列表) 对。"""
    out = []
    for f in sorted(BENCHMARK_DIR.glob("*.json")):
        item = json.loads(f.read_text(encoding="utf-8"))
        pts = item.get("gold", {}).get("reference_points", [])
        missing = [p for p in pts if not p.get("point_type")]
        if missing:
            out.append((f, missing))
    return out


def _classify_batch(batch: list[tuple[dict, str]]) -> dict[str, str]:
    """batch = [(point_dict, qtype), ...] → {id: point_type}。"""
    user = json.dumps(
        [{"id": p["id"], "point": p["point"], "keywords": p["keywords"], "qtype": qt}
         for p, qt in batch],
        ensure_ascii=False,
    )
    try:
        out = chat_json(_SYSTEM, user, temperature=0.0, max_tokens=2048)
        return {e["id"]: e["point_type"] for e in out.get("points", [])}
    except Exception as e:  # LLM 失败不破坏金标，整批跳过
        print(f"  ⚠️ LLM 分类失败（{e}），本批 {len(batch)} 个点跳过保留\"未分类\"")
        return {}


def backfill_benchmark(dry_run: bool = False) -> int:
    """给金标 JSON 补 point_type。返回补到的点数。"""
    todo = _loads_points()
    total_files = len(todo)
    if not total_files:
        print("benchmark 金标已全部带 point_type，跳过")
        return 0
    print(f"待补 {total_files} 个文件（{sum(len(ms) for _, ms in todo)} 个点）")

    done = 0
    for i, (f, missing) in enumerate(todo, 1):
        # 按题聚合上下文：qtype 帮助 LLM 判断角度（如 归纳概括 的"对策"点）
        item = json.loads(f.read_text(encoding="utf-8"))
        qtype = item.get("meta", {}).get("type", "")
        mapped: dict[str, str] = {}
        for j in range(0, len(missing), BATCH_SIZE):
            batch = [(p, qtype) for p in missing[j:j + BATCH_SIZE]]
            mapped.update(_classify_batch(batch))
        if not mapped:
            print(f"  [{i}/{total_files}] {f.name}：跳过（LLM 全失败）")
            continue
        if dry_run:
            continue
        for p in item["gold"]["reference_points"]:
            if p["id"] in mapped:
                p["point_type"] = mapped[p["id"]]
        f.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [{i}/{total_files}] {f.name}：补 {len(mapped)} 点")
        done += len(mapped)
    return done


def backfill_db() -> int:
    """真实库 weak_points 老行按题目 JSON 回填 point_type。"""
    if not DB_PATH.exists():
        print("无 data/shenlun.db，跳过库回填")
        return 0
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT point_key, question_id FROM weak_points WHERE point_type=''"
        ).fetchall()
        if not rows:
            print("weak_points 无待回填行")
            return 0
        # 一次读全部题目 JSON，按 qid 缓存 gold 点
        cache: dict[str, dict[str, str]] = {}
        for f in BENCHMARK_DIR.glob("*.json"):
            item = json.loads(f.read_text(encoding="utf-8"))
            cache[item["id"]] = {
                p["id"]: p.get("point_type", "")
                for p in item.get("gold", {}).get("reference_points", [])
            }
        filled = 0
        for row in rows:
            qid, pid = row["question_id"], row["point_key"].split(":", 1)[1]
            pt = cache.get(qid, {}).get(pid, "")
            if pt:
                conn.execute(
                    "UPDATE weak_points SET point_type=? WHERE point_key=?",
                    (pt, row["point_key"]),
                )
                filled += 1
        conn.commit()
        print(f"weak_points 回填 {filled}/{len(rows)} 行")
        return filled
    finally:
        conn.close()


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    print("== 1/2 benchmark 金标补 point_type ==")
    backfill_benchmark(dry_run=dry)
    if dry:
        print("（--dry-run：仅预览，未写盘）")
        sys.exit(0)
    print("\n== 2/2 真实库 weak_points 回填 ==")
    backfill_db()
