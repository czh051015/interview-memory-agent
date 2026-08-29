# 开发计划书：Eval 申论化改造与回归基线

> 版本：v1 · 2026-08-29 · 作者：产品通（与 hw 共建）
> 衔接：docs/13（point_type，已落地）、docs/15（错题回流+ReAct）、docs/16/17/18（cleaner/memory/mock 改造，均已落地且 pytest 281 全绿）
> 触发：13 修好后跑回归，发现 **4 个 eval 套件里 3 个测的是面试域旧链路**（retrieval/mock_interview/llm_judge），申论域只有 score_eval 一个——eval 体系必须跟着产品一起申论化。
> 性质：**只写计划书，不执行**（本计划不跑任何 eval，改造完成后再登记新 baseline）。

---

## 1. 目标

1. **4 个 eval 套件全部处置**：1 保留升级（score_eval）+ 2 改造（llm_judge→拆解评测、mock_interview→引导评测）+ 1 删除（retrieval_eval），彻底移除面试域残留。
2. **新 baseline**：改造完成后先跑一遍申论域套件，结果登记到 `eval/results/baseline`，作为后续回归对比锚点（沿用 `run_evals.py --baseline` 机制）。
3. **补齐 run_evals.py 的 gap**：现 SUITES 只有 3 套件、**漏了 score_eval**（申论域唯一的老 eval），改造后统一纳入。
4. **被测数据选型留待讨论**：本计划不拍板数据，§9 给出候选方案供 hw 决策。

一句话交付：**eval 从「面试时代的 3+1」收敛为「申论时代的 3」，且跑一遍就能拿到可作为简历 BEFORE 锚点的 baseline。**

---

## 2. 现状盘点（逐文件，基于真实代码）

| 套件 | 文件 | 被测对象 | 样本（ground truth） | 指标 | 域 |
|---|---|---|---|---|---|
| ① 检索质量 | `eval/retrieval_eval.py` | `src/memory/knowledge_store` 向量检索 | `eval/annotations.py`：20 条技术面试题标注（Agent/RAG/线程池…） | Recall@k / Precision@k / 噪音 | **面试域** |
| ② 阅卷判别 | `eval/mock_interview_eval.py` | `src/mock/judge.judge_single_round`（四模式消融 A/B/C/D） | `eval/samples/answers.json` + `questions.json`：11 道人工定题 + LLM 生成 4 类答案 | discrimination / order / no_fool / question_pass | **面试域** |
| ③ 拆解质量 | `eval/llm_judge_eval.py` | `src/cleaner.decompose.decompose`（面试复盘→结构化错题） | `data/seed/agent_dev_interview.txt`：27 题口语化复盘 | category 准确率 / topic 准确率（LLM-as-judge + 人工校准 4 条） | **面试域** |
| ④ 评分传感器 | `eval/score_eval.py` | `src.shenlun.score.score_answer` / `from_benchmark` | `benchmark/data/*.json`：36 题（河南 2024/2025 + 江苏 2019/2022/2023，official+training 金标），每题 good/bad 两档 | discrimination / no_fool / per-type | **申论域** ✅ |

**关键事实**：
- `benchmark/eval/eval_run.py` 是 benchmark 自带的极简引擎（README 说 14 道，实际 `benchmark/data` 已扩到 **36 道**，README 是 v1 老文档未更新）；`eval/score_eval.py` 是它的升级版（带 per-type 分组、--only、--out），两者并存，改造时以 score_eval 为准。
- 2026-08-29 已实测：pytest **281 passed 全绿**；score_eval **36 题 no_fool=1.000 / discrimination=0.899**（提出对策 1.0、综合分析 0.951、归纳概括 0.929、应用文 0.788；唯一瑕疵 jiangsu_2025_a_3 的 good 命中<0.8）。这些就是新 baseline 的预期锚点。
- 申论域三条链路都已具备可评测对象：**评分**（score_answer）、**拆解**（`decompose_points`，src/cleaner/decompose.py:153）、**逼近引导**（`_APPROACH_PROMPT`，src/mock/prompts.py:12）。
- `benchmark/data` 36 题的 `gold.reference_points` 就是现成的权威 ground truth——拆解评测不需要另造数据（§4.2 用）。
- `run_evals.py` 的 SUITES/HEADLINE/extract_summary/build_comparison 全部硬编码了 3 个旧套件名与字段，改造必动；`tests/test_run_evals.py` 同样全引用旧字段，需同步重写。

