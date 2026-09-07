"""seed 模拟练习历史 —— 填充薄弱档案，演示记忆机制动态分层（docs/40）。

用法：
  python scripts/seed_weak_history.py                    # 抽 6 题 + 固定 seed，灌真实库
  python scripts/seed_weak_history.py --dry-run          # 只打印计划（不备份不写库）
  python scripts/seed_weak_history.py --count 8 --seed 3 # 自选规模 / 换一批

职责：薄 CLI —— 抽题（sampler）+ 场景构造（loader.prepare）+ 打印汇报；
写库 / 备份逻辑只调 loader 与文件复制，不含任何业务判断。
数据性质声明：模拟练习（非真实作答），仅用于演示记忆机制；已 seed 的题不会重复写库。
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

from src.shenlun import profile, reflow
from src.shenlun.seed import loader, sampler

DEFAULT_SEED = 773
BACKUP = reflow.DB_PATH.with_suffix(reflow.DB_PATH.suffix + ".bak")


def _practiced_ids() -> list[str]:
    """实查 DB：已练过的 question_id（只读，作为抽题排除集）。"""
    if not reflow.DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(reflow.DB_PATH))
    try:
        return [r[0] for r in conn.execute("SELECT DISTINCT question_id FROM answers")]
    finally:
        conn.close()


def _backup() -> None:
    """首次运行自动备份（已存在则不覆盖），随时可回滚。"""
    if not BACKUP.exists():
        shutil.copy2(reflow.DB_PATH, BACKUP)
        print(f"备份 → {BACKUP.relative_to(Path.cwd())}")


def print_plan(scenarios, questions_by_id) -> None:
    print("\n=== 练习计划（模拟历史，非真实作答）===")
    total_weak = 0
    for s in scenarios:
        q = questions_by_id[s.question_id]
        title = q["task"]["question"][:46]
        rounds = " → ".join(f"{a.days_ago} 天前" for a in s.attempts)
        labels = "、".join(p["point"] for p in s.weak_points)
        total_weak += len(s.weak_points)
        print(f"\n[{s.question_id}] {q['meta']['province']}{q['meta']['year']} {s.question_type}")
        print(f"  题目：{title}")
        print(f"  练习日：{rounds}（共 {len(s.attempts)} 次作答）")
        print(f"  漏点 {len(s.weak_points)} 个：{labels}")
    print(f"\n计划：{len(scenarios)} 道题、新增薄弱点约 {total_weak} 个")


def print_tiers(limit: int = 12) -> None:
    print("\n=== 分层预览（profile.read_weak_points，确定性 0 LLM）===")
    pts = profile.read_weak_points(limit=50)
    for tier, icon in (("red", "🔴"), ("yellow", "🟡"), ("green", "🟢")):
        group = [p for p in pts if p.tier == tier][:limit]
        if not group:
            continue
        print(f"{icon} {tier} 档（{len(group)}）：")
        for p in group:
            days = int(profile._elapsed_days(p.last_practiced_at or p.last_miss_at,
                                             profile.utcnow()))
            print(f"   · [{p.qtype}] {p.label}（{p.question_id}，漏 {p.miss_count} 次，"
                  f"{days} 天没练，urgency={p.urgency:.3f}）")


def main() -> int:
    ap = argparse.ArgumentParser(description="seed 模拟练习历史（docs/40）")
    ap.add_argument("--count", type=int, default=6, help="抽题数（推荐 6–8）")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED, help="随机种子（可复现）")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不写库不备份")
    args = ap.parse_args()

    if loader.is_seed_applied(args.seed):
        print(f"seed={args.seed} 之前已跑过并落库（幂等），本次跳过，不重复写库。")
        return 0

    exclude = set(_practiced_ids()) | set(loader.load_seeded_ids())
    picked = sampler.pick_question_ids(reflow.list_questions(), exclude, args.count, args.seed)
    if not picked:
        print("题库已全部练过 / seed 过，无可新增题目。如需重来：先还原 DB，再删 data/seed/weak_history_seed.json")
        return 0
    if len(picked) < args.count:
        print(f"排除已练/已 seed 后剩余 {len(picked)} 道 < {args.count}，本次按实际数量抽")
    questions = [reflow.load_question(qid) for qid in picked]
    by_id = {q["id"]: q for q in questions}
    scenarios = loader.prepare_scenarios(questions, args.seed)
    print(f"seed={args.seed} · 计划抽 {args.count} 道 → 实抽 {len(picked)} 道")
    print_plan(scenarios, by_id)
    if args.dry_run:
        print("\n[dry-run] 未写库、未备份。")
        return 0

    _backup()
    report = loader.seed_scenarios(scenarios, seed=args.seed)
    print("\n=== 落库结果 ===")
    print(f"写库 {len(report.written)} 道题 / {report.answers_written} 次作答"
          + (f"，跳过已 seed {len(report.skipped)} 道" if report.skipped else ""))
    for qid in report.written:
        print(f"  ✓ {qid}")
    print_tiers()
    print(f"\n回滚口令：Copy-Item -Force '{BACKUP}' '{reflow.DB_PATH}'"
          "\n（如需重新 seed：还原后删除 data/seed/weak_history_seed.json）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


