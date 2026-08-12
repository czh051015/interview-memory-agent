"""LLM 调用封装 —— 统一 DeepSeek API（兼容 OpenAI SDK）调用，温度=0 保复现。"""

import json
import logging
from typing import Optional

from openai import OpenAI

from src.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

logger = logging.getLogger(__name__)

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    return _client


def chat(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str = DEEPSEEK_MODEL,
    temperature: float = 0.0,
    max_tokens: int = 1024,
) -> str:
    """单轮 LLM 调用，返回文本响应。"""
    client = _get_client()
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


def chat_json(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str = DEEPSEEK_MODEL,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    retries: int = 2,
) -> dict:
    """单轮 LLM 调用，解析并返回 JSON。失败时重试。"""
    last_error = None
    for attempt in range(retries):
        try:
            text = chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            # 尝试提取 JSON（处理 markdown code block 包裹的情况）
            text = text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                # 去掉 ```json 和 结尾的 ```
                lines = [l for l in lines if not l.startswith("```")]
                text = "\n".join(lines)
            return json.loads(text)
        except (json.JSONDecodeError, Exception) as e:
            last_error = e
            logger.warning("LLM JSON parse failed (attempt %d/%d): %s", attempt + 1, retries, e)

    raise ValueError(f"LLM JSON parse failed after {retries} retries: {last_error}")
