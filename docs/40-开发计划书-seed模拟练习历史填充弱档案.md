# 40 · 开发计划书：seed 模拟练习历史 —— 填充薄弱档案，演示记忆机制动态分层

日期：2026-09-06 · 状态：**计划（待用户确认后落地）** · 性质：一次性数据工具脚本，**业务代码零改动**

## 1. 背景与用户诉求

用户原话：「我现在数据集有点少，你在我的 benchmark 里多抽几道题，添加到错题本里，并且随机分配权重，呈现不同题添加进来，为了证明我的记忆机制有效果。」

拆解：
1. **痛点**：薄弱档案数据少 → 记忆机制（Agent 内核卖点）无法自证。
2. **要什么**：弱档案里出现**多道题、多个漏点、不同权重、不同遗忘状态** → 今日提醒/档案页能展示「按遗忘状态动态分层」，而不是静态清单。

## 2. 现状核查（代码事实，已钉死 2026-09-06）

| # | 事实 | 位置 |
|---|---|---|
| 1 | `data/shenlun.db` 现有练习数据**只覆盖 1 道题**：answers 5 行 / answer_rounds 6 行 / weak_points 9 行（全 `henan_2025_city_1:c1..c9`）/ events 5 行 | 实查 DB |
| 2 | 提醒池读取：`weak_points WHERE state IN (active, pinned)`，按紧急度降序 | `profile.py read_weak_points` |
| 3 | 紧急度公式：`urgency = (miss_count + guided_rounds_weight) × forgetting`，`forgetting = 1 - e^(-0.05 × 距上次练习天数)` —— **时间戳是遗忘分层的唯一杠杆** | `profile.py WeakPoint.score/forgetting` |
| 4 | tier 分层：`miss_count≥2 → red`；`miss_count≥1 且 >14 天没练（stale）→ red`；`miss_count≥1 → yellow`；其余 green | `profile.py _tier` |
| 5 | 作答入库唯一入口：`reflow_answer(question_id, question_type, answer, reference_points, ...)` → 评分真算 hit/miss → 自动写 answers/weak_points/events，upsert 语义与真实练习完全一致 | `reflow.py` |
| 6 | 评分可控点：`reflow_answer → score_answer(use_semantic=True)`；语义层 `embed_zh` 返回 None 时整段降级 → **纯关键词硬匹配**（`any(kw in answer)`），毫秒级、无外部调用 | `score.py _score_answer_kw / _semantic_match` |
| 7 | 时间可控点：`reflow.py` 内 `now = utcnow().isoformat()`，`utcnow` 为模块内导入名（`from src.cleaner.schema import utcnow`）→ **模块级 patch 即可让整次作答发生在过去任意一天**，落库四张表时间戳自动一致 | `reflow.py` L303 / `schema.py` |

## 3. 拍板记录（用户已确认，2026-09-06）

1. **数据落点**：直接灌真实库 `data/shenlun.db`（Web 工作台 / 提醒立即可见）；运行前先备份 `shenlun.db → shenlun.db.bak`，随时可回滚。
2. **造数规模**：从 `benchmark/data/`（36 道官方真题）随机抽 **6–8 道**，自动排除已练过的 `henan_2025_city_1`；每道题随机漏 2–5 个采分点、随机 1–2 次作答。
3. **时间跨度**：每题「最后练习日」散布在过去 **0–28 天**（含 <14 天的近期档与 >14 天的 stale 档），遗忘分层可视。

## 4. 方案设计：模块化 seed（**无上帝文件，职责单一**）

> 工程约束（用户 2026-09-06 追加，硬性）：**不出现上帝文件**——禁止把抽题、场景构造、作答生成、落库、汇报全塞进一个 `scripts/` 脚本。拆成**薄 CLI + 四个职责单一的小模块**，单向依赖、无循环引用；每个模块只做一件事、输入/输出边界一句话讲得清，能独立被讲给面试官。

