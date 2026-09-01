"""申论练习会话引擎（docs/22）：mock 重定位为「申论示证引擎」。

一句话：**"考你" → "帮你"。** 上传 题干+材料+标准答案+作答 → 评分（score_answer
确定性传感器）→ L1 命中/漏点列表（每漏点挂材料原话）→ 推 1 个最该补的漏点 + 示证
→ 用户点开某漏点按需生成 L2(DEMO)+L4(CAUSE)（guidance，LLM 只做示证）。
不自动循环逼问（旧 practice_one 逼近循环已删除，docs/22 §3.4）。

模块分区：
  · 示证域（新代码）：runtime.guidance 按需示证、prompts.{DEMO,CAUSE}_PROMPT。
  · 【废弃域】模拟面试：judge/plan/report/writeback 仍被 Web 版模拟面试
    （app/api/mock.py）引用，保留可导入但禁止新代码使用（docs/18）。
"""

WEAK_POOL_SIZE = 5        # 【废弃域】Web 模拟面试：薄弱项候选池

# ① 常量先绑定（子模块用 `from . import 常量` 已可解析）
from src.config import DATA_DIR, space_dir  # re-export（测试 mi.DATA_DIR、mi.space_dir 用到）
from src.llm import chat_json  # re-export：子模块经 _mi.chat_json 活引用，测试 patch 本模块属性才穿透

# ② 示证域（docs/22 新核心）
from .runtime import guidance, GuidanceResult, PASS_HIT_RATIO

# ③ 【废弃域】模拟面试 Web 版（app/api/mock.py）仍引用，保留可导入
from .judge import get_expected_points, judge_followup, judge_single_round
from .plan import plan_interview, get_weak_questions, _read_doc, _read_profile, _read_pdf_text
from .report import summarize_behaviors, generate_review_report, _format_review
from .writeback import (
    apply_verdict, record_result, _collect_new_item, _feedback_text,
    _build_writeback_items, _record_result, _write_back,
)
