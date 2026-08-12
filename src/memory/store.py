"""Chroma 向量存储 —— collection 管理 + 批量写入。"""

import logging
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from src.config import CHROMA_DIR
from src.models import CleanedFeedback, MemoryEntry

logger = logging.getLogger(__name__)

COLLECTION_NAME = "feedback_v1"

_client: Optional[chromadb.PersistentClient] = None


def _get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _client


def get_collection() -> chromadb.Collection:
    """获取或创建 feedback collection。"""
    client = _get_client()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine", "schema_version": "v1"},
    )


def store_feedback(
    cleaned: CleanedFeedback,
    embedding: Optional[list[float]] = None,
) -> None:
    """将一条清洗后反馈存入 Chroma。

    Args:
        cleaned: 清洗后的反馈对象
        embedding: 预生成的嵌入向量（可选，由外部管线注入）
    """
    collection = get_collection()

    # 跳过重复反馈
    if cleaned.is_duplicate:
        logger.debug("Skipping duplicate: %s", cleaned.id)
        return

    metadata = {
        "source": cleaned.source.value,
        "raw_id": cleaned.raw_id,
        "cleaned_at": cleaned.cleaned_at.isoformat(),
        "has_pii": cleaned.pii.get("masked", False),
        "dedup_hash": cleaned.dedup_hash,
    }

    collection.add(
        ids=[cleaned.id],
        documents=[cleaned.normalized_text],
        metadatas=[metadata],
        embeddings=[embedding] if embedding else None,
    )

    logger.debug("Stored: %s", cleaned.id)


def store_batch(
    cleaned_list: list[CleanedFeedback],
    embeddings: list[Optional[list[float]]],
) -> int:
    """批量存储清洗后反馈。

    Returns:
        实际写入数量（去重跳过的不计入）
    """
    count = 0
    for cleaned, emb in zip(cleaned_list, embeddings):
        if not cleaned.is_duplicate:
            store_feedback(cleaned, emb)
            count += 1
    logger.info("Stored %d feedbacks into Chroma", count)
    return count


def get_feedback_count() -> int:
    """获取已存储的反馈数量。"""
    collection = get_collection()
    return collection.count()


def clear_collection() -> None:
    """清空 collection（用于测试/重置）。"""
    client = _get_client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    logger.info("Collection cleared")
