"""交叉验证 —— 错题 topic × 题库高频 × JD 要求 → 复习优先级。

phase-2-plan §2.4。设计要点：
- adjust_priority 与计划书公式逐字符一致（不改一个字）
- 模糊匹配（"RAG" vs "RAG检索增强"）放在 build_market_stats 的聚类阶段：
  把题库 topic 和 JD 关键词贪心聚成 cluster，三个集合展开为成员拼写并集，
  公式里的精确 `in` 判断自然命中
- 高频/低频互斥：题库中出现 ≥N 次 → 高频（×1.5）；恰好 1 次 → 低频（×0.5）；
  题库中 0 次的 topic 两个集合都不进，只乘 JD 系数（×1.2）
- 权重 1.5/0.5/1.2 为初值（计划书风险表：攒够数据后用 eval 校准）
"""

import logging
from collections import Counter

from src.config import HIGH_FREQ_MIN_COUNT
from src.cleaner.schema import KnowledgeItem, ItemCategory, ItemSource

logger = logging.getLogger(__name__)


def _topics_match(a: str, b: str) -> bool:
    """topic 匹配：精确相等或双向包含（"RAG" ⊂ "RAG检索增强"）。"""
    a, b = a.strip(), b.strip()
    if not a or not b:
        return False
    return a == b or a in b or b in a


def build_market_stats(
    items: list[KnowledgeItem],
    *,
    high_freq_min: int = HIGH_FREQ_MIN_COUNT,
) -> dict:
    """从全量 KnowledgeItem 计算市场信号。

    题库（频率池）= source ∈ {self_review, public_jingyan} 且 category=knowledge
    且 topic 非空。JD 关键词 = source=jd 条目的 topic。

    Returns:
        {
            "high_freq_topics": set[str],     # 题库中 ≥N 次
            "low_freq_topics": set[str],      # 题库中恰好 1 次
            "jd_required_topics": set[str],   # 与 JD 关键词同 cluster 的所有拼写
            "topic_freq": dict[str, int],     # 仅供展示
        }
    """
    pool_topics: list[str] = []
    jd_keywords: list[str] = []
    for item in items:
        topic = (item.topic or "").strip()
        if not topic:
            continue
        if item.source == ItemSource.JD:
            jd_keywords.append(topic)
        elif item.category == ItemCategory.KNOWLEDGE and item.source in (
            ItemSource.SELF_REVIEW,
            ItemSource.PUBLIC_JINGYAN,
        ):
            pool_topics.append(topic)

    pool_freq = Counter(pool_topics)
    clusters: list[dict] = []  # {"members": set[str], "pool_count": int, "has_jd": bool}

    def _find_cluster(topic: str):
        for cluster in clusters:
            if any(_topics_match(topic, m) for m in cluster["members"]):
                return cluster
        return None

    # 题库 topic 先聚（pool_count 累加出现次数）
    for topic in pool_topics:
        cluster = _find_cluster(topic)
        if cluster is None:
            cluster = {"members": {topic}, "pool_count": 0, "has_jd": False}
            clusters.append(cluster)
        cluster["members"].add(topic)
        cluster["pool_count"] += 1

    # JD 关键词后聚（并入已有 cluster 或新建纯 JD cluster）
    for keyword in jd_keywords:
        cluster = _find_cluster(keyword)
        if cluster is None:
            cluster = {"members": {keyword}, "pool_count": 0, "has_jd": False}
            clusters.append(cluster)
        cluster["members"].add(keyword)
        cluster["has_jd"] = True

    high_freq: set[str] = set()
    low_freq: set[str] = set()
    jd_required: set[str] = set()
    for cluster in clusters:
        spellings = cluster["members"]
        if cluster["pool_count"] >= high_freq_min:
            high_freq |= spellings
        elif cluster["pool_count"] == 1:
            low_freq |= spellings
        # pool_count == 0 的纯 JD cluster 不进高/低频
        if cluster["has_jd"]:
            jd_required |= spellings

    logger.info(
        "Market stats: %d pool topics, %d jd keywords, %d clusters, "
        "%d high-freq, %d low-freq, %d jd-required",
        len(pool_topics), len(jd_keywords), len(clusters),
        len(high_freq), len(low_freq), len(jd_required),
    )

    return {
        "high_freq_topics": high_freq,
        "low_freq_topics": low_freq,
        "jd_required_topics": jd_required,
        "topic_freq": dict(pool_freq),
    }


def adjust_priority(item: KnowledgeItem, market_stats: dict) -> float:
    """错题 × 市场信号，修正优先级。"""
    priority = 1.0

    # 你的错题 + 题库高频 = 优先级提升
    if item.topic in market_stats["high_freq_topics"]:
        priority *= 1.5
    # 你的错题 + 题库低频 = 优先级降低
    elif item.topic in market_stats["low_freq_topics"]:
        priority *= 0.5
    # 你的错题 + JD 明确要求 = 额外提升
    if item.topic in market_stats["jd_required_topics"]:
        priority *= 1.2

    return priority


def apply_priorities(
    items: list[KnowledgeItem],
    market_stats: dict,
) -> list[KnowledgeItem]:
    """为每条 item 计算 priority，返回新列表（不改输入）。"""
    return [
        item.model_copy(update={"priority": adjust_priority(item, market_stats)})
        for item in items
    ]
