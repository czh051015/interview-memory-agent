"""全局配置，从环境变量加载。"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── 项目路径 ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CHROMA_DIR = Path(os.getenv("CHROMA_PERSIST_DIR", DATA_DIR / "chroma"))
RUN_DIR = Path(os.getenv("RUN_DATA_DIR", DATA_DIR / "runs"))
SEED_DIR = DATA_DIR / "seed"

# ── 空间（space）：独立记忆命名空间，多用户/多用途隔离 ──
# 每个空间一份独立的错题本 + 掌握度 + 复盘 + 行为特征。
# 默认 "default"（向后兼容存量数据）；用 `--space 名字` 或环境变量 OFFERLOOP_SPACE 切换。
SPACE = os.getenv("OFFERLOOP_SPACE", "default")


def space_dir(space: str | None = None) -> Path:
    """当前空间的数据目录（session/面试进度/复盘等临时文件）。

    传 space 则用指定值，不传则用全局 SPACE（向后兼容）。
    """
    name = space if space is not None else SPACE
    d = DATA_DIR / "spaces" / name
    d.mkdir(parents=True, exist_ok=True)
    return d

# ── DeepSeek API ──
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# ── 跨模型对照（L3 eval --cross-model 的第二判官）──
# 默认 deepseek-reasoner：同 key 零成本、不同推理路径（CoT），打破「同模型自洽」
# 可换任意第二家 OpenAI 兼容 API：CROSS_MODEL_BASE_URL/CROSS_MODEL_API_KEY 覆盖后即用独立供应商
CROSS_MODEL = os.getenv("CROSS_MODEL", "deepseek-reasoner")
CROSS_MODEL_BASE_URL = os.getenv("CROSS_MODEL_BASE_URL", "")  # 空 = 复用 DeepSeek endpoint
CROSS_MODEL_API_KEY = os.getenv("CROSS_MODEL_API_KEY", "")    # 空 = 复用 DeepSeek key

# ── Ollama (本地嵌入，记忆检索保留本地，评分语义层可切云端) ──
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "shaw/dmeta-embedding-zh:latest")

# ── SiliconFlow (云端 embedding，评分语义层默认走 api) ──
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
SILICONFLOW_EMBED_MODEL = os.getenv("SILICONFLOW_EMBED_MODEL", "BAAI/bge-m3")
SCORE_EMBED_BACKEND = os.getenv("SCORE_EMBED_BACKEND", "api")  # api | ollama

# ── 评分引擎选型（docs/26 A/B 对比，docs/31 切换默认）──
# llm = LLM-as-a-Judge（judge_score，单次约 10s，1 次 LLM 调用）
# kw  = 确定性两阶段（score_answer，0 token 秒级，兜底/离线）
SCORE_ENGINE = os.getenv("SCORE_ENGINE", "llm")  # llm | kw

# ── 评分语义匹配层（docs/25 §4 + 26 §7）：阶段2 语义命中阈值 τ ──
# 关键词硬匹配未中的采分点，与作答分句的 max cosine ≥ τ 即判命中（semantic hit）。
# 校准值 τ=0.734（eval/calibrate_tau.py）：确定性引擎（引擎A）基线档——fuzzy 漏判率
#   75%→57%（-18pp），no_fool 红线余量 0.026（稳健），discrimination 0.864（-3.5pp）。
#   doc 26 §8：dmeta 把套话 bad 簇与真改写簇压进同一相似度区间，40% 目标不可达是
#   数据事实；τ=0.734 是折中档，引擎选型由 docs/26 A/B 对比（vs LLM-as-a-Judge）决定。
def _env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    try:
        return float(v) if v is not None else default
    except ValueError:
        return default


SCORE_SEMANTIC_TAU = _env_float("SCORE_SEMANTIC_TAU", 0.734)

# ── 管道配置 ──
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ── 偏移检测阈值 (v1 硬编码) ──
SURGE_THRESHOLD = 1.20       # 增幅 > 20%
EMERGING_MIN_COUNT = 3       # 新簇至少 3 条才报
DECAY_THRESHOLD = 0.70       # 降幅 > 30%（v2 启用）

# ── 简报 ──
BRIEFING_VALIDITY_DAYS = 30  # 默认有效期

# ── 预算 (¥50/月软上限) ──
MONTHLY_BUDGET_YUAN = 50.0
DEEPSEEK_COST_PER_1K_TOKENS = 0.001  # ¥0.001 / 1K tokens (大致)
