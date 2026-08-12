"""KnowledgeItem 专用存储 —— 写入 Chroma + 按维度检索。"""

import logging
from datetime import datetime
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from src.config import CHROMA_DIR
from src.memory.embedding import embed_texts
from src.cleaner.schema import KnowledgeItem, ItemStatus

logger = logging.getLogger(__name__)

COLLECTION_NAME = "knowledge_items_v1"

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
    client = _get_client()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine", "schema_version": "v1"},
    )


def store_items(items: list[KnowledgeItem]) -> int:
    """批量写入 KnowledgeItem 到 Chroma。

    - question 文本 → 嵌入向量
    - 其余字段 → metadata
    - 已存在的 id 会更新

    Returns: 写入数量
    """
    if not items:
        return 0

    collection = get_collection()

    # 批量嵌入
    texts = [item.question for item in items]
    embeddings = embed_texts(texts)

    ids = [item.id for item in items]
    metadatas = [_to_metadata(item) for item in items]

    # upsert: 已存在则更新
    collection.upsert(
        ids=ids,
        documents=texts,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    logger.info("Stored %d KnowledgeItems", len(items))
    return len(items)


def search(
    query: Optional[str] = None,
    *,
    topic: Optional[str] = None,
    company: Optional[str] = None,
    status: Optional[str] = None,
    top_k: int = 20,
    similarity_threshold: Optional[float] = None,
) -> list[KnowledgeItem]:
    """按条件检索 KnowledgeItem。

    - 有 query → 语义搜索（cosine similarity）
    - 无 query → 只按 metadata 过滤（全量）
    - topic/company/status → metadata 精确过滤
    - similarity_threshold → 语义搜索时，低于此值的条目被丢弃（建议 0.3-0.5）

    Returns: KnowledgeItem 列表（按相似度降序）
    """
    collection = get_collection()

    # 构建过滤条件
    where_parts = []
    if topic:
        where_parts.append({"topic": topic})
    if company:
        where_parts.append({"company": company})
    if status:
        where_parts.append({"status": status})

    where_filter = None
    if len(where_parts) == 1:
        where_filter = where_parts[0]
    elif len(where_parts) > 1:
        where_filter = {"$and": where_parts}

    # 查询
    if query and query.strip():
        query_emb = embed_texts([query])[0]
        results = collection.query(
            query_embeddings=[query_emb],
            n_results=min(top_k, collection.count()),
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )
        items = _parse_results(results)

        # 余弦相似度阈值过滤（ISSUES F1）
        if similarity_threshold is not None:
            filtered = []
            for item in items:
                sim = getattr(item, "_similarity", 0.0)
                if sim >= similarity_threshold:
                    filtered.append(item)
            logger.debug(
                "Similarity filter: %d → %d items (threshold=%.2f)",
                len(items), len(filtered), similarity_threshold,
            )
            return filtered
        return items
    else:
        results = collection.get(
            where=where_filter,
            limit=top_k,
            include=["documents", "metadatas"],
        )
        return _parse_results(results)


def get_stats() -> dict:
    """统计各 status 数量 + 热门 topic。"""
    items = search(top_k=1000)

    status_count = {"fail": 0, "partial": 0, "pass": 0, "unknown": 0}
    topic_count: dict[str, int] = {}

    for item in items:
        # ISSUES F2: info 类不计入错题统计
        if item.category == "info":
            continue
        status_count[item.status.value] = status_count.get(item.status.value, 0) + 1
        if item.topic:
            topic_count[item.topic] = topic_count.get(item.topic, 0) + 1

    # 热门 topic top 5
    hot_topics = sorted(topic_count.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "total": len(items),
        "by_status": status_count,
        "hot_topics": [{"topic": t, "count": c} for t, c in hot_topics],
    }


def clear() -> None:
    """清空 collection（测试用）。"""
    client = _get_client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass


def _to_metadata(item: KnowledgeItem) -> dict:
    return {
        "question": item.question,
        "topic": item.topic,
        "company": item.company,
        "role": item.role,
        "round": item.round,
        "date": item.date,
        "status": item.status.value,
        "user_note": item.user_note[:200],  # 截断
        "category": item.category.value if hasattr(item.category, 'value') else str(item.category),
        "mastery_score": item.mastery_score,
        "review_count": item.review_count,
        "created_at": item.created_at.isoformat() if item.created_at else "",
    }


def _parse_results(results: dict) -> list[KnowledgeItem]:
    """将 Chroma 返回结果转回 KnowledgeItem 列表。"""
    items = []
    ids = results.get("ids", [])
    if not ids:
        return items

    # query() 返回嵌套列表，get() 返回平铺列表
    if ids and isinstance(ids[0], list):
        ids = ids[0]

    docs = results.get("documents", [])
    if docs and isinstance(docs[0], list):
        docs = docs[0]

    metas = results.get("metadatas", [])
    if metas and isinstance(metas[0], list):
        metas = metas[0]

    distances = results.get("distances", [])
    if distances and isinstance(distances[0], list):
        distances = distances[0]

    for i, item_id in enumerate(ids):
        meta = metas[i] if i < len(metas) else {}
        doc = docs[i] if i < len(docs) else ""
        dist = distances[i] if i < len(distances) else None

        try:
            status = ItemStatus(meta.get("status", "unknown"))
        except ValueError:
            status = ItemStatus.UNKNOWN

        cat_val = meta.get("category", "knowledge")
        try:
            from src.cleaner.schema import ItemCategory
            category = ItemCategory(cat_val) if cat_val in ("knowledge", "info") else ItemCategory.KNOWLEDGE
        except (ValueError, ImportError):
            category = ItemCategory.KNOWLEDGE

        item = KnowledgeItem(
            id=item_id,
            question=meta.get("question", doc),
            topic=meta.get("topic", ""),
            category=category,
            company=meta.get("company", ""),
            role=meta.get("role", ""),
            round=meta.get("round", ""),
            date=meta.get("date", ""),
            status=status,
            user_note=meta.get("user_note", ""),
            mastery_score=float(meta.get("mastery_score", 1.0)),
            review_count=int(meta.get("review_count", 0)),
            created_at=datetime.fromisoformat(meta["created_at"]) if meta.get("created_at") else None,
        )
        # 附上余弦相似度（用于阈值过滤，ISSUES F1）
        if dist is not None:
            setattr(item, "_similarity", round(1.0 - dist, 4))
        items.append(item)

    return items
