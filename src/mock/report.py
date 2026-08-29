"""【已废弃 · docs/18】复盘报告（07 计划 T5）：行为特征总结 + 复盘报告生成 + markdown 格式化。

申论复盘 = 命中/漏点清单（确定性输出），LLM 报告不再需要。本文件保留可导入，
仅因 Web 模拟面试（app/api/mock.py）仍在引用；新代码不得使用。
（_BEHAVIOR_PROMPT/_REVIEW_PROMPT 从 prompts.py 内联到本文件，随废弃模块共进退。）
"""

import logging

# 活引用：LLM 调用一律经包取 chat_json（测试 @patch.object(mi, "chat_json") 才穿透）
import src.mock as _mi

# ── 面试域 prompt（废弃模块自用，从 prompts.py 内联而来）──
_BEHAVIOR_PROMPT = (
    "你是面试官，回顾整场面试，总结候选人的行为特征。只输出 JSON：{\"tags\": [\"标签1\", ...]}\n"
    "维度（可多个，也可空数组）：答不到点（知识缺口）、表达绕弯（逻辑不清）、回避问题（转移话题）。\n"
    "只输出确实暴露的问题，没有就输出空数组。"
)

_REVIEW_PROMPT = (
    "你是资深面试官，刚面完一位候选人。下面是整场面试的完整记录（题目、逐轮问答、追问理由、最终表现）。\n"
    "请输出一份复盘报告，要具体、可执行，指出候选人每道题哪里没答到点、为什么、下次怎么改进。\n"
    "只输出 JSON：\n"
    '{"overall": "整体评价（2-3句，点出最致命的问题）", '
    '"items": [{"question": "题", "performance": "pass|partial|fail", "problem": "核心问题", "suggestion": "改进建议"}], '
    '"common": "共性建议（跨题总结的1-2个系统性问题）"}'
)


def summarize_behaviors(records: list[dict]) -> list[str]:
    """整场面试结束，总结行为特征标签。"""
    summary = "\n".join(
        f"题：{r['question']}\n答：{r['answer'][:120]}\n表现：{r['performance']}" for r in records
    )
    try:
        data = _mi.chat_json(_BEHAVIOR_PROMPT, summary)
        return data.get("tags", [])
    except Exception as e:
        logging.warning("行为特征总结失败：%s", e)
        return []


def generate_review_report(records: list[dict], behaviors: list[str]) -> dict | None:
    """面试结束后生成复盘报告。失败返回 None。"""
    lines = []
    for i, r in enumerate(records, 1):
        lines.append(f"第{i}题：{r['question']}")
        for t in r.get("transcript", []):
            lines.append(f"  第{t['round']}轮回答：{t['answer'][:200]}")
            lines.append(f"  面试官判断：{t.get('reason', '')}")
            if t.get("followup_question"):
                lines.append(f"  追问：{t['followup_question']}")
        lines.append(f"  最终表现：{r['performance']}")
    if behaviors:
        lines.append(f"行为特征：{', '.join(behaviors)}")
    try:
        data = _mi.chat_json(_REVIEW_PROMPT, "\n".join(lines), max_tokens=4096)
        return data if data.get("overall") or data.get("items") else None
    except Exception as e:
        logging.warning("复盘报告生成失败：%s", e)
        return None


def _format_review(report: dict) -> str:
    """把复盘报告格式化成 markdown 文本（终端打印 + 落盘共用）。"""
    lines = ["📋 面试复盘报告", "=" * 40, ""]
    if report.get("overall"):
        lines += ["【整体评价】", report["overall"], ""]
    lines.append("【逐题复盘】")
    for it in report.get("items", []):
        emoji = {"pass": "✅", "partial": "⚠️", "fail": "❌"}.get(it.get("performance"), "❓")
        lines.append(f"  {emoji} {it.get('question', '')}")
        if it.get("problem"):
            lines.append(f"     问题：{it['problem']}")
        if it.get("suggestion"):
            lines.append(f"     建议：{it['suggestion']}")
    if report.get("common"):
        lines += ["", "【共性建议】", report["common"]]
    return "\n".join(lines)