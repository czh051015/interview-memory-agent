# -*- coding: utf-8 -*-
"""docx 面经预处理：docx 解析 → 20 份面经切分 → 抽题/去噪 → 公司/岗位/日期 → 归一化去重。

阶段二（v1.5+）数据入口：把原始《面试题.docx》加工成可入库的题目列表，
再交给 src.market.jingyan.import_jingyan 生成 KnowledgeItem（source=public_jingyan）。

流水线（每步一个纯函数，便于测试）：
1. parse_docx         纯 stdlib 解析 docx（zipfile + ElementTree，不依赖 python-docx）
2. split_interviews   按文档自带的顺序编号（1~20）切成 20 份面经
3. extract_questions  抽题 + 去噪（编号切分、Q 系列、去广告/评论/答案尾巴）
4. extract_metadata   规则提取公司 / 岗位 / 日期，日期归一化为 YYYY-MM-DD
5. dedupe_questions   归一化 + 去重（每份面经内 + 全局）

用法：
  python -m src.market.jingyan_preprocess            # 打印解析摘要
  python -m src.market.jingyan_preprocess --seed     # 输出归一化去重后的题目列表
"""

from __future__ import annotations

import logging
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# 文档自带的面经顺序编号，从 1 开始
SECTION_START = 1

# 仓库根目录下的原始 docx
DEFAULT_DOCX = Path(__file__).resolve().parents[3] / "面试题.docx"

# 只有月/日的面经默认补全的年份（文档内为 2026 届校招）
DEFAULT_YEAR = 2026


# ─────────────────────────────── 1. docx 解析 ───────────────────────────────


def _collect_text(node: ET.Element) -> str:
    """收集节点下全部 w:t 文本（w:tab → 空格，w:br → 换行）。"""
    parts: list[str] = []
    for child in node.iter():
        if child.tag == _W + "t":
            if child.text:
                parts.append(child.text)
        elif child.tag == _W + "tab":
            parts.append(" ")
        elif child.tag == _W + "br":
            parts.append("\n")
    return "".join(parts)


def parse_docx(path: str | Path) -> list[str]:
    """读取 docx 全文，按段落返回文本（表格单元格按段落展开）。

    只依赖标准库，无需 python-docx。
    """
    with zipfile.ZipFile(Path(path)) as zf:
        xml_bytes = zf.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    body = root.find(_W + "body")
    paragraphs: list[str] = []
    if body is None:
        return paragraphs
    for child in body:
        if child.tag == _W + "p":
            paragraphs.append(_collect_text(child))
        elif child.tag == _W + "tbl":
            for row in child.iter(_W + "tr"):
                for cell in row.findall(_W + "tc"):
                    paragraphs.append(_collect_text(cell))
    return paragraphs


# ─────────────────────────────── 2. 20 份面经切分 ───────────────────────────

_SECTION_MARKER_RE = re.compile(r"^\s*(\d{1,2})\s+(\S.*)", re.DOTALL)


@dataclass
class InterviewRecord:
    """一份切分后的面经。"""

    index: int
    header: str
    company: str = ""
    role: str = ""
    date: str = ""
    questions: list[str] = field(default_factory=list)
    raw_paragraphs: list[str] = field(default_factory=list)


_HEADER_QUESTION_CUT_RE = re.compile(r"面试问题[:：]|(?<![A-Za-z0-9Qq])\d{1,2}\s*[.、)）:：](?!\d)")


def _truncate_header(header: str) -> str:
    """header 截断到面试问题/第一个编号题目为止，避免长段面经把题目混进元信息。"""
    m = _HEADER_QUESTION_CUT_RE.search(header)
    if m:
        header = header[: m.start()]
    return header.strip()


def split_interviews(paragraphs: list[str]) -> list[InterviewRecord]:
    """按顺序编号（1、2、…）切分面经。

    只有「行首数字 + 空白 + 内容」且数字等于下一个期望编号的段落才视为分界，
    避免把正文里的“1. 自我介绍”这类题目编号误判成分隔线。
    """
    records: list[InterviewRecord] = []
    current: InterviewRecord | None = None
    expected = SECTION_START
    for para in paragraphs:
        m = _SECTION_MARKER_RE.match(para)
        if m and int(m.group(1)) == expected:
            if current is not None:
                records.append(current)
            rest = m.group(2).strip()
            current = InterviewRecord(
                index=expected,
                header=_truncate_header(rest),
                raw_paragraphs=[rest],
            )
            expected += 1
            continue
        if current is not None:
            current.raw_paragraphs.append(para)
        else:
            # 编号前的封面/前言，不属于任何面经
            logger.debug("Ignoring paragraph before section %d: %r", expected, para[:40])
    if current is not None:
        records.append(current)
    return records