---

## 3. 改造决策总览

```
改造前（4 文件，3 面试 1 申论）                改造后（3 文件，全申论）
┌──────────────────────────────┐             ┌──────────────────────────────┐
│ ① retrieval_eval.py  面试检索 │ ──删除──▶   │（无对应物：申论域不用向量检索）│
│ ② mock_interview_eval.py     │             │                              │
│    面试判官判别              │ ──改造──▶   │ ② guidance_eval.py 引导质量   │
│ ③ llm_judge_eval.py 面试拆解 │             │                              │
│                            │ ──改造──▶   │ ③ decompose_eval.py 拆解质量  │
│ ④ score_eval.py 申论评分     │             │                              │
│                            │ ──保留升级─▶ │ ④ score_eval.py 评分传感器     │
└──────────────────────────────┘             └──────────────────────────────┘
```

| # | 文件 | 处置 | 理由 |
|---|---|---|---|
| ① | `eval/retrieval_eval.py` | **删除** | 申论域 D1（docs/13 §4）明确否决向量检索打标；`search_questions` 是确定性过滤（pytest 单测已覆盖 `tests/test_shenlun_react.py`），无独立 eval 需求；语义检索（练同类题推荐）属 Phase D 未做，届时再建 |
| ② | `eval/mock_interview_eval.py` | **改造 → guidance_eval** | mock 已重定位为练习会话（docs/18），判官换成确定性的 score_answer（被 ④ 覆盖）；LLM 残留职责只剩「逼近引导」，正是需要评测的 Agent 主动性部分 |
| ③ | `eval/llm_judge_eval.py` | **改造 → decompose_eval** | decompose_points 是申论入库地基（docs/16），16 号计划书 §5 步 1 的验收标准「点覆盖≥80%、无臆造点」应自动化成 eval |
| ④ | `eval/score_eval.py` | **保留 + 升级** | 已是申论域核心；升级点 = 纳入 run_evals + 文件名与输出对齐新 SUITES 规范 |

**改造后 run_evals SUITES（3 套件）**：

| 顺序 | 套件名 | 脚本 | 固定 json | 是否需要 LLM |
|---|---|---|---|---|
| 1 | `score` | `eval/score_eval.py` | `score_eval_results.json` | 否（确定性，秒级）|
| 2 | `decompose` | `eval/decompose_eval.py` | `decompose_eval_results.json` | 是（拆解 1 次/题）|
| 3 | `guidance` | `eval/guidance_eval.py` | `guidance_eval_results.json` | 是（引导 1 次/样本）|

---

## 4. 逐套件改造方案

### 4.1 `score_eval.py` —— 保留升级（🟢 低改动）

**现状已达标，不做结构性改动**，只做三处升级：

| # | 升级点 | 说明 |
|---|---|---|
| 1 | 纳入 run_evals | 加进 SUITES（这是本次最重要的修正——之前跑"全套 evals"永远覆盖不到申论核心） |
| 2 | 输出字段稳定化 | 确认 `score_eval_results.json` 顶层含 `data_count`/`n_points`/`mean_discrimination`/`no_fool`/`per_type`，供 extract_summary 扁平化；必要时补 `per_type` 到 summary |
| 3 | 题型缺口 | README 明确缺「提出对策」外的题型均衡（当前 36 题已含提出对策且 disc=1.0，无紧迫性）；是否补题归入 §9 数据讨论 |

**门槛（沿用 2026-08-28 拍板的评分降级方案）**：`no_fool == 1.0`（硬门槛）+ discrimination 越高越好（当前 0.899）；不追 MAE。

### 4.2 `decompose_eval.py` —— 新（由 llm_judge_eval 改造，🔴 核心新增）

**评测对象**：`src.cleaner.decompose.decompose_points`（LLM 拆标准答案 → ReferencePoint[]）。

**ground truth 零新增成本**：直接用 `benchmark/data/*.json` 的 `gold.reference_points`（official 金标 = 权威答案）。对每道题：
1. 把 `task.question/material/requirements` + `gold` 的标准答案全文喂给 `decompose_points`
2. 拿 LLM 拆出的点 vs 官方金标点做对照

