# 27 · 评分引擎升级总计划：embedding 云端化 + LLM 判定增强 + 评测加速（修订）

> 配套 docs/26（引擎 A/B 对比）、docs/25（语义层）、docs/24（解析+Trace）。
> **修订记录（2026-09-01）**：范围从"judge_llm 增强"扩展为三件事——
> ① embedding 切云端 bge-m3（内存 + 压簇实验）② judge_llm 加 CoT + pydantic（治 nosource，prompt 已定稿未实现）
> ③ compare_engines 评测加速（--quick）。三件独立，可并行推进。

---

## 0. 一句话

**三个独立问题一次规划**：内存爆 → embedding 切云端 bge-m3（顺带压簇实验看确定性引擎还有没有救）；nosource 假阳性 100% → judge_llm 加三步 CoT + pydantic 校验；评测 9-16 分钟太久 → 加 `--quick` 快速模式。

## 1. 为什么改（三个问题，各自独立）

| # | 问题 | 现状 | 改动 |
|---|---|---|---|
| A | **内存爆** | 本地 Ollama 常驻 qwen7B（5-8G）+ dmeta，16G 机器吃紧 | embedding 切云端 bge-m3（SiliconFlow，免费，0 本地占用） |
| B | **nosource 假阳性 100%** | judge_llm rubric 有规则没方法，材料支撑检查从未执行 | prompt 三步 CoT（material_source 成为判定钥匙）+ pydantic 防静默错判 |
| C | **评测太久** | compare_engines 每次 9-16 分钟（93 次串行 LLM 调用 + 一致性 ×3） | `--quick` 只跑 medium + 并发 |

## 2. 改动一：embedding 云端化（bge-m3 + 压簇实验）

### 2.1 为什么
- **内存刚需**：评分语义层从本地 dmeta → 云端 bge-m3，本地占用归零（记忆检索仍用本地 dmeta，~1GB，别动）
- **压簇实验**：bge-m3（1024 维，SOTA 梯队）可能分开"套话 bad 簇 vs 真改写簇"（dmeta 实测压在同一 0.708-0.73 区间 → 单 τ 无解）——数据决定"确定性引擎 A 还值不值得救"

### 2.2 4 步改造

**① `src/config.py` 加 4 个环境变量**
```python
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
SILICONFLOW_EMBED_MODEL = os.getenv("SILICONFLOW_EMBED_MODEL", "BAAI/bge-m3")
SCORE_EMBED_BACKEND = os.getenv("SCORE_EMBED_BACKEND", "api")  # api | ollama
```

**② `src/memory/embedding.py` 新增 `embed_api`**（不动 `embed_texts`/`embed_ollama`——记忆检索保持 dmeta）
```python
def embed_api(texts, model=SILICONFLOW_EMBED_MODEL):
    """SiliconFlow bge-m3（OpenAI 兼容 /embeddings，批量）。"""
    if not SILICONFLOW_API_KEY:
        raise RuntimeError("SILICONFLOW_API_KEY 未配置")
    resp = httpx.post(f"{SILICONFLOW_BASE_URL}/embeddings",
        json={"model": model, "input": texts},
        headers={"Authorization": f"Bearer {SILICONFLOW_API_KEY}"}, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]
```

**③ `score.py` 的 `embed_zh` 按后端分发 + 三级降级**（api → ollama → 纯硬匹配）
```python
def embed_zh(texts):
    if not texts: return []
    try:
        if SCORE_EMBED_BACKEND == "api":
            from src.memory.embedding import embed_api
            return embed_api(texts)              # 云端 bge-m3（1024 维）
        from src.memory.embedding import embed_ollama
        return embed_ollama(texts)               # 本地 dmeta（768 维）
    except Exception as e:
        logger.warning("embedding %s 失败，降级本地: %s", SCORE_EMBED_BACKEND, e)
        try:
            from src.memory.embedding import embed_ollama
            return embed_ollama(texts)
        except Exception as e2:
            logger.warning("本地 embedding 也失败，纯硬匹配: %s", e2)
            return None
```

**④ 环境准备**：`SILICONFLOW_API_KEY` 已配置并验证（curl 实测 /v1/embeddings 返回 1024 维）；确认持久化（`setx` 用户级）

### 2.3 压簇实验（判定 A 引擎去留）

```
取 medium 的 fuzzy 样本（真改写，该给）和 bad 样本（套话，不该给）
对每个样本每个采分点算 max cosine（点 query vs 作答句）
统计两组相似度分布（min/max/均值/重叠区间）
dmeta 版 vs bge-m3 版并排对比（SILICONFLOW_EMBED_MODEL 换值即可）
```

**结果怎么用**：
- bge-m3 分开了（改写簇整体高、套话簇整体低）→ τ 有解 → A 引擎上限提升，26 号"40% 不可达"结论更新
- 还是压一起 → 换 `Qwen/Qwen3-Embedding-8B`（SOTA 备选）再试；若 8B 也分不开 → **坚定走 LLM+CoT 路线，A 只留兜底**

## 3. 改动二：judge_llm 增强（CoT + pydantic）

> 状态：prompt 三步 CoT **已在本文定稿，judge_llm.py 代码未实现**——本次落地。

### 3.1 prompt 三步 CoT（治 nosource，替换 `_JUDGE_SYSTEM`）

