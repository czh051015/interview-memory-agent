# AI 求职教练 · Agent 设计文档（v1.0 薄切版）

> 配套文档：`ai-job-coach-agile-plan.md` v1.1（敏捷计划）
> 状态：v1.0 · 2026-08-12 · 基于 grilling 共识

---

## 0. 总览

蓝图定义 4 个 Agent——`cleaner`、`scout`、`evaluator`（`output` 是生成器而非 Agent，一并设计）。v1 薄切原则：**不搞 ReAct / 多步推理 / Function Call**，只做单轮结构化 prompt + 规则管线。每个模块是纯函数：`输入 JSON → 处理 → 输出 JSON`。

```
     ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌──────────┐    ┌───────────┐
CSV →│  Inbox  │→→→│ Cleaner │→→→│ Memory  │→→→│  Scout   │→→→│ Evaluator │→→→ Output
Web  │(非Agent)│    │ (Agent) │    │(Chroma) │    │ (Agent)  │    │  (Agent)  │    │(生成器)
hook └─────────┘    └─────────┘    └─────────┘    └──────────┘    └───────────┘    │
       e1                e2             e4            e5              e8            │
                                                                                    │
                                                     ┌──────────┐                   │
                                                     │ Approval │                   │
                                                     │(Streamlit)│──────────────────┘
                                                     └──────────┘    e7
                                                          e6
```

| 模块 | 类型 | 核心能力 | v1 调用方式 |
| --- | --- | --- | --- |
| Inbox | 接入层 | CSV 解析 + Webhook 接收 | 纯规则（Python pandas / FastAPI） |
| **Cleaner** | Agent | 去重判重 / PII 识别 / 标准化 | 规则粗筛 → LLM 精判 |
| Memory | 存储 | 向量入库 + metadata 检索 | Chroma API（非 Agent） |
| **Scout** | Agent | 聚类 / 偏移检测 / 信号报告 | 规则（HDBSCAN）+ LLM 簇命名 |
| Approval | 审批 | 人工闸门 | Streamlit UI（非 Agent） |
| **Evaluator** | Agent | 证据覆盖度 / 可证伪性打分 | 单轮 LLM 结构化输出 |
| Output | 生成器 | 简报 Markdown + JSON | 规则拼装 + 模板渲染 |

---

## 1. Cleaner Agent（语义清洗）

### 1.1 定位

> 把脏反馈变成干净的结构化记录。v1 做三件事：**去重**、**脱敏**、**标准化**。

### 1.2 输入

```jsonc
// 来自 inbox 的原始反馈
{
  "id": "raw_001",
  "raw_text": "13812345678 张三在腾讯面的 AI 岗，问了 RAG 项目... 2025年12月3日",
  "source": "other_jingyan",
  "received_at": "2026-08-18T10:00:00Z"
}
```

### 1.3 输出

```jsonc
{
  "id": "clean_001",
  "raw_id": "raw_001",
  "raw_text": "13812345678 张三在腾讯面的 AI 岗，问了 RAG 项目...",  // 保留原样
  "normalized_text": "某用户在腾讯面试 AI 岗，涉及 RAG 项目相关问题... 2025-12-03",
  "dedup_hash": "a3f8b2c1...",       // 规范化哈希（粗筛用）
  "dedup_embedding": null,           // S2 入库时由 Memory 生成
  "is_duplicate": false,             // true → 不入库，标记 dup_of
  "dup_of": null,                    // 被去重时指向保留的 clean_id
  "pii": {
    "found": ["phone:138****5678", "name:张三"],
    "masked": true
  },
  "source": "other_jingyan",
  "cleaned_at": "2026-08-18T10:00:01Z",
  "quality": {
    "dedup_stage": "llm",           // "hash" | "llm"（使用哪层判定）
    "pii_stage": "regex+llm",       // "regex_only" | "regex+llm"
    "normalization_ok": true
  }
}
```

### 1.4 处理管线

```
raw_text
  │
  ├─→ [规则] 标准化：日期→ISO / source 枚举校验 / 空白规范化 → normalized_text
  ├─→ [规则] 生成 dedup_hash（normalized_text 的 hash + source 组合）→ 粗筛
  ├─→ [LLM]  若 hash 碰撞或疑似相似 → 调 Cleaner Prompt 精判 → is_duplicate
  └─→ [规则+LLM] PII 扫描：正则扫手机/邮箱 → LLM 扫姓名/公司/学校 → 脱敏 → mask
```