**指标（对齐 16 号计划书 §5 步 1 验收标准，量化版）**：

| 指标 | 口径 | 门槛（初值，待校准） |
|---|---|---|
| **点覆盖率 recall** | LLM 拆出的点命中官方金标点的比例（关键词交集判定，同 score 的 hit 逻辑） | ≥ 0.80 |
| **臆造点率 fabrication** | LLM 拆出但官方金标没有、且 keywords 无法对到金标任何点的比例 | ≤ 0.10（人工复核兜底）|
| **结构合法性** | JSON 可解析、point≤8 字、keywords 出自原文（程序可验部分） | 100% |
| **分值合理性** | 各点 score 之和 vs max_score 偏差 | 报告不设门槛（提示人审核对）|
| **点数量合理性（防注水）** | 拆出点数 > 12（16 号计划书 §3.1 数量约束 3-8，允许 2 的特例；>12 即疑似把一个点拆成多个近义点刷覆盖率）| 超出区间题数 == 0（超出即标记"疑似注水拆分"，人工复核）|
| **脏标答鲁棒性** | 人工造脏标答 5-8 道（残缺 2 / 口语化 2 / 抄错 2），断言：拆出点数 < 金标点数一半 且 warnings 含"疑似标答过简" | == 1.0（全过——这是行为验证不是程度度量，样本覆盖类型即可）|

> **评测数据规模原则（面试可讲）**：好的那档 = 金标对照（36 题全量），测的是**正确性**（逐题累加，样本越多结论越硬）；坏的那档 = 脏标答（分类型小样本），测的是**行为模式**（LLM 对烂输入会不会预警，5-8 道即饱和）。全量好的 + 分类型小样本坏的，数据成本花在类型多样性而非数量堆砌。

**实现要点**：
- 拆解是温度 0 的结构化任务，但仍是 LLM 输出 → 36 题金标对照 + 6-8 道脏标答 ≈ 42-44 次调用，可接受（原 llm_judge 是 27 题）。
- 保留原 llm_judge 的 **LLM-as-judge + 人工校准** 骨架：抽样 N 条（如 8-10 条）让裁判 LLM 复核"漏拆/错拆/臆造"，人工抽 3-4 条校准裁判本身的准头（仿 `HUMAN_CALIBRATION` 模式，原文件 2026-08-17 的校准结论随面试域一起废弃）。
- 产出：`decompose_eval_results.json`，顶层含 `decomposed_count`/`point_recall`/`fabrication_rate`/`structural_ok`/`over_split_flags`（注水标记题数）/`dirty_robustness`（脏标答通过率）/`calibrated`。

### 4.3 `guidance_eval.py` —— 新（由 mock_interview_eval 改造，🔴 核心新增）

**评测对象**：`src.mock.prompts._APPROACH_PROMPT`（逼近引导，docs/18 §4.1）——LLM 只提示「漏了什么 + 去哪里找」，不代写。

**样本**：用 `benchmark/data/*.json` 的 `samples.bad`（跑题答）+ 该题 gold 金标。跑题答必然漏点 → 漏点集合已知（gold 中 bad 未命中的点）。

**指标（两类：红线 + 质量）**：

| 类别 | 指标 | 口径 | 门槛 |
|---|---|---|---|
| **红线（必须）** | `no_spoiler` | 引导输出不含金标原文原句/关键词（程序比对 hint 文本 vs gold keywords+point 文本） | == 1.0（代写即失败，18 号计划书 §7 风险 1 的自动化） |
| **红线（必须）** | `no_fabrication` | hint 指向的 `point_id` 必须 ∈ 该题真实漏点集（不引导已命中的点、不引导金标没有的点） | == 1.0 |
| 质量 | `hint_grounded` | hint 提到材料位置/事例（含材料特有名词），而非空话 | ≥ 0.8 |
| 质量 | `judge_score` | LLM-as-judge 对"引导有用性"打分（1-5），人工抽验裁判 | 报告，门槛待校准 |

