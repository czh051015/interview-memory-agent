# 开发计划：模拟面试拆包（`scripts/` → `src/mock/` 包）

> 关联文档：
> - `05-重构方案-模拟面试模块化.md`（本计划 = 该文档 **Phase 2 / Tier B** 的落地细化）
> - `06-开发计划-写回核心ApplyVerdict.md`（本计划的**前置依赖** = Phase 1，须先完成）
>
> 范围：把 `scripts/run_mock_interview.py`（1032 行单脚本）按生命周期拆成 `src/mock/` 多模块包；`scripts/run_mock_interview.py` **降级为薄壳**（`from src.mock import ...` 全量 re-export），使 5 处既有引用（3 测试 + eval + offerloop.py + app/api/mock.py）**零改动**。本计划**不删壳、不迁引用**（那是 Phase 3）。

---

## 1. 目标与范围

1. 消除"1032 行单脚本"的可维护性债务，对齐 `cleaner` 的"一阶段一文件 + prompts 独立"结构。
2. 把 inline 的 10 个 prompt 常量抽到 `src/mock/prompts.py`（对齐 cleaner 的 prompts.py 模式）。
3. 用薄壳保住全部既有引用，**不破坏任何测试 / API / CLI 入口**。
4. **不**动 `app/api/mock.py`、`eval/mock_interview_eval.py`、`offerloop.py`、`tests/*` 的 import（壳兜底）。
5. **不**删 `scripts/` 壳（Phase 3 才删）。

---

## 2. 前置依赖（必须先完成 06）

- `src/mock/__init__.py` 与 `src/mock/writeback.py` 已存在（`apply_verdict` 已落地）。
- 本计划假设 `apply_verdict` 已在 `writeback.py`，拆包时只搬其余函数，**不再重写写回逻辑**。
- 若 06 未落地，本计划需先补建 `src/mock/__init__.py`（仅常量占位）与 `writeback.py`（从 06 取），否则 `src/mock` 包不存在。

---

## 3. 已核准的代码事实（写计划前已读代码确认）

| 事实 | 位置 | 对计划的影响 |
|---|---|---|
| 模块级常量共 5 个 | `run_mock_interview.py:41-45` | 全部移入 `src/mock/__init__.py`：<br>`WEAK_POOL_SIZE=5 / MAX_FOLLOWUPS=2 / MAX_ROUNDS=3 / MAX_TOTAL_QUESTIONS=12 / MAX_SECTION_QUESTIONS=5` |
| `space_dir` 来自 `src.config` | `run_mock_interview.py:32` `from src.config import DATA_DIR, space_dir` | 壳与 `__init__` 需 re-export `space_dir`（测试 `mi.space_dir` 用到） |
| `_ACTION_OF` **不存在** | grep 无命中 | 05 文档写错了；**不** re-export 此符号 |
| inline prompt 常量共 10 个 | `:140 / 190 / 245 / 288 / 307 / 317 / 381 / 395 / 487 / 508` | 全部移入 `prompts.py` |
| 测试（`mi.*`）引用的符号 | `test_mock_interview.py` / `test_mock_interview_recover.py` | 壳必须 re-export 这些（含下划线私有函数） |
| `offerloop.py:29` 引用 | `import scripts.run_mock_interview as mock` → 仅用 `mock.main()` | 壳 re-export `main` 即可 |
| `eval/mock_interview_eval.py:35` 引用 | `from scripts.run_mock_interview import judge_single_round` | 壳 re-export `judge_single_round` 即可 |
| `app/api/mock.py` 引用 | `:12-20` 从 `scripts.run_mock_interview` import 出题/判卷函数；`:23` `from src.mock.writeback import apply_verdict` | 壳全量 re-export 后 `:12-20` 不受影响；本计划**不改 mock.py** |

### 3.1 测试实际引用的 `mi.*` 符号（壳 re-export 的硬约束清单）

**`test_mock_interview.py`：**
`interview_one`, `record_result`, `get_expected_points`, `judge_single_round`, `judge_followup`, `generate_review_report`, `decide_next`, `run_dynamic_session`, `MAX_TOTAL_QUESTIONS`, `MAX_SECTION_QUESTIONS`

