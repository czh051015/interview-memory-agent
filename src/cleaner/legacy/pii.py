"""PII 检测与脱敏 —— 正则粗筛 + LLM 精判。"""

import re
import logging
from typing import Optional

from src.llm import chat_json
from src.cleaner.legacy.prompts import PII_SYSTEM, PII_USER

logger = logging.getLogger(__name__)

# 正则：手机号（中国大陆）、邮箱
_RE_PHONE = re.compile(r"1[3-9]\d{9}")
_RE_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# PII 脱敏替换
_MASK_MAP = {
    "phone": lambda v: v[:3] + "****" + v[-4:],  # 138****5678
    "email": lambda v: v[0] + "***@" + v.split("@")[1] if "@" in v else "***",
    "name": lambda v: v[0] + "某" if v else "某",
}


def regex_scan(text: str) -> list[dict]:
    """正则扫描 phone + email，返回 PII 列表。"""
    results = []
    for m in _RE_PHONE.finditer(text):
        results.append({
            "type": "phone",
            "value": m.group(),
            "start": m.start(),
            "end": m.end(),
        })
    for m in _RE_EMAIL.finditer(text):
        results.append({
            "type": "email",
            "value": m.group(),
            "start": m.start(),
            "end": m.end(),
        })
    return results


def llm_scan(text: str) -> list[dict]:
    """LLM 扫描 PII（姓名等正则难以覆盖的边界情况）。"""
    try:
        result = chat_json(
            system_prompt=PII_SYSTEM,
            user_prompt=PII_USER.format(text=text[:2000]),  # 限制长度
        )
        return result.get("pii", [])
    except Exception as e:
        logger.warning("PII LLM scan failed, falling back to regex only: %s", e)
        return []


def scan_pii(text: str) -> dict:
    """双通道 PII 扫描：正则 + LLM，合并结果。

    Returns:
        {"found": ["phone:138****5678", "name:张三"], "masked": true/false, "pii_entries": [...]}
    """
    # 第一遍：正则
    regex_entries = regex_scan(text)
    found_descs = [f"{e['type']}:{e['value']}" for e in regex_entries]

    # 第二遍：LLM（只扫正则未覆盖的部分）
    # 先替换掉正则已发现的，避免重复扫描
    text_after_regex = text
    for entry in sorted(regex_entries, key=lambda x: x["start"], reverse=True):
        text_after_regex = text_after_regex[:entry["start"]] + " " + text_after_regex[entry["end"]:]

    llm_entries = llm_scan(text_after_regex)
    for entry in llm_entries:
        found_descs.append(f"{entry.get('type', 'unknown')}:{entry.get('value', '?')}")

    all_entries = regex_entries + llm_entries
    return {
        "found": found_descs,
        "masked": False,  # masking 在 mask_text 中完成
        "_entries": all_entries,  # 内部用
    }


def mask_text(text: str, pii_entries: list[dict]) -> str:
    """根据 PII 标记脱敏文本。

    从后往前替换以保持 start/end 偏移正确。
    """
    result = text
    for entry in sorted(pii_entries, key=lambda x: x.get("start", 0), reverse=True):
        start = entry.get("start", 0)
        end = entry.get("end", 0)
        pii_type = entry.get("type", "")
        original = entry.get("value", "")

        if 0 <= start < end <= len(result):
            mask_fn = _MASK_MAP.get(pii_type, lambda v: "***")
            masked = mask_fn(original)
            result = result[:start] + masked + result[end:]

    return result
