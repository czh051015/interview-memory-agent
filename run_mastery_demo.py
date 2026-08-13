# -*- coding: utf-8 -*-
"""掌握度三函数演示脚本（不用 pytest，直接 python run_mastery_demo.py）。

三个场景对应计划书 §3.5 验收 1~3，数字在下面 SCENARIO 里改。
"""

import io
import sys
from datetime import datetime, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from src.cleaner.schema import KnowledgeItem, ItemStatus
from src.cleaner.annotate import annotate_unknown
from src.memory.mastery import decay, effective_mastery, review, rank

NOW = datetime(2026, 8, 13, 12, 0, 0)  # 「今天」，改这里等于改测试基准日


def make_item(id, topic, status, days_since_review, mastery=1.0):
    """造一条错题：days_since_review 天没复习。"""
    return KnowledgeItem(
        id=id,
        question=f"{topic} 的原理是什么",
        topic=topic,
        status=status,
        mastery_score=mastery,
        last_reviewed_at=NOW - timedelta(days=days_since_review),
        review_count=0,
    )


print("=" * 60)
print("场景 1｜验收 1：掌握度衰减（30 天没复习，1.0 → 约 0.22）")
print("=" * 60)
item = make_item("ki_1", "RRF 重排序", ItemStatus.FAIL, days_since_review=30)
print(f"  题目：{item.question}")
print(f"  30 天没复习，有效掌握度：{effective_mastery(item, now=NOW):.3f}")
print("  参考：1 天 = %.3f ｜ 8 天 = %.3f ｜ 15 天 = %.3f ｜ 30 天 = %.3f" % (
    decay(1.0, 1), decay(1.0, 8), decay(1.0, 15), decay(1.0, 30)))

print()
print("=" * 60)
print("场景 2｜验收 2：复习重置（有效掌握度回升 + 次数 +1）")
print("=" * 60)
print(f"  复习前：有效掌握度={effective_mastery(item, now=NOW):.3f}, "
      f"复习次数={item.review_count}, 上次复习={item.last_reviewed_at}")
item = review(item, now=NOW)
print(f"  复习后：有效掌握度={effective_mastery(item, now=NOW):.3f}, "
      f"复习次数={item.review_count}, 上次复习={item.last_reviewed_at}")

print()
print("=" * 60)
print("场景 3｜验收 3：三元召回排序（谁最该复习谁排前）")
print("=" * 60)
candidates = [
    make_item("ki_a", "Chroma vs Milvus", ItemStatus.FAIL, days_since_review=8),   # 8 天没复习
    make_item("ki_b", "RRF 重排序", ItemStatus.FAIL, days_since_review=1),          # 昨天刚复习
    make_item("ki_c", "Agent 安全", ItemStatus.PASS, days_since_review=8),          # 会答，但 8 天没看
]
# 假设检索相似度：ki_a=0.9, ki_b=0.9, ki_c=0.5（靠边站的题）
ranked = rank(candidates, relevances={"ki_a": 0.9, "ki_b": 0.9, "ki_c": 0.5}, now=NOW)
for i, it in enumerate(ranked, 1):
    print(f"  {i}. [{it.status.value:>4}] {it.question:18s} "
          f"得分={it._recall_score:.3f}  距复习={int((NOW - it.last_reviewed_at).days)} 天")

print()
print("=" * 60)
print("场景 4｜验收 4：annotate 闭环（面经 unknown → 标 fail → 进复习列表）")
print("=" * 60)
mianjing = KnowledgeItem(
    id="ki_mj", question="Agent 记忆怎么实现", topic="Agent记忆",
    status=ItemStatus.UNKNOWN,
    created_at=NOW - timedelta(days=90),   # 模拟 90 天前导入的面经，一直没标
)
print(f"  标前：status={mianjing.status.value}, 导入于 90 天前, 有效掌握度={effective_mastery(mianjing, now=NOW):.3f}")
[marked] = annotate_unknown([mianjing], prompt_fn=lambda _: "f", now=NOW)
print(f"  标后：status={marked.status.value}, 上次复习={marked.last_reviewed_at}")
print(f"  有效掌握度={effective_mastery(marked, now=NOW):.3f}"
      f"（从标记时刻起算，而非 90 天前 → 不会误衰减到 0）")
ranked2 = rank([marked], now=NOW)
print(f"  复习列表第 1 位：{ranked2[0].question}（recall_score={ranked2[0]._recall_score:.3f}）")
