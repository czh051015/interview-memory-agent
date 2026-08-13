# -*- coding: utf-8 -*-
"""jingyan_preprocess 测试：docx 解析 / 20 份切分 / 抽题去噪 / 元信息 / 归一化去重。"""

import zipfile
import xml.sax.saxutils as sax
from pathlib import Path

import pytest

from src.market.jingyan_preprocess import (
    DEFAULT_YEAR,
    InterviewRecord,
    dedupe_questions,
    extract_company,
    extract_date,
    extract_metadata_fields,
    extract_questions,
    extract_role,
    flatten_questions,
    normalize_question,
    parse_docx,
    preprocess_docx,
    split_interviews,
    to_seed_text,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_DOCX = REPO_ROOT / "面试题.docx"


def make_docx(path: Path, paragraphs: list[str]) -> Path:
    """用标准库生成一个最小可用 docx（不依赖 python-docx）。"""
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )
    body = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{sax.escape(p)}</w:t></w:r></w:p>' for p in paragraphs
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}<w:sectPr/></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document)
    return path


# ── 1. docx 解析 ──


def test_parse_docx_roundtrip(tmp_path):
    paras = ["1 甲公司面经", "一、自我介绍", "1. 请介绍一下自己。", ""]
    path = make_docx(tmp_path / "t.docx", paras)
    assert parse_docx(path) == paras


# ── 2. 20 份面经切分 ──


def test_split_interviews_sequential():
    paras = [
        "1 甲公司面经",
        "问题一",
        "2 乙公司面经",
        "问题二",
        "3 丙公司面经",
        "问题三",
    ]
    records = split_interviews(paras)
    assert [r.index for r in records] == [1, 2, 3]
    assert records[0].header == "甲公司面经"
    assert records[1].header == "乙公司面经"
    assert [r.raw_paragraphs for r in records] == [
        ["甲公司面经", "问题一"],
        ["乙公司面经", "问题二"],
        ["丙公司面经", "问题三"],
    ]


def test_split_interviews_ignores_stray_numbers():
    """正文里的“5 档价位”不应被当成第 3 份面经（编号不连续）。"""
    paras = ["1 甲公司", "A", "5 不是编号", "B"]
    records = split_interviews(paras)
    assert len(records) == 1
    assert records[0].raw_paragraphs == ["甲公司", "A", "5 不是编号", "B"]


def test_split_interviews_truncates_dense_header():
    """长段面经 header 截断到面试问题为止，raw_paragraphs 保留全文。"""
    paras = [
        "1 甲公司面经",
        "2 面试时间：8月6号面试岗位：AI应用开发面试问题：1.自我介绍2.为什么选AI？",
    ]
    records = split_interviews(paras)
    assert records[1].header == "面试时间：8月6号面试岗位：AI应用开发"
    assert "1.自我介绍" in records[1].raw_paragraphs[0]


# ── 3. 抽题 / 去噪 ──


def test_extract_questions_numbered_dense():
    paras = [
        "面试时间：8月6号面试岗位：AI应用开发整体体验不错面试问题："
        "1.自我介绍2.为什么选择 AI 应用开发方向？3.项目相关介绍4.如何设计 Tool 的 Schema？"
        "准备方向还是要更加贴近实际项目"
    ]
    assert extract_questions(paras) == [
        "自我介绍",
        "为什么选择 AI 应用开发方向？",
        "项目相关介绍",
        "如何设计 Tool 的 Schema？",
    ]


def test_extract_questions_q_style_and_section_tails():
    paras = [
        "一、架构对比Q1： 对比两个框架有什么区别？为什么场景不同设计不同？"
        "二、项目深挖Q2： 你的 Skill 是怎么设计的？（追问了三轮，从原理到细节）"
    ]
    assert extract_questions(paras) == [
        "对比两个框架有什么区别？为什么场景不同设计不同？",
        "你的 Skill 是怎么设计的？",
    ]


def test_extract_questions_skips_noise():
    paras = [
        "# 注释",
        "面试公司：甲公司",
        "## 面试流程",
        "面试官最后评价感觉大概率挂",
        "8.9update，至今未回应",
        "笔试面试 没把握的可以T我帮忙",
        "一、自我介绍",
        "14.反问",
        "1. 请用两分钟介绍一下自己。",
        "上下文压缩",
        "项目一（合作多agent项目）",
        "RAG全流程：chunk → embedding → 重排序 → LLM生成",
        "你实习批量导入流程说一下",
    ]
    assert extract_questions(paras) == [
        "请用两分钟介绍一下自己",
        "你实习批量导入流程说一下",
    ]


def test_extract_questions_bare_question_paragraphs():
    paras = [
        "请具体介绍 Agent 项目，哪一块最复杂？你是怎么解决的？",
        "查课表是否需要对接校内接口？",
        "做了什么",  # “做了”在疑问动词前缀里 → 保留（项目子问题）
        "简单讲下 Transformer 底层原理？",
        "点评项目",  # 标题
    ]
    assert extract_questions(paras) == [
        "请具体介绍 Agent 项目，哪一块最复杂？你是怎么解决的？",
        "查课表是否需要对接校内接口？",
        "做了什么",
        "简单讲下 Transformer 底层原理？",
    ]


