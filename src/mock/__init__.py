"""申论练习会话引擎（docs/18）：mock 从「模拟面试官」重定位为「申论练习会话引擎」。

一句话：**"考察你" → "陪你练"。** 抽题 → 作答 → 评分（score_answer 确定性传感器）
→ 逼近引导（LLM 只提示漏了什么+去哪里找）→ 回流（reflow_answer + answer_rounds 轨迹）。

CLI：python -m src.mock [--space X] [--recover]

模块分区：
  · 练习域（新代码）：runtime.practice_one 逼近循环 + 断点续练（v2 版本化）、
    cli.main 练习会话主循环、prompts._APPROACH_PROMPT 逼近引导。
  · 【废弃域】模拟面试：judge/plan/report/writeback 仍被 Web 版模拟面试
    （app/api/mock.py）引用，保留可导入但禁止新代码使用；对应逻辑已被
    score_answer + 逼近引导 + reflow_answer 取代（docs/18）。
"""

MAX_ROUNDS = 3            # 逼近轮次上限（初稿 + 2 次引导补充；碎片化场景轮次多会拖时间）
WEAK_POOL_SIZE = 5        # 【废弃域】Web 模拟面试：薄弱项候选池

# ① 常量先绑定（子模块用 `from . import 常量` 已可解析）
from src.config import DATA_DIR, space_dir  # re-export（测试 mi.DATA_DIR、mi.space_dir 用到）
from src.llm import chat_json  # re-export：子模块经 _mi.chat_json 活引用，测试 patch 本模块属性才穿透

# ② 练习域（docs/18 新核心）
from .runtime import (
    practice_one, PracticeRound, PracticeResult,
    _progress_file, _save_practice, _load_practice, _clear_practice,
    PASS_HIT_RATIO, PROGRESS_VERSION,
)
from .cli import main

# ③ 【废弃域】模拟面试 Web 版（app/api/mock.py）仍引用，保留可导入
from .judge import get_expected_points, judge_followup, judge_single_round
from .plan import plan_interview, get_weak_questions, _read_doc, _read_profile, _read_pdf_text
from .report import summarize_behaviors, generate_review_report, _format_review
from .writeback import (
    apply_verdict, record_result, _collect_new_item, _feedback_text,
    _build_writeback_items, _record_result, _write_back,
)
