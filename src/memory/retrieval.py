"""检索 API —— topK + metadata 过滤 + 相似度阈值。"""

import logging
from typing import Optional

from src.memory.store import get_collection
from src.memory.embedding import embed_texts

logger = logging.getLogger(__name__)


def search(
    query: str,
    *,
    top_k: int = 5,
    source_filter: Optional[str] = None,
    similarity_threshold: Optional[float] = None,
) -> list[dict]:
    """语义检索 + metadata 过滤。

    Args:
        query: 查询文本
        top_k: 返回数量
        source_filter: 按来源过滤 (self_review / other_jingyan)
        similarity_threshold: 相似度阈值（cosine，0-1），低于此值的结果被过滤

    Returns:
        [{id, document, metadata, distance}, ...]
    """
    collection = get_collection()

    # 生成查询向量
    query_embedding = embed_texts([query])[0]

    # 构建过滤条件
    where_filter = None
    if source_filter:
        where_filter = {"source": source_filter}

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where_filter,
        include=["documents", "metadatas", "distances"],
    )

    # 整理结果
    items = []
    if results["ids"] and results["ids"][0]:
        for i, doc_id in enumerate(results["ids"][0]):
            distance = results["distances"][0][i] if results.get("distances") else 0.0
            similarity = 1.0 - distance  # cosine distance → similarity

            # 相似度阈值过滤
            if similarity_threshold is not None and similarity < similarity_threshold:
                continue

            items.append({
                "id": doc_id,
                "document": results["documents"][0][i] if results.get("documents") else "",
                "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                "distance": distance,
                "similarity": round(similarity, 4),
            })

    return items


def get_all_feedback(
    source_filter: Optional[str] = None,
    limit: int = 1000,
) -> list[dict]:
    """获取所有反馈（带可选的 source 过滤）。用于 Scout 全量分析。

    Returns:
        [{id, document, metadata, embedding}, ...]
    """
    collection = get_collection()

    where_filter = None
    if source_filter:
        where_filter = {"source": source_filter}

    results = collection.get(
        where=where_filter,
        limit=limit,
        include=["documents", "metadatas", "embeddings"],
    )

    items = []
    if results["ids"]:
        for i, doc_id in enumerate(results["ids"]):
            items.append({
                "id": doc_id,
                "normalized_text": results["documents"][i] if results.get("documents") else "",
                "metadata": results["metadatas"][i] if results.get("metadatas") else {},
                "embedding": results["embeddings"][i] if results.get("embeddings") is not None else None,
            })

    return items
