# 开发说明书：模拟面试 Phase 3 清场（迁引用 → 删壳 → 更新文档）

> 关联文档：
> - `05-重构方案-模拟面试模块化.md`（本说明书 = 该文档 **Phase 3 / Tier C** 的落地细化）
> - `06-开发计划-写回核心ApplyVerdict.md`（Phase 1，已完成 ✅）
> - `07-开发计划-模拟面试拆包SrcMock.md`（Phase 2，已完成 ✅）
> - `08-进度说明-模拟面试拆包.md`（Phase 2 中断快照，未完成项已于今日收尾，见 §0）
>
> 范围：把 6 处代码引用从 `scripts.run_mock_interview` 迁到 `src.mock`；删 `scripts/run_mock_interview.py` 薄壳；补 `src/mock/__main__.py` CLI 入口；更新活文档引用。**只做代码搬迁，不重写业务逻辑。**

---

## 0. 前置状态（2026-08-27 20:30 实测，非猜测）

- Phase 1（06）+ Phase 2（07）**已全部落地**：`src/mock/` 8 文件齐全、`scripts/run_mock_interview.py` 已是薄壳。
- 08 记录的 T9 失败（30 failed / 7 passed）**已修复**——当前实测：
  ```
  pytest tests/test_mock_interview.py tests/test_mock_interview_recover.py tests/test_mock_writeback.py tests/test_mock_api.py -q
  → 48 passed in 5.44s
  ```
- 壳当前已 re-export `DATA_DIR / space_dir / chat_json` 及全部私有符号（08 §4-A 的"壳缺私有符号"已补）。
- **结论：Phase 3 的所有前置依赖已满足，本说明书可直接开工。**

---

## 1. 目标

1. 消除最后的历史依赖：6 处代码引用全部迁到 `src.mock`，`scripts/run_mock_interview.py` 壳删除，全仓无 `scripts.run_mock_interview` 残留。
2. 测试的 patch 穿透机制**不破**：`@patch.object(mi, ...)` 的宿主 `mi` 从壳切换到 `src.mock`，子模块活引用同步切换（§3.1）。
3. CLI 直跑入口从 `python scripts/run_mock_interview.py` 无缝迁到 `python -m src.mock`（保留 `--space` / `--recover` 语义）。
4. 用户面向文档（README / architecture-spec 等）的路径更新；历史快照文档（方案/进度/评审/报告）保留不动。

---

## 2. 已核准的代码事实（2026-08-27 读盘核实）

### 2.1 待迁移的代码引用（6 处）

| # | 文件:行 | 现状 | 迁移为 |
|---|---|---|---|
| C1 | `app/api/mock.py:12-20` | `from scripts.run_mock_interview import (WEAK_POOL_SIZE, get_weak_questions, judge_single_round, judge_followup, plan_interview, summarize_behaviors, _read_profile)` | `from src.mock import (...)` 同 7 符号；`:23` 的 `from src.mock.writeback import apply_verdict` 保留 |
| C2 | `offerloop.py:29` | `import scripts.run_mock_interview as mock`（仅用 `mock.main()`） | `import src.mock as mock` |
| C3 | `eval/mock_interview_eval.py:35` | `from scripts.run_mock_interview import judge_single_round` | `from src.mock.judge import judge_single_round`（直达子模块，不依赖包 `__init__`） |
| C4 | `tests/test_mock_api.py:11` | `import scripts.run_mock_interview as mi` | `import src.mock as mi` |
| C5 | `tests/test_mock_interview.py:6` | `import scripts.run_mock_interview as mi` | `import src.mock as mi` |
| C5b | `tests/test_mock_interview.py:223, 270`（函数内） | `from scripts.run_mock_interview import run_dynamic_session` / `MAX_TOTAL_QUESTIONS` | `from src.mock import ...` |
| C6 | `tests/test_mock_interview_recover.py:5` | `import scripts.run_mock_interview as mi` | `import src.mock as mi` |

> 迁移后测试 `mi = src.mock`，`@patch.object(mi, "chat_json")` 等 patch 的是 `src.mock` 模块属性——只要子模块走活引用（§2.2）且 `__init__` re-export 齐全（§2.3），穿透机制与现在完全一致。

