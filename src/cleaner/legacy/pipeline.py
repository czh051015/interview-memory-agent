"""Cleaner 主管线 —— 编排去重、脱敏、标准化流程。"""

import logging
from datetime import datetime
from typing import Optional

from src.models import RawFeedback, CleanedFeedback, QualityReport
from src.cleaner.legacy.normalizer import normalize_text, generate_dedup_hash
from src.cleaner.legacy.pii import scan_pii, mask_text, regex_scan
from src.cleaner.legacy.dedup import find_duplicate

logger = logging.getLogger(__name__)


class CleanerStats:
    """一次清洗运行的统计。"""

    def __init__(self):
        self.total = 0
        self.cleaned = 0
        self.duplicates = 0
        self.pii_found = 0
        self.errors = 0
        self.pii_leaks = 0

    def report(self) -> dict:
        return {
            "total": self.total,
            "cleaned": self.cleaned,
            "duplicates": self.duplicates,
            "pii_found": self.pii_found,
            "errors": self.errors,
            "pii_leaks": self.pii_leaks,
            "success_rate": (self.cleaned / self.total * 100) if self.total > 0 else 0,
        }


def clean_single(
    raw: RawFeedback,
    existing_cleaned: list[CleanedFeedback],
    existing_hashes: set[str],
) -> CleanedFeedback:
    """清洗单条反馈。

    流程：
    1. 标准化文本 + 生成去重 hash
    2. 去重判定（hash 粗筛 + LLM 精判）
    3. PII 扫描 + 脱敏
    4. 生成清洗报告
    """
    # Step 1: 标准化
    normalized = normalize_text(raw.raw_text)
    dedup_hash = generate_dedup_hash(normalized, raw.source)

    # 创建基础清洗记录
    clean_id = raw.id.replace("raw_", "clean_")
    cleaned = CleanedFeedback(
        id=clean_id,
        raw_id=raw.id,
        raw_text=raw.raw_text,
        normalized_text=normalized,
        dedup_hash=dedup_hash,
        source=raw.source,
        cleaned_at=datetime.utcnow(),
    )

    # Step 2: 去重判定
    is_dup, dup_of, dedup_stage = find_duplicate(cleaned, existing_cleaned, existing_hashes)
    cleaned.is_duplicate = is_dup
    cleaned.dup_of = dup_of
    cleaned.quality.dedup_stage = dedup_stage

    if is_dup:
        # 标记为重复，不继续 PII 扫描
        cleaned.quality.normalization_ok = True
        return cleaned

    # Step 3: PII 扫描 + 脱敏
    pii_result = scan_pii(normalized)
    pii_entries = pii_result.pop("_entries", [])

    if pii_entries:
        cleaned.pii = {
            "found": pii_result["found"],
            "masked": True,
        }
        # 脱敏
        cleaned.normalized_text = mask_text(normalized, pii_entries)
        cleaned.quality.pii_stage = "regex+llm"
    else:
        cleaned.quality.pii_stage = "regex_only"

    # Step 4: 质量校验
    _validate(cleaned)

    return cleaned


def run_cleaner_pipeline(
    raw_feedbacks: list[RawFeedback],
    existing_cleaned: Optional[list[CleanedFeedback]] = None,
) -> tuple[list[CleanedFeedback], CleanerStats, dict]:
    """运行完整的清洗管线。

    Args:
        raw_feedbacks: 原始反馈列表
        existing_cleaned: 已有的清洗记录（用于跨批次去重）

    Returns:
        (清洗结果列表, 统计信息, 质量报告)
    """
    existing = existing_cleaned or []
    existing_hashes = {e.dedup_hash for e in existing}
    results: list[CleanedFeedback] = []
    stats = CleanerStats()

    for raw in raw_feedbacks:
        stats.total += 1
        try:
            cleaned = clean_single(raw, existing + results, existing_hashes)
            results.append(cleaned)

            if cleaned.is_duplicate:
                stats.duplicates += 1
            else:
                stats.cleaned += 1
                if cleaned.pii.get("masked"):
                    stats.pii_found += 1

            existing_hashes.add(cleaned.dedup_hash)

        except Exception as e:
            stats.errors += 1
            logger.error("Cleaner error on %s: %s", raw.id, e)

    # 最终 PII 泄漏检查
    for r in results:
        if not r.is_duplicate and _check_pii_leak(r.normalized_text):
            stats.pii_leaks += 1

    quality_report = stats.report()
    logger.info("Cleaner done: %s", quality_report)

    return results, stats, quality_report


def _validate(cleaned: CleanedFeedback) -> None:
    """质量自检：字段合法性校验。"""
    # is_duplicate 和 dup_of 一致性
    if cleaned.is_duplicate and not cleaned.dup_of:
        logger.warning("%s: is_duplicate=true but dup_of is null", cleaned.id)
    if cleaned.dup_of and not cleaned.is_duplicate:
        logger.warning("%s: dup_of set but is_duplicate=false", cleaned.id)

    # source 合法
    if cleaned.source.value not in {"self_review", "other_jingyan", "jd", "market_signal"}:
        raise ValueError(f"Invalid source: {cleaned.source}")


def _check_pii_leak(text: str) -> bool:
    """检查文本中是否有未脱敏的 PII（正则回扫）。"""
    remaining = regex_scan(text)
    if remaining:
        logger.warning("PII leak detected: %d entries remaining", len(remaining))
        return True
    return False
