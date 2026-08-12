"""JD 导入器测试。"""

from unittest.mock import patch

import pytest

from src.cleaner.schema import ItemStatus, ItemCategory, ItemSource
from src.market.jd import extract_jd_keywords, import_jd, jd_files_from

JD_TEXT = "字节跳动 AI应用开发 JD 正文，要求熟悉 RAG、Agent 开发"


class TestExtractJdKeywords:
    @patch("src.market.jd.chat_json")
    def test_extract(self, mock_chat):
        mock_chat.return_value = {"company": "字节跳动", "keywords": ["RAG", "Agent"]}
        result = extract_jd_keywords(JD_TEXT)
        assert result == {"company": "字节跳动", "keywords": ["RAG", "Agent"]}

    @patch("src.market.jd.chat_json")
    def test_company_falls_back_to_hint(self, mock_chat):
        mock_chat.return_value = {"company": "", "keywords": ["RAG"]}
        result = extract_jd_keywords(JD_TEXT, company_hint="字节")
        assert result["company"] == "字节"

    @patch("src.market.jd.chat_json")
    def test_llm_failure_raises(self, mock_chat):
        """JD 导入的价值全在提取，失败要响亮（不静默降级）。"""
        mock_chat.side_effect = ValueError("LLM down")
        with pytest.raises(ValueError):
            extract_jd_keywords(JD_TEXT)

    @patch("src.market.jd.chat_json")
    def test_empty_keywords_raises(self, mock_chat):
        mock_chat.return_value = {"company": "字节", "keywords": []}
        with pytest.raises(ValueError):
            extract_jd_keywords(JD_TEXT)


class TestImportJd:
    @patch("src.market.jd.chat_json")
    def test_keyword_mapping(self, mock_chat):
        mock_chat.return_value = {"company": "字节跳动", "keywords": ["RAG", "Agent编排"]}
        items = import_jd(JD_TEXT)

        assert len(items) == 2
        for item in items:
            assert item.question == item.topic  # topic 是交叉验证匹配键
            assert item.source == ItemSource.JD
            assert item.status == ItemStatus.UNKNOWN
            assert item.category == ItemCategory.KNOWLEDGE
            assert item.company == "字节跳动"
            assert item.id.startswith("jd_")

    @patch("src.market.jd.chat_json")
    def test_idempotent_ids(self, mock_chat):
        mock_chat.return_value = {"company": "字节", "keywords": ["RAG"]}
        ids1 = {i.id for i in import_jd(JD_TEXT)}
        ids2 = {i.id for i in import_jd(JD_TEXT)}
        assert ids1 == ids2


class TestJdFilesFrom:
    def test_single_file(self, tmp_path):
        f = tmp_path / "jd.txt"
        f.write_text("x", encoding="utf-8")
        assert jd_files_from(f) == [f]

    def test_directory_globs_txt(self, tmp_path):
        (tmp_path / "a.txt").write_text("x", encoding="utf-8")
        (tmp_path / "b.txt").write_text("x", encoding="utf-8")
        (tmp_path / "c.md").write_text("x", encoding="utf-8")
        result = jd_files_from(tmp_path)
        assert [p.name for p in result] == ["a.txt", "b.txt"]