**原则**：不手写 SQL 造档案行，而是**复用 `reflow_answer` 真实回流链路**——评分真算、写库 upsert 语义与真实练习逐字段一致，数据可辩护为"过去几周的练习历史"，日后不会被机制本身判为异常。

### 4.0 模块拆分与依赖（新增文件清单）

```
offerloop/
├── scripts/seed_weak_history.py   # ① CLI 入口：解析参数 + 编排 + 打印汇报（薄，~60 行）
└── src/shenlun/seed/              # 新包：seed 演示数据确定性核心（业务代码零改动，主流程不 import 它）
    ├── __init__.py                # 空
    ├── sampler.py                 # ② 题目采样器：抽题 + 排除已练 + 保证题型多样（纯函数，无 IO）
    ├── scenario.py                # ③ 场景构造器：生成「练习场景」（纯数据，无 IO）
    ├── builder.py                 # ④ 作答文本构造器：场景 → 关键词组织句（纯字符串，无 IO）
    └── loader.py                  # ⑤ 落库器：时间回拨 + 语义禁用 → 调 reflow_answer（唯一 IO 面）
```

| 模块 | 输入 | 输出 | 职责边界（不做的事） |
|---|---|---|---|
| ① `scripts/seed_weak_history.py` | 命令行参数 | 打印计划 / 落库结果 | 只编排与汇报；**不含任何业务逻辑** |
| ② `sampler.py` | 题库目录、`exclude_ids`（已练题，由调用方查 DB 传入）、count、seed | 抽中的 `question_id` 列表 | 只做抽样；**不查 DB、不构造作答** |
| ③ `scenario.py` | 题目 JSON + seed | `[{question_id, date, hit_point_ids, miss_point_ids, round_no}]` | 只决定「哪些点漏/中、练几次、落在哪天」；**不碰文本、不碰 DB** |
| ④ `builder.py` | 题目 JSON + 一个场景 | 作答文本（含命中点 keywords） | 只拼字符串；**不做任何判定** |
| ⑤ `loader.py` | 题库路径 + 场景列表 | 落库结果摘要（新增/更新点数） | 唯一写库面：patch 时间与语义 → 逐场景调 `reflow_answer`；**不含抽题/构造逻辑** |

依赖方向（单向，无环）：`scripts/seed_weak_history.py → loader → {scenario, builder, reflow}`，`sampler` 被 CLI 直调；②③④ 全部纯函数（无 DB/IO），可单独单测、可单独给面试官讲输入输出。单文件行数预算 ≤80，总逻辑 ~250 行分散在五个小单元，杜绝"一个脚本干所有事"。

### 4.1 流水线（模块职责对应）

**Step 1 · 抽题 → `sampler.py`**
- CLI 实查 DB 拿已练 `question_id`（只读）作为 `exclude_ids` 传入 → `sampler` 从 `reflow.BENCHMARK_DIR` 列题、用 `random.Random(seed)` 抽 6–8 道（默认 6，CLI 可调）。
- 目的：覆盖河南/江苏、不同 `meta.type`（归纳概括/应用文等）→ 档案 qtype 多样。

**Step 2 · 构造「部分命中」作答 → `scenario.py` + `builder.py`**
- `scenario`：对每道题随机选 30–60% 采分点作为**命中点**，其余为**漏点**（弱档案新增点，每道 2–5 个）；并决定该题练习日期与轮次。
- `builder`：按场景拼作答文本 = 命中点的组织句（含该点 keywords），**漏点 keywords 一律不出现**。
- 判定断言放 `loader`：落库前用同一场景先本地评分（`score_answer`）断言 `expected_hit ⊆ actual_hit`，不一致即中止（不该发生，防数据脏）。