**`test_mock_interview_recover.py`：**
`_save_progress`, `_load_progress`, `_write_back`, `_read_doc`, `_read_profile`, `_read_pdf_text`, `space_dir`（以上为 `mi.` 前缀访问）

> ⚠️ **关键陷阱**：`import *` 默认**不导出下划线前缀名称**。壳不能用 `from src.mock import *` 裸用，必须**显式列出** `_save_progress/_load_progress/_write_back/_read_doc/_read_profile/_read_pdf_text` 等私有符号。

---

## 4. 目标结构（模块 → 函数映射，行号已核对）

```
src/mock/
├── __init__.py      # 常量(WEAK_POOL_SIZE/MAX_FOLLOWUPS/MAX_ROUNDS/MAX_TOTAL_QUESTIONS/MAX_SECTION_QUESTIONS) + space_dir + 公共 API re-export
├── prompts.py       # 10 个 inline prompt 常量（见 §4.1）
├── plan.py          # get_weak_questions, _read_doc, _read_profile, _read_pdf_text
├── runtime.py       # decide_next, generate_dynamic_question, interview_one, run_dynamic_session,
│                    #   recover, _save_progress, _load_progress, _clear_progress,
│                    #   _progress_file, _q_dump, _r_dump
├── judge.py         # get_expected_points, judge_followup, judge_single_round
├── writeback.py     # 〔Phase 1 已建〕apply_verdict, record_result, _collect_new_item,
│                    #   _feedback_text, _log_write_back, _build_writeback_items
├── report.py        # summarize_behaviors, generate_review_report, _format_review
└── cli.py           # main()  (recover 入口在此调用 runtime.recover)

scripts/run_mock_interview.py   # 薄壳：显式 re-export 全部符号（含私有）
app/api/mock.py                 # 〔不动〕仍 import scripts.run_mock_interview + src.mock.writeback
```

### 4.1 `prompts.py` 内容（10 个常量，按原行号来源）

| 常量 | 原行 | 归属函数 |
|---|---|---|
| `_PLAN_PROMPT` | 140 | `plan_interview` |
| `_DECIDE_NEXT_PROMPT` | 190 | `decide_next` |
| `_DYNAMIC_QUESTION_PROMPT` | 245 | `generate_dynamic_question` |
| `_EXPECTED_POINTS_PROMPT` | 288 | `get_expected_points` |
| `_FOLLOWUP_PROMPT` | 307 | `judge_followup` |
| `_RUBRIC_FOLLOWUP_PROMPT` | 317 | `judge_followup`（量规版） |
| `_SINGLE_JUDGE_PROMPT` | 381 | `judge_single_round` |
| `_RUBRIC_SINGLE_PROMPT` | 395 | `judge_single_round`（量规版） |
| `_BEHAVIOR_PROMPT` | 487 | `summarize_behaviors` |
| `_REVIEW_PROMPT` | 508 | `summarize_behaviors` |

---

## 5. 关键设计：薄壳兼容策略

### 5.1 为什么保留 `scripts/` 壳

Phase 2 的目标只是"结构清晰"，**不动任何外部引用**风险最低。5 处引用全都 `import scripts.run_mock_interview`（或其符号），只要壳把符号都 re-export 出去，它们就完全无感。

### 5.2 壳的写法（不能用 `import *`）

```python
# scripts/run_mock_interview.py（改造后全文）
"""薄壳：兼容历史 import（tests / eval / offerloop.py / app/api/mock.py）。
实际实现已迁移至 src/mock/ 包。"""
from src.mock import (
    # 出题
    get_weak_questions, _read_doc, _read_profile, _read_pdf_text,
    # 运行
    decide_next, generate_dynamic_question, interview_one, run_dynamic_session,
    recover, _save_progress, _load_progress, _clear_progress,
    _progress_file, _q_dump, _r_dump,
    # 判卷
    get_expected_points, judge_followup, judge_single_round,
    # 写回
    apply_verdict, record_result, _collect_new_item, _feedback_text, _log_write_back,
    # 报告
    summarize_behaviors, generate_review_report, _format_review,
    # 入口
    main,
    # 常量
    WEAK_POOL_SIZE, MAX_FOLLOWUPS, MAX_ROUNDS, MAX_TOTAL_QUESTIONS, MAX_SECTION_QUESTIONS,
    space_dir,
)
```

