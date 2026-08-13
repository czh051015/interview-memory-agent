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

# ── DeepSeek API ──
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# ── Ollama (本地嵌入) ──
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "shaw/dmeta-embedding-zh:latest")

# ── 管道配置 ──
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ── 偏移检测阈值 (v1 硬编码) ──
SURGE_THRESHOLD = 1.20       # 增幅 > 20%
EMERGING_MIN_COUNT = 3       # 新簇至少 3 条才报
DECAY_THRESHOLD = 0.70       # 降幅 > 30%（v2 启用）

# ── 交叉验证 (v1.5) ──
# 题库 topic 出现 ≥N 次视为高频（2026-08-13 校准：池子 ~370 条，2→5 收紧区分度；env 可覆盖）
HIGH_FREQ_MIN_COUNT = int(os.getenv("HIGH_FREQ_MIN_COUNT", "5"))

# ── 简报 ──
BRIEFING_VALIDITY_DAYS = 30  # 默认有效期

# ── 预算 (¥50/月软上限) ──
MONTHLY_BUDGET_YUAN = 50.0
DEEPSEEK_COST_PER_1K_TOKENS = 0.001  # ¥0.001 / 1K tokens (大致)
