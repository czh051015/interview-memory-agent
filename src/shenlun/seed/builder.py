"""作答文本构造器 —— 场景 → 关键词组织句（纯字符串，无 IO/DB）。

输入：该题 reference_points + 本次作答应命中的点 id 列表
输出：作答文本 —— 命中点逐字带上自己的 keywords，漏点 keywords 一律不出现。
正文只含 keywords，不含采分点名称：避免名称串词把「想漏的点」意外判中，
也保证落库前的本地评分断言（expected_hit == actual_hit）可预期。
"""

from __future__ import annotations


def build_answer(points: list[dict], hit_ids: list[str]) -> str:
    """按命中点组织一段作答：每点一句（keywords 顿号连接），点间以句号分隔。"""
    hits = [p for p in points if p["id"] in hit_ids]
    return "".join(f"{'、'.join(p['keywords'])}。" for p in hits)
