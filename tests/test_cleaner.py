"""Cleaner Agent 单元测试。"""

import pytest
from datetime import datetime
from unittest.mock import patch

from src.models import RawFeedback, FeedbackSource, CleanedFeedback, QualityReport
from src.cleaner.legacy.normalizer import normalize_text, generate_dedup_hash, normalize_whitespace
from src.cleaner.legacy.pii import regex_scan, mask_text
from src.cleaner.legacy.pipeline import clean_single


class TestNormalizer:
    """标准化器测试。"""

    def test_normalize_chinese_date(self):
        text = "2025年12月3日在腾讯面试"
        result = normalize_text(text)
        assert "2025-12-03" in result

    def test_normalize_slash_date(self):
        text = "2025/12/03 面试"
        result = normalize_text(text)
        assert "2025-12-03" in result

    def test_normalize_whitespace(self):
        text = "  腾讯  面试  问了  RAG  "
        result = normalize_whitespace(text)
        assert result == "腾讯 面试 问了 RAG"

    def test_generate_dedup_hash_stable(self):
        """相同输入应生成相同 hash。"""
        h1 = generate_dedup_hash("腾讯面试RAG", FeedbackSource.OTHER_JINGYAN)
        h2 = generate_dedup_hash("腾讯面试RAG", FeedbackSource.OTHER_JINGYAN)
        assert h1 == h2

    def test_generate_dedup_hash_different_source(self):
        """不同 source 应生成不同 hash。"""
        h1 = generate_dedup_hash("腾讯面试RAG", FeedbackSource.SELF_REVIEW)
        h2 = generate_dedup_hash("腾讯面试RAG", FeedbackSource.OTHER_JINGYAN)
        assert h1 != h2


class TestPII:
    """PII 检测与脱敏测试。"""

    def test_regex_phone_detection(self):
        entries = regex_scan("联系13812345678")
        assert len(entries) == 1
        assert entries[0]["type"] == "phone"
        assert entries[0]["value"] == "13812345678"

    def test_regex_email_detection(self):
        entries = regex_scan("邮箱test@example.com联系")
        assert len(entries) == 1
        assert entries[0]["type"] == "email"

    def test_regex_multiple_matches(self):
        entries = regex_scan("13800001111和13900002222")
        assert len(entries) == 2

    def test_regex_no_match(self):
        entries = regex_scan("今天面试问了RAG项目")
        assert len(entries) == 0

    def test_mask_phone(self):
        entries = [{"type": "phone", "value": "13812345678", "start": 0, "end": 11}]
        result = mask_text("13812345678联系", entries)
        assert "13812345678" not in result
        assert "****" in result

    def test_mask_email(self):
        entries = [{"type": "email", "value": "test@example.com", "start": 0, "end": 16}]
        result = mask_text("test@example.com联系", entries)
        assert "test@example.com" not in result
        assert "***@" in result

    def test_mask_name(self):
        entries = [{"type": "name", "value": "张三", "start": 0, "end": 2}]
        result = mask_text("张三在腾讯面试", entries)
        assert "张三" not in result


class TestCleanerPipeline:
    """Cleaner 主管线测试。"""

    def test_clean_single_no_duplicate(self):
        raw = RawFeedback(
            id="raw_001",
            raw_text="腾讯AI岗面试问到了RAG项目",
            source=FeedbackSource.OTHER_JINGYAN,
        )
        result = clean_single(raw, [], set())
        assert result.id == "clean_001"
        assert result.is_duplicate is False
        assert result.normalized_text is not None
        assert len(result.dedup_hash) > 0

    @patch("src.cleaner.legacy.dedup.llm_dedup_check")
    def test_clean_single_hash_detected(self, mock_llm):
        """Hash 碰撞时触发 LLM 精判。"""
        # Mock LLM 返回 duplicate
        mock_llm.return_value = (True, "内容完全相同")

        raw1 = RawFeedback(
            id="raw_001",
            raw_text="腾讯AI岗面试问到了RAG项目",
            source=FeedbackSource.OTHER_JINGYAN,
        )
        existing = clean_single(raw1, [], set())

        raw2 = RawFeedback(
            id="raw_002",
            raw_text="腾讯AI岗面试问到了RAG项目",  # 完全相同
            source=FeedbackSource.OTHER_JINGYAN,
        )
        result = clean_single(raw2, [existing], {existing.dedup_hash})

        # Hash 碰撞后 LLM 精判应返回 duplicate
        assert result.is_duplicate is True
        assert result.dup_of is not None
        assert result.quality.dedup_stage == "llm"

    def test_quality_report_fields(self):
        raw = RawFeedback(
            id="raw_001",
            raw_text="今天面试问了Agent框架",
            source=FeedbackSource.OTHER_JINGYAN,
        )
        # 测试带 PII 的
        raw2 = RawFeedback(
            id="raw_002",
            raw_text="联系13812345678张三",
            source=FeedbackSource.SELF_REVIEW,
        )
        result = clean_single(raw2, [], set())
        assert result.quality.pii_stage in ("regex_only", "regex+llm")