# ─────────────────────────────── 3. 抽题 / 去噪 ─────────────────────────────

_QUESTION_SPLIT_RE = re.compile(r"(?<![A-Za-z0-9Qq])(?=(?:Q\s*)?\d{1,2}\s*[.、)）:：](?!\d))")
_QUESTION_PREFIX_RE = re.compile(r"^\s*(?:(?:Q\s*)?\d{1,2}\s*[.、)）:：]\s*|第\s*\d+\s*[题问]\s*)")
_METADATA_LINE_RE = re.compile(
    r"^\s*[\W_]*[-•*]?\s*(?:面试)?(?:公司|岗位|时间|批次|轮次|形式|时长)[:：]"
)
_HEADER_LINE_RE = re.compile(
    r"^\s*(?:"
    r"#{1,6}\s*"
    r"|第?[一二三四五六七八九十百]+[、.．]"
    r"|\d+️⃣"
    r"|[\u2460-\u2473]"
    r"|面试问题|面试流程|候选人反问|反问环节|点评项目|一面|二面"
    r")"
)
_QUESTION_VERB_RE = re.compile(
    r"^(?:请|介绍|讲讲|讲|说|描述|简述|解释|谈谈|聊|做了|如何|怎样|怎么|为什么|为何|"
    r"是否|有没有|能不能|可不可以|简单|对比|参考|了解|分析|评价|列举|列|举例|"
    r"写|实现|设计|你觉得|你认为|请你说|你)"
)
_QUESTION_HINT_RE = re.compile(
    r"什么|怎么|怎样|如何|哪|是否|是不是|有没有|能不能|为什么|为何|多少|吗|呢|"
    r"说一下|说说|讲讲|解释|介绍|简述|区别|原理|机制|方案|设计|实现|知道|了解|"
    r"原因|列举|举例|手撕|评价|聊聊|谈谈|理解"
)
_QUESTION_LABEL_KEEP = {"自我介绍", "项目介绍"}
_NOISE_RE = re.compile(
    r"^反问\s*[，,。;；]?$"
    r"|面试官分享|本来是想问|我说就是|没把握的可以T我|捞过不少人|笔试面试|"
    r"今天辅助|感觉大概率挂|大概率挂|至今未回应|oc了|二面挂|估计是凉了|"
    r"现在还没有消息|反问了一下|^8\.\d+update|^面完\s*\d|^（反问环节）|^[（(]?追问了|^聊了|^问了"
)
_TRAILING_NOISE_RE = re.compile(
    r"^(?:现在还没有消息|估计是凉了|至今未|准备方向|整体体验|面试官|update|oc了|挂了|"
    r"感觉大概率|没把握|T我帮忙|捞过不少|今天辅助|笔试面试|面完\s*\d)"
)


def _is_metadata_line(text: str) -> bool:
    return bool(_METADATA_LINE_RE.match(text))


def _is_header(text: str) -> bool:
    return bool(_HEADER_LINE_RE.match(text))


def _is_noise(text: str) -> bool:
    if not text:
        return True
    if _NOISE_RE.search(text):
        return True
    # 不含问号的“面试官/体验/方向”类评论句
    if (
        "？" not in text
        and "?" not in text
        and re.search(r"面试官|面试体验|整体体验|技术落地|准备方向", text)
    ):
        return True
    return False


def _should_drop_tail(tail: str) -> bool:
    """判断问号/句号之后的尾巴是否为答案、备注或评论。"""
    if not tail:
        return False
    if _QUESTION_VERB_RE.match(tail) or _QUESTION_HINT_RE.match(tail):
        return False  # 以疑问动词/提示词开头的是追问，不是答案尾巴
    if _TRAILING_NOISE_RE.match(tail):
        return True
    if re.fullmatch(r"[（(].{1,80}[）)]", tail):  # 全括号：答案/备注
        return True
    if re.fullmatch(r"\d[\d\s\-~.,]*(?:ms|s|MB|KB|GB|K|k)?", tail):  # 纯数字/单位
        return True
    if re.match(r"^[一二三四五六七八九十]+、", tail):  # 段落小标题（二、项目深挖…）
        return True
    if len(tail) >= 12 and re.search(r"[，。；,;]", tail):
        return True
    return False


