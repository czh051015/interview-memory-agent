# cleaner 修改计划书 · 从「拆面经」到「拆采分点」

> 配套：docs/15（错题回流+ReAct 主线）、docs/11（申论 Agent 迁移拆解）
> 定位：**cleaner 从主链路入口 → 上传时的一次性入库工具**。用户上传 题目+自己的答案+标准答案 → LLM 拆标准答案为采分点 → 人工审核 → 入库 → 之后无限次练习复用。

---

## 0. 一句话目标

**让 cleaner 能把「标准答案」拆成评分传感器能吃的 `reference_points`（point/keywords/score），并过一道人工审核闸门再入库。**

不拆点，`score_answer()` 没有输入，答案逼近/薄弱点档案/ReAct 三层全悬空——这是整个改造的地基。

---

## 1. 现状盘点（逐文件，基于真实代码）

| 文件 | 当前职责 | 面试→申论 | 处置 |
|---|---|---|---|
| `__init__.py` | 空壳 docstring | 更新描述 | 🟡 微改 |
| `prompts.py` | `DECOMPOSE_SYSTEM`：复盘文本→Q&A（company/role/round/date + items[question/answer/status/category]） | 拆解对象变了 | 🔴 **重写/新增** |
| `decompose.py` | 调 LLM → 校验 → 组装 `KnowledgeItem` → `record_birth` 留痕 | 产出结构变了 | 🟡 **复用骨架，改产出** |
| `annotate.py` | unknown 条目人工补标 f/p/g/x，走 `transition` 留痕 | 从「标状态」→「审采分点」 | 🟡 **改交互话术** |
| `state_machine.py` | `record_birth`/`transition`，证据链 `{time,from,to,reason,actor}` | 留痕机制通用 | 🟢 **复用，微泛化** |
| `status.py` | 关键词兜底推断 fail/partial/pass | 申论档位由命中率确定性算出，不需要 | ⚫ **不复用**（面试域继续用） |
| `schema.py` | `KnowledgeItem` + 枚举 + `DecomposeResult` | 需新增申论产出模型 | 🟡 **只增不改** |

**关键判断**：面试链路代码还在跑（模拟面试等），**改造采取「平行新增」策略——不删不破坏面试功能，新增申论模式**。`status.py`/`KnowledgeItem` 原样保留服务面试，申论走新模型。

---

## 2. 改造总览

```
┌─ 面试域（现状，零改动）─────────────────────┐
│ prompts.DECOMPOSE_SYSTEM → decompose()      │
│ → KnowledgeItem → annotate_unknown(f/p/g/x) │
└──────────────────────────────────────────────┘
                     │ 平行新增
                     ▼
┌─ 申论域（本次新增）──────────────────────────┐
│ prompts.SHENLUN_DECOMPOSE → decompose_points() │
│ → ReferencePoint[]（默认 approved=false）     │
│ → annotate_points()：人审闸门（确认/改分/删）  │
│ → 入库 benchmark 格式 JSON（source 标记）      │
└────────────────────────────────────────────────┘
```

申论域的输入/输出对齐 benchmark 金标格式（`benchmark/data/jiangsu_2023_a_1.json`）：

```json
{
  "id": "jiangsu_2023_a_1",
  "task": { "question": "...", "material": "...", "max_score": 20 },
  "gold": { "reference_points": [
    { "id": "c1", "point": "六尺巷·化解纠纷", "keywords": ["六尺巷","土地纠纷","谦让"], "score": 3 }
  ]}
}
```

---

## 3. 逐文件改造方案

### 3.1 `prompts.py` —— 新增 `SHENLUN_DECOMPOSE_SYSTEM`（🔴 核心改动）

**现状**：拆「面试复盘 → Q&A」，有 status/category 推断规则。
**改造**：新增一个 prompt，拆「标准答案 → 采分点」。要点：

| Prompt 要素 | 设计 | 为什么 |
|---|---|---|
| 输入 | 题目 + 材料 + 标准答案全文 | 拆点需要语境，只看标答会拆出答非所问的点 |
| 输出 | `reference_points: [{point, keywords[], score}]` | 对齐 benchmark 金标结构，`score_answer()` 直接吃 |
| point 命名 | ≤8 字，语义标签（如「设施互通」） | 要能在反馈里念给用户听 |
| keywords | **必须出自标准答案原文/材料原词**，2-5 个 | 这是评分传感器的比对底料，脱离原文的意译词会误判 |
| score | 按该点在答案里的重要性/篇幅分配，总和 = max_score | 人审时可按分比值核对 |
| 数量约束 | 一道题 3-8 个点；明显只有 2 个点也允许 | 漏拆=漏分，多拆=噪音，给 LLM 明确边界 |
| 防幻觉 | ① 不得臆造材料/标答里没有的点 ② 不确定的点也列出但 score=0 且标注 | 闸门兜底之外，Prompt 先减负 |
| 温度 | 0.0（同现状） | 拆点是结构化任务，不是创作 |