### 2.2 子模块活引用（删壳的关键前提，4 处）

- `src/mock/judge.py:8` / `plan.py:13` / `report.py:7` / `runtime.py:17` 均为：
  `import scripts.run_mock_interview as _mi`
- 内部经 `_mi.chat_json` / `_mi.get_expected_points` / `_mi.judge_followup` / `_mi.decide_next` / `_mi.interview_one` / `_mi.generate_dynamic_question` / `_mi._progress_file` 运行时动态查——这是测试 patch 穿透的根基。
- **删壳前必须把这 4 处改为 `import src.mock as _mi`**，否则删壳后 `scripts` 模块不存在 → 直接 AttributeError。
- `writeback.py` 无活引用（直接 import `src.cleaner.schema` / `src.memory`）✅ 不用改。

### 2.3 `src/mock/__init__.py` 现状与缺口

- 已 re-export：6 常量 + `DATA_DIR` + `space_dir` + 全部公共/私有符号。
- **缺 `chat_json`**：壳里有 `from src.llm import chat_json`，`__init__.py` 没有。删壳后若不补：
  - 子模块 `_mi.chat_json` → AttributeError；
  - `test_mock_api.py` / `test_mock_interview.py` 共 13 处 `@patch.object(mi, "chat_json")` 扑空。
- 测试 patch 目标全集（迁移后需可从 `src.mock` patch）：`chat_json` / `get_expected_points` / `judge_followup` / `decide_next` / `interview_one` / `generate_dynamic_question`——除 `chat_json` 外均已在 `__init__` re-export ✅。

### 2.4 CLI 入口现状

- 壳 `__main__`（`scripts/run_mock_interview.py:53-62`）：解析 `--space` → 改 `_cfg.SPACE`；`--recover` → `recover()`；否则 `main()`。
- `cli.py:main()` 自身**不解析** `--space/--recover`（靠壳入口）。
- `cli.py:131` 提示语："稍后重跑 `python run_mock_interview.py --recover` 补写" → 需随入口更新。
- `pyproject.toml` **无 `[project.scripts]` entry points** → 删壳不影响包安装/导入入口。

### 2.5 文档引用（处置分类）

| 文档:行 | 内容 | 处置 |
|---|---|---|
| `README.md:148-149` | CLI 示例 `python scripts/run_mock_interview.py [--recover]` | **改** → `python -m src.mock` |
| `docs/architecture-spec.md:153` | `run_mock_interview.py` + `app/api/mock.py`（Web 对齐 CLI） | **改** → `src/mock/` 包 + `app/api/mock.py` |
| `docs/MOCK-INTERVIEW-FRONTEND-DESIGN.md:110,123,176` | `run_mock_interview.get_weak_questions()` / `get_expected_points()` / `judge_followup()` / `interview_one` | **改** 前缀 → `src.mock.` |
| `docs/模拟面试最小闭环设计.md:123` | "写 `run_mock_interview.py`" | **改** → `src/mock/` 包 |
| `docs/扩展点评审与疑点解答-2026-08-19.md:3,75` | 历史评审快照（引用当时代码） | **不改**（历史快照） |
| `docs/eval/mock_interview_eval_report.md:60` | 历史 eval 报告 | **不改** |
| `docs/05 ~ 08` | 方案/计划/进度文档 | **不改**（历史） |
| `eval/mock_interview_eval.py:3` | 头注释"被测阅卷人：run_mock_interview.judge_single_round" | **顺手改** → `src.mock.judge.judge_single_round` |

> 已排除：`scripts/run_evals.py`（仅以字符串路径调 eval 脚本，不 import mock 代码）、`docs/实现说明/`、`overview.md`、`tests/test_mock_writeback.py`（已用 `from src.mock import writeback`）均无引用 ✅。

---

## 3. 关键设计

### 3.1 测试 patch 穿透的宿主切换（核心机制，必须整体理解再动手）