def _strip_trailing_noise(text: str) -> str:
    """把题目之后的答案尾巴、评论、状态更新截掉。"""
    for mark in ("？", "?"):
        if mark in text:
            idx = text.rfind(mark)
            tail = text[idx + 1 :].strip()
            if tail and _should_drop_tail(tail):
                return text[: idx + 1].strip()
            return text.strip()
    if "。" in text:
        idx = text.rfind("。")
        tail = text[idx + 1 :].strip()
        if tail and _should_drop_tail(tail):
            return text[: idx + 1].strip()
    return text.strip()


def _clean_question(text: str) -> str | None:
    text = text.strip().strip(" \t\u3000")
    if not text:
        return None
    text = _strip_trailing_noise(text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip("。；;，,、 ")
    if not text or _is_noise(text):
        return None
    return text


def _looks_like_prelude(text: str) -> bool:
    """编号前的引导段：像问题的短句保留（如“自我介绍”），元信息/标题丢弃。"""
    if not text:
        return False
    if any(k in text for k in ("面试问题", "面试时间", "面试岗位", "面试公司")):
        return False
    if (
        re.search(
            r"公司|面经|面试官|面试体验|技术落地|体验下来|HR环节|岗位务实|知识层|整体体验", text
        )
        and "？" not in text
        and "?" not in text
    ):
        return False
    if re.match(r"^第?[一二三四五六七八九十]+[、.．]", text):
        return False
    return True


def _looks_like_question(text: str, *, numbered: bool = False) -> bool:
    """是否像一道题。编号片段允许用内容提示词（如“原理”“机制”）兜底。"""
    if "？" in text or "?" in text:
        return True
    if _QUESTION_VERB_RE.match(text):
        return True
    if text in _QUESTION_LABEL_KEEP:
        return True
    if numbered and _QUESTION_HINT_RE.search(text):
        return True
    return False


def extract_questions(paragraphs: list[str]) -> list[str]:
    """从一份面经的段落里抽题并去噪。

    规则：
    - 含编号（1. / Q1： / 第2题）的段落按编号切分，编号片段即题目；
    - 编号前的引导段（元信息、标题、广告）丢弃；
    - 无编号的段落：只有像题目的行（带问号/疑问动词）才保留；
    - 题目尾巴里的答案、备注、状态更新（“估计是凉了”等）截掉。
    """
    questions: list[str] = []
    for para in paragraphs:
        text = para.strip()
        if not text:
            continue
        parts = _QUESTION_SPLIT_RE.split(text)
        numbered_present = any(_QUESTION_PREFIX_RE.match(p.strip()) for p in parts)
        if numbered_present:
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                numbered = bool(_QUESTION_PREFIX_RE.match(part))
                part = _QUESTION_PREFIX_RE.sub("", part).strip()
                if not part:
                    continue
                if not numbered and not _looks_like_prelude(part):
                    continue
                cleaned = _clean_question(part)
                if cleaned and _looks_like_question(cleaned, numbered=numbered):
                    questions.append(cleaned)
        else:
            if _is_metadata_line(text) or _is_header(text) or _is_noise(text):
                continue
            cleaned = _clean_question(text)
            if cleaned and _looks_like_question(cleaned):
                questions.append(cleaned)
    return questions


# ─────────────────────────── 4. 公司 / 岗位 / 日期 ──────────────────────────

_META_FIELD_RE = re.compile(
    r"^\s*[\W_]*[-•*]?\s*(?:面试)?(公司|岗位|时间|批次|轮次|形式|时长)[:：]\s*(.*)$"
)
_FIELD_CUT_RE = re.compile(r"(?:面试问题|整体|体验|流程|面试官|[，。;；])")
_DATE_PATTERNS = [
    re.compile(r"(\d{4})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})\s*[日号]?"),
    re.compile(r"(\d{2})\.(\d{1,2})\.(\d{1,2})"),
    re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]"),
]