### 1.5 Prompt 设计

**System Prompt**
```
你是一个求职反馈清洗助手。你的任务是：
1. 判断两条反馈是否为重复内容（同一个人同一个面试事件）
2. 识别并标记文本中的个人敏感信息（PII）

判重规则：
- 如果描述的面试事件（公司+岗位+核心问题）高度一致 → 重复
- 仅是公司相同但岗位不同 → 不重复
- 仅是面试形式相同（如"都问了算法题"）→ 不重复

PII 规则：
- 手机号、邮箱、真实姓名、身份证号 → 必须标记
- 公司名、岗位名、面试题内容 → 保留，不标记
- 只输出 JSON，不输出任何解释文字
```

**重复判断调用**（当两条 hash 碰撞或嵌入距离 < 阈值时）
```
## 反馈 A
{text_a}

## 反馈 B
{text_b}

判断两条反馈是否重复。只输出 JSON：
{"is_duplicate": true/false, "reason": "一句话（≤20字）"}
```

**PII 扫描调用**
```
## 反馈文本
{text}

标记所有 PII。规则：手机号→phone、邮箱→email、真实姓名→name。
输出 JSON：
{"pii": [{"type": "phone/email/name", "value": "原始值", "start": 0, "end": 5}]}

如无 PII：{"pii": []}
```

### 1.6 质量自检

| 检查项 | 方式 | 失败处理 |
| --- | --- | --- |
| 输出 JSON 可解析 | `json.loads()` | 重试 1 次，仍失败 → 抛异常 |
| PII 脱敏覆盖率 100% | 正则回扫：输出文本中不应有裸 PII | 记录原始文本、标记 `pii_leak: true` |
| `is_duplicate=true` 时 `dup_of` 非空 | 字段校验 | 抛异常 |
| `source` 合法枚举值 | 枚举白名单 | 抛异常 |

### 1.7 v1 取舍

| 做 | 不做（留 v2） |
| --- | --- |
| 双通道去重（hash + LLM） | 模糊去重阈值自动调参 |
| 正则 + LLM 联合 PII | 命名实体识别模型（BIO 序列标注） |
| 日期/枚举标准化 | 文本归一化（英文大小写、标点） |
| 质量报告统计汇总 | 质量趋势面板 |


---

## 2. Scout Agent（信号探测）

### 2.1 定位

> 从一堆反馈中找出主题规律和趋势变化。"scout"不是巡逻兵——是个看数据的探子。

### 2.2 输入

```jsonc
{
  "feedback_batch": [
    {
      "id": "clean_001",
      "normalized_text": "某用户在腾讯面试 AI 岗，涉及 Agent 框架相关问题...",
      "source": "other_jingyan",
      "created_at": "2026-08-15T12:00:00Z",
      "embedding": [0.123, -0.456, ...]    // 由 Memory 生成后传入
    },
    // ... 共 N 条
  ],
  "previous_signals": [                    // null 表示首次运行
    {
      "cluster_id": "c1",
      "label": "RAG与检索增强",
      "count": 12,
      "timestamp": "2026-08-08T00:00:00Z"
    }
  ]
}
```

### 2.3 输出

```jsonc
{
  "run_id": "scout_20260818_001",
  "clusters": [
    {
      "cluster_id": "c1",
      "label": "RAG与检索增强",
      "label_confidence": 0.85,           // LLM 命名自评
      "count": 15,
      "sample_ids": ["clean_001", "clean_005", "clean_012"],
      "keywords": ["向量检索", "RAG", "知识库", "Chroma"]
    },
    {
      "cluster_id": "c2",
      "label": "Agent框架与多智能体",
      "label_confidence": 0.78,
      "count": 8,
      "sample_ids": ["clean_003", "clean_009"],
      "keywords": ["LangGraph", "ReAct", "Function Call"]
    }
  ],
  "alerts": [
    {
      "type": "emerging",                  // "emerging" | "shift" | "surge"
      "cluster_id": "c2",
      "label": "Agent框架与多智能体",
      "description": "新主题出现：过去一周 8 条反馈涉及 Agent 框架，此前无此主题",
      "evidence_ids": ["clean_003", "clean_009"],
      "suggested_priority": "P0"           // P0/P1/P2，基于增幅与受影响的岗位数
    },
    {
      "type": "surge",
      "cluster_id": "c1",
      "label": "RAG与检索增强",
      "description": "量级激增：从 12 条增至 15 条，增幅 25%，超过阈值 20%",
      "evidence_ids": ["clean_001", "clean_005", "clean_012", "clean_018"],
      "suggested_priority": "P1"
    }
  ],
  "cluster_purity": 0.72,                  // eval 用
  "generated_at": "2026-08-18T12:00:00Z"
}
```

