# 秋招 Copilot · 产品计划书

> 版本 v1.0 · 2026-08-12 · 状态：v1 MVP 待执行
> 参考文档：`personal-coach-concept.md`（定位修正）、`agent-design-v1.md`（Agent 接口设计）、`ai-job-coach-agile-plan.md`（敏捷计划 v1.1）

---

## 1. 执行摘要

**秋招 Copilot** 是一个带长期记忆的 Agent 系统。应届生把面试复盘丢进去，系统自动拆成结构化 Q&A、标注哪些答错了、按遗忘曲线跟踪每个知识点的掌握度、每周推送个性化复习报告。

**一句话定位**：做了你的私人面试教练——它不是分析"市场在考什么"，是记住**你**还缺什么。

**v1 MVP**：一条 Agent——面经消化。人工输入复盘 → 拆成 Q&A → pass/fail/partial 自评打标 → 存入错题本。

---

## 2. 问题陈述

### 2.1 用户现状

应届生面完试打开备忘录敲几行："腾讯二面问了 RRF，忘了"。下周又面一场，同一个考点继续栽。备忘录不提醒、Excel 不跟踪、脑子不靠谱。漏掉的不是一道题，是一次面试机会——校招每条赛道的目标公司两只手数得完，错过一家少一家。

### 2.2 现有方案差距

| 方案 | 做什么 | 痛点 |
| --- | --- | --- |
| 备忘录 / Excel | 记题目 | 不拆 Q&A，不跟踪掌握度，不提醒复习 |
| 9.9 元面经资料（小红书） | 静态题库 + 考点总结 | 无个性化，不知道你的薄弱点在哪 |
| ChatGPT 丢面经 | 一次性分析 | 无状态——第二次告诉你同样的结论，不记得你上次栽在哪 |
| 你的秋招 Copilot | 记住错题，跟踪掌握度，个性化提醒 | — |

### 2.3 核心洞察

面经市场的竞品都在回答**"考什么"**。没有人回答**"你还差什么"**。前者的答案人人都能用，后者的答案只有你自己能用。后者才是壁垒。

---

## 3. 产品定位

### 3.1 产品边界

| 是 | 不是 |
| --- | --- |
| 个人成长引擎——跟踪你的知识状态，随时间进化 | 市场情报平台——分析面经趋势 |
| 带长期记忆的 Agent 系统 | 无状态的 LLM 调用管道 |
| 你的私人面试教练 | 面经题库 |

### 3.2 不可替代性

1. **个性化记忆**：100 个人丢面经给 ChatGPT，拿 100 份相同的分析。你的系统 100 个人拿 100 份不同的成长报告——因为每个人的错题不一样。
2. **时间维度**：mastery_score 在动——上周 fail → 复习后涨到 0.9 → 两周没碰又掉到 0.3。这个"状态随时间变化"是一般 Agent 做不出来的。
3. **交叉验证**（v1.5+）：面经说考 Agent + JD 也写要 Agent——两条独立数据线互搏，评估结果的覆盖度从 7 涨到 9。

---

## 4. 用户画像

**小张**，22 岁，软件工程大三，面 AI 应用开发岗。每天刷牛客、看面经、投简历。面完试靠备忘录记题目，复盘靠脑子回忆。

**核心场景**：今晚面完腾讯二面，打开系统贴一段复盘——"RRF 没答上来，Chroma vs Milvus 答了一半，Agent 安全不会"。系统自动拆成 3 道 KnowledgeItem，存入错题本。下周五打开成长报告——"RRF 已 8 天未复习，mastery 降至 0.18，本周优先"。

---

## 5. 产品架构

### 5.1 Agent 矩阵

| Agent | 职责 | v1 | v1.5 | v2 |
| --- | --- | --- | --- | --- |
| **面经消化** | 拆解复盘为结构化 Q&A + 自评打标 | ✅ | — | — |
| **知识记忆** | KnowledgeItem 入库 + mastery_score 衰减 + 三元召回排序 | ✅（基础存储） | ✅（衰减函数） | ✅（交叉验证增强） |
| **成长评估** | 薄弱领域识别 + 遗忘预警 + 掌握度变化对比 | — | ✅ | ✅ |
| **模拟面试** | 基于错题本扮演面试官追问薄弱点 | — | — | ✅ |

