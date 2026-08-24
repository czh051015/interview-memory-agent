# -*- coding: utf-8 -*-
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
"""面经题标注 CLI —— 冷启动补给：把面经 unknown 题手动标 fail/partial，填入错题本。

用法：
  python annotate_jingyan.py            # 逐条标注所有待标面经题（f=不会 p=半会 x=跳过）

数据流（产品计划书阶段②「面经库冷启动补给」）：
  面经题入库（status=unknown，source=public_jingyan，只是补给池）
      ↓ 本脚本逐条标注
  标 fail/partial → 变成"你的错题"，参与掌握度衰减 + 复习提醒
  按 x 跳过 → 保持 unknown，不进入错题本

标 fail/partial 时 annotate_unknown 会把 last_reviewed_at 设为标注时刻，
作为衰减起点（而不是导入时间，避免旧题被误衰减到 0）。
"""

import logging
import sys

from src.cleaner.schema import ItemStatus, ItemCategory
from src.cleaner.annotate import annotate_unknown
from src.memory import knowledge_store as store
import src.config as _cfg  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)


def main(argv: list[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    if args and args[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    # --space 参数（在 store 操作前设置当前空间）
    if "--space" in args:
        _i = args.index("--space")
        if _i + 1 < len(args):
            _cfg.SPACE = args[_i + 1]
        del args[_i:_i + 2]

    # 1. 检索面经里的 unknown 题，只标知识点（category=knowledge），过滤 info 类行为题
    items = store.search(source="public_jingyan", status="unknown", space=_cfg.SPACE, top_k=1000)
    items = [item for item in items if item.category == ItemCategory.KNOWLEDGE]
    if not items:
        print("没有待标注的知识点面经题（source=public_jingyan + status=unknown + category=knowledge）")
        print("先运行: python run_preprocess.py --import 导入面经题")
        return 0

    print(f"待标注面经题 {len(items)} 条，逐条标 f=不会 / p=半会 / x=跳过\n")

    # 2. 逐条标注（交互式）
    updated = annotate_unknown(items, prompt_fn=input)

    # 3. 只写回状态变化的条目（标了 fail/partial 的），避免重新嵌入全部面经题
    changed = [item for item in updated if item.status != ItemStatus.UNKNOWN]
    if changed:
        for item in changed:
            if item.space != _cfg.SPACE:
                item.space = _cfg.SPACE
        store.store_items(changed)

    # 统计
    fail = sum(1 for item in changed if item.status == ItemStatus.FAIL)
    partial = sum(1 for item in changed if item.status == ItemStatus.PARTIAL)
    skipped = len(items) - len(changed)

    print("\n" + "=" * 50)
    print(f"标注完成：fail {fail} | partial {partial} | 跳过 {skipped}")
    if changed:
        print(f"已写入错题本 {len(changed)} 条，开始参与掌握度衰减")
    print("查看复习提醒: python scripts/run_remind.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
