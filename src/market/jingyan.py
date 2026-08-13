"""网上面经导入器 —— 题目列表 → KnowledgeItem（source=public_jingyan）。

phase-2-plan §2.3：第二数据源。网上面经只有题目、没有自评，
所以 status=unknown、category=knowledge。非爬虫，文本文件或手动粘贴。
"""

import hashlib
import logging
import re
from datetime import datetime

from src.llm import chat_json
from src.cleaner.schema import (
    KnowledgeItem,
    ItemStatus,
    ItemCategory,
    ItemSource,
)
from src.market.prompts import JINGYAN_TOPIC_SYSTEM

logger = logging.getLogger(__name__)

# 每次 LLM 调用处理的题目数上限
_CHUNK_SIZE = 40

_NUMBER_PREFIX_RE = re.compile(r"^\s*(?:\d{1,2}[.、)）]\s*|第\s*\d+\s*[题问]\s*)")
_SEPARATOR_RE = re.compile(r"^\s*(?:-{3,}|={3,}|\*{3,})\s*$")


def parse_jingyan_lines(text: str) -> list[str]:
    """纯规则解析：每行一题。

    - 跳过空行、`#` 注释行、纯分隔线（---/===/***）
    - 剥离行首编号（`1.`、`第2题` 等），避免编号混进题目文本
    """
    questions = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        if _SEPARATOR_RE.match(line):
            continue
        questions.append(_NUMBER_PREFIX_RE.sub("", line).strip())
    return questions


def _extract_topics(questions: list[str], offset: int = 0) -> dict[int, str]:
    """LLM 批量提取 topic，按 index 回填。

    Args:
        questions: 题目列表
        offset: index 起始偏移（分块时全局递增）

    Returns:
        {全局题目位置(0 起): topic}；LLM 失败或 index 缺失的题目不进 dict。
        分块时返回全局下标（index-1），多块 update 合并不会互相覆盖。
    """
    numbered = "\n".join(f"[{offset + i + 1}] {q}" for i, q in enumerate(questions))
    try:
        result = chat_json(
            system_prompt=JINGYAN_TOPIC_SYSTEM,
            user_prompt=f"## 面试题库\n{numbered}",
            temperature=0.0,
            max_tokens=2048,
        )
    except Exception as e:
        logger.warning("Jingyan topic extraction failed: %s", e)
        return {}

    topics: dict[int, str] = {}
    for entry in result.get("topics", []):
        try:
            index = int(entry.get("index", -1))
            topic = (entry.get("topic") or "").strip()
        except (TypeError, ValueError):
            logger.warning("Bad topic entry ignored: %r", entry)
            continue
        if index < offset + 1 or index > offset + len(questions):
            logger.warning("Topic index out of range ignored: %d", index)
            continue
        pos = index - 1  # 全局 0-based，分块合并不冲突（修复 >40 题多块覆盖 bug）
        if pos in topics:
            logger.warning("Duplicate topic index ignored: %d", index)
            continue
        topics[pos] = topic

    return topics


def import_jingyan(
    text: str,
    *,
    item_meta: dict[int, dict[str, str]] | None = None,
) -> list[KnowledgeItem]:
    """把网上面经文本导入为 KnowledgeItem 列表（不入库，由调用方存储）。

    Args:
        text: 网上面经文本，每行一题（`#` 注释/空行/分隔线会跳过）。
        item_meta: 可选，按题目下标（0 起）附带的面经元信息，例如
            {0: {"company": "腾讯", "role": "AI应用开发", "date": "2026-07-25"}}。
            由 jingyan_preprocess 的 InterviewRecord 回填（company/role/date/round）；
            未提供或缺失的下标沿用默认值（role 默认 "AI应用开发"）。

    降级策略：LLM 提 topic 失败时 topic 置空，照常导入——题目本身仍有价值，
    且验收只要求 status=unknown、category=knowledge。
    """
    questions = parse_jingyan_lines(text)
    if not questions:
        return []

    # 分块提 topic（每块一次 LLM 调用，index 全局递增）
    topics: dict[int, str] = {}
    for start in range(0, len(questions), _CHUNK_SIZE):
        chunk = questions[start : start + _CHUNK_SIZE]
        topics.update(_extract_topics(chunk, offset=start))

    meta_by_index = item_meta or {}
    items = []
    for i, q in enumerate(questions):
        # 幂等 id：同一题目重复导入 = upsert 覆盖
        qid = hashlib.md5(q.encode("utf-8")).hexdigest()[:8]
        meta = meta_by_index.get(i) or {}
        items.append(
            KnowledgeItem(
                id=f"jy_{qid}",
                question=q,
                topic=topics.get(i, ""),
                category=ItemCategory.KNOWLEDGE,
                company=meta.get("company", ""),
                role=meta.get("role") or "AI应用开发",
                round=meta.get("round", ""),
                date=meta.get("date", ""),
                status=ItemStatus.UNKNOWN,
                source=ItemSource.PUBLIC_JINGYAN,
                created_at=datetime.utcnow(),
            )
        )

    logger.info(
        "Imported %d jingyan questions, %d with topic",
        len(items),
        len(topics),
    )
    return items
