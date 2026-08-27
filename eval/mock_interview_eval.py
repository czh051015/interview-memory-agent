"""L3 判别 eval —— 证明阅卷人能稳定区分好/坏答案（评分置信度的唯一证明）。

被测阅卷人：src.mock.judge.judge_single_round（use_rubric=True 量规版 / False 旧版）
样本：eval/samples/answers.json（人工定题 + LLM 生成 4 类答案 + 用户校准 good/confident）

判别断言（每题 4 类答案，三态映射 pass=2 / partial=1 / fail=0）：
  · good vs bad      strict：judge(good) > judge(bad)        —— 核心区分力
  · order_ok         弱序：judge(good) >= judge(mediocre) >= judge(bad)
  · strict_order     强序：judge(good) >  judge(mediocre) >  judge(bad)
  · no_fool          confident 不得被判 pass                  —— 不被自信错答骗
  · question_pass    good→pass 且 bad→fail                   —— 题本身可判

门槛（grill 定稿）：discrimination_rate ≥ 0.8，no_fool_rate == 1.0。
设计要点（四模式消融，两个正交旋钮：use_rubric=prompt 选型，inject_reference=金标准注入）：
  · A legacy       plain prompt + 不注入（模拟产品修复前现状）——对比基线
  · B plain_inject plain prompt + 注入金标准 —— 反例对照（plain 不强制引原文，未必会用金标准）
  · C rubric_no_ref rubric prompt + 不注入 —— 量规 prompt 单独贡献
  · D rubric       rubric prompt + 注入金标准 —— 当前默认（修复后）
  · 校准 fail-closed：good/confident 未全量 approved 则拒绝运行

用法：
  python eval/mock_interview_eval.py            # 只跑 D 量规版（44 次 LLM 调用）
  python eval/mock_interview_eval.py --compare  # 四模式消融 A/B/C/D（176 次）
  python eval/mock_interview_eval.py --cross-model  # 追加第二判官跑同一套样本（独立先验验证）
输出：eval/mock_interview_eval_results.json（可串 CI，风格对齐 retrieval_eval/llm_judge_eval）
"""
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.mock.judge import judge_single_round
from src.config import CROSS_MODEL

EVAL_DIR = Path(__file__).resolve().parent
SAMPLES = EVAL_DIR / "samples"
OUT = EVAL_DIR / "mock_interview_eval_results.json"

_ORD = {"pass": 2, "partial": 1, "fail": 0}
_PASS = 2


def _mode_label(use_rubric: bool, inject_reference: bool | None) -> str:
    if use_rubric and inject_reference:
        return "rubric"            # D 当前
    if use_rubric and not inject_reference:
        return "rubric_no_ref"     # C
    if not use_rubric and inject_reference:
        return "plain_inject"      # B
    return "legacy"                # A 当前 legacy

# 门槛（grill 定稿）
THRESHOLDS = {"discrimination": 0.8, "no_fool": 1.0}

_CALIBRATION_NEEDED = ("good", "confident")  # 必须经人工校准的两类


def _judge_ok(judge: dict) -> bool:
    return judge.get("suggested") in _ORD


def run_judge(question: str, answer: str, *, expected_points, use_rubric: bool,
              inject_reference: bool | None = None, cross: bool = False) -> str:
    """跑一次阅卷，返回三态；失败兜底 partial（与产品行为一致）。cross=True 走第二判官。

    inject_reference 独立开关：是否把金标准参考答案喂给阅卷人。默认跟随 use_rubric（向后兼容）。
    """
    if inject_reference is None:
        inject_reference = use_rubric
    judge = judge_single_round(
        question, answer,
        expected_points=expected_points if inject_reference else None,
        use_rubric=use_rubric,
        cross=cross,
    )
    return judge.get("suggested", "partial") if _judge_ok(judge) else "partial"


def check_calibration(items: list[dict]) -> list[str]:
    """fail-closed：good/confident 未校准的题列出，供调用方拒绝运行。"""
    pending = []
    for it in items:
        cal = it.get("calibration") or {}
        for key in _CALIBRATION_NEEDED:
            if cal.get(key) != "approved":
                pending.append(f"{it['id']}.{key}")
    return pending


def evaluate(items: list[dict], *, use_rubric: bool, inject_reference: bool | None = None,
             cross: bool = False, label: str | None = None) -> dict:
    """对全部样本跑一遍阅卷，返回逐题判定 + 汇总指标。cross=True 走第二判官。"""
    per_question = []
    for it in items:
        q = it["question"]
        exp = it.get("expected_points") or []
        judged = {
            kind: run_judge(q, it["answers"][kind], expected_points=exp,
                            use_rubric=use_rubric, inject_reference=inject_reference, cross=cross)
            for kind in ("good", "mediocre", "bad", "confident")
        }
        g, m, b, c = (_ORD[judged[k]] for k in ("good", "mediocre", "bad", "confident"))
        per_question.append({
            "id": it["id"],
            "topic": it["topic"],
            "judgments": judged,
            "checks": {
                "good_gt_bad": g > b,
                "order_ok": g >= m >= b,
                "strict_order": g > m > b,
                "no_fool": c != _PASS,
                "question_pass": judged["good"] == "pass" and judged["bad"] == "fail",
            },
        })

    n = len(per_question)
    def rate(key):
        return round(sum(1 for p in per_question if p["checks"][key]) / n, 4) if n else 0.0

    return {
        "judge_mode": label or _mode_label(use_rubric, inject_reference),
        "model": CROSS_MODEL if cross else "deepseek-chat",
        "cross": cross,
        "samples": n,
        "metrics": {
            "discrimination_rate": rate("good_gt_bad"),
            "order_ok_rate": rate("order_ok"),
            "strict_order_rate": rate("strict_order"),
            "no_fool_rate": rate("no_fool"),
            "question_pass_rate": rate("question_pass"),
        },
        "per_question": per_question,
    }


