"""申论评审 Agent · 演示闭环：抽题 → 作答 → 错题回流 → ReAct 建议。

用法：
    python scripts/run_shenlun.py                    # 交互：选一题 → 输入作答 → 回流 → 建议
    python scripts/run_shenlun.py --list             # 列出题库
    python scripts/run_shenlun.py --demo             # 自动演示（用 benchmark 的 good/bad 作答跑一遍）
    python scripts/run_shenlun.py --advice           # 只出今日建议（读已有档案，不作答）

用 Anaconda Python 跑：D:/ProgramData/anaconda3/python.exe scripts/run_shenlun.py
"""

from __future__ import annotations

import argparse
import sys

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from src.shenlun.reflow import (
    reflow_answer, load_question, list_questions, graduate_hits,
    ACTION_ANSWERED, ACTION_GRADUATION_CHECK,
)
from src.shenlun.profile import weakness_snapshot, stats, graduation_candidates
from src.shenlun.react import decide


def print_decision(out, *, indent: str = "") -> None:
    """打印决策：action + 计划 + 建议 + 毕业考候选（docs/17 §4.3）。"""
    print(f"{indent}⚡ action={out.action}" + ("（规则回退）" if out.fallback else ""))
    cands = graduation_candidates()
    if cands:
        print(f"{indent}🎓 毕业考候选（连续命中达标+间隔验证到期，可安排验证）:")
        for wp in cands[:3]:
            print(f"{indent}   · [{wp.qtype}] {wp.label}（{wp.question_id}，连续命中 {wp.consecutive_hits} 次）")
    for p in out.plan:
        print(f"{indent}   · {p['question_id']} — {p.get('why', '')[:60]}")
    if out.advice:
        print(f"{indent}💡 {out.advice}")


def cmd_list() -> None:
    print("=== 题库（benchmark/data）===")
    for q in list_questions():
        print(f"  {q['id']:<24} [{q['province']}{q['year']} {q['type']}] {q['question']}")


def cmd_interactive() -> None:
    bank = list_questions()
    print("=== 题库 ===")
    for i, q in enumerate(bank, 1):
        print(f"  {i}. {q['id']} [{q['type']}] {q['question'][:50]}")
    while True:
        try:
            n = int(input("\n选一题（输入编号，0 退出）: "))
        except (ValueError, EOFError):
            break
        if n == 0:
            break
        if n < 1 or n > len(bank):
            print("编号无效")
            continue
        q = bank[n - 1]
        item = load_question(q["id"])
        print(f"\n【{item['meta']['type']} · {item['meta']['province']}{item['meta']['year']}】")
        print(f"题目：{item['task']['question']}")
        print(f"要求：{item['task']['requirements']}")
        print(f"材料：{item['task']['material'][:200]}...")
        answer = input("\n写你的作答（回车结束）: ").strip()
        if not answer:
            continue
        qid = item["id"]
        # 毕业考判定（docs/17 §3 出口1）：作答前采集候选——作答会更新 last_hit_at，事后采集会漏判
        cand_keys = {wp.point_key for wp in graduation_candidates()}
        is_check = any(f"{qid}:{p['id']}" in cand_keys for p in item["gold"]["reference_points"])
        r = reflow_answer(
            qid, item["meta"]["type"], answer, item["gold"]["reference_points"],
            action=ACTION_GRADUATION_CHECK if is_check else ACTION_ANSWERED,
        )
        print(f"\n📊 命中 {len(r.result.hit_ids)}/{len(r.result.hit_ids)+len(r.result.miss_ids)}"
              + ("（本次为毕业考）" if is_check else ""))
        print(f"   漏掉采分点：{', '.join(p.point for p in r.result.miss_points) or '无'}")
        # 毕业考命中 → 毕业（移出提醒池，档案保留）
        graduated = graduate_hits(qid, r.result.hit_ids, cand_keys)
        for pid in graduated:
            point = next(p for p in r.result.hit_points if p.id == pid)
            print(f"   🎓 毕业考命中：{point.point} 已毕业（移出提醒池，档案保留）")
        if r.revived:
            print("   ♻ 有 graduated/stuck 的点被练到，已复活回提醒池")
        print("\n--- 薄弱点档案 ---")
        print(weakness_snapshot(limit=5))


def cmd_demo() -> None:
    """用 benchmark 的 good/bad 作答演示一遍完整闭环。"""
    print("=== 申论评审 Agent · 演示闭环 ===\n")
    # 1. 作答 good（满分档）
    qid = "henan_2025_city_1"
    item = load_question(qid)
    print(f"【步骤1】作答：{qid}（good 满分档）")
    r1 = reflow_answer(qid, item["meta"]["type"], item["samples"]["good"]["text"], item["gold"]["reference_points"])
    print(f"  命中 {len(r1.result.hit_ids)}/9，错题回流完成 ✓\n")
    # 2. 作答 bad（跑题档）
    print(f"【步骤2】作答：{qid}（bad 跑题档）")
    r2 = reflow_answer(qid, item["meta"]["type"], item["samples"]["bad"]["text"], item["gold"]["reference_points"])
    print(f"  命中 {len(r2.result.hit_ids)}/9，漏点已入档案 ✓\n")
    # 3. 薄弱点档案
    print("【步骤3】薄弱点档案（自动聚合）：")
    print(weakness_snapshot(limit=5))
    print()
    # 4. ReAct 决策
    print("【步骤4】ReAct 决策（读档案 → 检索题库 → 建议）：")
    out = decide(question_id=qid)
    print(f"  🎯 {out.focus}")
    print_decision(out, indent="  ")


def cmd_advice() -> None:
    print("=== 今日练习建议（基于薄弱点档案）===")
    st = stats()
    print(f"已积累薄弱点：{st['total_points']} 个")
    print()
    out = decide()
    print(f"🎯 {out.focus}")
    print_decision(out, indent="  ")


def main() -> None:
    ap = argparse.ArgumentParser(description="申论评审 Agent 演示")
    ap.add_argument("--list", action="store_true", help="列出题库")
    ap.add_argument("--demo", action="store_true", help="自动演示完整闭环")
    ap.add_argument("--advice", action="store_true", help="只出今日建议")
    args = ap.parse_args()

    if args.list:
        cmd_list()
    elif args.demo:
        cmd_demo()
    elif args.advice:
        cmd_advice()
    else:
        cmd_interactive()


if __name__ == "__main__":
    main()