**实现要点**：
- 每样本 1 次 LLM 调用；bad 作答按题型抽样（每种题型 3-4 条，覆盖四题型）。
- 对齐 18 号计划书红线：prompt 里已写「不得写出参考答案原句或关键词」，eval 就是这条红线的守护者。
- 产出：`guidance_eval_results.json`，顶层含 `sample_count`/`no_spoiler`/`no_fabrication`/`hint_grounded`/`judge_score`。

### 4.4 `retrieval_eval.py` —— 删除（⚫）

**删除理由**（写进 README 或本计划书留档）：
1. 被测对象 `knowledge_store` 向量检索是**面试域**资产；申论域评分/拆解/引导/回流全链路不经过向量库。
2. docs/13 §4 D1 明确否决"向量检索做 point_type 打标"；`search_questions` 的角度/题型过滤是确定性 SQL 过滤，已由 pytest 覆盖（`tests/test_shenlun_react.py::TestSearchQuestions`）。
3. 未来的语义检索（练同类题推荐，docs/13 §11 Phase D）落地时，再以当时的实现新建检索 eval，不为空转的框架留死文件。

---

## 5. `scripts/run_evals.py` 更新

| 位置 | 改动 |
|---|---|
| `SUITES` | `[("retrieval",…),("mock_interview",…),("llm_judge",…)]` → `[("score", "eval/score_eval.py", "score_eval_results.json"), ("decompose", "eval/decompose_eval.py", "decompose_eval_results.json"), ("guidance", "eval/guidance_eval.py", "guidance_eval_results.json")]` |
| `HEADLINE`（6 项对比指标） | 检索 Recall@5 → **评分 no_fool**；阅卷 discrimination → **拆解点覆盖率**；阅卷 strict_order → **拆解臆造点率**（方向 ↓）；阅卷 no_fool → **引导 no_spoiler**；阅卷 question_pass → **引导 hint_grounded**；拆解 category → **评分 discrimination**（顺序可按优先级重排） |
| `labels` | `mock_compare`/`mock_cross` 字段删除（那是四模式消融的遗产），改为可扩展的 `llm_calls` 计数或不设 |
| `extract_summary` | 重写三个套件的扁平化逻辑（对齐 §4 各产出 schema） |
| `build_comparison` | HEADLINE 改后自动生效；注意臆造点率/红线类指标方向是 **↓**（`delta<0` 标 ✅），需在路径定义里带方向标记 |
| `--compare`/`--cross-model` | 删除（四模式消融的遗产，申论域无对应） |
| `--baseline` | **机制保留不动**——改造完成后 `python scripts/run_evals.py --baseline` 快照当前 3 个 json 到 `eval/results/baseline/` |

---

## 6. 删除与清理清单（文件级）

| 文件 | 处置 | 波及 |
|---|---|---|
| `eval/retrieval_eval.py` | 删 | `run_evals.py` SUITES |
| `eval/mock_interview_eval.py` | 删（被 guidance_eval 取代） | 同上 |
| `eval/llm_judge_eval.py` | 删（被 decompose_eval 取代） | 同上 |
| `eval/annotations.py` | 删（检索 ground truth，纯面试域） | 无 |
| `eval/samples/answers.json` | 删（阅卷样本，纯面试域） | 无 |
| `eval/samples/questions.json` | 删（判官 eval 人工定题） | 无 |
| `eval/samples/generate_samples.py` | 删（LLM 生成 4 类判官答案的脚本，纯面试域） | 无 |
| `data/seed/agent_dev_interview.txt` | 删（llm_judge 拆解样本，纯面试域） | 无 |
| `eval/retrieval_eval_results.json` / `mock_interview_eval_results.json` / `llm_judge_results.json` | 删（旧结果，面试域；历史归档已在 eval/results/ 下留存，不丢） | 无 |
| `tests/test_run_evals.py` | **重写**（不是删——extract_summary/build_comparison 的纯函数测试框架保留，字段全换） | 见 §7 |
| `eval/results/baseline/` + `.latest` | **保留**，改造后重新登记 | — |

> 删除纪律（项目教训）：删文件用 `rm -f`/`rm -rf` + `git add -A`，**不要用 `git rm`**（本环境不可靠）；删完跑 pytest 全量确认无死测试引用。

---

