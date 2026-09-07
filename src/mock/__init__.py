"""申论练习会话引擎（docs/22）：mock 重定位为「申论示证引擎」→ docs/38 门禁运行态。

一句话：**"考你" → "帮你"。** 评分收敛为双模式（docs/38）：门禁（trusted，规则
绿/黄 + 灰带 LLM 疑似标注）与示证（align，0 判定 token 差异配对）；用户点开某采分点
按需生成建议区③改进建议（runtime.guidance，LLM 只出候选，不判分）。
不自动循环逼问（旧 practice_one 逼近循环已删除，docs/22 §3.4）。

模块分区：
  · 示证/门禁域（新代码）：runtime.guidance 按需改进建议 + explain_point、prompts.*。
  · 【废弃域】模拟面试：judge/plan/report/writeback 仍被 Web 版模拟面试
    （app/api/mock.py）引用，保留可导入但禁止新代码使用（docs/18）。
"""

WEAK_POOL_SIZE = 5        # 【废弃域】Web 模拟面试：薄弱项候选池

# ① 常量先绑定（子模块用 `from . import 常量` 已可解析）
from src.config import DATA_DIR, space_dir  # re-export（测试 mi.DATA_DIR、mi.space_dir 用到）
from src.llm import chat_json  # re-export：子模块经 _mi.chat_json 活引用，测试 patch 本模块属性才穿透

# ② 门禁/示证域（docs/22 示证核心 + docs/38 收敛）
from .runtime import guidance, GuidanceResult

# ③ 【废弃域】模拟面试 Web 版（app/api/mock.py）仍引用，保留可导入
from .judge import get_expected_points, judge_followup, judge_single_round
from .plan import plan_interview, get_weak_questions, _read_doc, _read_profile, _read_pdf_text
from .report import summarize_behaviors, generate_review_report, _format_review
from .writeback import (
    apply_verdict, record_result, _collect_new_item, _feedback_text,
    _build_writeback_items, _record_result, _write_back,
)
