"""JD 导入器 —— JD 文本 → 技能关键词 → KnowledgeItem（source=jd）。

phase-2-plan §2.3：第三数据源。JD 关键词用于交叉验证：
错题 topic 命中 JD 要求时优先级额外提升。
"""

import hashlib
import logging
from datetime import datetime
from pathlib import Path

from src.llm import chat_json
from src.cleaner.schema import (
    KnowledgeItem,
    ItemStatus,
    ItemCategory,
    ItemSource,
)
from src.market.prompts import JD_EXTRACT_SYSTEM

logger = logging.getLogger(__name__)


def extract_jd_keywords(jd_text: str, company_hint: str = "") -> dict:
    """LLM 提取 JD 技能关键词。

    Args:
        jd_text: JD 全文
        company_hint: 公司名提示（LLM 提取失败时兜底）

    Returns:
        {"company": str, "keywords": list[str]}

    Raises:
        ValueError: 提取失败（JD 导入的价值全在提取，不静默降级）
    """
    try:
        result = chat_json(
            system_prompt=JD_EXTRACT_SYSTEM,
            user_prompt=f"## 职位描述\n{jd_text[:6000]}",
            temperature=0.0,
            max_tokens=1024,
        )
    except Exception as e:
        raise ValueError(f"JD 关键词提取失败: {e}") from e

    keywords = result.get("keywords") or []
    if not isinstance(keywords, list) or not keywords:
        raise ValueError("JD 关键词提取失败：返回的 keywords 为空")

    company = (result.get("company") or "").strip() or company_hint.strip()
    keywords = [k.strip() for k in keywords if isinstance(k, str) and k.strip()]

    if not keywords:
        raise ValueError("JD 关键词提取失败：清洗后 keywords 为空")

    return {"company": company, "keywords": keywords}


def import_jd(jd_text: str, company_hint: str = "") -> list[KnowledgeItem]:
    """把 JD 技能关键词导入为 KnowledgeItem 列表（不入库，由调用方存储）。

    每个关键词一条：question=topic=关键词，status=unknown，source=jd。
    交叉验证以 topic 作为匹配键（cross_validate.build_market_stats）。
    """
    extracted = extract_jd_keywords(jd_text, company_hint=company_hint)
    company = extracted["company"]

    items = []
    for keyword in extracted["keywords"]:
        # 幂等 id：同公司同关键词重复导入 = upsert 覆盖
        kid = hashlib.md5(f"{company}{keyword}".encode("utf-8")).hexdigest()[:8]
        items.append(
            KnowledgeItem(
                id=f"jd_{kid}",
                question=keyword,
                topic=keyword,
                category=ItemCategory.KNOWLEDGE,
                company=company,
                status=ItemStatus.UNKNOWN,
                source=ItemSource.JD,
                created_at=datetime.utcnow(),
            )
        )

    logger.info("JD imported: %s → %d keywords", company or "(未识别)", len(items))
    return items


def jd_files_from(path: Path) -> list[Path]:
    """展开 JD 输入路径：单个 .txt 文件 → [file]，目录 → 目录下 *.txt 排序。"""
    if path.is_dir():
        return sorted(path.glob("*.txt"))
    return [path]
