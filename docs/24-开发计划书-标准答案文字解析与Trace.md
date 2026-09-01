# 24 · 开发计划书：标准答案支持文字版 + 自动解析 + 开发者 Trace

> 配套 doc/22、doc/23（逼近引导示证版）。本次目标：练习页「标准答案」从"只能贴 JSON"升级为"贴完整文字自动解析"——练习者无感，开发者可看解析 trace。
> 阶段：**仅方案定稿（grilling 收敛），未写代码**。

---

## 0. 一句话

把「标准答案（采分点 JSON）」输入框改成**自适应**：贴 JSON 走原逻辑；贴纯文字 → 后端 LLM 自动拆成采分点 → 继续走原评分链路。解析过程（trace）默认隐藏，开发者加 `?dev=1` 可展开查看。

## 1. 背景与目标

**痛点**：`PracticePanel` 的标准答案框只认 JSON（`[{id, point, keywords, score, point_type}]`），练题前要把参考答案手工"翻译"成 JSON——对练习者（尤其新手/非技术）是硬门槛。

**目标**：
1. 标准答案支持完整文字版，自动解析成采分点（复用已有 `decompose_points`）
2. 评分链路不变（纯确定性 keywords 匹配，0 token）
3. 练习者不见解析细节；开发者（你）可见 trace 验证解析质量

**非目标**：题库录入的人审拆点流程不动；不追求解析"精确"（评分=传感器，漏点识别可靠即可）。

## 2. 现状（关键事实）

| 现状 | 位置 | 含义 |
|---|---|---|
| 已有「标准答案文字→采分点」LLM 拆解 | `src/cleaner/decompose.py:153` `decompose_points` | 核心零件现成，直接复用 |
| 已有 trace 存取设施 | `app/utils/decompose_cache.py` | save_trace/load_trace 可复用 |
| 评分是纯确定性 keywords 匹配 | `src/shenlun/score.py` `score_answer` | 只吃结构化 points，无需改 |
| 前端 JSON-only | `PracticePanel.tsx` `buildGold()` | 本次主要改造点 |
| 前端无 trace 展示 | `lib/api.ts` | 需新增 |

## 3. 总体流程

```
练习者粘贴 文字版标准答案 + 题干 + 材料
        │ 点「评分」
        ▼
[前端] 检测：JSON？→ 走原逻辑（不解析）
        纯文字？→ POST /shenlun/practice/parse
        ▼
[后端] decompose_points（LLM，温度 0）
        → points[] + warnings + trace（每点挂 source_snippet 原文片段）
        ▼
[前端] 拿到 points → 拼 InlineGold → 走原 scorePractice 评分
        ▼
[练习者] 只看评分结果（命中/漏点/示证）—— 解析细节不可见
[开发者] 开 ?dev=1 → 输入框下方展开「解析 trace」折叠区
```

## 4. 后端改动

### 4.1 prompt 增强（`src/cleaner/prompts.py`）

`SHENLUN_DECOMPOSE_SYSTEM` 输出增加 `source_snippet` 字段：该采分点对应的**标准答案原文片段**。这是 trace 里验证"拆得准不准"的关键——现有输出没有它。

其余字段不变：`point / keywords / score / point_type`。

### 4.2 新端点 `POST /shenlun/practice/parse`（`app/api/shenlun.py`）

**请求**：

```json
{
  "standard_answer": "标准答案全文",
  "question": "题干（语境，防拆出答非所问的点）",
  "material": "给定材料（语境）",
  "max_score": 0
}
```

**响应**：

```json
{
  "points": [
    {
      "id": "p1",
      "point": "设施互通",
      "keywords": ["城际公交", "高速免费", "道路", "互通"],
      "score": 1,
      "point_type": "对策",
      "source_snippet": "这几年两地开通了城际公交，实现了高速公路免费互通…"
    }
  ],
  "warnings": ["采分点2分值不确定，已按1分处理"],
  "trace": {
    "standard_answer": "标准答案全文",
    "points": [ "…同上，含 source_snippet…" ],
    "warnings": ["…"]
  }
}
```

**要点**：
- 内部调 `decompose_points`，传入 question/material 作语境（LLM 拆点需要语境，否则拆出答非所问的点）
- `decompose_points` 不产出 `id` → 端点内补 `p1/p2/…`
- 错误处理：
  - LLM 调用失败 → **400**，detail 提示"解析失败，可切回 JSON 模式手填"
  - 拆点不完整/有不确定项 → **200** + `warnings` 标注（不阻断练习）

## 5. 前端改动（`PracticePanel.tsx` + `lib/api.ts` + `lib/types.ts`）

### 5.1 types / api 对齐

- 新增 `ParseResult { points, warnings, trace }`、`ParseTrace { standard_answer, points, warnings }`
- 新增 `parsePractice(ctx: {question, material}, standard_answer) -> ParseResult`

### 5.2 输入框自适应

- label 改为「标准答案（文字或 JSON）」
- `buildGold()` 改造：先试 `JSON.parse`——成功走原逻辑；失败且非空 → 标记"文字模式"，暂不解析
- 点「评分」：文字模式 → 先 `parsePractice`（busy 覆盖全程，出错 toast）→ 拿到 points 拼 `InlineGold` → 原 `scorePractice`；JSON 模式原样

### 5.3 trace 折叠区（开发者可见）

- 开关：URL `?dev=1` 或 localStorage `shenlun_dev=1`
- 开启后：标准答案框下方出现「解析 trace」折叠区，展示：
  - 原始答案全文
  - 拆出的采分点表：point / keywords / score / point_type / **source_snippet（原文片段）**
  - warnings
- 不开 dev：一切照旧，练习者无感

## 6. 验证方案

1. 造一段文字版标准答案（用示例题 SAMPLE 的 9 个采分点反写成文章/分点列表）
2. 端到端：文字模式 → parse → 评分 → 结果与 JSON 模式对照（hit/miss 应基本一致）
3. 边界：
   - 纯 JSON 粘贴 → 不触发解析（原逻辑）
   - 空答案 → 前端拦截（已有）
   - LLM 挂（模拟）→ 400 提示切 JSON
   - 拆点质量差 → 200 + warnings，评分仍跑
4. pytest：`decompose_points` 现有测试不回归；新增 parse 端点单测（mock LLM）

## 7. 工作量拆解

| 任务 | 复杂度 | 依赖 |
|---|---|---|
| 4.1 prompt 增强（source_snippet） | 低 | 无 |
| 4.2 parse 端点 | 中 | 4.1 |
| 5.1 types / api 对齐 | 低 | 4.2 |
| 5.2 输入框自适应 + 评分流程 | 中 | 5.1 |
| 5.3 trace 折叠区 | 中 | 5.1 |
| 6 验证 | 低 | 全部 |

## 8. 关键决策记录（grilling 定稿）

| 决策 | 选择 | 理由 |
|---|---|---|
| 解析位置 | 后端独立端点 | key 安全 + 复用 decompose_points |
| 输入形态 | 单框自动检测 | 保留 JSON 调试能力，练习者零学习成本 |
| 解析时机 | 点「评分」自动完成 | 解析是中间产物，不该成为必经步骤 |
| trace 内容 | 原文 + 点 + warnings + source_snippet | source_snippet 是验证拆点质量的关键 |
| trace 可见性 | `?dev=1` 开关 | 开发者即开即关，不污染练习者界面 |
| 失败策略 | LLM 挂→报错；拆点不完整→继续 | 符合「评分=传感器，不追求精确」 |
| 范围 | 只改 PracticePanel | 题库录入人审流程不动 |
