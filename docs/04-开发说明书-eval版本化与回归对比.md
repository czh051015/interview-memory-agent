# 开发说明书 ①：Eval 版本化与回归对比

> 关联优化项：参照简历差异化亮点「BEFORE→AFTER 数字」「评估闭环」
> 目标：把现有 3 个 eval 套件的"一次性覆盖式"结果，改为**带时间戳归档 + 历史对比**，让每一次 prompt / 检索改动都可被量化证明。
> 性质：**纯新增工具，零侵入**（不修改 `retrieval_eval.py` / `mock_interview_eval.py` / `llm_judge_eval.py` 任何一行）。

---

## 1. 背景与痛点

现状（已核实源码）：

| 套件 | 文件 | 输出文件 | 写入方式 |
|---|---|---|---|
| ① 检索质量 | `eval/retrieval_eval.py` | `eval/retrieval_eval_results.json` | 第 125 行 `open(..., "w")` 整体覆盖 |
| ② 阅卷判别 | `eval/mock_interview_eval.py` | `eval/mock_interview_eval_results.json` | 第 158 行 `OUT.write_text(...)` 整体覆盖 |
| ③ 拆解质量 | `eval/llm_judge_eval.py` | `eval/llm_judge_results.json` | 第 112 行 `open(..., "w")` 整体覆盖 |

**痛点**：三个套件跑完直接覆盖各自 json，不带日期、无历史。改一版 prompt 后再跑，旧数字消失，只能凭记忆/截图判断"是否变好"——无法产出简历里需要的 BEFORE→AFTER 证据。

**本说明书解决**：增加一个统一入口 `scripts/run_evals.py`，依次驱动 3 个套件，**把结果归档到 `eval/results/{run_id}/`**，并自动生成「本次 vs 上次」对比报告。

---

## 2. 目标 / 非目标

**目标（In scope）**
- 新增 `scripts/run_evals.py`，一键串起 3 个 eval。
- 每次运行结果写入 `eval/results/{run_id}/`（3 个原始 json + 一个扁平 `summary.json` + 运行日志）。
- 自动对比上一轮，生成 `comparison.md`（逐指标 上次 / 本次 / Δ）。
- 支持 `--baseline` 把**当前磁盘上已有的基线 json** 登记为"首轮 before"，使下一个真实 run 立刻有对比。

**非目标（Out of scope）**
- 不修改 3 个现有 eval 套件的逻辑、不改动它们的输出 schema。
- 不做 ②③④（Bad Case 归因 / 混合检索 / 耗时成本）——本项只是它们的"立账本"工具。
- 不接 CI（但设计上保留可被 CI 调用的纯函数）。

---

## 3. 目录与文件设计

```
offerloop/
├── scripts/
│   └── run_evals.py                 # 新增：统一入口（仅调用，不修改 3 套件）
└── eval/
    ├── retrieval_eval.py            # 不动
    ├── mock_interview_eval.py       # 不动
    ├── llm_judge_eval.py            # 不动
    ├── annotations.py               # 不动（检索 ground truth）
    ├── samples/answers.json         # 不动（阅卷 ground truth）
    └── results/                     # 新增目录
        ├── .latest                  # 指针文件：记录最近一次 run_id（含 baseline）
        ├── baseline/                # --baseline 快照（首轮 before 锚点）
        │   ├── retrieval_eval_results.json
        │   ├── mock_interview_eval_results.json
        │   ├── llm_judge_results.json
        │   └── summary.json
        └── 20260826_235000/         # 真实 run（时间戳命名）
            ├── retrieval_eval_results.json
            ├── mock_interview_eval_results.json
            ├── llm_judge_results.json
            ├── summary.json         # 扁平指标，供对比读取
            ├── eval_run.log         # 3 套件的标准输出/错误捕获
            └── comparison.md        # 仅当存在上一轮时生成
```

### run_id 命名
- 真实运行：`datetime.now().strftime("%Y%m%d_%H%M%S")`（如 `20260826_235000`）。
- 时间戳命名**字典序 = 时间序**，便于排序；但 `baseline` 为哨兵名，不参与时间排序，故用 `.latest` 指针文件而非纯排序来确定"上一轮"。

---

## 4. `scripts/run_evals.py` 设计

### 4.1 运行流程

```
main():
  1. root = 项目根（scripts/ 的父目录，即 offerloop/）
  2. 若 --baseline：见 §4.5，结束
  3. run_id = now("%Y%m%d_%H%M%S")
  4. run_dir = eval/results/{run_id}/  （mkdir）
  5. prev_id = 读 eval/results/.latest（可能为空/None）
  6. 依次运行 3 套件（§4.2），stdout+stderr 捕获进 eval_run.log
  7. 把 3 个固定 json 复制到 run_dir（不存在则跳过并记 ok=false）
  8. 提取 summary.json（§4.3）写入 run_dir
  9. 若 prev_id 存在且对应目录存在：生成 comparison.md（§4.4）写入 run_dir
 10. 更新 .latest = run_id
 11. 打印：run_id、各套件 ok、summary 关键指标、comparison.md 路径
```

### 4.2 驱动 3 个套件（非侵入）