> 旧 `main()` 与所有业务逻辑已从本文件删除，只留上述 re-export。CLI 调用 `python -m scripts.run_mock_interview` 仍走 `main`，行为不变。

### 5.3 `src/mock/__init__.py` 组织（避免循环 import）

```python
# src/mock/__init__.py
# ① 先定义常量（在 import 子模块之前绑定，供子模块 `from . import MAX_TOTAL_QUESTIONS` 使用）
WEAK_POOL_SIZE = 5
MAX_FOLLOWUPS = 2
MAX_ROUNDS = MAX_FOLLOWUPS + 1
MAX_TOTAL_QUESTIONS = 12
MAX_SECTION_QUESTIONS = 5
from src.config import space_dir  # re-export

# ② 再 import 子模块（子模块内 `from . import 常量` 此时已可解析）
from .plan import get_weak_questions, _read_doc, _read_profile, _read_pdf_text
from .runtime import (decide_next, generate_dynamic_question, interview_one,
                      run_dynamic_session, recover, _save_progress, _load_progress,
                      _clear_progress, _progress_file, _q_dump, _r_dump)
from .judge import get_expected_points, judge_followup, judge_single_round
from .writeback import (apply_verdict, record_result, _collect_new_item,
                        _feedback_text, _log_write_back)
from .report import summarize_behaviors, generate_review_report, _format_review
from .cli import main
from . import prompts  # 供需要处 `from .prompts import _PLAN_PROMPT`
```

> ⚠️ 子模块内部一律用**相对 import**（`from .prompts import ...`、`from .writeback import apply_verdict`、`from . import MAX_TOTAL_QUESTIONS`），不要再用 `from scripts.run_mock_interview import ...`（否则壳缺失时崩）。

---

## 6. 实施任务清单（建议顺序）

| # | 任务 | 文件 | 风险 |
|---|---|---|---|
| T1 | 新建 `src/mock/prompts.py`，搬 10 个 prompt 常量；各原函数改为 `from .prompts import ...` | 新文件 + 改动原函数 | 低 |
| T2 | 新建 `src/mock/plan.py`：搬 `get_weak_questions / _read_doc / _read_profile / _read_pdf_text`；内部 import 改相对路径 | 新文件 | 低 |
| T3 | 新建 `src/mock/runtime.py`：搬 `decide_next / generate_dynamic_question / interview_one / run_dynamic_session / recover` + 6 个进度持久化私有函数 | 新文件 | 中（含恢复机制） |
| T4 | 新建 `src/mock/judge.py`：搬 `get_expected_points / judge_followup / judge_single_round` | 新文件 | 低 |
| T5 | 新建 `src/mock/report.py`：搬 `summarize_behaviors / generate_review_report / _format_review` | 新文件 | 低 |
| T6 | 新建 `src/mock/cli.py`：搬 `main()`（`--recover` 调 `runtime.recover`） | 新文件 | 中（CLI 入口） |
| T7 | 改写 `src/mock/__init__.py`：常量 + `space_dir` + 全量 re-export（按 §5.3 顺序避免循环 import） | 改已有文件 | 中 |
| T8 | 把 `scripts/run_mock_interview.py` 重写为薄壳（按 §5.2） | 改已有文件 | 中（删全部业务逻辑） |
| T9 | 跑测试验证壳兼容 | pytest | — |

> 注：`writeback.py`（Phase 1 产物）本计划不改动；若 06 尚未落地，T0 先按 06 建 `writeback.py`。

---

## 7. 测试兼容性验证（无需改任何测试文件）

- **壳零改动验证**：
  - `pytest tests/test_mock_interview.py tests/test_mock_interview_recover.py -q`
  - 这两个文件 `import scripts.run_mock_interview as mi`，全绿即证明壳 re-export 完整。