### 2.4 处理管线

```
feedback_batch + embeddings
  │
  ├─→ [规则] HDBSCAN 聚类（min_cluster_size=3, metric=cosine）
  ├─→ [LLM]  每簇取前 5 条 sample → 调命名 Prompt → label + keywords + label_confidence
  ├─→ [规则] 对比 previous_signals：
  │      - 新簇（簇ID 首次出现） → emerging
  │      - 已有簇 count 增幅 >20% → surge
  │      - 已有簇 count 降幅 >30% → decay（v2 做，v1 忽略）
  └─→ [规则] 生成 alerts + suggested_priority
```

### 2.5 Prompt 设计（簇命名）

**System Prompt**
```
你是一个面经主题分析师。给定一个簇中的代表文本，请：
1. 提炼该簇的主题标签（≤10 字中文）
2. 提取 3-5 个关键词
3. 对标签质量自评（0-1 置信度）

标签要求：
- 具体而非泛泛（"RAG检索问题"优于"面试题"）
- 面经语境下可理解
- 不要编造不在样本中的内容

只输出 JSON，无解释：
{"label": "...", "keywords": ["...","..."], "label_confidence": 0.85}
```

**调用示例**
```
## 簇样本（代表该主题的若干条反馈）
1. 腾讯AI岗问了RAG项目的向量检索选型，追问了Chroma和Milvus的区别
2. 百度面试问了如何做混合检索，BM25和向量怎么融合
3. 字节面试问到了RRF重排序的原理和实现
4. RAG项目里问答质量怎么评估，面试官问到了Recall和MRR
5. 面试要求在知识库里做父子分块，解释为什么不用普通分块

为该簇命名：
```

### 2.6 偏移检测规则

```python
# v1 硬编码阈值（v2 可配置化）
SURGE_THRESHOLD = 1.20    # 增幅 > 20%
EMERGING_MIN_COUNT = 3    # 新簇至少 3 条才报

def detect_shifts(current, previous):
    prev_map = {c.cluster_id: c.count for c in previous}
    for c in current:
        prev_count = prev_map.get(c.cluster_id, 0)
        if prev_count == 0 and c.count >= EMERGING_MIN_COUNT:
            yield Alert(type="emerging", ...)
        elif prev_count > 0 and c.count / prev_count >= SURGE_THRESHOLD:
            yield Alert(type="surge", ...)
```

### 2.7 v1 取舍

| 做 | 不做（留 v2） |
| --- | --- |
| HDBSCAN + 固定阈值偏移 | 自动确定最佳聚类数 / 自适应阈值 |
| LLM 命名 + 置信度自评 | 人工审校命名质量（UI 支持重命名） |
| 3 种告警类型（emerging/surge） | decay 告警、复合告警、时间序列预测 |
| 基于增幅的 suggested_priority | 影响力加权（聚类规模 × 岗位覆盖度） |


---

## 3. Evaluator Agent（假设评估）

### 3.1 定位

> 给审批通过的一条信号（假设）打两个分：**证据覆盖度**（这个假设有多少条面经支撑？缺哪些维度？）、**可证伪性**（这个假设有没有被推翻的可能？）。

### 3.2 输入

