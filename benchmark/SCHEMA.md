# Benchmark Schema 定义（引擎与 domain 分离）

> 设计目标：**换壳不改引擎**。引擎（漏点识别 + hit/miss + 指标）只依赖两个结构——
> `gold.reference_points`（金标采分点）与 `samples`（分档作答）。其余字段全部是 domain 元数据。

## 一、文件组织

```
benchmark/
├── SCHEMA.md            # 本文件
├── README.md            # 数据来源 / 指标口径 / 换壳说明
├── data/                # 结构化金标（每道一个 JSON）
│   ├── henan_2025_city_1.json      # 河南 25 市级
│   ├── henan_2025_county_1.json    # 河南 25 县级
│   ├── henan_2024_city_1.json      # 河南 24 市级
│   └── jiangsu_2016_b_1.json       # 江苏 16 B 类
└── eval/
    └── eval_run.py      # 评测脚本：加载 data/ → 跑匹配 → 算指标
```

## 二、Item JSON 结构

```jsonc
{
  // —— 通用元数据（domain 无关，换壳时保留框架）——
  "id": "henan_2025_city_1",            // 唯一 ID
  "domain": "shenlun",                   // 壳名：换壳时改成新领域（如 interview）
  "meta": {
    "province": "河南",
    "year": 2025,
    "paper": "市级以上",
    "type": "归纳概括",                   // 题型（换壳后变成领域内题型）
    "authority": "official",             // official官方/training培训机构/self自标
    "source": "2025河南省考赋分标准docx"
  },

  // —— 任务描述（domain 数据，引擎不消费，仅存档/可溯源）——
  "task": {
    "question": "请根据给定资料1，梳理概括……",
    "requirements": "全面准确、条理清晰；不超过250字",
    "material": "……材料全文……",        // 完整保留，未来 material-grounded 抽取用
    "max_score": 20
  },

  // —— 金标（引擎唯一依赖的 domain 数据）——
  "gold": {
    "reference_points": [
      { "id": "c1", "point": "设施互通", "keywords": ["城际公交", "高速免费"], "score": 1 },
      { "id": "c2", "point": "产业协同", "keywords": ["新兴产业带动", "物流枢纽"], "score": 1 }
    ],
    "requirement_checklist": [           // 可选：格式/字数/卷面等要求分
      { "item": "全面准确、条理清晰", "score": 2 }
    ]
  },

  // —— 分档作答（引擎唯一的评测输入；good=好答 / bad=跑题或一般）——
  "samples": {
    "good": { "text": "……覆盖全部采分点的作答……", "note": "人工标注：满分档" },
    "bad":  { "text": "……流畅但跑题/漏大部分点的作答……", "note": "人工标注：跑题档" }
  }
}
```

## 三、引擎与 domain 的耦合点（换壳的唯一改点）

| 引擎读取 | 换壳时替换为 |
|---|---|
| `gold.reference_points[].keywords[]` | 新领域的"知识点关键词" |
| `gold.reference_points[].score` | 新领域的分值（可全为 1，权重不重要） |
| `samples.good.text` / `samples.bad.text` | 新领域的好/坏样例作答 |

**换壳即换 `data/` 目录内容，`eval/` 与指标逻辑零改动。**

## 四、计分口径（重要：得分点总和 ≠ 满分）

**河南官方赋分标准是"量分幅度制"，不是"精确累加制"。**

- 官方标准给出的是：每个内容要点的权重（如"概括要点准确全面 13 分"）+ 量分幅度表（全面准确/卷面/字数各 2 分）
- 实际阅卷按「要点命中 + 量分幅度 + 总体关照」**定档给分**，得分点列出的分值只是内容要点的权重分布，**相加通常不等于满分**（本集 11 道河南题缺口 2~7 分）
- 江苏 3 道为培训机构参考答案人工反推，分值人工配平，恰好合计 = 满分

**这对引擎没有影响**：引擎只比较 `good vs bad` 命中数的大小（区分档位），不依赖"得分点总和 = 满分"。`score` 字段的语义是**档位权重**，不是精确分数。

每个 item 的 `gold.scoring_note` 字段记录了该题的计分口径来源，面试/审计时直接引用。

## 五、字段约定

- `keywords`：每个采分点 2-5 个关键词，命中任意一个即算该点命中（命中率 = 命中的点 / 总点）
- `score`：整型；点分值不追求精确，只用于区分档位高低
- `samples.good`：必须覆盖 ≥90% 采分点（验证 recall）
- `samples.bad`：必须漏掉 ≥50% 采分点或跑题（验证 no_fool），且文字流畅（防"长度/流畅误导"）
