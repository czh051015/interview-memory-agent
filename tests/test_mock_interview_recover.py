"""模拟面试测试：章节化写回、自动采集、断点保护往返、幂等。"""

import pytest

import run_mock_interview as mi
from src.cleaner.schema import KnowledgeItem, ItemStatus, ItemSource


@pytest.fixture
def tmp_progress(tmp_path, monkeypatch):
    """把落盘文件指到临时目录，避免污染真实 data 目录。"""
    f = tmp_path / "interview_progress.json"
    monkeypatch.setattr(mi, "_progress_file", lambda: f)
    return f


# ── 断点保护：落盘往返无损 ──
def test_progress_roundtrip(tmp_progress):
    item = KnowledgeItem(id="ki_a", question="为什么选这个模型？", status=ItemStatus.FAIL)
    questions = [
        {"question": "为什么选这个模型？", "source": "weak", "topic": "模型选型",
         "item_id": "ki_a", "section": "技术验证", "item": item},
        {"question": "讲讲你的 RAG 项目", "source": "resume", "topic": "项目深挖",
         "item_id": None, "section": "项目深挖", "item": None},
    ]
    answered = [
        {"question": "为什么选这个模型？", "source": "weak", "topic": "模型选型",
         "performance": "fail", "answer": "答得不好", "item": item},
    ]
    mi._save_progress(questions, answered, ["表达绕弯"])

    prog = mi._load_progress()
    assert prog["questions"][0]["item"].id == "ki_a"
    assert prog["questions"][0]["item"].status == ItemStatus.FAIL
    assert prog["questions"][1]["item"] is None  # 无 item 的题保持 None
    assert prog["answered"][0]["performance"] == "fail"
    assert prog["behaviors"] == ["表达绕弯"]


def test_load_missing_returns_none(tmp_progress):
    assert mi._load_progress() is None


# ── 写回：weak 题更新 mastery + 新题答差自动采集 ──
def test_write_back_weak_and_new():
    item = KnowledgeItem(id="ki_a", question="题", status=ItemStatus.FAIL, mastery_score=0.3)
    results = [
        {"question": "题", "source": "weak", "topic": "t", "performance": "pass",
         "answer": "答", "item": item},
        {"question": "新题", "source": "resume", "topic": "项目深挖",
         "performance": "fail", "answer": "没答上", "item": None},
    ]
    updated, new = mi._write_back(results, [])
    assert len(updated) == 1
    assert updated[0].mastery_score == 0.45  # 0.3 × 1.5
    assert len(new) == 1
    assert new[0].status == ItemStatus.FAIL
    assert new[0].source == ItemSource.MOCK_INTERVIEW
    assert new[0].topic == "项目深挖"


def test_write_back_pass_new_not_collected():
    """答好的新题不采集（只有 fail/partial 才进错题本）。"""
    results = [
        {"question": "新题", "source": "resume", "topic": "项目深挖",
         "performance": "pass", "answer": "答得好", "item": None},
    ]
    updated, new = mi._write_back(results, [])
    assert updated == []
    assert new == []


def test_record_result_idempotent():
    item = KnowledgeItem(id="ki_a", question="题", status=ItemStatus.FAIL, mastery_score=0.3)
    first = mi.record_result(item, "pass", [])
    second = mi.record_result(item, "pass", [])
    assert first.mastery_score == second.mastery_score
    assert first.review_count == second.review_count


# ── 读简历/JD：.md / .txt / 回退 / 容错 ──
def test_read_doc_md(tmp_path, monkeypatch):
    monkeypatch.setattr(mi, "DATA_DIR", tmp_path)
    (tmp_path / "resume.md").write_text("简历内容", encoding="utf-8")
    assert mi._read_doc("resume") == "简历内容"


def test_read_doc_txt(tmp_path, monkeypatch):
    monkeypatch.setattr(mi, "DATA_DIR", tmp_path)
    (tmp_path / "jd.txt").write_text("JD 内容", encoding="utf-8")
    assert mi._read_doc("jd") == "JD 内容"


def test_read_doc_falls_back_when_pdf_broken(tmp_path, monkeypatch):
    """有损坏 pdf 时，提取失败应回退到 md。"""
    monkeypatch.setattr(mi, "DATA_DIR", tmp_path)
    (tmp_path / "resume.pdf").write_bytes(b"not a real pdf")
    (tmp_path / "resume.md").write_text("md 内容", encoding="utf-8")
    assert mi._read_doc("resume") == "md 内容"


def test_read_doc_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(mi, "DATA_DIR", tmp_path)
    assert mi._read_doc("resume") == ""


def test_read_pdf_corrupt_returns_empty(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"this is not a pdf")
    assert mi._read_pdf_text(bad) == ""