```jsonc
{
  "hypothesis": {
    "alert_id": "alert_002",
    "type": "surge",
    "cluster_label": "Agent框架与多智能体",
    "description": "Agent框架题目出现频次激增，可能成为近期高频考点",
    "evidence_ids": ["clean_003", "clean_009", "clean_015", "clean_022"]
  },
  "evidence_fulltext": [               // 证据原文（去除了 PII 的 normalized_text）
    "某用户在腾讯面试 AI 岗，问了 LangGraph 的 Agent 编排原理...",
    "某百度面试官问到了多 Agent 协作模式...",
    // ...
  ],
  "memory_context": {                  // Memory 检索到的相关背景信息
    "related_feedback_count": 5,
    "related_company": ["腾讯", "百度", "字节"],
    "related_roles": ["AI应用开发", "大模型算法"]
  }
}
```

### 3.3 输出

```jsonc
{
  "evaluation_id": "eval_20260818_001",
  "hypothesis_alert_id": "alert_002",

  // ── 证据覆盖度 ──
  "coverage": {
    "score": 7,                        // 1-10
    "strengths": [
      "4 条证据来自 3 家不同公司（腾讯、百度、字节），来源分散度高",
      "证据覆盖了 Agent 框架的多个子维度：编排、协作、工具调用"
    ],
    "gaps": [
      "所有证据均来自大厂，缺少中小公司视角",
      "未覆盖 Agent 框架的性能/成本相关面试题",
      "证据时间跨度仅 1 周，长期趋势未知"
    ],
    "evidence_density": 0.08           // 证据条数 / 同期总反馈数（8% 的反馈在谈这个话题）
  },

  // ── 可证伪性 ──
  "falsifiability": {
    "score": 6,                        // 1-10
    "testable": true,
    "falsification_conditions": [
      "如果后续 2 周 Agent 相关反馈回落至 3 条以下，则假设不成立",
      "如果这些面试题仅集中在 P7+ 岗位，假设需限缩为'高频仅针对高级岗'"
    ],
    "counter_example_suggestions": [
      "搜索：同期 AI 应用开发岗面经中，没有提及 Agent 的案例",
      "搜索：同期后端/前端岗面经中 Agent 相关问题的出现率"
    ]
  },

  // ── 综合评分（v1 简单加权） ──
  "overall_confidence": "中",         // 高(8-10) / 中(5-7) / 低(1-4)，映射自 coverage*0.6+falsifiability*0.4
  "recommended_action": "纳入简报，标注置信度'中'，建议 30 天内跟踪验证",
  "evaluated_at": "2026-08-18T12:05:00Z"
}
```

### 3.4 Prompt 设计

**System Prompt**
```
你是一个求职面试信号评估专家。给定一条假设和支撑证据，请完成两项评估：

一、证据覆盖度（1-10 分）
评估维度：
- 来源多样性：证据来自多少家不同的公司、岗位
- 子维度覆盖：假设涉及的主题是否被多角度验证
- 样本代表性：证据能否代表目标岗位群体的整体趋势

二、可证伪性（1-10 分）
- 假设是否有明确的验证/推翻条件
- 推翻条件是否可操作（可通过进一步收集数据检验）
- 是否存在明显反例的可能

输出 JSON（无其他文字）：
{
  "coverage": {"score": 整数1-10, "strengths": ["理由1"...], "gaps": ["缺口1"...], "evidence_density": 浮点数},
  "falsifiability": {"score": 整数1-10, "testable": true/false, "falsification_conditions": ["条件1"...], "counter_example_suggestions": ["建议1"...]},
  "overall_confidence": "高/中/低",
  "recommended_action": "一句话建议"
}

评分锚点：
- coverage: 10=跨5+公司多岗位多维度，1=单条孤证
- falsifiability: 10=有精确可执行的推翻条件，1=无法被推翻（不可证伪的断言）
- overall_confidence: 高=8-10分加权，中=5-7，低=1-4（coverage*0.6+falsifiability*0.4）
```

**调用示例**
```
## 待评估假设
{alert_description}

## 支撑证据（共 {n} 条）
{evidence_fulltext}

## 背景信息
{memory_context}

请评估：
```

### 3.5 质量自检

| 检查项 | 方式 | 失败处理 |
| --- | --- | --- |
| 输出 JSON 可解析 | `json.loads()` | 重试 1 次 |
| score 在 1-10 | 范围校验 | 抛异常 |
| evidence_density 在 [0,1] | 范围校验 | 抛异常 |
| overall_confidence 在枚举内 | 枚举白名单 | 抛异常 |
| 一致性：温度 0 下 3 次重复评估分差 ≤1 | eval 脚本 | 标记但不阻塞 |

