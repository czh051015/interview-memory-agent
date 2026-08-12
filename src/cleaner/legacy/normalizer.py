"""标准化器 —— 日期 ISO 化、source 枚举校验、空白规范化。"""

import re
import hashlib
from datetime import datetime
from typing import Optional

from src.models import FeedbackSource

# 中文日期模式 → ISO
_DATE_PATTERNS = [
    (re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"), r"\1-\2-\3"),
    (re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})"), r"\1-\2-\3"),
    (re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})"), r"\1-\2-\3"),  # 已经是 ISO
]


def normalize_text(raw_text: str) -> str:
    """标准化文本：日期→ISO、空白规范化、去除首尾空格。

    保留公司名、岗位名、面试题内容，不处理英文大小写/标点（留 v2）。
    """
    text = raw_text.strip()
    text = re.sub(r"\s+", " ", text)  # 多空白→单空格

    # 日期标准化
    for pattern, repl in _DATE_PATTERNS:
        text = pattern.sub(_date_replacer, text)

    return text


def _date_replacer(match: re.Match) -> str:
    """将匹配的日期转为 ISO 格式 YYYY-MM-DD。"""
    groups = match.groups()
    if len(groups) >= 3:
        year, month, day = groups[0], groups[1], groups[2]
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return match.group()


def normalize_whitespace(text: str) -> str:
    """纯空白规范化，不改变文字内容。"""
    return re.sub(r"\s+", " ", text.strip())


def generate_dedup_hash(normalized_text: str, source: FeedbackSource) -> str:
    """生成去重哈希：normalized_text 的 SHA256 + source 组合。"""
    content = f"{normalized_text}|{source.value}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def validate_source(source: str) -> Optional[FeedbackSource]:
    """校验 source 枚举值。"""
    try:
        return FeedbackSource(source)
    except ValueError:
        return None
