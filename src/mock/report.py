"""复盘报告（07 计划 T5）：行为特征总结 + 复盘报告生成 + markdown 格式化。"""

import logging

from .prompts import _BEHAVIOR_PROMPT, _REVIEW_PROMPT
# 活引用：LLM 调用一律经包取 chat_json（测试 @patch.object(mi, "chat_json") 才穿透）
import src.mock as _mi


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