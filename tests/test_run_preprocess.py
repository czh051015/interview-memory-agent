# -*- coding: utf-8 -*-
"""run_preprocess CLI 测试：参数解析、摘要/seed、导入（mock LLM/存储）。"""

from pathlib import Path

import pytest

import run_preprocess as rp
from src.market import jingyan as jingyan_mod
from src.market import jingyan_preprocess as preprocess_mod

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_DOCX = REPO_ROOT / "面试题.docx"


def make_records():
    return [
        preprocess_mod.InterviewRecord(
            index=1,
            header="甲公司面经",
            company="甲公司",
            role="AI应用开发",
            date="2026-07-01",
            questions=["题一", "题二", "题一"],
        ),
        preprocess_mod.InterviewRecord(
            index=2,
            header="乙公司面经",
            company="乙公司",
            role="",
            date="",
            questions=["题三"],
        ),
    ]


# ── _flatten_with_meta：拍平 + item_meta 对齐 ──


def test_flatten_with_meta_dedup():
    pairs = rp._flatten_with_meta(make_records(), dedup=True)
    assert [q for q, _ in pairs] == ["题一", "题二", "题三"]  # 全局去重
    assert pairs[0][1] == {"company": "甲公司", "role": "AI应用开发", "date": "2026-07-01"}
    assert pairs[2][1] == {"company": "乙公司", "role": "", "date": ""}


def test_flatten_with_meta_no_dedup():
    pairs = rp._flatten_with_meta(make_records(), dedup=False)
    assert len(pairs) == 4  # 重复的“题一”保留


# ── cmd_*：摘要 / seed / 导入 ──


def test_cmd_summary(capsys):
    rc = rp.cmd_summary(make_records(), Path("t.docx"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "2 份面经" in out
    assert "甲公司 | AI应用开发 | 2026-07-01" in out


def test_cmd_seed(capsys):
    rc = rp.cmd_seed(make_records(), dedup=True)
    lines = capsys.readouterr().out.strip().splitlines()
    assert rc == 0
    assert lines == ["题一", "题二", "题三"]


def test_cmd_import_mocked(monkeypatch, capsys):
    """cmd_import：mock LLM 提 topic 与存储，验证 item_meta 回填 + 去重。"""
    monkeypatch.setattr(jingyan_mod, "chat_json", lambda **kw: {"topics": []})
    stored = []
    monkeypatch.setattr(rp.store, "store_items", lambda items: stored.extend(items))

    rc = rp.cmd_import(make_records(), dedup=True, limit=None)
    out = capsys.readouterr().out

    assert rc == 0
    assert len(stored) == 3  # “题一”重复被去重
    assert stored[0].company == "甲公司"
    assert stored[0].date == "2026-07-01"
    assert stored[2].company == "乙公司"
    assert stored[2].source.value == "public_jingyan"
    assert "入库 3 条" in out


# ── main：参数解析 ──


def test_main_help():
    assert rp.main(["--help"]) == 0


def test_main_unknown_flag():
    assert rp.main(["--bogus"]) == 1


def test_main_extra_positional():
    assert rp.main(["a.docx", "b.docx"]) == 1


def test_main_missing_file():
    assert rp.main(["no_such_file.docx"]) == 1


@pytest.mark.skipif(not REAL_DOCX.exists(), reason="仓库根目录没有《面试题.docx》")
def test_main_summary_default_docx(capsys):
    rc = rp.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "20 份面经" in out


@pytest.mark.skipif(not REAL_DOCX.exists(), reason="仓库根目录没有《面试题.docx》")
def test_main_seed_real_docx(capsys):
    rc = rp.main(["--seed"])
    lines = capsys.readouterr().out.strip().splitlines()
    assert rc == 0
    assert len(lines) > 300  # 全部题目，全局去重后
    assert lines[0] == "请用两分钟介绍一下自己"


@pytest.mark.skipif(not REAL_DOCX.exists(), reason="仓库根目录没有《面试题.docx》")
def test_main_import_real_docx(monkeypatch):
    """端到端 --import：真实 docx 预处理，mock LLM 提 topic 与存储。"""
    monkeypatch.setattr(jingyan_mod, "chat_json", lambda **kw: {"topics": []})
    stored = []
    monkeypatch.setattr(rp.store, "store_items", lambda items: stored.extend(items))

    rc = rp.main(["--import", "--limit", "5"])
    assert rc == 0
    assert len(stored) > 200
    assert stored[0].company == "FOSHO"
    assert stored[0].date == "2026-07-20"
    assert all(i.company == "FOSHO" for i in stored[:21])  # 第一份面经 21 题
    assert stored[21].company == ""  # 第二份面经无公司名
