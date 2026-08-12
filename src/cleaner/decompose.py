"""面经消化管线 —— 输入复盘文本 → 输出结构化 KnowledgeItem 列表。

product-plan §7.3 定义的处理流程：
1. [规则] 识别结构化标记（"Q1:" "公司：" "自评："等）
2. [LLM]  对非结构化碎片做 Q&A 抽取 + status 推断
3. [规则] 校验输出 JSON schema（必填字段、枚举值）
4. [输出] List[KnowledgeItem]
"""

import logging
import re
from datetime import datetime

from src.llm import chat_json
from src.cleaner.prompts import DECOMPOSE_SYSTEM
from src.cleaner.status import infer_status
from src.cleaner.schema import KnowledgeItem, ItemStatus, ItemCategory, DecomposeResult

logger = logging.getLogger(__name__)

# ISSUES E2: 题目含占位符（***、...、略）时记录日志，不推断补全
_PLACEHOLDER_RE = re.compile(r"(\*{2,}|\.{3,}|略)")


def has_placeholder(text: str) -> bool:
    """题目是否含占位符（*** / ... / 略）。"""
    return bool(_PLACEHOLDER_RE.search(text))


def decompose(raw_text: str, *, max_tokens: int = 4096) -> DecomposeResult:
    """拆解一篇面试复盘文本为结构化 Q&A 列表。

    流程：
    1. 调 LLM 做 Q&A 抽取 + 初步 status 推断
    2. 规则层兜底：LLM 返回 unknown 的条目，再用规则关键词判断一次
    3. 校验并生成 KnowledgeItem

    Args:
        raw_text: 用户写的面试复盘全文
        max_tokens: LLM 最大输出 token

    Returns:
        DecomposeResult（company/role/round/date/items/unknown_count）
    """
    logger.info("Decomposing interview review (%d chars)", len(raw_text))

    # Step 1: LLM 拆解
    user_prompt = f"## 面试复盘\n{raw_text[:6000]}"  # 限制长度

    try:
        result = chat_json(
            system_prompt=DECOMPOSE_SYSTEM,
            user_prompt=user_prompt,
            temperature=0.0,
            max_tokens=max_tokens,
        )
    except Exception as e:
        logger.error("Decompose LLM call failed: %s", e)
        return DecomposeResult(raw_text=raw_text, total_count=0)

    # Step 2: 组装 KnowledgeItem
    items = []
    unknown_count = 0
    raw_items = result.get("items", [])

    for i, item_data in enumerate(raw_items):
        question = (item_data.get("question") or "").strip()
        if not question:
            continue

        # LLM 推断的 status
        llm_status = item_data.get("status", "unknown")
        user_note = (item_data.get("user_note") or "").strip()

        # 规则层兜底：LLM 返回 unknown 的，规则再判断一次
        if llm_status == "unknown" and user_note:
            rule_status = infer_status(user_note)
            if rule_status != ItemStatus.UNKNOWN:
                logger.debug("Rule override: '%s' → %s", user_note[:30], rule_status.value)
                final_status = rule_status
            else:
                final_status = ItemStatus.UNKNOWN
        else:
            try:
                final_status = ItemStatus(llm_status)
            except ValueError:
                final_status = ItemStatus.UNKNOWN

        if final_status == ItemStatus.UNKNOWN:
            unknown_count += 1

        # 解析 category（ISSUES F2）
        cat_raw = (item_data.get("category") or "knowledge").strip()
        try:
            category = ItemCategory(cat_raw)
        except ValueError:
            category = ItemCategory.KNOWLEDGE

        # ISSUES E2: 占位符题目记录日志
        if has_placeholder(question):
            logger.warning("题目含占位符，保留原样未推断: %s", question[:60])

        ki = KnowledgeItem(
            id=f"ki_{datetime.utcnow():%Y%m%d}_{i+1:03d}",
            question=question,
            topic=(item_data.get("topic") or "").strip(),
            category=category,
            company=(result.get("company") or "").strip(),
            role=(result.get("role") or "").strip(),
            round=(result.get("round") or "").strip(),
            date=(result.get("date") or "").strip(),
            status=final_status,
            user_note=user_note,
            created_at=datetime.utcnow(),
        )
        items.append(ki)

    logger.info(
        "Decomposed: %d items, %d unknown (%.0f%%)",
        len(items), unknown_count,
        unknown_count / len(items) * 100 if items else 0,
    )

    return DecomposeResult(
        company=(result.get("company") or "").strip(),
        role=(result.get("role") or "").strip(),
        round=(result.get("round") or "").strip(),
        date=(result.get("date") or "").strip(),
        items=items,
        raw_text=raw_text,
        unknown_count=unknown_count,
        total_count=len(items),
    )