## 7. 测试计划（`tests/test_run_evals.py` 重写）

保留纯函数测试框架（extract_summary / build_comparison 不依赖 subprocess），替换字段与用例：

| 测试 | 覆盖 |
|---|---|
| `test_extract_summary_score` | 喂伪造 `score_eval_results.json` → 断言 `no_fool`/`mean_discrimination`/`data_count` 抽取正确 |
| `test_extract_summary_decompose` | 断言 `point_recall`/`fabrication_rate`/`decomposed_count` |
| `test_extract_summary_guidance` | 断言 `no_spoiler`/`no_fabrication`/`hint_grounded` |
| `test_build_comparison_direction` | **新增方向断言**：↑ 类指标 Δ>0 标 ✅；↓ 类指标（臆造点率）Δ<0 标 ✅ |
| `test_missing_json_marks_fail` | 3 个新套件任一 json 缺失 → ok=false |
| `test_latest_pointer` | `--baseline` 后 `.latest` 指向 baseline（沿用现有逻辑） |

**验收**：改造后 `pytest` 全量全绿；`run_evals.py --list` 正常；删除清单中无文件仍被 src/tests 引用（grep 兜底）。

---

## 8. Baseline 登记流程（本计划的目标产出）

```
第 1 步（实施）: 按 §4 改造 3 套件 + §5 更新 run_evals + §6 清理 + §7 重写测试
第 2 步（回归）: python -m pytest tests/ -q          → 全绿
第 3 步（首跑）: python scripts/run_evals.py           → 跑 3 套件，产生 eval/results/{run_id}/
第 4 步（锚点）: python scripts/run_evals.py --baseline → 把本轮 3 个 json 快照登记为 eval/results/baseline/
                 （注意顺序：先真实跑一次拿到完整 json，再 --baseline 快照，
                  与 docs/04 的原始流程一致；也可直接 --baseline 快照首跑结果）
第 5 步（验证）: 读 baseline/summary.json，确认 3 套件 ok + 指标在门槛内
```

- **baseline 内容（预期锚点）**：score（no_fool=1.0、disc=0.899 已有实测）；decompose / guidance 为首轮绝对值（无历史对比，comparison.md 写"首次运行"）。
- 之后的每次回归（改 prompt/拆解/引导）跑 `python scripts/run_evals.py` 即与 baseline 对比，产出 BEFORE→AFTER 物证。

---

## 9. 待确认事项（重点：被测数据选型）

> hw 拍板项。本计划刻意不预设，以下为候选方案 + 推荐。

| # | 事项 | 候选 | 推荐 |
|---|---|---|---|
| 1 | **score_eval 数据** | A. 沿用 benchmark/data 36 题（河南+江苏，official+training）B. 扩充：补「提出对策」更多题 / 加省份（国考、其他省）| **A**（已达标，别动数据源；扩充属于后续加题，不阻塞 baseline）|
| 2 | **decompose_eval 数据** | A. **全量好的 + 分类型小样本坏的**：36 题金标对照（good 全量，零新增成本）+ 5-8 道人工脏标答（残缺 2 / 口语化 2 / 抄错 2，行为验证）B. 只做金标对照，不做脏标答 C. 另建"拆解专用"人工标注集 | **A**（金标对照保证"每题拆得准"的全量证据；脏标答覆盖真实用户上传劣质标答的场景；§4.2 已含两档的指标与断言）|
| 3 | **guidance_eval 样本** | A. 36 题的 samples.bad（跑题答，漏点已知）B. 人工写几个"半吊子答"（部分命中，更贴近真实用户）C. 两者混合 | **C**（bad 全漏太极端，真实用户是漏一半；bad 保底 + 少量人工半吊子答增强 realism）|
| 4 | **sample 规模** | decompose：全 36 题 vs 抽样 15-20 题；guidance：每题型 3-4 条 vs 全部 | 先按推荐规模（decompose 全量 36 / guidance 每题型 3-4 条共 12-16 条），成本可控且数字稳定 |
| 5 | **门槛初值** | 拆解点覆盖≥0.80、臆造≤0.10、点数量注水标记>12、脏标答鲁棒性==1.0、红线类==1.0（本计划 §4 的初值）| 先按初值落地，首轮跑完看实际分布再校准（对齐项目"参数先定结构、数字跑起来再调"惯例）|
| 6 | 删除面试样本后，`data/seed/` 里的 `interview.txt`/`my_feedback.csv` 等是否一并清 | A. 只删 eval 直接依赖的（agent_dev_interview.txt）B. 面试域 seed 全清 | **A**（`data/seed` 是数据目录不是 eval 目录，interview.txt 可能被其他脚本引用，grep 后再定）|
| 7 | mock_interview 旧结果 json 是否从工作区删除 | A. 删（历史在 eval/results/ 归档）B. 留 | **A** |