> 面试版 `DECOMPOSE_SYSTEM` **原样保留**，互不干扰。

### 3.2 `schema.py` —— 新增申论产出模型（🟡 只增不改）

```python
class ReferencePoint(BaseModel):
    id: str = ""                 # "c1"...（入库时按序编号）
    point: str = Field(..., description="采分点名称，≤8字")
    keywords: list[str] = Field(..., description="比对关键词，须出自原文")
    score: float = 0
    approved: bool = False       # ← 人审闸门，默认不通过
    source: str = "llm_draft"    # llm_draft / human_approved / official

class PointDecomposeResult(BaseModel):
    question: str = ""
    requirements: str = ""
    material: str = ""
    max_score: int = 0
    reference_points: list[ReferencePoint] = []
    warnings: list[str] = []     # LLM 自报的不确定项，人审时优先看
```

**注意**：`approved` 默认 `false` 是防循环论证的关键——LLM 拆的点 → LLM 判的分，必须人审后才成为"可信金标"。这与之前定的「闸门只锁采分点」一致。

### 3.3 `decompose.py` —— 新增 `decompose_points()`（🟡 复用骨架）

**现状**：`decompose()` = 调 LLM → 逐条组装 KnowledgeItem → record_birth。
**改造**：新增 `decompose_points(raw_answer, question, material, max_score)`：

```
1. 调 chat_json(SHENLUN_DECOMPOSE_SYSTEM, ...)   # 复用现成 LLM 封装
2. pydantic 校验输出（ReferencePoint 校验失败 → warnings 记录，不整体崩）
3. 组装 PointDecomposeResult（approved=False, source="llm_draft"）
4. record_birth 等价物：留痕「由 LLM 拆解生成，待人工审核」
5. 返回结果（不写库！写库是 annotate_points 通过后的事）
```

复用点：`chat_json` 调用、异常兜底（LLM 挂了返回空结果而非崩溃）、长度截断（`raw_text[:6000]` 同款）。

**删除点**：status 推断、category 分类、mastery_score 初始化、占位符正则——全是面试域的，申论不需要。

### 3.4 `annotate.py` —— 新增 `annotate_points()`（🟡 人审闸门）

**现状**：`annotate_unknown()` 逐条 f/p/g/x。
**改造**：新增人审闸门，交互从「标状态」变「审采分点」：

```
逐条展示: [c3] 河长制·治水  keywords: 河长/水质/清淤泥  score: 3
  操作: k=确认  s=改分值  w=改关键词  d=删除  a=新增点  x=跳过(不通过)
```

| 操作 | 作用 | 落库行为 |
|---|---|---|
| k 确认 | 认可 LLM 拆的点 | `approved=True, source="human_approved"` |
| s 改分值 | 分值不合理（如 20 分题某点给 5 分太多） | 改 score |
| w 改关键词 | 关键词没抓住要点 | 改 keywords |
| d 删除 | LLM 拆错/臆造 | 不落库 |
| a 新增 | LLM 漏拆 | 手动补一个点（human_approved）|
| x 跳过 | 整批存草稿，不发布 | 全组保持 approved=False |

**复核交互走 `transition` 留痕**（复用 state_machine 模式）：每步操作记 `{time, from, to, reason, actor:"annotate_points"}`。

### 3.5 `state_machine.py` —— 微泛化（🟢 复用）

**现状**：`record_birth`/`transition` 强绑定 `KnowledgeItem`（pydantic model + history 字段）。
**改造**：两个选择——

- **方案 A（推荐，改动最小）**：不动 state_machine.py，在 annotate_points 里用同样的 `_append_history` 逻辑（或抽一个小函数），给 `ReferencePoint` 加 `history` 字段。10 行以内。
- 方案 B：把 history 逻辑抽成泛型工具。更优雅但动到面试域，回归成本高。

**理由**：申论侧"留痕"的消费者是未来的逼近轨迹（`{from:0.33, to:0.56, reason:"第1轮引导补设施互通"}`），数据结构与状态机同构但语义不同，没必要现在硬绑。

### 3.6 `status.py` —— 不动（⚫）

申论档位由 `score.hit_ratio` 确定性算出，不需要关键词推断。文件保留服务面试域。