def main() -> int:
    if not SAMPLES.exists() or not (SAMPLES / "answers.json").exists():
        print("缺样本：先跑 eval/generate_samples.py 生成答案，并完成人工校准。")
        return 1

    data = json.loads((SAMPLES / "answers.json").read_text(encoding="utf-8"))
    items = data["items"]

    pending = check_calibration(items)
    if pending:
        print(f"❌ 校准未完成（{len(pending)} 项 pending）：")
        for p in pending:
            print(f"   - {p}")
        print("请打开 eval/samples/answers.json，校准每题的 good 与 confident，")
        print("把 calibration 字段改为 \"approved\" 后重跑。")
        return 1

    compare = "--compare" in sys.argv
    cross = "--cross-model" in sys.argv
    runs = [evaluate(items, use_rubric=True, inject_reference=True)]                       # D 默认
    if compare:
        runs.append(evaluate(items, use_rubric=False, inject_reference=False, label="legacy"))        # A
        runs.append(evaluate(items, use_rubric=False, inject_reference=True, label="plain_inject"))   # B
        runs.append(evaluate(items, use_rubric=True, inject_reference=False, label="rubric_no_ref"))  # C
    if cross:
        # 第二判官：同一套样本、同一量规，独立模型（默认 deepseek-reasoner，可配独立供应商）
        runs.append(evaluate(items, use_rubric=True, cross=True, label="rubric_cross"))

    result = {
        "meta": {
            "generated": "2026-08-19",
            "samples": len(items),
            "thresholds": THRESHOLDS,
            "cross_model": CROSS_MODEL,
            "note": "四模式消融：A legacy(plain+无注入) / B plain_inject(plain+注入) / C rubric_no_ref(rubric+无注入) / D rubric(rubric+注入)。"
                    "归因（固定另一旋钮）：D-C=注入贡献，D-B=量规 prompt 贡献，D-A=整体增益（修复前后）。no_fool=confident 未判 pass。"
                    "rubric_cross=第二判官（默认 deepseek-reasoner，配置 CROSS_MODEL_* 可换独立供应商）验证非单模型自洽。",
        },
        "runs": runs,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 68)
    for r in runs:
        m = r["metrics"]
        status = "PASS" if (m["discrimination_rate"] >= THRESHOLDS["discrimination"]
                            and m["no_fool_rate"] >= THRESHOLDS["no_fool"]) else "FAIL"
        print(f"[{r['judge_mode']:>12}] model={r.get('model',''):<16} "
              f"disc={m['discrimination_rate']:.0%} strict={m['strict_order_rate']:.0%} "
              f"no_fool={m['no_fool_rate']:.0%} qpass={m['question_pass_rate']:.0%} → {status}")
    print("=" * 68)
    # 归因（两正交旋钮的边际贡献，均固定另一旋钮）：
    #   注入贡献  D - C：prompt 同为 rubric，只变量金标准注入
    #   量规贡献  D - B：注入同为真，只变量 prompt（rubric vs plain）
    #   整体增益  D - A：修复前后
    _rubric = next((r for r in runs if r["judge_mode"] == "rubric"), None)
    _c = next((r for r in runs if r["judge_mode"] == "rubric_no_ref"), None)
    _b = next((r for r in runs if r["judge_mode"] == "plain_inject"), None)
    _a = next((r for r in runs if r["judge_mode"] == "legacy"), None)
    if _rubric and _c:
        print(f"\n[注入贡献] D - C: 区分力 {_rubric['metrics']['discrimination_rate']-_c['metrics']['discrimination_rate']:+.0%}"
              f"  抗骗 {_rubric['metrics']['no_fool_rate']-_c['metrics']['no_fool_rate']:+.0%}")
    if _rubric and _b:
        print(f"[量规贡献] D - B: 区分力 {_rubric['metrics']['discrimination_rate']-_b['metrics']['discrimination_rate']:+.0%}"
              f"  抗骗 {_rubric['metrics']['no_fool_rate']-_b['metrics']['no_fool_rate']:+.0%}")
    if _rubric and _a:
        print(f"[整体增益] D - A: 区分力 {_rubric['metrics']['discrimination_rate']-_a['metrics']['discrimination_rate']:+.0%}"
              f"  抗骗 {_rubric['metrics']['no_fool_rate']-_a['metrics']['no_fool_rate']:+.0%}")
    print(f"结果已落盘 → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