### 5.2 数据流

```
用户输入复盘文本
  │
  ▼
┌──────────────────┐
│ Agent 1 面经消化   │  ← 拆 Q&A + 推断 status（fail/partial/pass/unknown）
│ 输出：List[Q&A]    │     无备注 → unknown，入库后催用户补标
└────────┬──────────┘
         ▼
┌──────────────────┐
│ Agent 2 知识记忆   │  ← Chroma 向量化 + metadata 存储
│ KnowledgeItem 库   │     mastery_score 初始化 = 1.0
└────────┬──────────┘
         ▼
┌──────────────────┐
│ Agent 3 成长评估   │  ← 三元排序：relevance × 0.5 + importance × 0.3 + time_decay × 0.2
│ 输出：个性化排序    │     decay = 1 - mastery_score(t)
└────────┬──────────┘
         ▼
┌──────────────────┐
│ 成长报告          │  ← Markdown：错题回顾 + 遗忘预警 + 进步对比
│ 输出：简报         │
└──────────────────┘
```

### 5.3 记忆系统设计（核心技术资产）

**四步记忆**：结构 → 写入 → 管理 → 读取。

**结构**：KnowledgeItem schema

```
id, question, topic, company, role, date, round
status: fail | partial | pass | unknown
user_note: 用户原始备注（"忘了""答了一半"等）
mastery_score: 0.0-1.0
last_reviewed_at: timestamp
review_count: int
related_items: [id]
```

**写入**：status 不为 unknown 的条目入库。initial mastery_score = 1.0。同 topic 条目做合并。

**管理**：`mastery_score(t) = 1.0 × e^(-λt)`，λ = 0.05。复习后重置为 `min(1.0, 上次 × 1.2)`。score < 0.2 且 review_count ≥ 3 → 标记"顽固错题"。

**读取**：`recall_score = relevance × 0.5 + importance × 0.3 + (1 - time_decay) × 0.2`。推送 Top 3 到成长报告。

---

## 6. v1 MVP 定义

### 6.1 v1 范围——一条 Agent

| 要做的 | 不做的（砍到 v2） |
| --- | --- |
| 面经消化：拆 Q&A + 打标 pass/fail/partial/unknown | 掌握度衰减曲线 |
| 基础存储：KnowledgeItem 写入 Chroma | 三元召回排序 |
| 手动触发：`make run` 跑一遍 | 成长报告自动生成 |
| status unknown 催用户补标（控制台输出） | Streamlit 审批 / 复习 UI |
| 单元测试 + eval 脚本（拆解准确率基线） | E2E 管道 + 简报模板 |

### 6.2 v1 验收标准

- [ ] 输入一篇合成面经复盘（含 5 道题、混合备注），输出 5 条 KnowledgeItem，每条 status 与预期一致
- [ ] status unknown 率 ≤ 20%（即 5 题中最多 1 题无法推断）
- [ ] 拆解准确率 ≥ 90%（基于人工标注的 10 篇合成面经）
- [ ] KnowledgeItem 成功写入 Chroma，可按 topic / company / status 过滤检索

### 6.3 v1 交付物

- `src/cleaner/` — Cleaner Agent 核心代码（拆解 prompt + 规则管线）
- `src/cleaner/prompt.py` — 结构化拆解 prompt
- `tests/test_cleaner.py` — 拆解准确率单元测试
- `eval/cleaner_eval.py` — 10 篇标注面经的评估脚本
- `data/seed/synthetic_interviews.json` — 10 篇合成面经 + 标注真值

---

## 7. 技术架构

### 7.1 技术栈

| 层 | 选型 | 约束依据 |
| --- | --- | --- |
| 语言 | Python 3.13（venv） | 本机环境 |
| LLM | DeepSeek API（deepseek-chat） | 本机 16GB 无独显 |
| 嵌入 | nomic-embed-text（Ollama） | 本地免费、无独显 |
| 向量库 | Chroma（本地文件模式） | 16GB 内存友好 |
| Agent 编排 | LangGraph（后续 Memory agent） | v1 Cleaner 先用纯函数 |
| Web 框架 | FastAPI（v1.5 起） | Webhook + 后续 API |
| 前端 | Streamlit（v2 起） | 轻量可演示 |
| 测试 | pytest + eval 脚本 | 质量门自动化 |
| CI | GitHub Actions | lint + test |

