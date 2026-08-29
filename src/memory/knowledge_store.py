"""KnowledgeItem 专用存储 —— 写入 Chroma + 按维度检索。"""

import json
import logging
import re
from datetime import datetime
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from src import config
from src.memory.embedding import embed_texts
from src.cleaner.schema import KnowledgeItem, ItemStatus, ItemCategory, ItemSource

logger = logging.getLogger(__name__)

_client: Optional[chromadb.PersistentClient] = None


def _collection_name() -> str:
    """统一单 collection + metadata.space 过滤（v2 架构）。

    历史：v1 曾按空间分 collection（knowledge_items_{SPACE}），中文 space 名在
    Chroma 非法（仅允许 [a-zA-Z0-9._-]）→ CLI `--space 试玩` 直接崩。
    现在所有空间共享 knowledge_items_v1，靠 search/store 的 space 参数严格过滤。
    """
    return "knowledge_items_v1"


def _get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        config.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(config.CHROMA_DIR),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _client


def get_collection() -> chromadb.Collection:
    client = _get_client()
    return client.get_or_create_collection(
        name=_collection_name(),
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
    source: Optional[str] = None,
    space: Optional[str] = None,
    top_k: int = 20,
    similarity_threshold: Optional[float] = None,
) -> list[KnowledgeItem]:
    """按条件检索 KnowledgeItem。

    - 有 query → 语义搜索（cosine similarity）
    - 无 query → 只按 metadata 过滤（全量）
    - topic/company/status/source/space → metadata 精确过滤
    - similarity_threshold → 语义搜索时，低于此值的条目被丢弃（建议 0.3-0.5）

    注意：source 过滤依赖 metadata 里存在 source key。
    存量旧数据（v1.0 入库）没有该 key，跑 run_interview.py --fresh 重新 upsert 补齐。
    space：严格过滤（2026-08-19 起）。v1.0 存量已由 run_backfill_space.py 补齐
    space=default，所以「不传 space = 不过滤（全空间）」与「space=default = 只 default」
    语义明确分离。空间隔离 B 方案：default 只含 default，不再吞并其他空间。

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
    if source:
        where_parts.append({"source": source})
    if space:
        where_parts.append({"space": space})

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


def _normalize(text: str) -> str:
    """归一化题目：去空白、小写、去标点，用于精确去重。"""
    t = re.sub(r"[\s\u3000]+", "", text.lower())
    t = re.sub(r"[，。！？、,.!?：:；;()（）【】\[\]\"'“”‘’]", "", t)
    return t


def find_duplicates(
    items: list[KnowledgeItem], threshold: float = 0.93,
) -> list[tuple[str, str, float]]:
    """对库查重：判断每道新题是否已存在。

    用向量相似度——对每道新题 query 库里 top-1，相似度 >= threshold 视为重复。
    完全相同文本 embedding 相同（cosine≈1.0），语义相近措辞不同也能抓。

    Returns: [(新题question, 已有题question, 相似度)]，只含判定为重复的。
    """
    if not items:
        return []
    collection = get_collection()
    if collection.count() == 0:
        return []

    embs = embed_texts([it.question for it in items])
    results = collection.query(
        query_embeddings=embs,
        n_results=1,
        include=["documents", "distances"],
    )

    docs = results.get("documents", [])
    dists = results.get("distances", [])
    dupes = []
    for i, item in enumerate(items):
        dist = None
        if i < len(dists) and dists[i]:
            dist = dists[i][0]
        if dist is None:
            continue
        sim = round(1.0 - dist, 4)
        if sim >= threshold:
            existing_q = docs[i][0] if i < len(docs) and docs[i] else ""
            dupes.append((item.question, existing_q, sim))
    return dupes


def dedupe_items(
    items: list[KnowledgeItem], threshold: float = 0.93,
) -> tuple[list[KnowledgeItem], list[dict]]:
    """维护 Agent 去重编排：先批内精确去重，再对库做向量查重。

    Returns:
        kept: 保留（可入库）的题
        reports: 去重报告，每项 {"kind": "within_batch"|"existing",
                                "question": 新题, "existing": 匹配到的已有题或None, "sim": 相似度}
    """
    # 1. 批内精确去重（同一批里完全相同的题只留一道）
    seen: set[str] = set()
    unique: list[KnowledgeItem] = []
    reports: list[dict] = []
    for it in items:
        key = _normalize(it.question)
        if key in seen:
            reports.append({"kind": "within_batch", "question": it.question, "existing": None, "sim": 1.0})
            continue
        seen.add(key)
        unique.append(it)

    # 2. 对库向量查重（语义相近 / 完全相同）
    dupes = find_duplicates(unique, threshold=threshold)
    dup_qs = {d[0] for d in dupes}
    kept = [it for it in unique if it.question not in dup_qs]
    for new_q, old_q, sim in dupes:
        reports.append({"kind": "existing", "question": new_q, "existing": old_q, "sim": sim})

    return kept, reports


def find_intra_duplicates(threshold: float = 0.93) -> list[tuple[str, str, float]]:
    """全库体检：找出库内语义重复的题对。

    对每道题 query top-2（top-1 是自己，top-2 是最相似的别的题），
    相似度 >= threshold 判定为一对重复。

    Returns: [(题A, 题B, 相似度)]，已去重（A-B 与 B-A 只报一次）。
    """
    collection = get_collection()
    n = collection.count()
    if n < 2:
        return []

    got = collection.get(include=["documents"])
    docs = got.get("documents", [])
    if len(docs) < 2:
        return []

    embs = embed_texts(docs)
    results = collection.query(
        query_embeddings=embs,
        n_results=2,
        include=["documents", "distances"],
    )

    dists = results.get("distances", [])
    qdocs = results.get("documents", [])
    pairs: list[tuple[str, str, float]] = []
    seen: set[tuple[str, str]] = set()
    for i, q in enumerate(docs):
        if i >= len(dists) or len(dists[i]) < 2:
            continue
        sim = round(1.0 - dists[i][1], 4)
        if sim < threshold:
            continue
        other = qdocs[i][1] if i < len(qdocs) and len(qdocs[i]) > 1 else ""
        if not other:
            continue
        key = tuple(sorted([_normalize(q), _normalize(other)]))
        if key in seen:
            continue
        seen.add(key)
        pairs.append((q, other, sim))
    return pairs


def find_exact_duplicates() -> list[list[KnowledgeItem]]:
    """找出完全相同的重复题（归一化后 question 相同），返回重复组列表（每组 >1 条）。"""
    items = search(top_k=1000)
    groups: dict[str, list[KnowledgeItem]] = {}
    for it in items:
        key = _normalize(it.question)
        groups.setdefault(key, []).append(it)
    return [g for g in groups.values() if len(g) > 1]


def get_by_id(item_id: str) -> Optional[KnowledgeItem]:
    """按 id 查单条。不存在返回 None（模拟面试写回 / Web 判定用）。"""
    if not item_id:
        return None
    collection = get_collection()
    if collection.count() == 0:
        return None
    results = collection.get(ids=[item_id], include=["documents", "metadatas"])
    items = _parse_results(results)
    return items[0] if items else None


def delete_by_ids(ids: list[str]) -> int:
    """按 id 删除，返回删除数量。"""
    if not ids:
        return 0
    collection = get_collection()
    collection.delete(ids=ids)
    return len(ids)


def auto_clean() -> dict:
    """维护 Agent 自动清理：删掉完全相同的重复题，每组保留信息最全的一条。

    这是确定性判断（归一化后完全相同），不需要用户确认。
    返回 {"removed": 删除数, "groups": 重复组数}。
    """
    groups = find_exact_duplicates()
    if not groups:
        return {"removed": 0, "groups": 0}

    def _priority(it: KnowledgeItem) -> int:
        p = 0
        if it.answer:  # 有参考答案的优先保留
            p += 10
        status_rank = {"fail": 3, "unknown": 2, "pass": 1, "partial": 0}
        p += status_rank.get(it.status.value, 0)  # 错题优先（信息价值更高）
        return p

    to_delete: list[str] = []
    for g in groups:
        g_sorted = sorted(g, key=_priority, reverse=True)
        for dup in g_sorted[1:]:
            to_delete.append(dup.id)

    removed = delete_by_ids(to_delete)
    return {"removed": removed, "groups": len(groups)}


def get_stats(space: str | None = None) -> dict:
    """统计各 status 数量 + 热门 topic + 来源分布。space 传则只统计该空间。"""
    items = search(top_k=1000)
    if space:
        items = [it for it in items if (it.space or "default") == space]

    status_count = {"fail": 0, "partial": 0, "pass": 0, "unknown": 0}
    topic_count: dict[str, int] = {}
    source_count: dict[str, int] = {}

    for item in items:
        source_count[item.source.value] = source_count.get(item.source.value, 0) + 1
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
        "by_source": source_count,
        "hot_topics": [{"topic": t, "count": c} for t, c in hot_topics],
    }


def clear() -> None:
    """清空 collection（测试用）。"""
    client = _get_client()
    try:
        client.delete_collection(_collection_name())
    except Exception:
        pass


def _to_metadata(item: KnowledgeItem) -> dict:
    return {
        "question": item.question,
        "answer": item.answer,
        "question_type": item.question_type,
        "topic": item.topic,
        "company": item.company,
        "role": item.role,
        "round": item.round,
        "date": item.date,
        "space": item.space or "default",
        "status": item.status.value,
        "user_note": item.user_note[:200],  # 截断
        "feedback": item.feedback[:4000],  # 面试官反馈，防 Chroma metadata 单值过大
        "category": item.category.value,
        "source": item.source.value,
        "mastery_score": item.mastery_score,
        "last_reviewed_at": item.last_reviewed_at.isoformat() if item.last_reviewed_at else "",
        "review_count": item.review_count,
        "created_at": item.created_at.isoformat() if item.created_at else "",
        "history": json.dumps(item.history, ensure_ascii=False),
        "behavior_tags": json.dumps(item.behavior_tags, ensure_ascii=False),
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

        try:
            category = ItemCategory(meta.get("category", "knowledge"))
        except ValueError:
            category = ItemCategory.KNOWLEDGE

        # v1.0 存量数据没有 source key → 默认 self_review（phase-2-plan §2.3）
        try:
            source = ItemSource(meta.get("source", ItemSource.SELF_REVIEW.value))
        except ValueError:
            source = ItemSource.SELF_REVIEW

        last_reviewed = meta.get("last_reviewed_at", "")

        # 证据链：老数据无 history key → 默认空 list
        try:
            history = json.loads(meta.get("history", "[]"))
        except (TypeError, ValueError):
            history = []

        # 行为特征：老数据无 behavior_tags key → 默认空 list
        try:
            behavior_tags = json.loads(meta.get("behavior_tags", "[]"))
        except (TypeError, ValueError):
            behavior_tags = []

        item = KnowledgeItem(
            id=item_id,
            question=meta.get("question", doc),
            answer=meta.get("answer", ""),
            question_type=meta.get("question_type", ""),
            topic=meta.get("topic", ""),
            category=category,
            company=meta.get("company", ""),
            role=meta.get("role", ""),
            round=meta.get("round", ""),
            date=meta.get("date", ""),
            space=meta.get("space", "default"),
            status=status,
            history=history,
            user_note=meta.get("user_note", ""),
            feedback=meta.get("feedback", ""),
            mastery_score=float(meta.get("mastery_score", 1.0)),
            review_count=int(meta.get("review_count", 0)),
            source=source,
            behavior_tags=behavior_tags,
            last_reviewed_at=datetime.fromisoformat(last_reviewed) if last_reviewed else None,
            created_at=datetime.fromisoformat(meta["created_at"]) if meta.get("created_at") else None,
        )
        # 附上余弦相似度（用于阈值过滤，ISSUES F1）
        if dist is not None:
            setattr(item, "_similarity", round(1.0 - dist, 4))
        items.append(item)

    return items
