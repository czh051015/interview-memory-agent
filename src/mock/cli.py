"""申论练习会话 CLI（docs/18 §4.5）：断点 → 抽题 → 练习 → 回流 → 循环。

main() 新流程：
  1. 读断点（有未完成 → 询问续练 or 重新开始；--recover 直接续练）
  2. 抽题：react.decide() 推荐优先；失败/无档案 → 题库随机（冷启动降级）
  3. practice_one() 循环：作答 → 评分 → 逼近 → 达标/上限
  4. reflow_answer 回流 + answer_rounds 轨迹
  5. 打印本次命中/漏点清单（确定性复盘，替代 LLM 报告）
  6. 循环 2-5，直到用户输入退出
"""

import logging
import random
import sys

import src.config as _cfg  # 活引用：CLI --space 在 import 后改 _cfg.SPACE
from src.shenlun.reflow import (
    reflow_answer, load_question, list_questions, ACTION_ANSWERED,
)
from src.shenlun.react import decide
from src.shenlun.score import from_benchmark
from src.mock.runtime import (
    practice_one, _progress_file, _load_practice, _clear_practice,
)


def _pick_question() -> str | None:
    """抽题：ReAct 推荐优先；推荐失败/无档案 → 题库随机（docs/18 §4.5 冷启动降级）。"""
    try:
        out = decide()
        if out.plan and out.plan[0].get("question_id"):
            return out.plan[0]["question_id"]
    except Exception as e:
        logging.warning("ReAct 抽题失败，题库随机：%s", e)
    bank = list_questions()
    if not bank:
        return None
    q = random.choice(bank)
    print(f"（ReAct 无推荐，题库随机：{q['id']} [{q['province']}{q['year']} {q['type']}]）")
    return q["id"]


def _ask(question: str, material: str, requirements: str, guidance) -> str:
    """收作答/补充的 ask_fn。guidance=None 收初稿，否则展示引导收补充。"""
    if guidance is None:
        print(f"\n{'=' * 50}\n【题目】{question}\n【要求】{requirements}\n{'=' * 50}")
        print(f"\n【材料】\n{material}\n")
        return input("✍️ 写你的作答（回车结束，q 退出）: ").strip()
    if guidance:
        print("\n📌 逼近引导（只提示方向，不代写）：")
        for g in guidance:
            print(f"   · {g['point']}：{g['hint']}")
    else:
        print("\n（本轮无引导——LLM 引导失败，请凭材料再想想）")
    return input("✍️ 根据提示补充你的作答（回车跳过，q 退出）: ").strip()


def _run_one(question_id: str, *, resume_rounds=None):
    """练一题：practice_one → 回流 + 轨迹 → 返回 (result, item) 供打印复盘。"""
    item = load_question(question_id)
    if not item:
        print(f"⚠️ 题目不存在：{question_id}")
        return None
    question = item["task"]["question"]
    requirements = item["task"].get("requirements", "")
    material = item["task"]["material"]
    points = from_benchmark(item["gold"]["reference_points"])
    print(f"\n【{item['meta']['type']} · {item['meta']['province']}{item['meta']['year']}】")

    def ask_fn(question, material, guidance):
        return _ask(question, material, requirements, guidance)

    try:
        result = practice_one(
            question_id, question, material, points, ask_fn,
            progress_path=str(_progress_file()), resume_rounds=resume_rounds,
        )
    except (KeyboardInterrupt, EOFError):
        print("\n⏸ 已保存练习进度，随时重跑 `python -m src.mock` 续练。")
        raise

    # 回流：终稿入库 + 每轮轨迹 answer_rounds（weak_points 按终稿命中更新）
    rounds = [
        {"round_no": r.round_no, "answer": r.answer, "hit_ids": r.hit_ids,
         "miss_ids": r.miss_ids, "hit_ratio": r.hit_ratio,
         "guided_point_ids": r.guided_point_ids}
        for r in result.rounds
    ]
    reflow_answer(question_id, item["meta"]["type"], result.final_answer,
                  item["gold"]["reference_points"], action=ACTION_ANSWERED, rounds=rounds)
    _clear_practice(str(_progress_file()))  # 本题完成，清断点
    return result, item


def _print_review(result) -> None:
    """确定性复盘（docs/18 §4.5 步 5）：命中/漏点清单，替代 LLM 报告。"""
    last = result.rounds[-1]
    first = result.rounds[0]
    arrow = f"{first.hit_ratio:.0%} → {last.hit_ratio:.0%}" if len(result.rounds) > 1 else f"{last.hit_ratio:.0%}"
    status = "✅ 达标" if result.passed else "⚠️ 未达标（已达轮次上限，漏点已入档案）"
    print(f"\n📊 本题：{status}（命中率 {arrow}，{len(result.rounds)} 轮）")
    if len(result.rounds) > 1:
        print(f"   逼近增益：初稿命中 {len(first.hit_ids)} 个点，最终命中 {len(last.hit_ids)} 个点")
    miss_points = result.rounds[-1].miss_ids
    if miss_points:
        print(f"   漏掉采分点：{len(miss_points)} 个（已入薄弱点档案，后续 ReAct 会安排重练/补知识）")
    else:
        print("   采分点全部命中，无漏点。")


def main(*, recover: bool = False) -> None:
    """练习会话主循环。recover=True：有断点直接续练，不询问（--recover 参数语义）。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows GBK 控制台打 emoji 会崩（同 run_shenlun）
    except Exception:
        pass
    print("=" * 60)
    print("OfferLoop 申论练习 · 陪你练（抽题 → 作答 → 逼近 → 回流）")
    print("=" * 60)

    # 1. 读断点
    resume_rounds = None
    first_qid: str | None = None
    prog = _load_practice(str(_progress_file()))
    if prog:
        if recover:
            resume_rounds = prog["rounds"]
            first_qid = prog["question_id"]
            print(f"\n▶ 检测到未完成的练习（{prog['question'][:30]}… 第 {len(prog['rounds'])} 轮），直接续练。")
        else:
            try:
                ans = input("\n▶ 检测到未完成的练习，续练？(y=续练 / n=重新开始) ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                ans = "n"
            if ans in ("y", "yes", "1", ""):
                resume_rounds = prog["rounds"]
                first_qid = prog["question_id"]
            else:
                _clear_practice(str(_progress_file()))
                print("已放弃上次进度，重新开始。")

    # 2-6. 练习循环
    while True:
        qid = first_qid or _pick_question()
        first_qid = None
        if qid is None:
            print("⚠️ 题库为空（benchmark/data 无题目），退出。")
            return
        out = _run_one(qid, resume_rounds=resume_rounds)
        resume_rounds = None  # 断点只用于第一题
        if out is None:
            continue
        _print_review(out[0])
        try:
            more = input("\n继续练下一题？(回车继续，q 退出) ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            more = "q"
        if more in ("q", "quit", "exit", "x"):
            print("👋 本次练习结束。漏点已入档案，随时回来续练。")
            return