### 3.6 v1 取舍

| 做 | 不做（留 v2） |
| --- | --- |
| 单轮 LLM 打分（温度 0） | 多次投票取均值 / 校准偏差 |
| 覆盖度 + 可证伪性两项 | 时效性、影响力、新颖性等维度 |
| 简单加权 overall_confidence | 学习型权重 / 贝叶斯更新 |
| 3 次一致性锚定 | 跑完所有假设的均值→分差校准（需更多数据） |


---

## 4. Output Generator（简报生成器）

### 4.1 定位

> 非 Agent，是一个纯规则引擎 + Jinja2 模板渲染。把审批通过且评估过的信号打包输出。

### 4.2 输入

```jsonc
{
  "run_id": "run_20260818_001",
  "approved_hypotheses": [
    {
      "alert_id": "alert_002",
      "cluster_label": "Agent框架与多智能体",
      "suggested_priority": "P0",
      "approved_priority": "P0",
      "approved_by": "hw",
      "approved_at": "2026-08-18T14:00:00Z",
      "evaluation": {
        "coverage": {"score": 7, "strengths": [...], "gaps": [...]},
        "falsifiability": {"score": 6, "falsification_conditions": [...]},
        "overall_confidence": "中",
        "recommended_action": "纳入简报，30 天内跟踪验证"
      }
    }
    // ... 更多审批通过的假设
  ],
  "run_stats": {
    "total_feedback": 50,
    "cleaned": 48,
    "duplicates_removed": 2,
    "clusters_found": 5,
    "alerts_generated": 3,
    "approved": 2,
    "rejected": 1,
    "pending": 0,                      // 未审批
    "tokens_used": 12450,
    "total_duration_s": 45.2
  }
}
```

### 4.3 输出

**JSON 简报**（结构化数据，供后续消费）
```jsonc
{
  "briefing_id": "brief_20260818_001",
  "generated_at": "2026-08-18T14:30:00Z",
  "valid_until": "2026-09-17T14:30:00Z",    // 默认 30 天
  "summary": "本期基于 50 条面试反馈，识别出 2 条值得关注的求职信号",
  "items": [
    {
      "rank": 1,
      "hypothesis": "Agent框架成为近期高频考察方向",
      "confidence": "中",
      "priority": "P0",
      "evidence_count": 4,
      "evidence_ids": ["clean_003", "clean_009", "clean_015", "clean_022"],
      "coverage_score": 7,
      "falsifiability_score": 6,
      "strengths": [...],
      "gaps": [...],
      "risks": [
        "证据仅来自大厂，中小公司情况未知",
        "观察窗口仅 1 周，可能为短期波动"
      ],
      "recommended_action": "优先准备 Agent 框架相关面试题；2 周后复查信号是否持续",
      "valid_until": "2026-09-17T14:30:00Z"
    }
  ],
  "run_stats": {...},
  "pipeline_version": "v1.0.0"
}
```

**Markdown 简报**（人类可读，用于演示和分享）
```markdown
# 🔍 求职策略简报 · 2026-08-18

> 基于 50 条面试反馈 | 5 个主题簇 | 2 条审批通过的信号
> 本简报有效期至 2026-09-17

---

## ⚡ P0 · Agent框架成为近期高频考察方向

| 维度 | 详情 |
| --- | --- |
| 置信度 | 🟡 中 |
| 证据覆盖 | 7/10 — 4 条证据覆盖 3 家公司，但缺乏中小公司视角 |
| 可证伪性 | 6/10 — 若后续 2 周回落至 3 条以下则假设不成立 |
| 证据 | [查看原文 #003] [#009] [#015] [#022] |
| 风险 | 仅大厂视角；观察窗口短 |

> **建议**: 优先准备 Agent 框架（LangGraph/ReAct/多智能体协作）；2 周后复查信号持续性。

---

## 📊 运行统计

| 指标 | 数值 |
| --- | --- |
| 输入反馈 | 50 |
| 清洗后 | 48（去重 2） |
| 聚类数 | 5 |
| 告警数 | 3（批准 2 / 驳回 1） |
| LLM Token | 12,450（¥0.12） |
| 耗时 | 45s |

---
*由 AgentLoop v1.0.0 自动生成 · run_id: run_20260818_001*
```

