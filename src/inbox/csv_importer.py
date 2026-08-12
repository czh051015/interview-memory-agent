"""CSV 批量导入器 (US-01) —— 校验、ID 生成、错误行隔离。"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Iterator

from src.models import FeedbackSource, RawFeedback

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"raw_text", "source"}
VALID_SOURCES = {s.value for s in FeedbackSource}


def import_csv(filepath: str | Path) -> list[RawFeedback]:
    """从 CSV 文件导入反馈。预期列：raw_text, source[, received_at]。

    - 缺少必填列 → 跳过并记录 warning
    - source 非法 → 跳过并记录 warning
    - 正确行生成唯一 ID
    """
    filepath = Path(filepath)
    feedbacks: list[RawFeedback] = []
    errors: list[dict] = []

    with open(filepath, encoding="utf-8") as f:
        reader = csv.DictReader(f)

        # 校验列头
        headers = set(reader.fieldnames or [])
        if not REQUIRED_COLUMNS.issubset(headers):
            missing = REQUIRED_COLUMNS - headers
            raise ValueError(f"CSV 缺少必填列: {missing}")

        for i, row in enumerate(reader, start=2):  # 第 1 行是 header
            try:
                raw_text = (row.get("raw_text") or "").strip()
                if not raw_text:
                    errors.append({"line": i, "error": "raw_text 为空"})
                    continue

                source_raw = (row.get("source") or "").strip()
                if source_raw not in VALID_SOURCES:
                    errors.append({"line": i, "error": f"非法 source: {source_raw}"})
                    continue

                feedback = RawFeedback(
                    id=f"raw_{len(feedbacks) + 1:04d}",
                    raw_text=raw_text,
                    source=FeedbackSource(source_raw),
                    received_at=_parse_datetime(row.get("received_at")),
                )
                feedbacks.append(feedback)

            except Exception as e:
                errors.append({"line": i, "error": str(e)})
                logger.warning("CSV row %d error: %s", i, e)

    logger.info("CSV import: %d success, %d errors", len(feedbacks), len(errors))
    return feedbacks


def _parse_datetime(value: str | None) -> datetime:
    """尝试多种格式解析日期时间，失败返回当前时间。"""
    if not value:
        return datetime.utcnow()
    value = value.strip()
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return datetime.utcnow()