用 `subprocess.run([PY, 脚本相对路径], cwd=root, capture_output=True, text=True)` 依次执行：

| 顺序 | 命令 | 备注 |
|---|---|---|
| 1 | `python eval/retrieval_eval.py` | 无参数；KB 为空时打印提示并不写 json（视为 ok=false） |
| 2 | `python eval/mock_interview_eval.py` `[--compare] [--cross-model]` | 参数按需透传；`good/confident` 未校准时返回 1 且不写 json（ok=false） |
| 3 | `python eval/llm_judge_eval.py` | 无参数；`sample` 缺失/拆解失败则不写 json（ok=false） |

- `PY` 取 `sys.executable`，保证与当前解释器一致。
- 任一失败**不中断**其余套件；失败套件在 summary 中 `ok=false` 并附错误信息。
- 复制原始 json 时，仅当源文件存在才复制。

### 4.3 `summary.json` 提取 schema

从 3 个原始 json 扁平化抽取，供对比读取（避免对比时重复解析嵌套结构）。

```json
{
  "run_id": "20260826_235000",
  "created_at": "2026-08-26T23:50:00",
  "labels": { "mock_compare": false, "mock_cross": false },
  "suites": {
    "retrieval": {
      "ok": true,
      "data_count": 120,
      "recall_at_1": 0.55,
      "recall_at_5": 0.704,
      "recall_at_10": 0.88,
      "total_noise": 3
    },
    "mock_interview": {
      "ok": true,
      "by_mode": {
        "rubric":       { "discrimination_rate": 1.0, "strict_order_rate": 0.85, "no_fool_rate": 1.0, "order_ok_rate": 0.95, "question_pass_rate": 0.92 },
        "legacy":       { "...": "..." },            // 仅 --compare 时存在
        "rubric_cross": { "...": "..." }             // 仅 --cross-model 时存在
      }
    },
    "llm_judge": {
      "ok": true,
      "decomposed_count": 27,
      "real_category_accuracy": 0.963,
      "topic_accuracy": 0.89,
      "judge_missed": 2
    }
  }
}
```

**提取规则（务必对齐源码字段）：**

- `retrieval_eval_results.json`：
  - `data_count` → 顶层 `data_count`
  - `recall_at_k` 为列表，找 `k==N` 的条目 → 取其 `recall_at_k`（注意字段名与 key 同名）；`total_noise` 取同条目 `total_noise`
- `mock_interview_eval_results.json`：
  - `runs[]` 每个元素含 `judge_mode`（"rubric"/"legacy"/"rubric_cross"）与 `metrics{}`；按 `judge_mode` 建 `by_mode` 映射
- `llm_judge_results.json`：
  - `real_category_accuracy`、`topic_accuracy`、`judge_missed`、`decomposed_count` 直接取顶层

> 提取函数 `extract_summary(run_dir) -> dict` 做成**纯函数**，便于单测。

### 4.4 `comparison.md` 生成逻辑

输入：当前 `summary.json` + 上一轮 `summary.json`（读 `eval/results/{prev_id}/summary.json`）。

**对比指标（headline，固定 6 项）：**

| 指标 | 来源 | 方向 |
|---|---|---|
| 检索 Recall@5 | `retrieval.recall_at_5` | 越高越好 ↑ |
| 阅卷 discrimination | `mock_interview.by_mode.rubric.discrimination_rate` | ↑ |
| 阅卷 strict_order | `...rubric.strict_order_rate` | ↑ |
| 阅卷 no_fool | `...rubric.no_fool_rate` | ↑ |
| 阅卷 question_pass | `...rubric.question_pass_rate` | ↑ |
| 拆解 category 准确率 | `llm_judge.real_category_accuracy` | ↑ |

**输出格式（示例）：**

```markdown
# Eval 回归对比 — {run_id}

> 对比基准：{prev_id}  →  本轮：{run_id}
> 生成时间：{created_at}

| 指标 | 上次 | 本次 | 变化 | 判定 |
|---|---|---|---|---|
| 检索 Recall@5 | 0.704 | 0.821 | +0.117 | ✅ 提升 |
| 阅卷 discrimination | 1.000 | 1.000 | 0.000 | — 持平 |
| 阅卷 strict_order | 0.850 | 0.920 | +0.070 | ✅ 提升 |
| 阅卷 no_fool | 1.000 | 1.000 | 0.000 | — 持平 |
| 阅卷 question_pass | 0.920 | 0.940 | +0.020 | ✅ 提升 |
| 拆解 category 准确率 | 0.963 | 0.963 | 0.000 | — 持平 |

## 套件状态
- retrieval: ok
- mock_interview: ok（modes: rubric）
- llm_judge: ok
```

- Δ 计算：`cur - prev`；保留两位小数。
- 判定：Δ>0 标 ✅ 提升，Δ<0 标 ⚠️ 回退（醒目），Δ==0 标 — 持平。
- 任一指标在任一侧缺失 → 该格写 `N/A`，不计入 Δ。
- 无上一轮 → `comparison.md` 仅写"首次运行，无历史对比"，并列出本轮绝对值。