def _truncate_field_value(val: str) -> str:
    """同一行塞了多个字段时，取到下一个字段/句子为止。"""
    m = _FIELD_CUT_RE.search(val)
    if m:
        val = val[: m.start()]
    return val.strip()


def extract_metadata_fields(paragraphs: list[str]) -> dict[str, str]:
    lines: list[str] = []
    for paragraph in paragraphs:
        lines.extend(paragraph.split("\n"))
    fields: dict[str, str] = {}
    for i, line in enumerate(lines):
        m = _META_FIELD_RE.match(line.strip())
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if not val and i + 1 < len(lines):
            # 值在下一行（如“面试公司：\n凯越集团”）
            nxt = lines[i + 1].strip()
            if nxt and not re.match(
                r"^(?:面试|##|###|\d{1,2}[.、)）:：]|第[一二三四五六七八九十]+[、.．])", nxt
            ):
                val = nxt
        if val:
            fields.setdefault(key, _truncate_field_value(val))
    return fields


def _is_plausible_company(cand: str) -> bool:
    if not cand:
        return False
    if re.search(r"面试|面经|岗位|时间|体验|整体", cand):
        return False
    if re.fullmatch(r"[\d\s.\-/]+", cand):
        return False
    return True


def extract_company(fields: dict[str, str], header: str) -> str:
    """规则提取公司名：面试公司字段 > 表头模式。"""
    if fields.get("公司"):
        return fields["公司"]
    h = header
    # 1) 日期 - 公司 - 岗位（26.7.20 - FOSHO - AI应用开发二面）
    m = re.search(r"\d{1,2}\.\d{1,2}\.\d{1,2}\s*-\s*([^-]+?)\s*-", h)
    if m:
        return m.group(1).strip()
    # 2) 面了X（面了淘天AI Agent岗位 → 淘天）
    m = re.search(r"面了\s*([^，。；;,\s]+)", h)
    if m:
        return re.sub(r"(?:AI|Agent|agent|岗位)$", "", m.group(1)).strip()
    # 3) X｜Y / X，Y（百智百慧科技｜AI 应用开发实习面经）
    m = re.match(r"^\s*([^｜|，,]+?)[｜|，,]", h)
    if m and _is_plausible_company(m.group(1)):
        return m.group(1).strip()
    # 4) X <空格> AI/Agent（百度 ai应用工程师）
    m = re.match(r"^\s*(.+?)\s+(?:AI|ai|AGENT|Agent|agent)", h)
    if m and _is_plausible_company(m.group(1)):
        return m.group(1).strip()
    # 5) X AI/Agent 无空格（腾讯ai应用开发一面）
    m = re.match(r"^\s*(.+?)(?:AI|ai|AGENT|Agent|agent)", h)
    if m and _is_plausible_company(m.group(1)):
        return m.group(1).strip()
    return ""


def extract_role(fields: dict[str, str], header: str) -> str:
    """规则提取岗位：面试岗位字段 > 表头关键词。"""
    role = fields.get("岗位", "")
    if not role:
        m = re.search(r"(?:AI|ai)\s*应用(?:开发|工程师)?(?:工程师|实习生)?", header)
        if m:
            role = m.group(0)
        elif "算法岗" in header:
            role = "算法岗"
        elif "研发实习生" in header:
            role = "研发实习生"
    role = re.sub(r"^ai(?=\s|应用)", "AI", role, flags=re.IGNORECASE)
    return re.sub(r"\s+", "", role)


def extract_date(fields: dict[str, str], header: str) -> str:
    """规则提取日期并归一化为 YYYY-MM-DD；缺年份补 DEFAULT_YEAR。"""
    haystack = f"{header}\n{fields.get('时间', '')}"
    for pat in _DATE_PATTERNS:
        m = pat.search(haystack)
        if not m:
            continue
        parts = m.groups()
        if len(parts) == 3:
            year = int(parts[0])
            if year < 100:
                year += 2000
            return f"{year:04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
        return f"{DEFAULT_YEAR:04d}-{int(parts[0]):02d}-{int(parts[1]):02d}"
    return ""