```
你是申论阅卷人。对每个采分点，先找证据、再按证据判定；严禁先判 hit/miss 再补证据。

对每个采分点，按三步执行：
【第1步·作答检查】作答里有没有表达该点的内容（原词或同义改写都算）？
  完全没有 → 直接判 miss，cause=没写，两个证据都填空串，跳过第2、3步。
【第2步·材料支撑检查】第1步找到的作答内容，能否在材料中找到语义支撑句？
  支撑句 = 材料中表达同一要点的原句；提出对策题可放宽：能对应到材料里的
  问题句/原因句也算支撑（阅卷规则：已有对策直接摘抄，隐性问题反向推导对策）。
  找到 → 记入 material_source；找不到 → material_source 填空串。
【第3步·按证据判定】
  - 有内容 + 找到材料支撑        → hit
  - 有内容 + 找不到材料支撑      → miss，cause=没结合材料（内容自创/套话/答非所问）
  - 有内容但表达模糊、意思没到位 → miss，cause=写模糊

输出 JSON（每个点必须包含三步证据，只输出 JSON）：
{"verdicts": [{"point_id": "c1",
               "verdict": "hit"|"miss",
               "cause": "没写"|"写模糊"|"没结合材料"|"",
               "matched_text": "作答原句（第1步证据，找不到填空串）",
               "material_source": "材料支撑句（第2步证据，找不到填空串）"}]}
```

关键机制：`material_source` 从"可选证据"变"判定钥匙"——**hit 必须有材料支撑**。fuzzy（源自材料→锚得到→hit）与 nosource（自创→锚不到→miss）被同一检查分开；对策题放宽防误杀推导型好答。

### 3.2 pydantic 语义校验（防静默错判）

```python
from pydantic import BaseModel
from typing import Literal

class Verdict(BaseModel):
    point_id: str
    verdict: Literal["hit", "miss"]
    cause: Literal["没写", "写模糊", "没结合材料", ""] = ""
    matched_text: str = ""
    material_source: str = ""

class JudgeOutput(BaseModel):
    verdicts: list[Verdict]
```

解析流程：`JudgeOutput.model_validate(result)` → 整体失败降级 `score_answer`；单条失败记 warnings 按 miss（仿 decompose 模式）。与语法层（`_repair_tail_brackets`，已修）分工：语法救"读不出来"，pydantic 救"读出来是错的"。

## 4. 改动三：评测加速（--quick）

**为什么**：compare_engines 每次 9-16 分钟（93 次串行 LLM 调用 + 一致性 ×3）——日常迭代等不起。

**方案**：
```
--quick 模式（日常迭代用）：
  - 只跑 medium 7 条（跳过 benchmark 36 题）→ 1-2 分钟
  - 一致性测试降为 1 次（定稿才 3 次）
  - LLM 调用并发 5（串行 → 3-5 路，注意 API 限速）
--full 模式（定稿/发布用）：现状不变（全量 + 一致性 3 次）
```

**工程习惯**：快慢两档——日常改 prompt 用 quick 看趋势，大定稿才 full。

## 5. 验证（整合）

| 验证项 | 方法 | 通过标准 |
|---|---|---|
| 压簇实验 | medium 上 dmeta vs bge-m3 分布对比 | 看重叠区间是否收窄/消失（数据决策，无预设） |
| nosource 攻防 | `--quick` 重跑 compare_engines | nosource 假阳性 100% → 明显下降 |
| fuzzy 不退化 | 同上 | 保持 0% |
| 红线 | 同上 | no_fool = 1.0 |
| 一致性 | 同上 | ≥90% |
| 边界 | 对策推导型（jiangsu nosource1/fuzzy1） | 推导型不误杀、套话型卡住 |
| 回归 | pytest 全量 | 326 条无回归（pydantic 新增用例） |
| 内存 | 任务管理器对比 | 评分时本地无 qwen7B、无 API 嵌入占用 |

## 6. 工作量拆解

| 任务 | 复杂度 | 依赖 |
|---|---|---|
| 2.2 embedding 4 步改造 | 低 | 无（key 已配） |
| 2.3 压簇实验脚本 | 低 | 2.2 |
| 3.1 CoT prompt 落地 | 低 | 无 |
| 3.2 pydantic + 解析流程 | 低 | 无 |
| 4. `--quick` 模式 | 中 | 无 |
| 5. 验证与回归 | 中 | 全部 |

## 7. 风险与边界

| 风险 | 应对 |
|---|---|
| 云端 embedding 网络依赖 | 三级降级链（api→ollama→纯硬匹配），评分永不空转 |
| bge-m3 免费限速（429） | 触发即降级；使用量小（每次评分 1 次调用） |
| CoT 让 prompt 变长 → 更慢 | --quick 加速 + 并发；单点判定不变 |
| 对策推导型被误杀 | prompt 放宽"问题/原因句算支撑" + 边界用例 |
| 一致性 <90% | 维持 A 默认，B 不切 |

## 8. 决策记录（面试叙事）

| 决策 | 选择 | 理由 |
|---|---|---|
| embedding 云端化 | bge-m3（免费）→ Qwen3-Embedding-8B（备选） | 内存刚需 + 压簇实验数据说话；先免费后更强 |
| 治 nosource | prompt 三步 CoT（材料支撑=判定钥匙） | A/B 对比证明瓶颈在判定方法不在引擎 |
| 防错判 | pydantic 语义校验（语法层已修） | 语法救格式、语义救内容，两层缺一不可 |
| 评测加速 | --quick（medium + 并发 + 一致性降频） | 快速反馈循环：日常 1-2 分钟，定稿才全量 |
| 引擎组织 | 可插拔并存不覆盖（docs/26 §6） | 兜底 + 对照 + 回滚 |

**面试一句话**："我做了三件独立的事：embedding 切云端（省内存 + 压簇实验用数据决定确定性引擎去留）、LLM 判定加三步 CoT + pydantic（材料支撑成为判定钥匙，语法语义双层防御）、评测加快速模式（日常迭代 1-2 分钟）——资源、质量、效率三个维度同时优化。"
