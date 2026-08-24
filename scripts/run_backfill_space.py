"""存量数据补齐 space key 脚本（空间隔离 B 方案的前置）。

背景：v1.0 存量条目 metadata 没有 space key（search 读成 default）。
严格隔离后 search(space="default") 用 chroma where {"space": "default"} 精确匹配，
缺 key 的条目将不再被 default 空间命中 → 必须把存量补上 space="default"。

用法：
  python run_backfill_space.py [--dry-run]

输出：迁移条数；--dry-run 只看不改。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

from src.memory.knowledge_store import get_collection  # noqa: E402


def backfill_space_default(dry_run: bool = False) -> int:
    """给缺 space key 的存量条目补 space=default。返回补了多少条。"""
    collection = get_collection()
    got = collection.get(include=["metadatas"])
    ids = got.get("ids") or []
    metas = got.get("metadatas") or []
    if isinstance(metas, list) and metas and isinstance(metas[0], list):
        metas = metas[0]

    targets = []
    for i, m in enumerate(metas):
        if isinstance(m, dict) and "space" not in m:
            targets.append((ids[i], m))

    if not targets:
        logger.info("没有缺 space key 的存量条目，无需迁移")
        return 0

    logger.info("发现 %d 条缺 space key（将补为 default）", len(targets))
    if dry_run:
        logger.info("dry-run 模式，不写入")
        for item_id, m in targets[:5]:
            logger.info("  %s | %s", item_id, (m.get("question") or "")[:30])
        if len(targets) > 5:
            logger.info("  …… 其余 %d 条省略", len(targets) - 5)
        return len(targets)

    # Chroma update 整体替换 metadata，必须带全字段
    updated_ids = [i for i, _ in targets]
    updated_metas = [dict(m, space="default") for _, m in targets]
    collection.update(ids=updated_ids, metadatas=updated_metas)
    logger.info("已补齐 %d 条 → space=default", len(updated_ids))
    return len(updated_ids)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="存量补齐 space key")
    parser.add_argument("--dry-run", action="store_true", help="只看不改")
    args = parser.parse_args()
    n = backfill_space_default(dry_run=args.dry_run)
    print(f"backfilled={n}")
