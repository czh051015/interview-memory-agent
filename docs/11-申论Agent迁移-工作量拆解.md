# 11 · 申论 Agent 迁移 · 四层面工作量拆解

> 目的：按「功能 / 数据层 / 代码 / benchmark」四个层面，评估从「面试错题本」迁移到「申论刷题 Agent」各自的工作量，定位瓶颈。
> 依据：已读真实代码（schema.py / knowledge_store.py / mastery.py / mock/{plan,runtime,judge}.py / cleaner）。

## 结论速览（由重到轻）

| 排名 | 层面 | 工作量 | 性质 |
|---|---|---|---|
| 1 | Benchmark 数据集 | 🔴 最重 | 人工密集 + IP 风险 + 串行瓶颈 |
| 2 | mock 核心逻辑 | 🟠 重 | 大删除 + 重写判卷（减法） |
| 3 | 功能映射 | 🟡 中 | 偏设计，实现删多于写 |
| 4 | 数据层 schema | 🟡 中 | 加字段 + 改枚举 + 改两处序列化 |
| 5 | cleaner | 🟡 中 | 管线复用 + 重写映射 |
| 6 | memory | 🟢 最轻 | mastery 零改，store/remind 小改 |

---

## 1. 功能层：留 / 转 / 删

### 留（零改动，项目灵魂）
- **错题本 + 间隔重复内核**：`memory/mastery.py` 的 `decay / review / rank / layer` 是纯函数，只认 `status / mastery_score / 时间戳`，与"面试还是申论"无关。✅ 直接复用。
- **写回引擎**：`mock/writeback.py` 的 `apply_verdict` 把 (pass/partial/fail) 流转成 status + mastery 更新。申论判完分照样标 fail/partial/pass，逻辑通用。✅
- **考前提醒**：`run_remind.py` 按 gap 分层（🔴快忘了/🟡该看看/✅刚看过）。申论变成"按题型维度提醒复习"。引擎通用，改文案+维度。✅

### 转（质变，价值锚点）
- **「三者出题」（resume/JD/weak → LLM 生成章节题）** → **「真题库抽题」（按 题型/主题/年份 从 benchmark 确定性抽取）**。
  - 代码位置：`mock/plan.py:plan_interview`（30-56 行，LLM 生成 sections）。
  - 工作量其实是**下降**的：从"LLM 自由生成"变成"从已标注题库捞题"，确定性更强、更可控。
- **「动态追问」（decide_next 状态机 deep_dive/switch/next_section/end）** → 基本删除，退化为"答完给解析 + 推荐同类题"。面试官人格消失。
- **「判卷」（主观 LLM + 量规 + 第二判官）** → **「采分点比对」（客观/可验证）** 。
  - 这是整个迁移的**核心增益**：把最不可信的 LLM 主观判，换成最可信的 采分点命中比对。代码位置：`mock/judge.py`（19-123 行）。
  - 逻辑比原版**更简单确定**：采分点 = gold standard（来自 benchmark 标注），比对 = 关键词/语义匹配 + 可选 LLM 模糊匹配。
- **「面试报告」** → **「申论能力雷达/趋势报告」**。`mock/report.py` 重写。

### 删（面试专属，直接移除）
- resume/JD 解析（`mock/plan.py:_read_profile` 59-127 行）
- 面试官人格与追问决策树（`mock/runtime.py:decide_next` 20-54、`run_dynamic_session` 206-313）
- 行为画像 `behavior_tags`（"表达绕弯/回避问题"——申论无此概念，`schema.py:54-57`）

---

## 2. 数据层：结构化字段必须改（但引擎不动）

`KnowledgeItem`（`cleaner/schema.py:33-60`）现状字段与申论映射：

| 现状字段 | 面试语义 | 申论处置 |
|---|---|---|
| company / role / round | 公司/岗位/轮次 | 删或改 → province(省份)/year(年份)/paper(试卷) |
| question | 面试题 | 保留（= 申论题干） |
| answer | 参考答案 | **转义** → reference_points（结构化采分点，带分值权重） |
| question_type | 八股文/项目/场景/行为 | **改枚举** → 归纳概括/提出对策/综合分析/贯彻执行/应用文 |
| feedback | 面试官反馈 | 转 → 解析（命中/漏答采分点 + 改进建议） |
| behavior_tags | 行为画像 | 删 |
| material | —— | **新增**：材料原文（长文本，申论核心输入） |
| scoring_criteria | —— | **新增**：评分标准/分值分配 |

**改动点**：
- `schema.py` 加 `material / reference_points / scoring_criteria`，改 `question_type` 枚举，删 `behavior_tags` 或保留为空。pydantic 加字段很快。
- `knowledge_store.py:_to_metadata`（385-407）与 `_parse_results`（410-496）两处序列化要同步改（加新字段、改 company/role/round → province/year/paper）。
- `search()` 过滤维度（83-128 行）：company/role/round → type/province/year。
- **Chroma 引擎本身（embedding/upsert/query/去重）完全不动**。

