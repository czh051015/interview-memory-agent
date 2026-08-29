# mock 修改计划书 · 从「模拟面试官」到「申论练习会话引擎」

> 配套：docs/15（错题回流+ReAct 主线）、docs/16（cleaner 计划书）、docs/17（memory 计划书）
> 定位：mock 不再模拟面试，而是申论主闭环的**交互外壳**——题库抽题、一次一题、答案逼近、断点续练、复盘回流。
> 一句话：**"考察你" → "陪你练"。**

---

## 0. 一句话目标

**把 mock 从"LLM 面试官出题+追问+判定表现"的场次模型，重定位为"抽题 → 作答 → 评分 → 逼近引导（循环）→ 回流 → 下一题"的练习会话模型，复用断点/循环骨架，替换出题源/判官/写回。**

这条交互链正是 docs/15 主线闭环缺的最后一环——之前所有模块（score/reflow/profile/react）是引擎，mock 是驾驶舱。

---

## 1. 现状盘点（基于真实代码）

| 文件 | 当前职责 | 面试域 | 申论处置 |
|---|---|---|---|
| `cli.py` | `main()`：读简历/JD/薄弱项 → 章节化出题 → 动态循环 → 行为总结 → 写回 → 复盘报告 | 整场面试编排 | 🔴 **重写**为练习会话主循环 |
| `runtime.py` | `decide_next`/`generate_dynamic_question`（LLM 现场出题）、`interview_one`（多轮追问）、`run_dynamic_session`（章节状态机）、`_progress_file` 断点、`recover` | 动态面试状态机 | 🟡 **复用骨架**：interview_one 循环 + 断点机制保留，出题/追问逻辑替换 |
| `judge.py` | `get_expected_points`/`judge_followup`（LLM 判官：期望要点+追问+单轮判定） | 考察用户 | 🔴 **替换**为 `score_answer`（确定性评分）+ 逼近引导 prompt |
| `writeback.py` | `apply_verdict`：写 knowledge_store（掌握度/行为标签/review_log） | 面试域写回 | 🔴 **替换**为 `reflow_answer`（申论域写回） |
| `plan.py` | `plan_interview`：读简历/JD 出章节计划 | 面试域 | ⚫ **不复用**（申论不按章节出题，按 ReAct 推荐/题库抽） |
| `report.py` | `summarize_behaviors`/`generate_review_report`：行为特征+复盘 | 面试域 | ⚫ **不复用**（申论复盘 = 命中/漏点清单，确定性输出） |
| `prompts.py` | 10 个面试 prompt 常量 | 面试域 | 🔴 **重写**：新增逼近引导 prompt，删面试 prompt |
| `__main__.py` | CLI 直跑入口（`--space`/`--recover`） | 通用 | 🟢 **保留**（入口语义不变，换内部实现） |

**判断**：`runtime.py` 的循环+断点骨架（`interview_one`/`_progress_file`/`recover`）是 domain 无关的资产，**直接复用**；其余全部围绕"考察"逻辑的，替换为"陪练"逻辑。

---

## 2. 前置尾巴（先收，否则 mock 改造跑不通）

动手前必须修完两个已知问题：

| # | 问题 | 现状 | 修法 |
|---|---|---|---|
| 1 | `scripts/run_shenlun.py` import `graduate_hits` 但 reflow.py 没有此函数 | 上一轮 memory 改造写的是单点版 `mark_graduated(conn, qid, pid)`，脚本要的是批量版 | reflow.py 补 `graduate_hits(qid, hit_ids, cand_keys)`：命中的点在毕业考候选里 → 标毕业 → 返回已毕业 id 列表 |
| 2 | `tests/test_shenlun_memory.py` 8 个失败 | `dict(r)` 报错：测试里 `sqlite3.connect` 没设 `row_factory=sqlite3.Row` | 测试 `_row`/`_answer` 辅助函数补 row_factory |

> 这两个不修，`run_shenlun.py --demo` 直接崩，mock 改造后也无法验证毕业考。

---

## 3. 目标交互：练习会话循环

