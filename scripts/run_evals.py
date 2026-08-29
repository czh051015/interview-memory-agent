"""Eval 全套统一入口：串起 3 个申论 eval 套件 + 时间戳归档 + 与上一轮回归对比。

零侵入：只 subprocess 调用并复制结果，不 import 任何一个 eval 模块内部逻辑。
套件（docs/19 §3 改造后：全申论域）：
  1. score     评分传感器（确定性，秒级）
  2. decompose 拆解质量（LLM，金标对照 + 脏标答）
  3. guidance  逼近引导（LLM，红线 + 质量）
用法：
  python scripts/run_evals.py                 # 跑全部 3 套件 + 归档 + 与上一轮对比
  python scripts/run_evals.py --no-compare    # 跳过对比生成（仅归档）
  python scripts/run_evals.py --baseline      # 快照当前固定 json 为 baseline 锚点（不跑）
  python scripts/run_evals.py --list          # 列出 eval/results/ 下所有 run 及时间
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = ROOT / "eval"
RESULTS_DIR = EVAL_DIR / "results"
LATEST_POINTER = RESULTS_DIR / ".latest"
PY = sys.executable

# (套件名, 脚本相对路径, 固定 json 名)
SUITES = [
    ("score", "eval/score_eval.py", "score_eval_results.json"),
    ("decompose", "eval/decompose_eval.py", "decompose_eval_results.json"),
    ("guidance", "eval/guidance_eval.py", "guidance_eval_results.json"),
]

# 6 项 headline 指标：(指标名, 套件, extract 后 summary 里的路径, 方向)
# 方向 up=越大越好 / down=越小越好（臆造点率、红线类指标是 ↓，delta<0 才算提升）
HEADLINE = [
    ("评分 no_fool", "score", "no_fool", "up"),
    ("拆解点覆盖率", "decompose", "point_recall", "up"),
    ("拆解臆造点率", "decompose", "fabrication_rate", "down"),
    ("引导 no_spoiler", "guidance", "no_spoiler", "up"),
    ("引导 hint_grounded", "guidance", "hint_grounded", "up"),
    ("评分 discrimination", "score", "mean_discrimination", "up"),
]


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _get(data: dict | None, path) -> float | None:
    """按 HEADLINE 的 path 取指标值；任一环节缺失返回 None。"""
    if data is None:
        return None
    if isinstance(path, str):
        return data.get(path)
    cur = data
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur if isinstance(cur, (int, float)) else None


def extract_summary(run_dir: Path) -> dict:
    """纯函数：把 3 个原始 json 扁平化为 summary（不依赖 subprocess，便于单测）。

    指标缺失的套件 ok=false 并留错误摘要。
    """
    created = run_dir.name if run_dir.name and run_dir.name != "baseline" else datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    summary = {
        "run_id": run_dir.name,
        "created_at": created,
        "labels": {"llm_calls": 0},
        "suites": {},
    }

    # score（顶层字段稳定化，docs/19 §4.1）
    s = _load_json(run_dir / "score_eval_results.json")
    if s is None:
        summary["suites"]["score"] = {"ok": False, "error": "json 缺失或损坏"}
    else:
        summary["suites"]["score"] = {
            "ok": True,
            "data_count": s.get("data_count"),
            "n_points": s.get("n_points"),
            "mean_discrimination": s.get("mean_discrimination"),
            "no_fool": s.get("no_fool"),
            "per_type": s.get("per_type"),
            "good_leak_count": s.get("good_leak_count"),
            "bad_fooled_ids": s.get("bad_fooled_ids"),
        }

    # decompose（docs/19 §4.2）
    dc = _load_json(run_dir / "decompose_eval_results.json")
    if dc is None:
        summary["suites"]["decompose"] = {"ok": False, "error": "json 缺失或损坏"}
    else:
        sm = dc.get("summary", {})
        summary["suites"]["decompose"] = {
            "ok": True,
            "decomposed_count": sm.get("decomposed_count"),
            "point_recall": sm.get("point_recall"),
            "fabrication_rate": sm.get("fabrication_rate"),
            "structural_ok": sm.get("structural_ok"),
            "score_deviation_mean": (sm.get("score_deviation") or {}).get("mean"),
            "over_split_flags": sm.get("over_split_flags"),
            "dirty_robustness": sm.get("dirty_robustness"),
            "calibrated": sm.get("calibrated"),
        }
        summary["labels"]["llm_calls"] += sm.get("llm_calls") or 0

    # guidance（docs/19 §4.3）
    g = _load_json(run_dir / "guidance_eval_results.json")
    if g is None:
        summary["suites"]["guidance"] = {"ok": False, "error": "json 缺失或损坏"}
    else:
        sm = g.get("summary", {})
        summary["suites"]["guidance"] = {
            "ok": True,
            "sample_count": sm.get("sample_count"),
            "no_spoiler": sm.get("no_spoiler"),
            "no_fabrication": sm.get("no_fabrication"),
            "hint_grounded": sm.get("hint_grounded"),
            "judge_score_mean": (sm.get("judge_score") or {}).get("mean"),
            "empty_guidance_count": sm.get("empty_guidance_count"),
        }
        summary["labels"]["llm_calls"] += sm.get("llm_calls") or 0

    return summary


def _fmt(v) -> str:
    return f"{v:.3f}" if isinstance(v, (int, float)) else "N/A"


def build_comparison(cur: dict, prev: dict) -> str:
    """纯函数：当前 vs 上一轮 summary → comparison.md 文本（不依赖 subprocess）。

    Δ = cur - prev；保留两位小数；任一侧缺失该格 N/A，不参与 Δ。
    方向判定：up 指标 Δ>0 标 ✅ 提升；down 指标（臆造点率等）Δ<0 标 ✅ 提升。
    """
    lines = [
        f"# Eval 回归对比 — {cur.get('run_id')}",
        "",
        f"> 对比基准：{prev.get('run_id')}  →  本轮：{cur.get('run_id')}",
        f"> 生成时间：{cur.get('created_at')}",
        "",
        "| 指标 | 上次 | 本次 | 变化 | 判定 |",
        "|---|---|---|---|---|",
    ]
    for name, suite, path, direction in HEADLINE:
        a = _get(prev.get("suites", {}).get(suite), path)
        b = _get(cur.get("suites", {}).get(suite), path)
        if a is None or b is None:
            lines.append(f"| {name} | {_fmt(a)} | {_fmt(b)} | N/A | — 缺失 |")
            continue
        delta = round(b - a, 3)
        better = (delta > 0) if direction == "up" else (delta < 0)
        judge = "✅ 提升" if better else ("⚠️ 回退" if delta != 0 else "— 持平")
        lines.append(f"| {name} | {_fmt(a)} | {_fmt(b)} | {delta:+.2f} | {judge} |")

    lines += ["", "## 套件状态"]
    for name, _, _ in SUITES:
        s = cur.get("suites", {}).get(name, {})
        desc = f"（llm_calls={cur.get('labels', {}).get('llm_calls')}）" if name == "guidance" else ""
        lines.append(f"- {name}: {'ok' if s.get('ok') else 'fail'}{desc}")
    return "\n".join(lines) + "\n"


def first_run_md(cur: dict) -> str:
    lines = [
        f"# Eval 回归对比 — {cur.get('run_id')}",
        "",
        "> 首次运行，无历史对比。本轮绝对值：",
        "",
        "| 指标 | 本次 |",
        "|---|---|",
    ]
    for name, suite, path, _direction in HEADLINE:
        lines.append(f"| {name} | {_fmt(_get(cur.get('suites', {}).get(suite), path))} |")
    lines.append("")
    for name, _, _ in SUITES:
        s = cur.get("suites", {}).get(name, {})
        lines.append(f"- {name}: {'ok' if s.get('ok') else 'fail'}")
    return "\n".join(lines) + "\n"


def _copy_if_exists(src: Path, dst_dir: Path) -> bool:
    if src.exists():
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst_dir.joinpath(src.name).write_bytes(src.read_bytes())
        return True
    return False


def _run_one(rel: str, extra_args: list[str]) -> tuple[int, str]:
    cmd = [PY, str(ROOT / rel)] + extra_args
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stdout + p.stderr


def run_all_evals(no_compare: bool) -> int:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RESULTS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # 3 套件依次跑，任一失败不中断其余
    results = {}
    log_lines = []
    for label, rel, jname in SUITES:
        print(f"▶ [{label}] python {rel}")
        returncode, out = _run_one(rel, [])
        log_lines.append(f"===== {label} (rc={returncode}) =====\n{out}")
        ok = returncode == 0 and _copy_if_exists(RESULTS_DIR / "baseline" / jname, run_dir)
        results[label] = {"rc": returncode, "ok": ok}
        if not ok:
            print(f"  ✗ {label} 失败（rc={returncode}），无 json 或非 0 退出")

    # 写日志
    (run_dir / "eval_run.log").write_text("\n".join(log_lines), encoding="utf-8")

    # 提取 summary
    summary = extract_summary(run_dir)
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # 对比
    prev_id = _read_latest()
    if not no_compare:
        if prev_id and (prev_dir := RESULTS_DIR / prev_id).exists() and (prev_dir / "summary.json").exists():
            prev = _load_json(prev_dir / "summary.json")
            (run_dir / "comparison.md").write_text(build_comparison(summary, prev), encoding="utf-8")
        else:
            (run_dir / "comparison.md").write_text(first_run_md(summary), encoding="utf-8")

    # 更新指针
    LATEST_POINTER.write_text(run_id, encoding="utf-8")

    # 打印摘要
    print("\n" + "=" * 60)
    print(f"run_id: {run_id} → {run_dir}")
    for label, _, _ in SUITES:
        r = results[label]
        print(f"  {label:<14} ok={r['ok']} rc={r['rc']}")
    print(f"  llm_calls（本轮）: {summary.get('labels', {}).get('llm_calls')}")
    if not no_compare and (run_dir / "comparison.md").exists() and (run_dir / "comparison.md").read_text(encoding="utf-8").startswith("# Eval 回归对比 —"):
        print(f"  comparison: {run_dir / 'comparison.md'}")

    all_ok = all(r["ok"] for r in results.values())
    return 0 if all_ok else 1


def baseline_snapshot() -> int:
    """登记 baseline：eval 脚本产物直接落在 results/baseline/（3 个 eval 脚本 --out 默认路径），
    这里只需确认 3 个 json 在位并写 summary.json + 指针。"""
    target = RESULTS_DIR / "baseline"
    target.mkdir(parents=True, exist_ok=True)
    n = 0
    for _, _, jname in SUITES:
        if (target / jname).exists():
            n += 1
    summary = extract_summary(target)
    (target / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    LATEST_POINTER.write_text("baseline", encoding="utf-8")
    print(f"baseline 已登记：{n}/{len(SUITES)} 个 json（位于 {target}）")
    print("后续真实 run 将以 baseline 为对比基准。")
    return 0


def _read_latest() -> str | None:
    if not LATEST_POINTER.exists():
        return None
    return LATEST_POINTER.read_text(encoding="utf-8").strip() or None


def list_runs() -> int:
    if not RESULTS_DIR.exists():
        print("eval/results/ 尚不存在。")
        return 0
    latest = _read_latest()
    print("run_id               | 最近 | 生成时间")
    print("---------------------|------|--------------------")
    for d in sorted(RESULTS_DIR.iterdir(), key=lambda p: p.name):
        if not d.is_dir():
            continue
        s = _load_json(d / "summary.json")
        mark = " ★" if d.name == latest else ""
        print(f"{d.name:<19} | {mark:<3} | {s.get('created_at') if s else '-'}")
    return 0


def main(argv: list[str]) -> int:
    if "--list" in argv:
        return list_runs()
    if "--baseline" in argv:
        return baseline_snapshot()
    return run_all_evals(no_compare="--no-compare" in argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