- **Web 契约验证**：`pytest tests/test_mock_api.py -q`（mock.py 未动，端点契约不变）。
- **写回单测**：`pytest tests/test_mock_writeback.py -q`（Phase 1 产物，确认拆包未影响）。
- **评测脚本**：`python eval/mock_interview_eval.py`（其 `from scripts.run_mock_interview import judge_single_round` 经壳仍可用）。

> 若某测试报 `AttributeError: module 'scripts.run_mock_interview' has no attribute 'X'`，说明壳漏 re-export `X` → 补进 §5.2 清单重跑，不动测试。

---

## 8. 风险与回滚

| 风险 | 缓解 |
|---|---|
| 循环 import（`__init__` 引子模块、子模块引 `__init__` 常量） | 严格按 §5.3 顺序：常量先绑定、再 import 子模块；子模块用 `from . import 常量` |
| 壳漏 re-export 私有函数（`_save_progress` 等） | 测试 `test_mock_interview_recover.py` 必 catch；补清单即可，无需改测试 |
| `recover` / `_save_progress` 搬迁不完整 → 崩溃补写失效 | `test_mock_interview_recover.py` 覆盖；搬迁时整段搬、不拆分 |
| 误改 `app/api/mock.py` / `offerloop.py` / `tests/*` | 本计划明确**不改**这些文件；仅 `scripts/run_mock_interview.py` 与 `src/mock/*` 变动 |
| 旧 `main()` 残留引用 scripts 内部符号 | T8 重写壳时彻底删除业务代码，仅留 import |

**回滚**：拆包是纯新增 `src/mock/` + 改壳；若出问题，`git revert` 壳与 `src/mock/` 即可，原 `scripts/run_mock_interview.py` 历史版本可恢复为完整脚本（Phase 3 才删壳，故旧内容仍在 git 历史）。

---

## 9. 验收标准

- [x] `src/mock/` 含 `prompts/plan/runtime/judge/writeback/report/cli/__init__.py` 共 8 文件。
- [x] `prompts.py` 含 10 个常量；原脚本中对应 inline 常量已删除。
- [x] `scripts/run_mock_interview.py` 仅含 re-export，无业务逻辑（行数从 ~1032 降至 61，
      另含 `_write_back` 兼容壳 + CLI 直跑入口）。
- [x] `tests/test_mock_interview*.py` 全绿（壳兼容）：37 passed。
- [x] `tests/test_mock_api.py` + `tests/test_mock_writeback.py` 全绿（Web/写回未受拆包影响）：11 passed。
- [x] `python eval/mock_interview_eval.py` 可运行（`judge_single_round` 经壳可达）：PASS
      （disc=100% strict=73% no_fool=100% qpass=100%）。
- [x] `offerloop.py` 的 `mock.main()` 入口调用正常（CLI 未破）：import 冒烟 OK。
- [x] **未改动** `app/api/mock.py` / `offerloop.py` / `eval/mock_interview_eval.py` / 任意 `tests/*` 文件。

> 完成记录见 `08-进度说明`。关键设计补充：子模块内部互调一律经壳活引用
> （`import scripts.run_mock_interview as _mi` + `_mi.xxx`），测试 patch 的是壳命名空间，
> 模块级值绑定穿透不进来——这是拆包后 30 项测试失败的根因与解法。

---

## 10. 与 Phase 1 / Phase 3 的衔接

- **← Phase 1（06）**：提供 `src/mock/writeback.py::apply_verdict`，本计划只搬其余模块、复用之。
- **→ Phase 3**：待本计划稳定后，把 5 处引用直接迁到 `src.mock`（eval 改 `from src.mock.judge import judge_single_round`、offerloop.py 改 `from src.mock import ...`、`test_*` 改 import、文档路径更新），最后**删除 `scripts/run_mock_interview.py` 壳**。
- **独立优化（不在本计划）**：是否把 `app/api/mock.py` 内的 `MockQuestion`/`_to_question` Web 专属展示逻辑下沉（当前留 Web 层不动）。