**结论**：数据层改动是"加字段 + 改枚举 + 改两处序列化 + 改 search 过滤"，属于**中等偏低**工作量。但注意——**真实的重活在 benchmark 数据集本身（第 4 点），不是 schema**。

---

## 3. 代码层：cleaner / memory / mock 各自动多少

### memory（最轻，最大红利）
- `mastery.py`：**零改动**。✅（纯函数，与领域无关）
- `knowledge_store.py`：改 search 过滤字段 + 两处序列化。**低-中**。
- `memory_keeper.py` / `profile.py`：候选人画像 → 考生能力画像（按题型维度聚合）。`review_log.py` 通用。
- `run_remind.py`：改维度（题型）+ 文案。**低**。

### cleaner（中）
- 现状：`面经消化 Agent`——`decompose` 把面经 PDF → KnowledgeItem 列表（`cleaner/decompose.py`、`annotate.py`、`state_machine.py`）。
- 申论同样需要"消化"：真题 PDF（题干+材料+参考答案）→ 真题 item。
- **保留**：PDF 读文本管线（`plan.py:_read_pdf_text` 59-82，PyMuPDF→pypdf 回退）、去重（`knowledge_store.find_duplicates` 170-206）。
- **重写**：decompose prompt + 输出映射（面经题 → 真题 item，含 material/reference_points）。
- 工作量：**中**（管线复用，映射重写）。

### mock 核心（重，但方向是减法）
- `plan.py`：删 `plan_interview` + `_read_profile`，换成 真题抽取器（确定性）。**删除为主**。
- `runtime.py`：删 `decide_next` + `run_dynamic_session` + 断点恢复（面试专属状态机）。**大删除**。
- `judge.py`：重写判卷（采分点比对）。这是**新核心**，但比原"LLM 主观判 + 第二判官"更简单确定。
- `prompts.py`：删 10 个面试 prompt，写 2-3 个申论 prompt（采分点提取 / 答案比对 / 报告生成）。
- `writeback.py`：几乎不动（status 流转通用）。
- `report.py`：重写（能力雷达/趋势）。

**结论**：代码层**中等偏高**，但本质是"删状态机（大块删除）+ 把最不确定的判卷换成确定的（减法）+ 新 prompts + 报告"。记忆层几乎免费，这是好消息。

---

## 4. Benchmark：最主要、最重、串行瓶颈 ⚠️

这是"可验证" claim 的基石，也是整个迁移**工作量最大、风险最高、无法并行绕过**的部分。

### 为什么重
1. **金标准是 IP 灰区**：官方参考答案/采分点**不能爬商业站**（renrendoc 等）再分发。只能用**开源真题集**（GitHub: `weimsli/shenlunzhang`、`mkih76/SLB`、`WangJunqing-coder/shenlun-skill` MIT）。
2. **开源集往往只有题干+材料，没有结构化采分点** → 采分点要自己标或 LLM 辅助标。标采分点本身就是苦力：一道归纳概括题，参考答案 200 字隐含 5-6 个采分点，要拆成 `[要点, 关键词, 分值]`。
3. **规模要求**：要证明"准确率从 X 到 Y"，需覆盖多题型（归纳概括/对策/综合分析/贯彻执行）、多年份、多省份。至少 **50-100 道带可靠采分点的真题**才有统计意义（你之前 n=11 的教训：CI ±26-28pp，无法归因）。
4. **评测指标设计**：
   - 采分点 **recall / precision**（关键词匹配 vs 语义匹配，需处理"同义表述"→ 引入 embedding/LLM，新变量）
   - 评分 **MAE**（系统给分 vs 标准分）
   - 从 `eval/mock_interview_eval.py` 改造，但原 5 指标（discrimination 等）不适用，需换一套。
5. **可复现 eval 脚本**：`scripts/run_evals.py` 的 by_mode 对比框架可复用，但指标与数据集结构要重写。

### 建议 Phase 0 独立做（先于代码）
1. 锁定 2-3 个开源真题集（MIT/可商用），确认其**是否含参考答案/采分点**。
2. 定**采分点标注规范**（结构：`{point, keywords[], score}`），先标 20 道 pilot 验证标注一致性。
3. 建 `benchmark/` 目录：真题 JSON（material + question + type + reference_points + scoring_criteria）。
4. 写 eval 指标（recall/precision/MAE）+ 最小 eval 脚本跑通。
5. 再回头写代码——代码依赖 benchmark 的 schema 和指标定义。

---

## 关键洞察（给你决策用）
- **先做 Benchmark（Phase 0）**：它是瓶颈且能独立于代码启动。
- **记忆层（mastery）免费**：这是项目最大的资产保留，迁移不损失核心能力。
- **mock 改动方向是"变简单"**：把最不可信的 LLM 主观判卷，换成最可信的采分点比对——恰好解决你之前最大痛点（判卷不可验证）。代码是做减法，不是加法。
- **真正的苦活在采分点标注**：无银弹，要么用开源已标集（少），要么自己标（累）。这是整个迁移成败的关键变量。
