"""src.llm 的 JSON 解析单测 —— 宽松解析兜底（docs/26 A/B 实测 DeepSeek 偶发尾逗号/单引号）。

不调真实 LLM：直接测 _parse_json_lenient 的容错，以及 chat_json 在 chat 返回瑕疵 JSON 时的行为。
"""
import json
from unittest.mock import patch

import pytest

from src.llm import _parse_json_lenient, chat_json


# ── 宽松解析兜底 ────────────────────────────────────────────────

def test_lenient_normal_json():
    assert _parse_json_lenient('{"a": 1}') == {"a": 1}


def test_lenient_trailing_comma():
    """尾逗号（DeepSeek 实测高频瑕疵）→ 兜底成功。"""
    text = '{"verdicts": [{"point_id": "c1", "verdict": "hit",},],}'
    assert _parse_json_lenient(text) == {"verdicts": [{"point_id": "c1", "verdict": "hit"}]}


def test_lenient_single_quote_keys_values():
    """单引号键/值（如 'point_id': 'c1'）→ 兜底成功，中文内容不受影响。"""
    text = "{'point_id': 'c1', 'cause': '写模糊'}"
    assert _parse_json_lenient(text) == {"point_id": "c1", "cause": "写模糊"}


def test_lenient_missing_closing_bracket():
    """结尾缺 `]`（DeepSeek 实测高频：finish_reason=stop 但漏数组收尾，如 `[...}]}`）→ 补全成功。"""
    text = '{"verdicts": [{"point_id": "c1", "verdict": "hit"}}'
    assert _parse_json_lenient(text) == {"verdicts": [{"point_id": "c1", "verdict": "hit"}]}


def test_lenient_missing_closing_brace():
    """结尾缺 `}`（漏外层的对象收尾）→ 补全成功。"""
    text = '{"verdicts": [{"point_id": "c1"}]'
    assert _parse_json_lenient(text) == {"verdicts": [{"point_id": "c1"}]}


def test_lenient_closers_wrong_order():
    """闭合符顺序错位（实测样本：`[...}}]` 应为 `[...}]}`，`]` 跑到了外层 `}` 后）→ 重排修复。"""
    text = '{"verdicts": [{"point_id": "c1", "verdict": "hit"}}]'
    assert _parse_json_lenient(text) == {"verdicts": [{"point_id": "c1", "verdict": "hit"}]}


def test_lenient_broken_internal_still_raises():
    """内部损坏（缺逗号）→ 补括号救不了，仍抛 JSONDecodeError（不误修成错误结果）。"""
    with pytest.raises(json.JSONDecodeError):
        _parse_json_lenient('{"a": 1 "b": 2')


def test_lenient_still_raises_on_garbage():
    """完全不可解析 → 抛 JSONDecodeError（交给调用方 retry/降级）。"""
    with pytest.raises(json.JSONDecodeError):
        _parse_json_lenient("完全不是 JSON")


# ── chat_json 集成：瑕疵 JSON 不再浪费重试 ────────────────────────

def test_chat_json_uses_lenient_fallback():
    """chat 返回尾逗号 JSON → 一次成功，不触发重试。"""
    raw = '{"ok": [1, 2,],}'
    with patch("src.llm.chat", return_value=raw) as m:
        assert chat_json("s", "u") == {"ok": [1, 2]}
    m.assert_called_once()  # 无重试


def test_chat_json_garbage_retries_then_raises():
    """不可解析 → 重试 retries 次后抛 ValueError（调用方降级）。"""
    with patch("src.llm.chat", return_value="垃圾"):
        with pytest.raises(ValueError, match="after 2 retries"):
            chat_json("s", "u", retries=2)