### 3.7 `__init__.py` —— 更新模块描述

`"""Cleaner Agent —— 语义清洗：去重、脱敏、标准化。"""` → 补一句「+ 申论：标准答案 → 采分点拆解与人工审核」。

---

## 4. 配套改动（cleaner 的产出要喂给谁）

cleaner 拆完的采分点，最终要变成 `score_answer()` 能吃的 reference_points。两条落地路径：

### 4.1 入库目标：新增「用户题库」目录

```
benchmark/data/            ← 官方金标（训练用，不动）
data/user_questions/       ← 用户上传拆解后的人审通过题（新增）
```

`reflow.py` 的 `from_benchmark()` 扩展为按目录加载（官方 + 用户），用户题在 `meta.authority="user"` 标记。

### 4.2 `weak_points` 补 `source` 列（上一轮已定，列入排期）

`weak_points` 加 `source TEXT`（`official` / `llm_draft` / `human_approved`），档案统计可按来源过滤——防止自动拆的低质量点稀释官方金标建立的"漏点识别可靠"口碑。配套 `answers` 补 `rounds`/`initial_hit_ratio`、新建 `answer_rounds` 表，见 docs/15 讨论，**不在本计划书范围内**（cleaner 先行）。

---

## 5. 实施顺序（每步独立可验收，一点点来）

| 步 | 改动 | 文件 | 验收标准 |
|---|---|---|---|
| 1 | 写拆采分点 prompt | `prompts.py` | 拿江苏真题标答试拆，LLM 输出合法 JSON；人工对比官方金标，**点覆盖 ≥80%、无臆造点** |
| 2 | `ReferencePoint` 模型 + `decompose_points()` | `schema.py`、`decompose.py` | 真实 LLM 跑通：返回结构合法、approved=False、warnings 记录不确定项 |
| 3 | 人审闸门 `annotate_points()` | `annotate.py` | 交互走通：确认/改分/删/新增各操作落库正确，留痕完整 |
| 4 | 入库：写 user_questions JSON + `from_benchmark` 扩展 | scripts/ + `reflow.py` | 人审通过的题能被 `score_answer()` 正常评分 |
| 5 | 回归：面试域测试全绿 | — | `pytest` 无失败（平行新增不破坏旧链路） |

**建议节奏**：第 1、2 步可以合一次做完（都是拆解侧），第 3 步单独做（交互逻辑），第 4 步做入口脚本。

---

## 6. 风险与规避

| 风险 | 概率 | 规避 |
|---|---|---|
| LLM 拆点质量不可控（漏拆/多拆/臆造） | 高 | 三层兜底：prompt 约束（原词+数量边界）→ 人审闸门（可删可加可改）→ `source` 标记（档案可过滤）|
| 循环论证：LLM 拆点 → LLM 判分 | 中 | `approved=False` 默认 + 人审通过才可入库评分；benchmark 的 recall 指标只对 official/human_approved 数据负责 |
| 破坏面试域现有测试 | 低 | 平行新增策略，面试代码零改动；第 5 步 pytest 回归兜底 |
| 用户上传的标答质量差（抄的/残缺） | 中 | 交互时提示「标答需为权威参考答案」；拆出的点少时 warnings 里提示「疑似标答过简，建议更换」|
| 拆出的点与官方金标风格不一致，污染题库 | 中 | user_questions 与 benchmark/data 物理隔离，`authority` 字段区分 |

---

## 7. 面试讲点（这轮改造能讲什么）

1. **「拆点」不是额外工作，是地基**：申论按点给分，评分传感器需要 point/keywords 输入，没有 cleaner 的拆解，答案逼近/薄弱点档案/ReAct 全部悬空。
2. **防循环论证的工程实现**：LLM 拆的点默认不通过，人工审核闸门（确认/改分/删/新增）通过后才进题库——「我知道自动拆不可全信，所以保留了来源标记和人工闸门」。
3. **成本摊薄**：一道题只拆一次（LLM+人审），之后每次练习、每轮逼近都复用同一套点——这正好对应粉笔养教研团队录得分点的护城河，你用 LLM+人审把这件事做轻。
4. **平行新增不破坏旧链路**：面试域代码零改动，申论域作为新模式加入，pytest 回归保证。

---

## 8. 待确认事项

- [ ] 入库路径：`data/user_questions/` 是否 OK，还是直接混入 benchmark/data？（影响 eval 隔离）
- [ ] 第 1+2 步合并做，还是严格分开？
- [ ] `annotate_points` 交互形式：CLI 逐条（复用现有 input 风格）还是要留 Web/API 口子？
