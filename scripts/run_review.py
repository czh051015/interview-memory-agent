"""复习循环 —— 阶段三最小闭环（间隔重复）。

出题 → 自评(对/错) → 更新 mastery → 动态重排 → 下一题。

- 选题：只 fail/partial（pass/unknown 过滤）
- 答对 → review()（mastery ×1.2）；答错 → review_fail()（min(当前,0.5)）
- 动态重排：每答一题重新 rank，答错的题会浮上来（间隔重复的 again 语义）
- 退出：q 手动退出；所有题掌握度到 1.0 时提示"复习完"
- 复习不改 status（历史事实）；改动只在退出时统一写回库
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

from datetime import datetime

from src.memory import knowledge_store as store
from src.memory import review_log
from src.memory.mastery import rank, review, review_fail, effective_mastery
from src.cleaner.schema import KnowledgeItem, utcnow
import src.config as _cfg  # noqa: E402  （SPACE：OFFERLOOP_SPACE 环境变量切换）


def load_review_items() -> list[KnowledgeItem]:
    """拿所有 fail + partial 的题（pass/unknown 过滤），限当前空间。"""
    fails = store.search(status="fail", space=_cfg.SPACE, top_k=1000)
    partials = store.search(status="partial", space=_cfg.SPACE, top_k=1000)
    return fails + partials


def main() -> int:
    now = utcnow()
    items = load_review_items()
    if not items:
        print("没有待复习的题（fail/partial 为空）。")
        print("先跑 run_preprocess.py --import + annotate_jingyan.py 标注错题。")
        return 0

    print(f"📚 待复习 {len(items)} 道题，答完按 y/n 自评，q 退出。\n")

    changed: dict[str, KnowledgeItem] = {}
    answered_this_round: set[str] = set()

    while True:
        # 本轮未答 + 掌握度未满 的题
        reviewable = [
            it for it in items
            if effective_mastery(it, now) < 1.0 and it.id not in answered_this_round
        ]
        if not reviewable:
            if all(effective_mastery(it, now) >= 1.0 for it in items):
                print("🎉 该复习的都复习完了（所有题掌握度已到 1.0）。")
                break
            # 一轮过完，清空已答标记，进入下一轮（答错的题下轮再出现）
            remaining = sum(1 for it in items if effective_mastery(it, now) < 1.0)
            print(f"\n🔄 本轮已过一遍，还有 {remaining} 道未掌握，进入下一轮...\n")
            answered_this_round.clear()
            continue

        ranked = rank(reviewable, now=now)
        top = ranked[0]
        em = effective_mastery(top, now)

        print(f"【{len(reviewable)} 道待复习】当前最该复习：")
        print(f"  {top.question}")
        meta = " · ".join(x for x in (top.topic, top.company, top.round) if x)
        print(f"  掌握度 {em:.2f}  |  {meta or '（无元信息）'}")

        ans = input("  答对了吗？(y=对 / n=错 / q=退出): ").strip().lower()
        if ans == "q":
            break
        elif ans == "y":
            before = top.mastery_score
            top = review(top, now=now)
            review_log.append(item_id=top.id, question=top.question, before=before,
                              after=top.mastery_score, action="review", actor="review")
            print(f"  ✅ 掌握度 → {top.mastery_score:.2f}\n")
        elif ans == "n":
            before = top.mastery_score
            top = review_fail(top, now=now)
            review_log.append(item_id=top.id, question=top.question, before=before,
                              after=top.mastery_score, action="review_fail", actor="review")
            print(f"  ❌ 掌握度 → {top.mastery_score:.2f}\n")
        else:
            print("  无效输入，请输入 y / n / q\n")
            continue

        answered_this_round.add(top.id)  # 本轮不再重复出这题
        # 更新内存里的 item（动态重排依据）
        for i, it in enumerate(items):
            if it.id == top.id:
                items[i] = top
                break
        changed[top.id] = top

    if changed:
        store.store_items(list(changed.values()))
        print(f"\n已写回 {len(changed)} 道题的掌握度变化。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
