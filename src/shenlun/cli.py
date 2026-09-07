"""申论示证 CLI（docs/22 §5）—— 上传 题干+材料+标准答案+作答 → 评分 + 示证。

用法：
  python -m src.shenlun.cli --gold benchmark/data/henan_2025_city_1.json --answer "H市开通了城际公交。"
  python -m src.shenlun.cli --question "..." --material "..." \
      --gold '{"reference_points":[{"id":"c1","point":"设施互通","keywords":["城际公交"],"score":2}]}' \
      --answer "..."
  python -m src.shenlun.cli --question "..." --material "..." --gold "标准答案全文（散文式）" --answer "..."

行为：
  1. 解析 gold → reference_points（结构化 JSON 直接解析，0 token；散文式才 LLM 拆解兜底）
  2. score_answer → 打印 L1：命中/漏点列表，每漏点挂材料原话（material_source）
  3. pick_leading_point 推 1 个最该补的漏点 + guidance 生成示证（L3 锚定 + L2 示范 + L4 错因）
  4. 交互命令：show <point_id> 展开其他漏点的 L2/L3/L4；add <point_id> 按漏点加入错题本；quit

关键约束（docs/22 §5）：CLI 调用的后端函数（score_answer / pick_leading_point / guidance /
build_wrongbook_item）= eval 与 API 复用的同一批函数，不另写两套逻辑。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.shenlun.score import from_benchmark, score_answer
from src.mock.runtime import guidance, pick_leading_point
from src.shenlun.wrongbook import build_wrongbook_item


def _parse_gold(gold_arg: str, question: str) -> dict:
    """解析 --gold → {"points", "material", "question_id", "question", "question_type"}。

    gold 三种形态（docs/22 §5）：
      1. 文件路径（benchmark/用户题 JSON，含 gold.reference_points）→ 直接解析，材料/题干/题型随文件；
      2. 内联 JSON 字符串（含 reference_points）→ 直接解析；
      3. 散文式标准答案全文 → decompose_points LLM 拆解兜底（极少，Q6 主路径 0 token）。
    """
    out = {"points": None, "material": "", "question_id": "cli",
           "question": "", "question_type": ""}
    raw: dict | None = None
    path = Path(gold_arg)
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            out["material"] = str(raw.get("task", {}).get("material") or "")
            out["question"] = str(raw.get("task", {}).get("question") or "")
            out["question_type"] = str(raw.get("meta", {}).get("type") or "")
            out["question_id"] = str(raw.get("id") or "cli")
        except (OSError, json.JSONDecodeError) as e:
            print(f"⚠️ --gold 文件解析失败：{e}；按散文式标准答案处理")
    else:
        try:
            raw = json.loads(gold_arg)
        except json.JSONDecodeError:
            raw = None

    if raw is not None:
        refs = raw.get("gold", {}).get("reference_points") or raw.get("reference_points")
        if refs:
            out["points"] = from_benchmark(refs)
            return out

    # 散文式兜底：LLM 拆解（docs/22 §5：极少，主路径 0 token）
    if not question:
        print("⚠️ 散文式 --gold 需要 --question 提供题干（拆解要用），退出。")
        sys.exit(1)
    print("（--gold 非结构化 JSON → LLM 拆解标准答案，稍候…）")
    from src.cleaner.decompose import decompose_points
    r = decompose_points(gold_arg, question=question, material=out["material"],
                         max_score=20, question_id="__cli__")
    pts = [p.model_dump() for p in r.reference_points]
    if not pts:
        print("⚠️ LLM 拆解未产出采分点，退出。")
        sys.exit(1)
    out["points"] = from_benchmark(pts)
    return out


def _print_l1(sr) -> None:
    """打印 L1：命中/漏点列表，每漏点挂材料原话。"""
    print(f"\n📊 评分 · 命中率 {sr.hit_ratio:.0%}")
    if sr.hit_points:
        print(f"✅ 命中 {len(sr.hit_points)} 个点：")
        for p in sr.hit_points:
            print(f"   · [{p.id}] {p.point}（{p.score} 分）—— 作答片段：{p.matched_text or ''}")
    if sr.miss_points:
        print(f"❌ 漏掉 {len(sr.miss_points)} 个点（材料锚定）：")
        for p in sr.miss_points:
            print(f"   · [{p.id}] {p.point}（{p.score} 分）")
            print(f"      📄 {p.material_source or '（材料中未锚到该点原话）'}")


def _print_show(g) -> None:
    """打印单个采分点的示证（L3 + L4 + L2 分支语境，docs/35 口径）。"""
    print(f"\n🔎 示证 · [{g.point_id}] {g.point}")
    if g.material_source:
        print(f"   📄 材料原话：{g.material_source}")
    else:
        print("   📄 材料原话：（未锚到，无锚点不硬标——疑似锚已砍，docs/35 D27）")
    if g.cause:
        # cause 已是「文本比对：…」（docs/33 §4.1 确定性），不再重复贴 cause_type 标签
        print(f"   🔬 {g.cause}")
    if g.fix:
        print(f"   🛠️ 参考改法（供参考，以官方答案为准）：{g.fix}")
    if g.demo:
        print(f"   ✍️ 分支语境示例（供参考，以官方答案为准）：{g.demo}")
    else:
        print("   ✍️ 分支语境示例：（未生成）")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="申论示证 CLI（docs/22 §5）")
    ap.add_argument("--question", help="题干（--gold 为 JSON 且含 task.question 时可省略）")
    ap.add_argument("--material", help="给定材料（--gold 为 JSON 时自动读取）")
    ap.add_argument("--gold", required=True, help="标准答案：benchmark JSON 路径 / 内联 JSON / 散文全文")
    ap.add_argument("--answer", required=True, help="用户作答")
    ap.add_argument("--qtype", default="", help="题型（散文式 gold 且无 meta.type 时兜底，如 归纳概括）")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows GBK 控制台打 emoji 会崩
    except Exception:
        pass

    parsed = _parse_gold(args.gold, args.question or "")
    points = parsed["points"]
    material = args.material or parsed["material"]
    question = args.question or parsed["question"]
    qtype = args.qtype or parsed["question_type"]
    qid = parsed["question_id"]

    # L1：评分（与 eval / API 同一函数）
    sr = score_answer(args.answer, points, materials=material)
    _print_l1(sr)
    if not sr.miss_points:
        print("\n🎉 采分点全部命中，无需示证。")
        return 0

    # 推 1 个最该补 + 示证（docs/22 §4 + Q7b：示证式主动，非逼问）
    leading = pick_leading_point(sr.miss_points, qid)
    print(f"\n🎯 最该补的漏点：[{leading.id}] {leading.point}（{leading.score} 分）")
    g = guidance(material, args.answer, points, leading.id, question=question)
    if g:
        _print_show(g)

    # 加入错题本用的题目载体（CLI 无题目库条目，按实际输入组装）
    item_ctx = {"id": qid, "task": {"question": question}, "meta": {"type": qtype}}
    shown: dict[str, dict] = {}

    while True:
        try:
            cmd = input("\n命令：show <漏点id> 展开示证 / add <漏点id> 加入错题本 / quit 退出 > ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break
        parts = cmd.split(maxsplit=1)
        if cmd.lower() in ("quit", "q", "exit"):
            break
        if len(parts) < 2 or parts[0] not in ("show", "add"):
            print("  格式：show c2 或 add c2（漏点 id 见上方列表）")
            continue
        pid = parts[1].strip()
        p = next((x for x in points if x.id == pid), None)
        if p is None:
            print(f"  无此漏点：{pid}")
            continue
        if parts[0] == "show":
            g = guidance(material, args.answer, points, pid, question=question)
            if g:
                _print_show(g)
                shown[pid] = {"demo": g.demo, "cause": g.cause, "cause_type": g.cause_type}
        else:  # add → 加入错题本（按漏点一条，docs/22 §3.6）
            sp = next((x for x in sr.hit_points + sr.miss_points if x.id == pid), None)
            s = shown.get(pid, {})
            ki = build_wrongbook_item(
                item_ctx, p,
                material_source=sp.material_source if sp else None,
                answer_snippet=(sp.matched_text if sp and sp.matched_text else ""),
                demo=s.get("demo", ""), cause=s.get("cause", ""),
                cause_type=s.get("cause_type", ""),
            )
            try:
                from src.memory import knowledge_store as store
                n = store.store_items([ki])
            except Exception as e:
                print(f"  ⚠️ 入库失败：{e}")
                continue
            print(f"  ✅ 已加入错题本（{ki.id}）" if n else "  ⚠️ 未写入")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
