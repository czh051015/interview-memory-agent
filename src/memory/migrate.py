"""Schema 版本迁移脚本 (US-09)。"""

import logging
from pathlib import Path
from datetime import datetime

from src.config import CHROMA_DIR
from src.memory.knowledge_store import get_collection
from src.cleaner.schema import utcnow

logger = logging.getLogger(__name__)

MIGRATION_LOG_DIR = CHROMA_DIR / "migrations"


def current_schema_version() -> str:
    """获取当前 collection 的 schema 版本。"""
    try:
        collection = get_collection()
        return collection.metadata.get("schema_version", "v1")
    except Exception:
        return "v1"


def migrate(to_version: str) -> None:
    """执行 schema 迁移（v1 占位，实际迁移逻辑在版本升级时实现）。

    Args:
        to_version: 目标版本，如 "v2"
    """
    current = current_schema_version()
    if current == to_version:
        logger.info("Schema already at %s, no migration needed", to_version)
        return

    MIGRATION_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = MIGRATION_LOG_DIR / f"migrate_{current}_to_{to_version}_{utcnow():%Y%m%d_%H%M%S}.log"

    logger.info("Migrating schema %s → %s", current, to_version)

    # v1 → v2 示例迁移逻辑（待 v2 实现）
    if current == "v1" and to_version == "v2":
        _migrate_v1_to_v2(log_file)

    # 更新 collection metadata
    collection = get_collection()
    collection.modify(metadata={"schema_version": to_version})

    logger.info("Migration complete: %s → %s", current, to_version)


def _migrate_v1_to_v2(log_file: Path) -> None:
    """v1 → v2 迁移逻辑（占位，v2 实际实现时填写）。"""
    logger.info("v1 → v2 migration: no field changes yet, placeholder")
    log_file.write_text(f"Migration v1→v2 placeholder\n")


def rollback(to_version: str) -> None:
    """回滚到指定版本（占位）。"""
    logger.info("Rollback to %s (placeholder)", to_version)
