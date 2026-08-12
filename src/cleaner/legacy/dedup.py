"""去重逻辑 —— 规范化哈希粗筛 + LLM 嵌入精判。"""

import logging
from typing import Optional

from src.llm import chat_json
from src.cleaner.legacy.prompts import CLEANER_SYSTEM, DEDUP_USER
from src.models import CleanedFeedback

logger = logging.getLogger(__name__)

# 相似度阈值（v1 硬编码，v2 可配置化）
HASH_COLLISION_THRESHOLD = 0  # hash 相同即碰撞


def check_hash_collision(new_hash: str, existing_hashes: set[str]) -> Optional[str]:
    """检查哈希是否与已有记录碰撞。

    Returns:
        碰撞时返回已有的 clean_id，否则 None。
    """
    # v1 简化：直接集合查找；v2 可用 Bloom Filter
    return new_hash if new_hash in existing_hashes else None


def llm_dedup_check(text_a: str, text_b: str) -> tuple[bool, str]:
    """LLM 精判两条反馈是否重复。

    Returns:
        (is_duplicate, reason)
    """
    try:
        result = chat_json(
            system_prompt=CLEANER_SYSTEM,
            user_prompt=DEDUP_USER.format(text_a=text_a[:1000], text_b=text_b[:1000]),
        )
        return result.get("is_duplicate", False), result.get("reason", "")
    except Exception as e:
        logger.warning("LLM dedup check failed: %s", e)
        return False, f"LLM error: {e}"


def find_duplicate(
    current: CleanedFeedback,
    existing: list[CleanedFeedback],
    existing_hashes: set[str],
) -> tuple[bool, Optional[str], str]:
    """双通道去重判定。

    1. 哈希碰撞粗筛
    2. 若有碰撞 → LLM 逐条比较 semantic 重复 → 返回结果

    Returns:
        (is_duplicate, dup_of_id, dedup_stage)
    """
    # Stage 1: 哈希粗筛
    if current.dedup_hash not in existing_hashes:
        return False, None, "hash"

    # Stage 2: LLM 精判 —— 对 hash 碰撞的候选做 semantic 比较
    candidates = [e for e in existing if e.dedup_hash == current.dedup_hash]
    if not candidates:
        return False, None, "hash"

    for candidate in candidates:
        is_dup, reason = llm_dedup_check(current.normalized_text, candidate.normalized_text)
        if is_dup:
            logger.info("Duplicate found: %s → %s (%s)", current.id, candidate.id, reason)
            return True, candidate.id, "llm"

    return False, None, "llm"
