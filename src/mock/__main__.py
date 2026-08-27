"""CLI 直跑入口：python -m src.mock [--space X] [--recover]。

承接原 scripts/run_mock_interview.py 的直跑语义（Phase 3 删壳后）。
"""

import sys
from pathlib import Path

# 任意 cwd 下 `python -m src.mock` 也能 import src.*（同原壳的路径引导）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import src.config as _cfg  # --space 在 __main__ 里改 _cfg.SPACE（活引用）
from src.mock import main, recover


if __name__ == "__main__":
    if "--space" in sys.argv:
        idx = sys.argv.index("--space") + 1
        if idx < len(sys.argv):
            _cfg.SPACE = sys.argv[idx]
    if "--recover" in sys.argv:
        recover()
    else:
        main()