现在：测试 `patch.object(mi, "chat_json")` → patch **壳**属性 → 子模块 `_mi.chat_json` 活引用穿透。
改后：测试 `mi = src.mock` → patch **包**属性 → 子模块 `_mi` 改为 `src.mock` 后同样穿透。

**机制不变，只是宿主从壳换成包。** 因此 T1（补 `chat_json` re-export）+ T2（4 处活引用切换）必须**同批完成、先于删壳**，缺一即崩。

### 3.2 CLI 入口：新增 `src/mock/__main__.py`

承接壳的 `__main__` 逻辑，保留任意 cwd 直跑能力：

```python
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
```

> 等价映射：`python scripts/run_mock_interview.py` → `python -m src.mock`；`--space X` / `--recover` 参数原样保留。

### 3.3 文档处置原则

- **活文档**（README / architecture-spec / 前端设计 / 最小闭环设计）：引用前缀与命令示例更新为 `src.mock` / `python -m src.mock`。
- **历史快照**（扩展点评审 / eval 报告 / 05-08 系列）：不改正文。如需提示，可在文件顶部加一行注记，但不属于本说明书必做项。

---

## 4. 实施任务清单（建议提交顺序，含依赖）

| # | 任务 | 文件 | 依赖 | 风险 |
|---|---|---|---|---|
| T1 | `__init__.py` 补 `from src.llm import chat_json`（re-export） | `src/mock/__init__.py` | — | 低（删壳前必做） |
| T2 | 4 个子模块活引用 `import scripts.run_mock_interview as _mi` → `import src.mock as _mi` | `src/mock/{judge,plan,report,runtime}.py` | — | 中（删壳前必做） |
| T3 | 迁 eval：`:35` import + `:3` 头注释 | `eval/mock_interview_eval.py` | — | 低 |
| T4 | 迁 3 个测试文件（C4/C5/C5b/C6，共 5 处 import） | `tests/test_mock_api.py` / `test_mock_interview.py` / `test_mock_interview_recover.py` | — | 低（`import src.mock as mi` 一行改） |
| T5 | 迁 offerloop.py（C2） | `offerloop.py` | — | 低 |
| T6 | 迁 app/api/mock.py（C1） | `app/api/mock.py` | — | 低 |
| T7 | 新建 `src/mock/__main__.py`（§3.2） | 新文件 | — | 中（CLI 入口） |
| T8 | 删 `scripts/run_mock_interview.py` 壳 + 改 `cli.py:131` 提示语为 `python -m src.mock --recover` | 删文件 + `src/mock/cli.py` | **T1+T2+T7** | 中 |
| T9 | 更新文档引用（§2.5 活文档 4 处） | `README.md` / `architecture-spec.md` / `MOCK-INTERVIEW-FRONTEND-DESIGN.md` / `模拟面试最小闭环设计.md` | T8 | 低 |
| T10 | 全量验证（§5） | — | T1-T9 | — |

> ⚠️ **顺序硬约束**：T1 + T2 必须先于 T8（删壳），否则中间态崩；T7 与 T8 同批完成。T3-T6 与 T8 无严格先后（壳在时先迁亦可）。
> 建议一次提交：`feat: mock Phase 3 清场（迁引用 + 删壳 + python -m src.mock 入口）`。

---

## 5. 验证方法

```bash
# 1. 迁移后 48 项 mock 测试保持全绿（核心证明：patch 穿透 + 契约未破）
pytest tests/test_mock_interview.py tests/test_mock_interview_recover.py \
       tests/test_mock_writeback.py tests/test_mock_api.py -q

# 2. CLI 入口冒烟（不触发 LLM：无进度文件时 --recover 应安静返回/提示无中断记录）
python -m src.mock --recover

# 3. offerloop 入口冒烟（import 即验证，输入"退出"退出）
python offerloop.py

# 4. eval 导入冒烟（不实跑 44 次 LLM）
python -c "from src.mock.judge import judge_single_round; print('ok')"

# 5. 残留检查（代码 + 活文档，应无命中）
grep -rn "scripts.run_mock_interview\|run_mock_interview.py" --include="*.py" --include="*.md" \
  app offerloop.py eval tests src README.md docs/architecture-spec.md docs/MOCK-INTERVIEW-FRONTEND-DESIGN.md docs/模拟面试最小闭环设计.md

# 6. 壳已删确认
ls scripts/run_mock_interview.py   # 应报不存在
```