def test_extract_questions_keeps_followup_question_tail():
    paras = ["1. 是否了解过 LangChain、n8n 等行业产品？简单讲讲LangChain 的特点。"]
    assert extract_questions(paras) == [
        "是否了解过 LangChain、n8n 等行业产品？简单讲讲LangChain 的特点"
    ]


# ── 4. 公司 / 岗位 / 日期 ──


def test_extract_company_variants():
    cases = [
        ({"公司": "百智百慧科技"}, "百智百慧科技｜AI 应用开发实习面经", "百智百慧科技"),
        ({}, "26.7.20 - FOSHO - AI应用开发二面，30min", "FOSHO"),
        ({}, "面了淘天AI Agent岗位，知识层有RAG", "淘天"),
        ({}, "百度 ai应用工程师 社招 一面面经", "百度"),
        ({}, "腾讯ai应用开发一面", "腾讯"),
        ({}, "镜玩科技有限公司，ai应用开发", "镜玩科技有限公司"),
        ({}, "追觅科技 AI 应用开发三轮面", "追觅科技"),
        ({}, "面试时间：8月6号面试岗位：AI应用开发", ""),
    ]
    for fields, header, expected in cases:
        assert extract_company(fields, header) == expected, header


def test_extract_role_variants():
    assert (
        extract_role({"岗位": "研发实习生（AI 应用开发方向）"}, "x")
        == "研发实习生（AI应用开发方向）"
    )
    assert extract_role({}, "腾讯ai应用开发一面") == "AI应用开发"
    assert extract_role({}, "百度 ai应用工程师 社招") == "AI应用工程师"
    assert extract_role({}, "淘宝闪购ai研究算法岗面经") == "算法岗"


def test_extract_date_variants():
    cases = [
        ({}, "26.7.20 - FOSHO - AI应用开发二面", "2026-07-20"),
        ({"时间": "2026.7.16"}, "面试公司：凯越集团", "2026-07-16"),
        ({"时间": "2026 年 7 月 17 日"}, "百智百慧科技面经", "2026-07-17"),
        ({}, "面试时间：8月6号面试岗位：AI应用开发", f"{DEFAULT_YEAR}-08-06"),
        ({}, "面试时间：7月25号", f"{DEFAULT_YEAR}-07-25"),
        ({}, "字节agent应用开发二面", ""),
    ]
    for fields, header, expected in cases:
        assert extract_date(fields, header) == expected, header


def test_extract_metadata_fields_next_line():
    fields = extract_metadata_fields(
        ["面试公司：", "凯越集团", "🕐面试时间：", "2026.7.16", "面试岗位：", "AI应用开发工程师"]
    )
    assert fields["公司"] == "凯越集团"
    assert fields["时间"] == "2026.7.16"
    assert fields["岗位"] == "AI应用开发工程师"


# ── 5. 归一化去重 ──


def test_normalize_question():
    assert normalize_question("  RAG 项目怎么切分？  ") == "RAG 项目怎么切分？"
    assert normalize_question("问题。") == "问题"


def test_dedupe_questions():
    questions = [
        "1. Agent项目是否上线部署？",
        "Agent 项目是否上线部署？",
        "RAG项目的分块策略有哪些？",
        "7.RAG项目的分块策略有哪些？",
    ]
    assert dedupe_questions(questions) == [
        "Agent项目是否上线部署？",
        "RAG项目的分块策略有哪些？",
    ]


def test_flatten_and_seed_text():
    records = [
        InterviewRecord(
            index=1,
            header="h1",
            company="甲公司",
            role="AI应用开发",
            date="2026-07-01",
            questions=["题一", "题一", "题二"],
        ),
    ]
    assert flatten_questions(records) == ["题一", "题二"]
    assert "甲公司 | AI应用开发 | 2026-07-01" in to_seed_text(records)


# ── 6. 真实 docx 集成（验收：20 份面经）──


@pytest.mark.skipif(not REAL_DOCX.exists(), reason="仓库根目录没有《面试题.docx》")
def test_real_docx_preprocess():
    records = preprocess_docx(REAL_DOCX)
    assert len(records) == 20
    assert all(r.questions for r in records)  # 每份至少 1 题

    by_index = {r.index: r for r in records}
    assert by_index[1].company == "FOSHO"
    assert by_index[1].date == "2026-07-20"
    assert by_index[8].company == "腾讯"
    assert by_index[13].company == "百度"
    assert by_index[11].company == "淘天"
    assert by_index[2].date == "2026-08-06"
    assert by_index[16].company == ""

    all_q = flatten_questions(records)
    raw = sum(len(r.questions) for r in records)
    assert len(all_q) < raw  # 全局去重确实生效（淘宝闪购两份面经重复）
    assert all(q.strip() for q in all_q)
    # 广告/评论没有混进题目
    assert not any("T我帮忙" in q or "捞过不少人" in q or "估计是凉了" in q for q in all_q)
