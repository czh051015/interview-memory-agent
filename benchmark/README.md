# 申论评审 Agent · 自建 Benchmark（v1）

> 目的：**验证"漏点识别"传感器不瞎**（能区分好答 vs 跑题答），为「错题回流 → 薄弱点档案 → ReAct 决策 → 计划/建议」这条 Agent 主线提供可信的数据源。
> 设计原则：**评分不追求精确，只输出 hit/miss；benchmark 缩到最小（两档作答，两个指标）**。

## 数据总览（36 道）

| 省份 | 年份 | 卷 | 题数 | 题型 | 权威性 |
|---|---|---|---|---|---|
| 河南 | 2024 | 市级以上 | 3 | 应用文×2 / 综合分析 | official（官方赋分标准）|
| 河南 | 2025 | 市级以上 | 3 | 归纳概括 / 应用文 / 综合分析 | official |
| 河南 | 2025 | 县级以下 | 5 | 归纳概括×2 / 应用文×2 / 综合分析 | official |
| 江苏 | 2019 | B 卷 | 3 | 综合分析 / 归纳概括 / 应用文 | training（培训机构参考答案反推）|
| 江苏 | 2022 | B 卷 | 4 | 归纳概括 / 综合分析 / 提出对策 / 应用文 | training |
| 江苏 | 2023 | A/B/C 卷 | 9 | 每卷 归纳概括 / 综合分析 / 提出对策 / 应用文 各一卷覆盖 | training |
| 江苏 | 2024 | B/C 卷 | 6 | 每卷 归纳概括 / 综合分析 / 应用文 | training |
| 江苏 | 2025 | A 卷 | 3 | 归纳概括 / 综合分析 / 应用文 | training |

- 题型覆盖：归纳概括×11、综合分析×11、应用文×11、提出对策×3（四题型齐备）
- 省份×年份：河南×{2024,2025} + 江苏×{2019,2022,2023,2024,2025} = **2 省 7 年**
- 每道含：`task.material/question/requirements` + `gold.reference_points`（带分值）+ `gold.requirement_checklist` + `samples.good/bad`（两档人工作答）

## 评测结果（权威引擎 `eval/score_eval.py`，A 纯关键词模式）

> ⚠️ 双引擎说明（docs/19 §10）：`benchmark/eval/eval_run.py` 是 benchmark 自带的极简引擎（v1 时代产物，README 曾记载 14 道）；
> **全仓权威引擎是 `eval/score_eval.py`**（带 per-type 分组、--only、--out，2026-08-29 实测 36 题），`eval_run.py` 仅保留作极简参考。

```
数据: 36 题  |  no_fool: 1.000  |  mean discrimination: 0.899
提出对策 1.000 / 综合分析 0.951 / 归纳概括 0.929 / 应用文 0.788
（2026-08-29 实测，即 eval/results/baseline 锚点）
```

| 指标 | 口径 | 结果 |
|---|---|---|
| discrimination | good 命中点数 > bad 命中点数（逐题均值） | 0.899 ✓ |
| no_fool | bad 未被误判「全命中」的比例 | 36/36 ✓ |
| per-type | 各题型 discrimination | 提出对策 1.0 / 综合分析 0.951 / 归纳概括 0.929 / 应用文 0.788 |

**结论：漏点识别传感器可靠** —— 能稳定区分"好答（命中 ~全部采分点）"和"跑题答（命中 <50%）"，且不会被流畅长文误导。
唯一瑕疵：jiangsu_2025_a_3 的 good 命中 <0.8（采分点可能标漏），已在 `score_eval` 的 `good_leak_count` 报告。

## 换壳说明（核心！）

引擎与 domain 完全解耦：

```
benchmark/eval/eval_run.py     ← 引擎（换壳零改动）
benchmark/data/*.json          ← domain 数据（换壳只改这里）
```

**换壳 = 替换 `data/` 目录内容**，新领域（如面试题、行测知识点）只需：
1. 按 `SCHEMA.md` 定义 JSON：`gold.reference_points[].keywords` 换成新领域的"知识点关键词"
2. 每题写 `samples.good`（覆盖 ≥90% 知识点）与 `samples.bad`（漏 ≥50% 或跑题、但文字流畅）
3. 跑 `eval/eval_run.py`，引擎和指标逻辑完全复用

引擎读取的字段只有 3 个：`gold.reference_points[].keywords`、`samples.good.text`、`samples.bad.text`。省份/题型/材料全部是元数据，不影响评测。

## 数据来源与 IP 边界

- **河南 11 道**：官方阅卷赋分标准（用户自整理 docx），`authority=official`，来源可讲
- **江苏 25 道**：培训机构真题+参考答案（公开 PDF），采分点由参考答案人工反推、分值人工分配，`authority=training`，权威性低于河南官方
- 不包含任何爬取的商业站数据；大作文（分档制）不进踩点 benchmark

## ⚠️ 计分口径：得分点总和 ≠ 满分（已知且正确）

河南官方赋分标准是**量分幅度制**，不是精确累加制：官方给出内容要点权重 + 量分幅度表（全面准确/卷面/字数分），实际阅卷按「要点 + 量分幅度 + 总体关照」**定档给分**。因此本集 11 道河南题的 `reference_points` 分值相加**均小于满分**（缺口 2~7 分），属正常现象，已逐题在 `gold.scoring_note` 记录。

**引擎不受影响**：评测只比较 good/bad 命中数大小（区分档位），不依赖"得分点总和 = 满分"。`score` 字段语义是档位权重，不是精确分数。江苏 3 道为人工配平，合计恰好 = 满分。

## 已知限制

1. **纯关键词匹配的漏判**：同义/拆分表述会漏判（A 模式已知短板），后续可用 embedding/LLM 模糊匹配增强——但那属于引擎升级，benchmark 结构不用改
2. **提出对策题量偏少**：四题型齐备但提出对策仅 3 道（discrimination=1.0 已达标），后续可补更多省份/年份的对策题
3. **bad 档人工构造**：为验证 no_fool 特意写了"流畅但跑题"的作答，真实考生作答分布可能不同（真实作答是加分项，非必须）
4. **江苏材料为摘要版**：材料取自 PDF 提取整理，非逐字原文（不影响评分评测；但拆解/引导评测会读材料，锚点词以材料实际文本为准）

## 目录结构

```
benchmark/
├── SCHEMA.md            # 字段定义与换壳契约
├── README.md            # 本文件
├── data/                # 36 道金标 JSON
│   ├── henan_2024_city_1..3.json
│   ├── henan_2025_city_1..3.json
│   ├── henan_2025_county_1..5.json
│   └── jiangsu_2019_b_1..3.json
│       jiangsu_2022_b_1..4.json
│       jiangsu_2023_a/b/c_1..3.json
│       jiangsu_2024_b/c_1..3.json
│       jiangsu_2025_a_1..3.json
└── eval/
    └── eval_run.py      # 极简参考引擎（权威引擎是 eval/score_eval.py）
```

> 本数据集的另一身份：**拆解评测（eval/decompose_eval.py）的 ground truth** —— `gold.reference_points` 直接作为
> 「LLM 拆解 vs 官方金标」对照的权威点集，无需另造标注数据（docs/19 §4.2）。
