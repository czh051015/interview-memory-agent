"""CLI 直跑入口：python -m src.mock [--space X] [--recover]。

--space   记忆空间（活引用改 _cfg.SPACE）
--recover 有未完成练习直接续练，不询问（docs/18 断点续练语义）
"""

import sys
from pathlib import Path

# 任意 cwd 下 `python -m src.mock` 也能 import src.*（同原壳的路径引导）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import src.config as _cfg  # --space 在 __main__ 里改 _cfg.SPACE（活引用）
from src.mock import main


if __name__ == "__main__":
    if "--space" in sys.argv:
        idx = sys.argv.index("--space") + 1
        if idx < len(sys.argv):
            _cfg.SPACE = sys.argv[idx]
    if "--recover" in sys.argv:
        main(recover=True)
    else:
        main()