### 7.2 v1 仓库结构

```
copilot/
├── src/
│   └── cleaner/           # v1：只有这个目录有代码
│       ├── __init__.py
│       ├── decompose.py   # 拆解管线
│       ├── prompt.py      # 拆解 prompt 模板
│       └── schema.py      # KnowledgeItem 定义
├── tests/
│   └── test_cleaner.py
├── eval/
│   └── cleaner_eval.py
├── data/seed/
│   └── synthetic_interviews.json
├── docs/
│   └── product-plan.md    # 本文档
├── Makefile
└── README.md
```

### 7.3 Cleaner 处理管线

```
原始复盘文本
  │
  ├─→ [规则] 识别结构化标记（"Q1:""公司：""自评："等）
  ├─→ [LLM]  对非结构化碎片做 Q&A 抽取 + status 推断
  ├─→ [规则] 校验输出 JSON schema（必填字段、枚举值）
  └─→ [输出] List[KnowledgeItem]
```

**status 推断规则**（无需 LLM 即可闭包的部分优先用规则）：
- 备注含"忘了""不会""没答""没答上" → `fail`
- 备注含"答了一半""漏了""追问没接住""补上了" → `partial`
- 备注含"答了""过了""完整" → `pass`
- 备注为空或不可识别 → `unknown`

**LLM 介入**：当规则无法推断 + 备注为非结构化文本时，调用一次 LLM 做语义推断。

---

## 8. 数据模型

### 8.1 KnowledgeItem（核心实体）

```jsonc
{
  "id": "ki_20260815_001",
  "question": "RRF 重排序的原理是什么",
  "topic": "混合检索",
  "company": "腾讯",
  "role": "AI应用开发",
  "round": "技术二面",
  "date": "2026-08-15",
  "status": "fail",
  "user_note": "忘了，只记得是多路融合",
  "mastery_score": 1.0,
  "last_reviewed_at": "2026-08-15T14:00:00Z",
  "review_count": 0,
  "related_items": [],
  "created_at": "2026-08-15T14:05:00Z"
}
```

### 8.2 输入格式（用户复盘）

```
公司：腾讯
岗位：AI 应用开发
轮次：技术二面
日期：2026-08-15

Q1：Chroma 和 Milvus 怎么选型？  答了一半
Q2：RRF 重排序的原理？  忘了
Q3：你怎么评估 RAG 系统质量？  答了 Recall 但漏了 MRR
Q4：Agent 安全防护措施？  不会
Q5：LangGraph 的 checkpoint 机制？  过了
```

### 8.3 输出格式（成长报告 v2 起）

```
📊 本周成长报告（2026-08-22）

✅ 攻克：RRF 重排序 [fail→pass，复习 3 次，mastery 0.92]
⚠️ 遗忘预警：Chroma vs Milvus [12 天未复习，mastery 0.18]
🆕 新错题：Agent 安全防护 [字节一面新增，fail]

📖 本周优先复习：
  1. Chroma vs Milvus 选型 [mastery 0.18，紧急]
  2. RAG 评估指标 MRR [mastery 0.55，建议]
  3. Agent 安全防护 [mastery 1.0，新题]
```

---

## 9. Sprint 计划（v1 MVP）

| Sprint | 周期 | 目标 | 交付物 |
| --- | --- | --- | --- |
| S0 | 第 1 周 | 仓库 + 环境 + seed 数据 | 可运行的 `make demo` + 10 篇合成面经 |
| S1 | 第 2 周 | Cleaner 拆解 + 打标 | 拆解准确率 ≥ 90%，pytest 全绿 |
| S2 | 第 3 周 | Chroma 入库 + 基础检索 | KnowledgeItem CRUD，按 topic/company/status 过滤 |
| S3 | 第 4 周 | v1 发布 + 文档 | README + CHANGELOG + 演示录屏 |

> 注：旧计划的 S3~S5 已按定位修正砍掉。v2 从第 5 周起做 Memory agent（mastery_score 衰减 + 三元排序），不在本计划书范围。