```
抽题（ReAct 推荐优先 / 题库） → 作答（提交） → 评分（传感器判 hit/miss）
    ↑                                         │
    │           未达标（≤3 轮内）              ▼
    └── 逼近引导（提示漏点+材料位置） ←── 达标?───
                                                │ 达标 或 轮次上限
                                                ▼
                             回流（终稿入库 + 每轮轨迹 + 弱点更新）
                                                │
                                                ▼
                          自动抽下一题 · 随时退出 → 断点续练
```

**一次练习 = 一道题的一次完整逼近过程**，用户主动退出才结束会话。

---

## 4. 逐文件改造方案

### 4.1 `prompts.py` —— 重写为逼近引导（🔴 核心）

新增 `_APPROACH_PROMPT`（替代 judge 的追问 prompt）：

```
你是申论陪练。用户写了一段作答，漏了若干采分点。
对每个漏掉的点，给出引导：点名称 + 材料里可引用的内容位置。
要求：
- 不直接给答案、不代写句子（红线），只提示"漏了什么 + 去哪里找"
- 一次只引导最关键的 1-2 个漏点（引导太多用户记不住）
- 输出 JSON：{"guidance": [{"point": "设施互通", "hint": "材料第4段有城际公交，想想公共服务互通"}]}
```

**输入**：题目 + 材料 + 用户最新作答 + 漏点列表（来自 score_answer）。
**输出**：引导提示列表。命中率达标或轮数上限 → 不再调 LLM，直接回流。

### 4.2 `runtime.py` —— 复用循环骨架，替换核心逻辑（🟡）

| 保留（复用） | 替换 |
|---|---|
| `interview_one` 的多轮循环结构 | 判定从 `judge_followup`（LLM）→ `score_answer`（确定性） |
| `_progress_file` 断点落盘 | 进度文件内容：当前题 id + 轮次 + 每轮答案（续练用） |
| `recover` 断点恢复 | 恢复后回到"上一题第 N 轮"而非"整场面试" |
| KeyboardInterrupt 退出保护 | 同左 |

新增 `practice_one(question, material, points, ask_fn, max_rounds=3)`：

```
轮1：用户提交 → score_answer → 达标? → 回流
      未达标 → 逼近引导（LLM）→ 用户补充
轮2..N：同轮1（累加答案）→ 达标 或 轮数上限 → 回流
每轮落盘（断点续练）
```

### 4.3 `judge.py` —— 不再需要，废弃（🔴）

判定职责被 `score_answer`（确定性，不调 LLM）+ 逼近引导 prompt（LLM 只做提示，不做判断）取代。文件标记废弃，删除前确认无测试引用（`test_mock_*` 系列需同步清理）。

### 4.4 `writeback.py` —— 写回目标切换（🔴）

`apply_verdict`（写面试 knowledge_store）→ 改为调用 `reflow_answer`（写申论 answers/weak_points/events）+ 逼近轨迹写 `answer_rounds`（见 §5）。`writeback.py` 可作为薄封装保留，内部换实现。

### 4.5 `cli.py` / `__main__.py` —— 主循环重写（🔴 / 🟢）

`main()` 新流程：

```
1. 读断点（有未完成 → 询问续练 or 重新开始）
2. 抽题：react.decide() 推荐优先；推荐失败/无档案 → 题库随机
3. practice_one() 循环：作答 → 评分 → 逼近 → 达标/上限
4. reflow_answer 回流 + answer_rounds 轨迹
5. 打印本次命中/漏点清单（确定性复盘，替代 LLM 报告）
6. 循环 2-5，直到用户输入退出
```

`__main__.py` 的 `--space`/`--recover` 参数保留不动。

### 4.6 `plan.py` / `report.py` —— 废弃（⚫）

申论不需要章节计划和行为特征报告。标注废弃，删除时清理测试引用。

---

## 5. 表结构变更：新建 `answer_rounds`（docs/16 讨论过，一直没建）

逼近轨迹表——**一次练习 1 行 answers + N 轮 N 行 answer_rounds**（分离原因：混在一起会让 weak_points 统计被重复计数污染）：

```sql
CREATE TABLE IF NOT EXISTS answer_rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    answer_id INTEGER NOT NULL,        -- 关联 answers.id
    round_no INTEGER NOT NULL,         -- 0=初稿, 1..N=每轮逼近
    answer TEXT NOT NULL,              -- 该轮答案
    hit_ids TEXT NOT NULL DEFAULT '[]',
    miss_ids TEXT NOT NULL DEFAULT '[]',
    hit_ratio REAL NOT NULL DEFAULT 0,
    guided_point_ids TEXT NOT NULL DEFAULT '[]',  -- 该轮 AI 引导了哪些点
    ts TEXT NOT NULL
);
```