**Step 3 · 时间回拨落库 → `loader.py`**
- 每题一个「练习日」，`days_ago ∈ [1, 28]` 随机（由 `scenario` 决定，seed 固定可复现）。
- 两次作答的题（约半数）：第一次较早（更老）、第二次较近（间隔 3–7 天）→ 制造 `miss_count=2` 的高权重点（红档）与"补过一次"的叙事。
- 实现：`loader` 内模块级 patch `reflow.utcnow = lambda: fake_naive_utc`（fake = 真实 now − days_ago，naive UTC，与 `schema.utcnow` 语义一致）与 `score.embed_zh → None`（语义降级纯 kw），每次作答后恢复——patch 范围被 `loader` 收口，不泄漏到其他模块。

### 4.2 入参

| 参数 | 默认 | 说明 |
|---|---|---|
| `--count` | 6 | 抽题数（6–8 推荐档） |
| `--seed` | 固定值 | 随机种子，结果可复现（默认固定，加参可换批） |
| `--dry-run` | 关 | 只打印计划（抽了哪些题、每道漏哪些点、落在哪天），不写库 |

### 4.3 副作用与回滚

- 影响表：`answers` / `answer_rounds` / `weak_points` / `events` 各增行（reflow_answer 自动写，四表一致）；**不碰** Chroma/面试域/题库文件/schema。
- 回滚：`rm data/shenlun.db && mv data/shenlun.db.bak data/shenlun.db`（备份在首次运行自动生成，已存在则不覆盖）。
- 数据性质声明：模拟练习，非真实作答，仅用于演示记忆机制（如需交付面试叙事，按"真实练习历史"口径如实描述演进，不虚报训练量）。

## 5. 验收标准（跑完脚本立即自查）

1. 弱档案覆盖 **≥5 道不同题**、新增 **≥20 个漏点**（视抽取量）。
2. 调用 `profile.read_weak_points()`（确定性，0 LLM）打印分层预览，**同时存在**：
   - 🔴 红档（`miss_count≥2` 或 stale>14 天）—— 证明"多漏 + 遗忘风险"被识别；
   - 🟡 黄档（近期漏 1 次）—— 证明"需关注"；
   - 且 urgency 呈梯度（同红档内排序不是写死，而是 `miss × forgetting` 实时算）。
3. `GET /shenlun/remind` 等价语义输出：毕业考候选 ≤2 + 该练 topK ≤3，来自多道不同题。
4. 重复跑同 `--seed` → 档案不重复膨胀（upsert 覆盖，不产生脏数据）；不传 seed 换一批 → 仍收敛。
5. `python -m pytest -q` 全量无回归（业务代码零改动，理论上必过，仍跑一遍保险）。

## 6. 关键风险与对策

| 风险 | 对策 |
|---|---|
| 语义层把「想漏的点」判中，档案与意图不符 | `loader` 内 patch `score.embed_zh → None`（语义整段降级纯 kw，patch 收口不泄漏）+ 落库前本地评分断言 |
| 时间回拨不生效（utcnow 被别处绑定） | patch `reflow.utcnow`（reflow.py 内的导入名，非 schema 源模块）；落库后抽查 `last_practiced_at` 距今 = days_ago |
| 污染真实练习数据、无法区分 | 运行前自动备份 `.bak`；seed 全打印清单（题/点/时间），可人工核对 |
| 抽到已有档案的题（重复 upsert 累加 miss_count） | 抽题前实查 DB 排除已有 `question_id` |

## 7. 执行清单（等用户说「做」再动）

1. 备份 `shenlun.db` → `.bak`
2. 写 `src/shenlun/seed/` 四模块（sampler / scenario / builder / loader）+ `scripts/seed_weak_history.py` 薄入口（五文件，每文件 ≤80 行）
3. `--dry-run` 预览：确认抽题/漏点/时间分布合理
4. 正式跑：灌库
5. 验证：分层预览 + remind 输出 + pytest 无回归
6. 汇报：新增了哪些题/多少点/红黄绿分布，附回滚口令