---

## 10. 成功度量

| 指标 | 基线 | 测量方式 |
| --- | --- | --- |
| 拆解准确率 | ≥ 90% | 10 篇人工标注面经，status 预期 vs 实际 |
| unknown 率 | ≤ 20% | 拆解后 status=unknown 的条目占比 |
| 假阳性率（pass 打成 fail） | ≤ 5% | 标注数据中 pass 被误判为 fail 的比例 |
| test coverage | ≥ 70% | pytest --cov |

---

## 11. 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
| --- | --- | --- | --- |
| Cleaner 拆解不准（核心假设） | 中 | 高 | 先跑 10 篇合成数据验证；不准就调 prompt + 规则闭包 |
| unknown 率过高 | 中 | 中 | 入库后催用户补标；补标流程设计为 3 秒点击 |
| 合成数据偏离真实输入 | 高 | 中 | S1 结束后用真实面经做二次验证 |
| DeepSeek API 不稳定 | 低 | 高 | 规则层优先，减少 LLM 调用次数 |
| v1 做太大了想加 Memory | 高 | 高 | 严格执行 v1 砍法——只做面经消化；新需求进 v2 backlog |

---

## 12. 版本路线图

| 版本 | 时间 | 核心能力 |
| --- | --- | --- |
| **v1.0** | 4 周 | 面经消化 Agent：拆 Q&A + 打标 + Chroma 入库 |
| **v1.5** | +2 周 | JD 监控 + 面经-JD 交叉验证 |
| **v2.0** | +4 周 | 知识记忆 Agent：mastery_score 衰减 + 三元召回排序 + 成长报告 |
| **v2.5** | +2 周 | 学习路径规划：掌握度 + JD 差距 → 个性化计划 |
| **v3.0** | 远期 | 模拟面试 Agent + 多用户 + 云端部署 |

---

## 13. 面试叙事（30 秒电梯陈述）

> 我做的是一个带长期记忆的 Agent 系统——秋招 Copilot。把面试复盘丢进去，系统自动拆成结构化 Q&A、标出哪些答错了，按遗忘曲线跟踪每个知识点的掌握度，每周推个性化复习报告。
>
> 跟丢面经给 ChatGPT 的本质区别——ChatGPT 不记得你上周错在哪，我的系统记得。它的 mastery_score 在动，你的进步它看得到，你的遗忘它也看得到。这不是一个 LLM 管道，是一个有状态的 Agent 记忆系统。

---

## 附录 A · 关键设计决策记录

| # | 决策 | 结论 | 日期 |
| --- | --- | --- | --- |
| D1 | 产品定位 | 个人成长引擎（非市场情报管道） | 2026-08-12 |
| D2 | v1 MVP 范围 | 仅面经消化 Agent；其余三个砍到 v2 | 2026-08-12 |
| D3 | 打标方式 | Cleaner 自动推断 + unknown 催用户补标（非强制结构化输入） | 2026-08-12 |
| D4 | 记忆系统 | 四步记忆：结构 → 写入 → 管理 → 读取；艾宾浩斯衰减 | 2026-08-12 |
| D5 | 技术栈 | Python 3.13 + Chroma + DeepSeek API + LangGraph + FastAPI | 2026-08-12 |
| D6 | 项目定位 | Agent 开发（非后台开发）——核心竞争力是记忆系统设计 | 2026-08-12 |

## 附录 B · 参考文档索引

| 文档 | 路径 | 内容 |
| --- | --- | --- |
| 原始蓝图 | `ai-544c5e24-blueprint-v0.md` | AgentLoop 节点与连线 |
| 定位修正 | `personal-coach-concept.md` | 情报管道 → 成长引擎 的完整论证 |
| Agent 接口设计 | `agent-design-v1.md` | Cleaner/Scout/Evaluator 的 I/O schema + prompt |
| 敏捷计划（旧） | `ai-job-coach-agile-plan.md` | Sprint 计划 v1.1（含 24 项 grilling 决策） |
| 刘小排诊断 | `xiaopai-discuss/2026-08-12-qiuzhao-copilot.md` | 产品诊断卡片 |
| 本文档 | `product-plan.md` | **正式产品计划书，以此为唯一执行基准** |
