"""L3 判别 eval —— 证明阅卷人能稳定区分好/坏答案（评分置信度的唯一证明）。

被测阅卷人：run_mock_interview.judge_single_round（use_rubric=True 量规版 / False 旧版）
样本：eval/samples/answers.json（人工定题 + LLM 生成 4 类答案 + 用户校准 good/confident）

判别断言（每题 4 类答案，三态映射 pass=2 / partial=1 / fail=0）：
  · good vs bad      strict：judge(good) > judge(bad)        —— 核心区分力
  · order_ok         弱序：judge(good) >= judge(mediocre) >= judge(bad)
  · strict_order     强序：judge(good) >  judge(mediocre) >  judge(bad)
  · no_fool          confident 不得被判 pass                  —— 不被自信错答骗
  · question_pass    good→pass 且 bad→fail                   —— 题本身可判

门槛（grill 定稿）：discrimination_rate ≥ 0.8，no_fool_rate == 1.0。
设计要点：
  · 量规版阅卷注入 L2 参考答案（expected_points）——阅卷对照金标准，不是自己现编
  · 旧版不注入（模拟产品现状：自生成要点）——对比 = 现状 vs 修复后的真实差距
  · 校准 fail-closed：good/confident 未全量 approved 则拒绝运行

用法：
  python eval/mock_interview_eval.py            # 只跑量规版（44 次 LLM 调用）
  python eval/mock_interview_eval.py --compare  # 量规版 vs 旧版（88 次）
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
from run_mock_interview import judge_single_round

EVAL_DIR = Path(__file__).resolve().parent
SAMPLES = EVAL_DIR / "samples"
OUT = EVAL_DIR / "mock_interview_eval_results.json"

_ORD = {"pass": 2, "partial": 1, "fail": 0}
_PASS = 2

# 门槛（grill 定稿）
THRESHOLDS = {"discrimination": 0.8, "no_fool": 1.0}

_CALIBRATION_NEEDED = ("good", "confident")  # 必须经人工校准的两类


def _judge_ok(judge: dict) -> bool:
    return judge.get("suggested") in _ORD


def run_judge(question: str, answer: str, *, expected_points, use_rubric: bool) -> str:
    """跑一次阅卷，返回三态；失败兜底 partial（与产品行为一致）。"""
    judge = judge_single_round(
        question, answer,
        expected_points=expected_points if use_rubric else None,
        use_rubric=use_rubric,
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


def evaluate(items: list[dict], *, use_rubric: bool) -> dict:
    """对全部样本跑一遍阅卷，返回逐题判定 + 汇总指标。"""
    per_question = []
    for it in items:
        q = it["question"]
        exp = it.get("expected_points") or []
        judged = {
            kind: run_judge(q, it["answers"][kind], expected_points=exp, use_rubric=use_rubric)
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
        "judge_mode": "rubric" if use_rubric else "legacy",
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
    runs = [evaluate(items, use_rubric=True)]
    if compare:
        runs.append(evaluate(items, use_rubric=False))

    result = {
        "meta": {
            "generated": "2026-08-19",
            "samples": len(items),
            "thresholds": THRESHOLDS,
            "note": "量规版注入 L2 参考答案；旧版不注入（模拟现状自生成要点）。no_fool=confident 未判 pass。",
        },
        "runs": runs,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 56)
    for r in runs:
        m = r["metrics"]
        status = "PASS" if (m["discrimination_rate"] >= THRESHOLDS["discrimination"]
                            and m["no_fool_rate"] >= THRESHOLDS["no_fool"]) else "FAIL"
        print(f"[{r['judge_mode']:>6}] discrimination={m['discrimination_rate']:.0%} "
              f"order_ok={m['order_ok_rate']:.0%} strict={m['strict_order_rate']:.0%} "
              f"no_fool={m['no_fool_rate']:.0%} question_pass={m['question_pass_rate']:.0%} → {status}")
    print("=" * 56)
    print(f"结果已落盘 → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
