"""模拟面试模块（Phase 2：拆包完成，07 计划）。

Phase 1（06 计划）已建 writeback.py（统一写回核心 apply_verdict）。
Phase 2 补齐：常量绑定 + plan/runtime/judge/report/cli 各归一文件，全部 re-export，
使 scripts/run_mock_interview.py 薄壳与既有引用（tests/eval/offerloop/app）零改动。
"""

WEAK_POOL_SIZE = 5        # 薄弱项候选池（LLM 从错题本挑技术验证题）
MAX_FOLLOWUPS = 2         # 每题最多追问 2 次
MAX_ROUNDS = MAX_FOLLOWUPS + 1   # 首答 + 2 追问 = 3 轮
MAX_TOTAL_QUESTIONS = 12  # 动态循环整场题数上限
MAX_SECTION_QUESTIONS = 5  # 动态循环单章题数上限
MIN_SECTION_QUESTIONS = 1  # 动态循环单章最少题数（保证章节骨架）

# ① 常量先绑定（子模块用 `from . import 常量` 已可解析）
from src.config import DATA_DIR, space_dir  # re-export（测试 mi.DATA_DIR、mi.space_dir 用到）
from src.llm import chat_json  # re-export：子模块经 _mi.chat_json 活引用，测试 patch 本模块属性才穿透

# ② 再 import 子模块（子模块内部用相对 import，见各文件）
from .plan import plan_interview, get_weak_questions, _read_doc, _read_profile, _read_pdf_text
from .judge import get_expected_points, judge_followup, judge_single_round
from .runtime import (
    decide_next, generate_dynamic_question, interview_one, run_dynamic_session,
    recover, _save_progress, _load_progress, _clear_progress,
    _progress_file, _q_dump, _r_dump,
)
from .writeback import (
    apply_verdict, record_result, _collect_new_item, _feedback_text,
    _build_writeback_items, _record_result, _write_back,
)
from .report import summarize_behaviors, generate_review_report, _format_review
from .cli import main