---

## 10. 风险与规避

| 风险 | 概率 | 规避 |
|---|---|---|
| 改造后 run_evals 首次跑 LLM 套件（decompose/guidance）慢或挂 | 中 | 两个 LLM 套件共 ~50 次调用，超时重试机制沿用原 llm_judge；任一失败不中断其余（run_evals 已保证）|
| 拆解评测的"点覆盖"判定口径模糊（LLM 拆的点 vs 金标点如何算命中） | 中 | 复用 score 的 hit 判定（keywords 交集），先按宽松口径（任一 keyword 命中即算覆盖）；若分布过差再收紧 |
| guidance 红线误报（LLM 没代写但 hint 含了金标词） | 中 | no_spoiler 判定按"整句/关键词串"比对而非单字；误报案例人工复核后调判定规则 |
| 删除面试文件引发死测试（历史教训：漏删导致 pytest 6 失败） | 低 | 删除后 grep 全仓引用 + pytest 全量回归（§6 纪律）|
| README（benchmark v1 说 14 道、实际 36 道）与新 baseline 数字不符 | 低 | 顺手更新 benchmark/README.md 数据总览为 36 道 |
| eval 目录与 benchmark/eval/eval_run.py 双引擎并存造成口径混乱 | 中 | 明确以 `eval/score_eval.py` 为唯一权威（README 补一句指向），eval_run.py 保留作极简参考 |

---

## 11. 面试讲点（这轮改造能讲什么）

1. **"我把评测体系跟着产品一起迁移了"**：产品从面试错题本 → 申论 Agent，eval 从「3 面试 + 1 申论」收敛为「3 全申论」——不是技术债务，是产品演进的同步治理。
2. **删检索 eval 是有意识的决策**：D1 否决向量检索打标 → 检索层没有评测必要 → 删除而非留空壳。面试官问"为什么删 eval"，答"删的是不再被信任的评测，不是评测本身"。
3. **拆解评测零新增成本**：官方金标 benchmark 直接当 ground truth，LLM 拆解 vs 金标对照 = 16 号计划书「点覆盖≥80%、无臆造点」验收标准的自动化——人审闸门（cleaner）与评测闸门（eval）同一套信任逻辑。
4. **引导评测守护红线**：mock 重定位后 LLM 只剩"提示漏了什么"，no_spoiler/no_fabrication 两条红线自动化——"我知道 LLM 会忍不住代写，所以我写了个 eval 盯着它"。
5. **baseline 是简历证据**：改造完跑一遍登记 baseline，之后每个 prompt 改动都有 BEFORE→AFTER 物证（docs/04 的"评估闭环"叙事延续）。

---

## 附：改造影响面速查

```
eval/retrieval_eval.py            ← 删除（面试域，无申论对应物）
eval/mock_interview_eval.py       ← 删除，改造为 eval/guidance_eval.py（引导质量）
eval/llm_judge_eval.py            ← 删除，改造为 eval/decompose_eval.py（拆解质量）
eval/score_eval.py                ← 保留升级（纳入 run_evals）
eval/annotations.py               ← 删除（检索标注，面试域）
eval/samples/answers.json + questions.json + generate_samples.py ← 删除（判官样本，面试域）
data/seed/agent_dev_interview.txt ← 删除（llm_judge 样本，面试域）
scripts/run_evals.py              ← SUITES/HEADLINE/extract_summary/build_comparison 重写
tests/test_run_evals.py           ← 字段替换 + 方向断言新增
eval/results/baseline/            ← 改造后重新登记（本计划目标产出）
benchmark/README.md               ← 数据总览 14 → 36 道 + 权威引擎指向
```