**配套**：`answers` 补 2 列（`rounds` 总轮数、`initial_hit_ratio` 初稿命中率——算逼近增益用）；`weak_points` 补 `guided_count`/`rescue_rounds_sum`（docs/17 的 `guided_rounds_weight` 数据源，本阶段可先留 0）。

---

## 6. 实施顺序（每步独立可验收）

| 步 | 改动 | 文件 | 验收标准 |
|---|---|---|---|
| 0a | 补 `graduate_hits` + 修 memory 测试 | `reflow.py`、`test_shenlun_memory.py` | `run_shenlun.py --demo` 跑通；pytest 全绿 |
| 0b | 建 `answer_rounds` 表 + answers 补列 | `reflow.py` | 老库迁移后数据不丢 |
| 1 | 重写 `prompts.py`（逼近引导 prompt） | `prompts.py` | 真实 LLM 试跑：输出合法 JSON，不代写句子 |
| 2 | `practice_one()` 循环 + 断点改造 | `runtime.py` | 单测：3 轮内达标/超轮次上限两种出口；退出后恢复 |
| 3 | 主循环重写（抽题→练习→回流→循环）| `cli.py` | 交互演练：练 1 题走通全链；退出后可续练 |
| 4 | 清理废弃文件（judge/plan/report 引用）| `mock/`、tests | pytest 全绿（同步删/改死测试）|

**建议节奏**：0a+0b 一次做完（都是数据层）；1+2 一起（逼近核心）；3+4 一起（编排+清理）。

---

## 7. 风险与规避

| 风险 | 规避 |
|---|---|
| **逼近引导代写答案**（LLM 忍不住给整句） | prompt 红线 + 测试断言"guidance 不含参考答案片段"；引导只给点+位置 |
| **mock 现有测试大量引用旧逻辑**（test_mock_*） | 第 4 步统一清理；删除文件前 grep 引用，避免死测试（过往教训：漏删死测试导致 pytest 6 失败） |
| **断点续练语义变化**（从"整场面试"→"单题第 N 轮"） | 进度文件结构显式版本化（加 `v: 2` 字段），旧文件读失败 → 提示重新开始而非静默崩 |
| **抽题无档案时的冷启动**（react.decide 无数据） | 降级：题库随机抽题（run_shenlun 现有逻辑） |
| **逼近轮次上限后用户仍不会** | 正常回流（按当前命中率入档），漏点进 weak_points 等着被 ReAct 安排重练/补知识——闭环自洽 |

---

## 8. 面试讲点

1. **"我把模拟面试重定位成了练习会话"**：不是删功能，是换语义——从"LLM 考察你"到"系统陪你练"，复用循环/断点骨架，替换判定核心
2. **评分和引导分离**：评分是确定性传感器（可 benchmark），LLM 只做"提示漏了哪个点"——守住可验证性，又保留 Agent 主动性
3. **逼近 = 踩点层引导，不是语言层改写**：竞品（腾讯教育AI作文/驰声）全在作文语言层改表达；申论有客观金标，每轮逼近可用 hit/miss 验证——这是差异化
4. **断点续练 + 随时退出**：对齐"在职碎片化备考"画像（通勤 15-30 分钟），不是整块时间产品
5. **轨迹入档案**：`answer_rounds` 记录"第几轮补上哪个点"——这是 docs/17 `guided_rounds_weight`（记忆问题 vs 理解问题）的数据来源，整套记忆机制终于有输入了

---

## 9. 待确认事项

- [ ] mock 模块是否改名（`src/mock` → `src/practice`？改名的 import 波及面 vs 语义清晰度）
- [ ] 逼近轮次上限默认 3 轮是否 OK（碎片化场景下轮次多会拖时间）
- [ ] 达标阈值（命中率 ≥ 0.8？）——与 docs/15 的"漏点识别"语义对齐即可，参数待校准
- [ ] 断点文件兼容：旧版 interview_progress.json 直接提示重新开始，还是要做迁移
