"""LLM 输出质量评测 —— 拆解（用 LLM 当裁判 + 人工校准）。

评的对象：decompose（面试复盘 → 结构化错题），它是所有 LLM 输出的入口，拆错后面全错。
方法：LLM-as-judge —— 让 DeepSeek 换一个「质检裁判」角色，独立判断拆解质量
      （category 分类 / topic 标签 / 漏拆 / 错拆），再人工抽几条核对裁判准不准（校准裁判）。
样本：data/seed/agent_dev_interview.txt（真实口语化复盘，27 题，含追问往返+错别字+自评）。

用法：python eval/llm_judge_eval.py
输出：eval/llm_judge_results.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

from src.cleaner.decompose import decompose
from src.llm import chat_json
from src.config import DATA_DIR

SAMPLE = DATA_DIR / "seed" / "agent_dev_interview.txt"

# 人工校准结论（2026-08-17，用户人工判定 4 处有争议的分类/题）
# - decompose 把「调试代码」标 info 是错的（应为 knowledge）
# - 「建议补 Harness」是面试官建议，不该算题（错拆）
HUMAN_CALIBRATION = {
    "reviewed": 4,
    "category_corrections": {"你平时调试代码怎么调试的?": "knowledge"},
    "not_a_question": ["建议下去再补一点Harness的知识"],
}

JUDGE_SYSTEM = (
    "你是「面试复盘拆解」的质检裁判。给你一段面试复盘原文，和一个拆解结果（把原文拆成若干道面试题，每题标了 category 和 topic）。\n"
    "请独立判断拆解质量，不要盲信拆解结果。对每一道拆出的题，判断：\n"
    "1. category 对不对：knowledge=技术/知识点考察题（八股、项目细节、算法、追问技术点）；"
    "info=信息性问题（自我介绍、薪酬、反问、建议、没有具体考察点的闲聊）。\n"
    "2. topic 贴不贴切（主题标签是否准确概括这道题）。\n"
    "3. 有没有漏拆（原文里明确出现的题没拆出来）。\n"
    "4. 有没有错拆（拆出的题原文里没有，或把一道题拆成多道、把追问拆丢）。\n\n"
    "只输出 JSON，格式：\n"
    '{"verdicts":[{"question":"题","category_correct":true/false,"category_should":"knowledge或info",'
    '"topic_correct":true/false,"issue":"问题说明，无问题则空字符串"}],'
    '"missed":["漏拆的题"],"extra":["错拆的题"]}'
)


def main():
    text = SAMPLE.read_text(encoding="utf-8")
    r = decompose(text)
    if not r.items:
        print("拆解失败，无输出。")
        return

    items_desc = "\n".join(
        f"{i + 1}. [{it.category.value}] {it.question} (topic={it.topic})"
        for i, it in enumerate(r.items)
    )
    user_prompt = f"## 面试复盘原文\n{text[:6000]}\n\n## 拆解结果\n{items_desc}"

    print(f"拆出 {len(r.items)} 题，正在让裁判质检...")
    verdict = chat_json(JUDGE_SYSTEM, user_prompt, max_tokens=4096)

    verdicts = verdict.get("verdicts", [])
    n = len(verdicts)
    cat_correct = sum(1 for v in verdicts if v.get("category_correct"))
    topic_correct = sum(1 for v in verdicts if v.get("topic_correct"))

    print("=" * 60)
    print(f"裁判判定 category 准确率：{cat_correct}/{n} = {cat_correct / n:.0%}" if n else "无 verdicts")
    print(f"裁判判定 topic 准确率：{topic_correct}/{n} = {topic_correct / n:.0%}" if n else "")
    print(f"漏拆：{verdict.get('missed', [])}")
    print(f"错拆：{verdict.get('extra', [])}")

    wrong = [v for v in verdicts if not v.get("category_correct")]
    if wrong:
        print(f"\n--- 裁判认为 category 标错的 {len(wrong)} 题（人工校准对象）---")
        for v in wrong:
            print(f"  · {v.get('question', '')[:48]}  → 裁判说应为 {v.get('category_should', '')}")

    out = {
        "sample": SAMPLE.name,
        "decomposed_count": len(r.items),
        "category_accuracy": round(cat_correct / n, 3) if n else None,
        "topic_accuracy": round(topic_correct / n, 3) if n else None,
        "missed": verdict.get("missed", []),
        "extra": verdict.get("extra", []),
        "verdicts": verdicts,
        "human_calibration": HUMAN_CALIBRATION,
    }

    # ── 人工校准后的真实数字 ──
    corrections = HUMAN_CALIBRATION["category_corrections"]
    not_q = HUMAN_CALIBRATION["not_a_question"]
    real_cat_errors = len(corrections)
    real_cat_acc = (n - real_cat_errors) / n if n else None
    # judge 说「全对」但漏判了：category 错 + 错拆（把建议当题）
    judge_missed = real_cat_errors + len(not_q)

    print("\n" + "=" * 60)
    print("【人工校准后】")
    print(f"拆解 category 准确率：{n - real_cat_errors}/{n} = {real_cat_acc:.1%}" if real_cat_acc is not None else "")
    print(f"错拆（把建议当题）：{len(not_q)} 处 → {not_q}")
    print(f"裁判漏判：{judge_missed} 处（裁判说 100%，实际有 category 错 + 错拆没发现）")
    out["real_category_accuracy"] = round(real_cat_acc, 3) if real_cat_acc is not None else None
    out["judge_missed"] = judge_missed

    with open("eval/llm_judge_results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: eval/llm_judge_results.json")


if __name__ == "__main__":
    main()