### 4.4 处理管线

```
approved_hypotheses + run_stats
  │
  ├─→ [规则] 按 approved_priority 排序（P0 > P1 > P2）
  ├─→ [规则] 过滤：overall_confidence=低 的条目仍输出，但置信度字段标 🔴
  ├─→ [规则] 计算 valid_until = now + 30天
  ├─→ [规则] 过期条目 → 回流待审队列（检查 validity_until < now 的已审批项）
  └─→ [模板] Jinja2 渲染 Markdown + JSON 双输出
```

### 4.5 v1 取舍

| 做 | 不做（留 v2） |
| --- | --- |
| Markdown + JSON 双格式 | PDF / 网页版 |
| Jinja2 静态模板 | 动态模板 / 图表嵌入 |
| 置信度标色 | 雷达图 / 多维雷达 |
| 过期自动回流 | 邮件/推送提醒 |


---

## 5. Agent 间数据契约（连线对照）

| 连线 | 起点 → 终点 | 起点的输出字段 | 终点的输入字段 |
| --- | --- | --- | --- |
| e1 | Inbox → Cleaner | `raw_text`, `source`, `received_at` | Cleaner 输入（§1.2） |
| e2 | Cleaner → Memory | `clean_*` 全部字段 | Memory 写入：`normalized_text`（向量化）+ metadata 全量 |
| e4 | Memory → Scout | `feedback_batch`（含 `embedding`） | Scout 输入（§2.2） |
| e5 | Scout → Approval | `alerts[]` 全量 | Streamlit 渲染：信号摘要、证据条数、趋势方向、suggested_priority |
| e6 | Approval → Evaluator | 审批通过的 alert + 优先级 + 审批人 + 理由 | Evaluator 输入（§3.2） |
| e7 | Approval → Output | 审批信息（不经过 eval，兜底输出） | Output 直接打包（无评估分数，置信度标注"未评估"） |
| e8 | Evaluator → Output | `evaluation` 全量 | Output 简报 items（§4.3） |

**契约校验规则**
- 每个模块入口校验必填字段非 null
- schema 版本号附在输出中：`{..., "schema_version": "v1"}`
- 字段语义变更需递增 `schema_version`，下游做版本判断

---

## 6. 附录：Prompt 模板汇总

### A. Cleaner 去重 Prompt
```
## 反馈 A
{text_a}

## 反馈 B
{text_b}

判断两条反馈是否重复。只输出 JSON：
{"is_duplicate": true/false, "reason": "一句话（≤20字）"}
```

### B. Cleaner PII 扫描 Prompt
```
## 反馈文本
{text}

标记所有 PII。规则：手机号→phone、邮箱→email、真实姓名→name。
输出 JSON：
{"pii": [{"type": "phone/email/name", "value": "原始值", "start": 0, "end": 5}]}

如无 PII：{"pii": []}
```

### C. Scout 簇命名 Prompt
```
你是一个面经主题分析师。给定一个簇中的代表文本，请：
1. 提炼该簇的主题标签（≤10 字中文）
2. 提取 3-5 个关键词
3. 对标签质量自评（0-1 置信度）

只输出 JSON：{"label": "...", "keywords": ["...","..."], "label_confidence": 0.85}

## 簇样本
{samples}
```

### D. Evaluator 评估 Prompt
```
你是一个求职面试信号评估专家。给定一条假设和支撑证据，请完成两项评估并输出 JSON。

评估维度：证据覆盖度（1-10）、可证伪性（1-10）。
评分锚点：覆盖度 10=跨5+公司多维度，1=孤证；可证伪性 10=有精确推翻条件，1=不可证伪。

输出 JSON：
{
  "coverage": {"score": 1-10, "strengths": [...], "gaps": [...], "evidence_density": 0.0-1.0},
  "falsifiability": {"score": 1-10, "testable": true/false, "falsification_conditions": [...], "counter_example_suggestions": [...]},
  "overall_confidence": "高/中/低",
  "recommended_action": "一句话"
}

## 待评估假设
{hypothesis_description}

## 支撑证据（共 {n} 条）
{evidence_fulltext}

## 背景信息
{memory_context}
```
