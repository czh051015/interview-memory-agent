"""嵌入管线 —— 记忆检索仍用本地 dmeta；评分语义层可切云端 bge-m3。"""

import logging
from typing import Optional

import httpx

from src.config import (
    OLLAMA_BASE_URL,
    OLLAMA_EMBED_MODEL,
    SILICONFLOW_API_KEY,
    SILICONFLOW_BASE_URL,
    SILICONFLOW_EMBED_MODEL,
)

logger = logging.getLogger(__name__)

_OLLAMA_AVAILABLE: Optional[bool] = None


def check_ollama() -> bool:
    """检测 Ollama 是否可用。"""
    global _OLLAMA_AVAILABLE
    if _OLLAMA_AVAILABLE is not None:
        return _OLLAMA_AVAILABLE

    try:
        resp = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        _OLLAMA_AVAILABLE = resp.status_code == 200
    except Exception:
        _OLLAMA_AVAILABLE = False

    logger.info("Ollama available: %s", _OLLAMA_AVAILABLE)
    return _OLLAMA_AVAILABLE


def embed_ollama(texts: list[str], model: str = OLLAMA_EMBED_MODEL) -> list[list[float]]:
    """使用 Ollama /api/embed 批量生成嵌入向量（一次 HTTP 请求）。"""
    try:
        resp = httpx.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json={"model": model, "input": texts},
            timeout=httpx.Timeout(connect=3.0, read=60.0, write=15.0, pool=3.0),
        )
        resp.raise_for_status()
        data = resp.json()
        return data["embeddings"]
    except Exception as e:
        logger.error("Ollama batch embedding failed: %s", e)
        raise


def embed_api(texts: list[str], model: str = SILICONFLOW_EMBED_MODEL) -> list[list[float]]:
    """SiliconFlow bge-m3（OpenAI 兼容 /embeddings，批量，评分语义层云端优先）。

    超时拆 connect/read：网络黑洞时快速失败（connect 5s），让 score.embed_zh 的
    降级链（api→ollama→纯硬匹配）及时触发，不挂死整条评测链路。
    """
    if not SILICONFLOW_API_KEY:
        raise RuntimeError("SILICONFLOW_API_KEY 未配置")
    try:
        resp = httpx.post(
            f"{SILICONFLOW_BASE_URL}/embeddings",
            json={"model": model, "input": texts},
            headers={"Authorization": f"Bearer {SILICONFLOW_API_KEY}"},
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=15.0, pool=5.0),
        )
        resp.raise_for_status()
        data = resp.json()
        ordered = sorted(data.get("data", []), key=lambda x: x["index"])
        return [item["embedding"] for item in ordered]
    except Exception as e:
        logger.error("SiliconFlow embedding failed: %s", e)
        raise


def embed_texts(texts: list[str], *, batch_size: int = 32) -> list[list[float]]:
    """统一嵌入入口：Ollama 优先，失败降级为空向量。

    v1 不使用 API 嵌入作为默认——API 嵌入成本高，本地 Ollama 足够。
    如果 Ollama 不可用，返回全零向量（管道可继续运行，但检索质量受影响）。
    """
    if not texts:
        return []

    if check_ollama():
        # 批量处理
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            all_embeddings.extend(embed_ollama(batch))
        return all_embeddings
    else:
        logger.warning("Ollama not available, returning zero vectors")
        # 返回零向量作为占位符（维度 768，dmeta-embedding-zh 默认）
        return [[0.0] * 768 for _ in texts]
