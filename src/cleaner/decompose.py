"""面经消化管线 —— 输入复盘文本 → 输出结构化 KnowledgeItem 列表。

product-plan §7.3 定义的处理流程：
1. [规则] 识别结构化标记（"Q1:" "公司：" "自评："等）
2. [LLM]  对非结构化碎片做 Q&A 抽取 + status 推断
3. [规则] 校验输出 JSON schema（必填字段、枚举值）
4. [输出] List[KnowledgeItem]
"""

import logging
import re
import uuid
from datetime import datetime

from src.llm import chat_json
from src.cleaner.prompts import DECOMPOSE_SYSTEM
from src.cleaner.schema import KnowledgeItem, ItemStatus, ItemCategory, DecomposeResult, utcnow
from src.cleaner.state_machine import record_birth
from src.memory.mastery import INITIAL_MASTERY

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
    raw_items = result.get("items", [])

    # 段级声明：整篇"没答上"→疑似错题（需用户确认后标 fail）；其余→知识库
    default_status = (result.get("default_status") or "").strip()
    suspected_fail = default_status == "fail"

    for i, item_data in enumerate(raw_items):
        question = (item_data.get("question") or "").strip()
        if not question:
            continue

        user_note = (item_data.get("user_note") or "").strip()

        # 分流设计：不再逐题猜 status，一律 unknown，等用户手动标错题
        final_status = ItemStatus.UNKNOWN

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
            id=f"ki_{utcnow():%Y%m%d}_{uuid.uuid4().hex[:6]}_{i+1:03d}",
            question=question,
            answer=(item_data.get("answer") or "").strip(),
            question_type=(item_data.get("question_type") or "").strip(),
            topic=(item_data.get("topic") or "").strip(),
            category=category,
            company=(result.get("company") or "").strip(),
            role=(result.get("role") or "").strip(),
            round=(result.get("round") or "").strip(),
            date=(result.get("date") or "").strip(),
            status=final_status,
            mastery_score=INITIAL_MASTERY[final_status],
            user_note=user_note,
            created_at=utcnow(),
        )
        # 记出生证据（from=null），来源可追溯：LLM 推断 or 规则兜底
        ki = record_birth(
            ki,
            reason="入库（待用户标错题）",
            actor="decompose",
        )
        items.append(ki)

    logger.info("Decomposed: %d items", len(items))

    return DecomposeResult(
        company=(result.get("company") or "").strip(),
        role=(result.get("role") or "").strip(),
        round=(result.get("round") or "").strip(),
        date=(result.get("date") or "").strip(),
        items=items,
        raw_text=raw_text,
        unknown_count=len(items),
        total_count=len(items),
        suspected_fail=suspected_fail,
    )
