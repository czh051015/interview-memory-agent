"""LLM 调用封装 —— 统一 OpenAI 兼容 API（默认 DeepSeek），温度=0 保复现。

跨模型对照：judge/出题均走本模块；eval --cross-model 时传 model=CROSS_MODEL，
若配置了 CROSS_MODEL_BASE_URL/CROSS_MODEL_API_KEY 则使用独立第二供应商（真独立先验）。
"""

import itertools
import json
import logging
import re
from typing import Optional

from openai import OpenAI

from src.config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    CROSS_MODEL_BASE_URL,
    CROSS_MODEL_API_KEY,
)

logger = logging.getLogger(__name__)

_client: Optional[OpenAI] = None
_cross_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        # timeout=300s：防 DeepSeek 高峰排队时单次调用挂 10 分钟（默认 600s），
        # 失败交给 chat_json 的重试，别让一次调用拖死整个流程（docs/26 A/B 实测 10.8h）
        _client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, timeout=300.0)
    return _client


def _get_cross_client() -> OpenAI:
    """第二判官的 client：配置了独立 base_url/key 就用独立供应商，否则复用 DeepSeek。"""
    global _cross_client
    if _cross_client is None:
        if CROSS_MODEL_BASE_URL and CROSS_MODEL_API_KEY:
            _cross_client = OpenAI(api_key=CROSS_MODEL_API_KEY, base_url=CROSS_MODEL_BASE_URL)
        else:
            _cross_client = _get_client()
    return _cross_client


def chat(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str = DEEPSEEK_MODEL,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    cross: bool = False,
) -> str:
    """单轮 LLM 调用，返回文本响应。cross=True 走第二判官（跨模型对照）。"""
    client = _get_cross_client() if cross else _get_client()
    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    content = response.choices[0].message.content or ""
    usage = response.usage
    if usage:
        logger.debug(
            "LLM call: prompt=%d, completion=%d, total=%d tokens",
            usage.prompt_tokens,
            usage.completion_tokens,
            usage.total_tokens,
        )
    return content


def _repair_tail_brackets(text: str) -> str | None:
    """修复结尾闭合括号错位/缺失（实测 DeepSeek 高频瑕疵，finish_reason=stop 但 JSON 不完整）：
    - 漏 `]`：`{"verdicts": [O1, O2}}`（数组收尾丢了，外层 `}` 提前闭合）
    - 顺序错：`{"verdicts": [O1, O2}}]`（`]` 跑到了外层 `}` 之后）
    做法：取文本末尾连续的 `]`/`}` 串，穷举重排 + 按括号赤字插入补全；只有补全后能整体
    解析才接受（内部损坏的 JSON 救不回来，不会误修出"合法但错误"的结果）。
    赤字封顶 3、尾串封顶 6：文本内容里夹的 `[`/`{` 会虚增计数，真缺的只有几个。
    """
    cut = len(text)
    while cut > 0 and text[cut - 1] in "]}":
        cut -= 1
    tail = text[cut:]
    db = min(text.count("[") - text.count("]"), 3)
    dc = min(text.count("{") - text.count("}"), 3)
    if db < 0 or dc < 0 or len(tail) > 6:
        return None
    candidates: set[str] = set()
    for perm in itertools.permutations(tail):           # 重排（`}}]` → `}]}`）
        candidates.add("".join(perm))
    for i in range(len(tail) + 1):                      # 按赤字插补（`}}` → `}]}`）
        for nb in range(db + 1):
            for nc in range(dc + 1):
                if nb or nc:
                    candidates.add(tail[:i] + "]" * nb + "}" * nc + tail[i:])
    for cand in candidates:
        try:
            return json.loads(text[:cut] + cand)
        except json.JSONDecodeError:
            continue
    return None


def _parse_json_lenient(text: str) -> dict:
    """宽松 JSON 解析（严格 loads 失败后的兜底，docs/26 A/B 实测 DeepSeek 偶发瑕疵）：
    1. 去尾逗号（`,}` `,]`）
    2. 键/值单引号 → 双引号（`'key':`、`: 'value'`，成对替换，不碰内容）
    3. 结尾闭合括号错位/缺失 → 补全修复（见 _repair_tail_brackets）
    4. 仍失败则抛 JSONDecodeError（交给调用方 retry/降级）
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    text2 = re.sub(r",(\s*[}\]])", r"\1", text)  # 尾逗号
    try:
        return json.loads(text2)
    except json.JSONDecodeError:
        pass
    text3 = re.sub(r"'([^'\"]*?)'(\s*:)", r'"\1"\2', text2)   # 键的单引号
    text3 = re.sub(r":\s*'([^'\"]*?)'", r':"\1"', text3)      # 值的单引号
    try:
        return json.loads(text3)
    except json.JSONDecodeError:
        pass
    repaired = _repair_tail_brackets(text3)
    if repaired is not None:
        return repaired
    return json.loads(text3)  # 救不回来：原样严格解析，抛原始 JSONDecodeError 交给调用方


def chat_json(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str = DEEPSEEK_MODEL,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    retries: int = 2,
    cross: bool = False,
) -> dict:
    """单轮 LLM 调用，解析并返回 JSON。严格解析失败 → 宽松兜底；再失败重试。cross=True 走第二判官。"""
    last_error = None
    for attempt in range(retries):
        try:
            text = chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                cross=cross,
            )
            # 尝试提取 JSON（处理 markdown code block 包裹的情况）
            text = text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                # 去掉 ```json 和 结尾的 ```
                lines = [l for l in lines if not l.startswith("```")]
                text = "\n".join(lines)
            return _parse_json_lenient(text)
        except (json.JSONDecodeError, Exception) as e:
            last_error = e
            logger.warning("LLM JSON parse failed (attempt %d/%d): %s", attempt + 1, retries, e)

    raise ValueError(f"LLM JSON parse failed after {retries} retries: {last_error}")