### 4.5 `--baseline` 模式（回填现有基线）

目的：把磁盘上**当前已有的** 3 个固定 json（即你现在已知的基线：Recall@5=70.4%、discrimination=100%、no_fool=100%、category=96.3%）登记为"首轮 before 锚点"。

流程：
```
若 --baseline：
  1. target = eval/results/baseline/
  2. 复制当前 3 个固定 json 进 target（不存在则跳过）
  3. 提取 summary.json 进 target
  4. 写/更新 .latest = "baseline"
  5. 打印：baseline 已登记，后续真实 run 将与之对比
```
- 不运行任何 eval 套件，纯快照。
- 之后首次真实 `python scripts/run_evals.py` 即以 `baseline` 为 prev，产出第一份 BEFORE→AFTER。

---

## 5. CLI 接口

```
python scripts/run_evals.py                 # 跑全部 3 套件 + 归档 + 与上一轮对比
python scripts/run_evals.py --no-compare    # 跳过对比生成（仅归档）
python scripts/run_evals.py --compare       # 透传 --compare 给 mock_interview_eval（legacy 对比）
python scripts/run_evals.py --cross-model   # 透传 --cross-model 给 mock_interview_eval
python scripts/run_evals.py --baseline      # 快照当前固定 json 为 baseline 锚点（不跑）
python scripts/run_evals.py --list          # 列出 eval/results/ 下所有 run（含 baseline）及时间
```

- `--compare` 与 `--cross-model` 可叠加，均只影响 `mock_interview_eval.py` 的调用参数。
- 退出码：全部套件 ok → 0；有任一 ok=false → 1（便于 CI 感知）。

---

## 6. 边界情况

| 情况 | 处理 |
|---|---|
| 某套件未写 json（KB 空 / 校准 pending / 拆解失败） | 该套件 `ok=false`，summary 记错误摘要；其余套件照常；不写崩溃 |
| `.latest` 指向的上一轮目录缺失 | 跳过对比，comparison.md 写"无有效历史" |
| summary 中某指标缺失 | 对比表该格 `N/A`，不参与 Δ |
| 首次运行（无 `.latest`） | 仅归档，comparison.md 写"首次运行，无历史对比" + 本轮绝对值 |
| 重复运行 `--baseline` | 覆盖 `baseline/` 内容，幂等 |
| 同一秒并发运行 | 概率极低；run_id 精确到秒，若冲突后者覆盖前者目录（可接受，CI 串行） |

---

## 7. 测试

新增 `tests/test_run_evals.py`（沿用项目既有 222 单测体系）：

1. **`test_extract_summary_retrieval`**：喂入伪造 `retrieval_eval_results.json`，断言 `recall_at_5` 取对 k==5 条目、`total_noise` 正确。
2. **`test_extract_summary_mock`**：喂入含 `rubric`/`legacy` 两种 mode 的 json，断言 `by_mode` 映射正确。
3. **`test_extract_summary_llm_judge`**：断言 `real_category_accuracy` 取自人工校准字段。
4. **`test_build_comparison`**：两个最小 summary dict → 断言 Δ 计算、方向判定（↑/⚠️/—）、缺失值 `N/A`。
5. **`test_latest_pointer`**：连续两次 run 后 `.latest` 指向最新 run_id；`--baseline` 后指向 `baseline`。
6. **集成（手动）**：先 `--baseline` 登记现有基线，再真实跑一次，确认 `comparison.md` 出现 6 行对比且 Δ 正确。

> 提取与对比逻辑（`extract_summary` / `build_comparison`）必须做成**不依赖 subprocess 的纯函数**，测试直接构造 dict 驱动。

---

## 8. 验收标准

- [ ] `python scripts/run_evals.py` 在现有环境下成功产生 `eval/results/{run_id}/`，内含 3 个原始 json + `summary.json` + `eval_run.log`。
- [ ] 第二次运行产生新的 `run_id` 目录，并生成 `comparison.md`，列出 6 项 headline 指标的 上次/本次/Δ。
- [ ] `python scripts/run_evals.py --baseline` 能把当前磁盘基线 json 登记为 `baseline/`，使后续真实 run 立刻有 BEFORE→AFTER。
- [ ] `--compare` / `--cross-model` 正确透传给 `mock_interview_eval.py`（summary 中出现对应 mode）。
- [ ] 3 个现有 eval 套件**零修改**（diff 为空）。
- [ ] `tests/test_run_evals.py` 通过，且未破坏既有 222 单测。
- [ ] 任一 eval 失败时整体不崩溃，退出码为 1，summary 标记 `ok=false`。

---

## 9. 落地后的使用节奏（给简历供料）

1. 先跑一次 `--baseline`，把现有数字（Recall@5=70.4% 等）钉死为锚点。
2. 做 ②（Bad Case 归因）或 ③（BM25+RRF）的改动后，跑 `python scripts/run_evals.py`。
3. 直接读 `comparison.md` 的 Δ，作为简历 BEFORE→AFTER 数据来源（例："混合检索后 Recall@5 70.4%→82.1%"）。
4. 每个大改动 commit 前跑一次，历史归档即"评估闭环"的物证。