def apply_metadata(records: list[InterviewRecord]) -> None:
    """回填每份面经的公司 / 岗位 / 日期（就地修改）。"""
    for record in records:
        fields = extract_metadata_fields(record.raw_paragraphs)
        record.company = extract_company(fields, record.header)
        record.role = extract_role(fields, record.header)
        record.date = extract_date(fields, record.header)


# ─────────────────────────────── 5. 归一化去重 ──────────────────────────────


def normalize_question(question: str) -> str:
    """题目归一化：去行首编号、去空白（含全角空格）、去尾部句号。"""
    q = question.strip().replace("\u3000", " ")
    q = re.sub(r"^(?:Q\s*)?\d{1,2}\s*[.、)）:：]\s*|第\s*\d+\s*[题问]\s*", "", q)
    q = re.sub(r"\s+", " ", q)
    return q.strip("。；;，,、 ")


def dedup_key(question: str) -> str:
    """去重键：去掉标点/空白/大小写后的小写文本。"""
    return re.sub(r"[\W_]+", "", question).lower()


def dedupe_questions(questions: list[str]) -> list[str]:
    """归一化去重，保留第一次出现的顺序。"""
    seen: set[str] = set()
    result: list[str] = []
    for question in questions:
        normalized = normalize_question(question)
        key = dedup_key(normalized)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


# ─────────────────────────────── 组装 / 输出 ────────────────────────────────


def preprocess_docx(path: str | Path, *, dedup: bool = True) -> list[InterviewRecord]:
    """完整流水线：docx → 20 份面经 → 抽题去噪 → 元信息 → 去重。"""
    paragraphs = parse_docx(path)
    records = split_interviews(paragraphs)
    apply_metadata(records)
    for record in records:
        record.questions = extract_questions(record.raw_paragraphs)
    if dedup:
        for record in records:
            record.questions = dedupe_questions(record.questions)
    logger.info(
        "preprocess_docx: %d interviews, %d questions after per-interview dedup",
        len(records),
        sum(len(r.questions) for r in records),
    )
    return records


def flatten_questions(records: list[InterviewRecord], *, dedup: bool = True) -> list[str]:
    """把所有面经的题目拍平；dedup=True 时全局归一化去重。"""
    questions = [q for r in records for q in r.questions]
    return dedupe_questions(questions) if dedup else questions


def to_seed_text(records: list[InterviewRecord], *, per_interview_dedup: bool = True) -> str:
    """输出分组 seed 文本（# 注释标公司/岗位/日期），可直接喂 import_jingyan。"""
    lines: list[str] = []
    for record in records:
        meta = " | ".join(x for x in (record.company, record.role, record.date) if x)
        lines.append(f"# {record.index}. {meta}" if meta else f"# {record.index}")
        questions = dedupe_questions(record.questions) if per_interview_dedup else record.questions
        lines.extend(questions)
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv: list[str] | None = None) -> int:
    """CLI：默认打印摘要；--seed 输出归一化去重后的题目列表。"""
    import argparse

    parser = argparse.ArgumentParser(
        description="docx 面经预处理：切分 20 份 → 抽题去噪 → 元信息 → 归一化去重"
    )
    parser.add_argument(
        "docx",
        nargs="?",
        default=str(DEFAULT_DOCX),
        help="docx 路径（默认仓库根目录《面试题.docx》）",
    )
    parser.add_argument("--seed", action="store_true", help="输出可直接导入的题目列表（每行一题）")
    parser.add_argument("--no-dedup", action="store_true", help="跳过去重")
    args = parser.parse_args(argv)

    path = Path(args.docx)
    if not path.exists():
        print(f"文件不存在: {path}", file=sys.stderr)
        return 1

    records = preprocess_docx(path, dedup=not args.no_dedup)
    if args.seed:
        print("\n".join(flatten_questions(records, dedup=not args.no_dedup)))
        return 0

    raw = sum(len(r.questions) for r in records)
    unique = len(flatten_questions(records, dedup=not args.no_dedup))
    print(f"解析 {path.name}: {len(records)} 份面经, 抽题 {raw} 条, 全局去重后 {unique} 条")
    for record in records:
        meta = (
            " | ".join(x for x in (record.company, record.role, record.date) if x) or "(无元信息)"
        )
        print(f"  {record.index:>2}. {meta}  {len(record.questions)} 题")
    return 0


if __name__ == "__main__":
    sys.exit(main())