---

## 6. 风险与回滚

| 风险 | 缓解 |
|---|---|
| 删壳但漏 T1（`chat_json`）→ 子模块/测试 AttributeError | T1 先于 T8 完成 + §5-1 全量验证 |
| 漏 T2 任意一处活引用 → 删壳即崩 | T2 4 处逐一改 + §5-5 残留 grep 兜底 |
| 测试 patch 穿透失效（宿主换了） | 机制不变（活引用动态查），48 项全绿即证明 |
| `python -m src.mock` 在任意 cwd 失败 | `__main__.py` 保留 sys.path 引导（同原壳） |
| 文档漏改 README 命令示例 | T9 清单逐条勾选 |
| `cli.py:131` 提示语仍指向旧命令 | T8 顺手改（同批） |

**回滚**：全部改动 = 1 行 `__init__` + 4 行活引用 + 6 处 import + 1 个新文件 + 删 1 个壳 + 4 处文档。`git checkout -- <上述文件>` 即整体还原；壳的完整逻辑仍在 git 历史（此前从未提交过旧版全量脚本的删除——旧版在更早提交里）。

---

## 7. 验收标准

- [x] 全仓（代码 + 活文档）grep 无 `scripts.run_mock_interview` / `run_mock_interview.py` **可执行引用**（import/命令/路径）残留；
      剩余命中均为模块头部的「从原 scripts 壳搬迁」历史来源说明注释（保留）。
- [x] 48 项 mock 测试全绿（`test_mock_interview*` + `test_mock_writeback` + `test_mock_api`）：48 passed。
- [x] `python -m src.mock`、`python -m src.mock --space X --recover` 行为与原壳一致（冒烟通过）。
- [x] `python offerloop.py` 的模拟面试路由（`mock.main()`）不崩（import 冒烟 OK，`mock = src.mock`）。
- [x] `app/api/mock.py` 的 `/api/mock/*` 4 端点契约不变（`test_mock_api.py` 全绿即证明）。
- [x] `src/mock/` 内无任何 `import scripts` 残留；`scripts/run_mock_interview.py` 已删除。
- [x] README 的 CLI 示例已更新为 `python -m src.mock`。

> 实施补记：09 §2.1 迁移表未列 `mi._write_back`（原壳兼容函数），测试 `test_write_back_*` 2 项
> 在删壳后失败——已把 `_write_back`（`_build_writeback_items` 薄封装）补进 `src/mock/writeback.py`
> 并 re-export，2 项即恢复全绿。

---

## 8. 面试官讲点（清场完成后的叙事）

> "模拟面试最初是 1032 行的 CLI 脚本，Web 端还重写了一遍写回逻辑、行为不一致。我分三个阶段收掉：① 抽共享写回核心 `apply_verdict` 统一 CLI/Web 行为（还借机把面试官反馈落到专用 `feedback` 字段）；② 按生命周期拆成 `src/mock/` 包（plan/runtime/judge/writeback/report/cli/prompts）；③ 把所有引用迁到新包、删掉旧脚本壳，CLI 入口变成 `python -m src.mock`。
>
> 拆包时有个关键技巧：子模块不缓存 `chat_json` 这类函数，而是 `import src.mock as _mi` 后运行时动态取 `_mi.chat_json`——这样测试 `@patch.object(mi, "chat_json")` 只要 patch 包属性就能穿透到所有子模块。这是'让模块化可测试'的落地细节，比单纯拆文件更重要。"

---

## 9. 待确认（已归档 ✅）

- [x] CLI 入口用 `python -m src.mock`（推荐，包语义干净）——已采纳实施。
- [x] 历史快照文档不加注记（默认只改活文档，不动历史）——已按默认执行。
- [x] 05 文档 §10 的三个待确认项（写回行为、重构档位、壳策略）——本说明书实施完成后一并闭环
      （写回=apply_verdict 统一、重构=分层模块化、壳策略=Phase 3 删壳完成）。
