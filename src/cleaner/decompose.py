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

from pydantic import ValidationError

from src.llm import chat_json
from src.cleaner.prompts import DECOMPOSE_SYSTEM, SHENLUN_DECOMPOSE_SYSTEM
from src.cleaner.schema import (
    KnowledgeItem,
    ItemStatus,
    ItemCategory,
    DecomposeResult,
    ReferencePoint,
    PointDecomposeResult,
    append_point_history,
    utcnow,
)
from src.cleaner.state_machine import record_birth
from src.cleaner.status import infer_status
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

        # 有自评信号（user_note 非空）→ LLM 主判，规则兜底；纯题目/无备注 → unknown 等手动标
        if user_note:
            llm_status = (item_data.get("status") or "").strip()
            if llm_status in {"fail", "partial", "pass"}:
                final_status = ItemStatus(llm_status)
            else:
                final_status = infer_status(user_note)
        else:
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
        unknown_count=sum(1 for it in items if it.status == ItemStatus.UNKNOWN),
        total_count=len(items),
        suspected_fail=suspected_fail,
    )


# ── 申论域：标准答案 → 采分点（docs/16 §3.3）───────────────────────────────
# 复用骨架：chat_json 调用 / 异常兜底（LLM 挂了返回空结果而非崩溃）/ 长度截断。
# 删除点：status 推断、category 分类、mastery 初始化、占位符正则——全是面试域的，申论不需要。
def decompose_points(
    standard_answer: str,
    *,
    question: str = "",
    requirements: str = "",
    material: str = "",
    max_score: int = 0,
    question_id: str = "",
    max_tokens: int = 4096,
) -> PointDecomposeResult:
    """把申论标准答案拆成采分点（ReferencePoint[]，默认 approved=False）。

    流程：
    1. 调 LLM（SHENLUN_DECOMPOSE_SYSTEM，温度 0）拆点
    2. pydantic 校验输出——单条失败记 warnings，不整体崩
    3. 组装 PointDecomposeResult（approved=False, source="llm_draft"）
    4. 每点留出生证据（from=null，actor="decompose_points"）
    5. 返回结果——不写库！写库是 annotate_points 人审通过后的事

    Args:
        standard_answer: 标准答案全文（拆点对象）
        question/requirements/material: 题目语境，拆点需要，否则会拆出答非所问的点
        max_score: 题目满分，LLM 按它分配各点分值
        question_id: 题目 id（入库时用，留空则后续填）

    Returns:
        PointDecomposeResult（reference_points + warnings）
    """
    logger.info("Decomposing standard answer into points (%d chars)", len(standard_answer))

    user_prompt = (
        f"## 题目\n{question}\n\n"
        f"## 要求\n{requirements}\n\n"
        f"## 材料（给定资料）\n{material[:6000]}\n\n"
        f"## 题目满分\n{max_score}\n\n"
        f"## 标准答案\n{standard_answer[:6000]}"
    )

    try:
        result = chat_json(
            system_prompt=SHENLUN_DECOMPOSE_SYSTEM,
            user_prompt=user_prompt,
            temperature=0.0,
            max_tokens=max_tokens,
        )
    except Exception as e:
        logger.error("Decompose points LLM call failed: %s", e)
        return PointDecomposeResult(
            question_id=question_id,
            question=question,
            requirements=requirements,
            material=material,
            max_score=max_score,
        )

    # pydantic 校验：单条失败 → warnings 记录，不整体崩
    points: list[ReferencePoint] = []
    warnings: list[str] = []
    now = utcnow()
    raw_points = result.get("reference_points") or []
    for i, p_data in enumerate(raw_points, 1):
        try:
            rp = ReferencePoint(
                id=f"c{len(points) + 1}",  # 只对成功的点连续编号，跳过的不占号
                point=(p_data.get("point") or "").strip(),
                keywords=[str(k).strip() for k in (p_data.get("keywords") or []) if str(k).strip()],
                score=float(p_data.get("score") or 0),
                point_type=(p_data.get("point_type") or "").strip(),
                created_at=now,
            )
        except (ValidationError, TypeError, ValueError) as e:
            warnings.append(f"第 {i} 个采分点校验失败，已跳过: {e}")
            continue
        # 出生证据：由 LLM 拆解生成，待人工审核
        points.append(append_point_history(
            rp,
            to_source="llm_draft",
            reason="由 LLM 拆解生成，待人工审核",
            actor="decompose_points",
            now=now,
        ))

    warnings.extend(str(w) for w in (result.get("warnings") or []) if w)

    if not points:
        warnings.append("未拆出任何采分点，请检查标准答案是否完整")
    elif len(points) < 2:
        warnings.append("疑似标答过简，拆出的点过少，建议更换标准答案")

    logger.info("Decomposed points: %d (approved: 0, warnings: %d)", len(points), len(warnings))

    return PointDecomposeResult(
        question_id=question_id,
        question=question,
        requirements=requirements,
        material=material,
        max_score=max_score,
        reference_points=points,
        warnings=warnings,
    )
