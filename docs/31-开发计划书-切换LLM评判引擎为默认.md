# 31 · 开发计划书：切换 LLM 评判引擎（B）为默认评分引擎

> 前置：docs/26（引擎选型决策）、docs/29（金标口径回归）、docs/30（金标落地，已验证）。
> 本文把「B 上位」落成代码：**可插拔分发 + 默认切 llm + A 留兜底**。

---

## 0. 一句话

**加 `SCORE_ENGINE` 配置分发，默认值切 `"llm"`（B），`score_answer` 内部按配置分发到 `judge_score`，LLM 失败自动降级回 A（kw+语义），API/前端零改动。**

## 1. 背景：为什么现在切（full 终局数据，2026-09-01 17:51）

| 指标 | A 现有（kw+语义） | B（LLM-as-a-Judge） | 判定 |
|---|---|---|---|
| fuzzy 漏判率 | 68% | **0%** | B 完胜 |
| nosource 假阳性 | 38% | 36% | 平 |
| F1（medium 金标） | 49% | **84%** | B 大幅领先 |
| no_fool（红线） | 100% | 100% | ✅ 双守 |
| discrimination | 90% | 89% | ⚪ B 略降 1pp，仍健康 |
| 重跑一致性 | 100% | 100% | ✅ 生命线达标 |

- 对照 docs/26 §4 门槛：B 全部达标（no_fool=1.0、一致性≥90%、nosource 大幅降、F1 84%）
- 之前"B 未达标"是金标全 0 造成的假象（docs/29/30 已修正）
- 代价：单次评分 1 次 LLM 调用（约 10 秒）——碎片化备考场景可接受

## 2. 现状事实（代码侦察结论）

| 事实 | 位置 |
|---|---|
| ✅ `judge_score` 已存在：`(answer, points, materials, question) → (ScoreResult, warnings)`，**内部已内置 LLM 失败降级 score_answer** | `src/shenlun/judge_llm.py:140` |
| ✅ `score_answer` 签名：`(answer, points, materials, use_semantic, tau) → ScoreResult` | `src/shenlun/score.py:174` |
| ❌ **`SCORE_ENGINE` 配置不存在**（26 号规划的插拔架构未落地） | `src/config.py` |
| ✅ 评分调用点仅 2 处（后端 API），前端无感知 | `app/api/shenlun.py:163`、`:294` |
| ⚠️ 两引擎签名差异：`judge_score` 多 `question` 参数（题干，判"答非所问"用） | — |

**关键**：`judge_score` 返回结构兼容（ScoreResult），`from_benchmark` 产出的 `points` 两个引擎都吃——**分发层只需处理 `question` 参数的传递**。

## 3. 改动清单

### 3.1 `src/config.py`：加 SCORE_ENGINE 配置（1 处）

```python
# ── 评分引擎选型（docs/26 A/B 对比，docs/31 切换默认）──
# llm = LLM-as-a-Judge（judge_score，fuzzy 0%/F1 84%，单次约 10s，1 次 LLM 调用）
# kw  = 确定性两阶段（score_answer，0 token 秒级，留作兜底/离线）
SCORE_ENGINE = os.getenv("SCORE_ENGINE", "llm")  # llm | kw
```

### 3.2 `src/shenlun/score.py`：`score_answer` 加引擎分发（入口改造）

在 `score_answer` 函数体最前面加分发（**函数签名不变**，调用方零改动）：

```python
def score_answer(answer, points, materials="", use_semantic=True, tau=None):
    """两阶段命中判定……（原 docstring 保留）"""
    # docs/31：默认引擎切 llm，LLM 失败 judge_score 内部自动降级回本函数
    if SCORE_ENGINE == "llm":
        from src.shenlun.judge_llm import judge_score
        result, _warnings = judge_score(
            answer, points, materials=materials,
            question=points[0].question if points and hasattr(points[0], "question") else "",
        )
        return result
    # ... 原 kw+语义逻辑不动
```

**关键决策：question 从哪来？**
- `Point` 模型若已带 `question` 字段 → 直接取（零改动）
- 若没有 → 两方案：
  - **A. 在 `from_benchmark` 生成 points 时注入**（从 `d['task']['question']` 取，改 1 处）
  - B. API 层把 `req.question` 传给 `score_answer`（要改 2 处调用 + 签名，侵入大）
  - **推荐 A**：改动最小，且 points 自带题干语境对示证/错题回流也有用

> 需在实现时先查 `Point` 模型字段（`src/cleaner/schema.py:92` 附近），确认有没有 `question`。

### 3.3 降级链确认（无需改，验证即可）

`judge_score` 内部已有：LLM 挂 → 调 `score_answer` → 若 `SCORE_ENGINE=="llm"` 会**递归**！

**⚠️ 必须防递归**：`judge_score` 降级时应直接调 kw 分支，不能走分发入口。验证方式：
- 查 `judge_score` 降级处是否直接 `from src.shenlun.score import score_answer` 后调用——若是，需改为**传参绕过分发**（如 `score_answer(..., _engine="kw")` 或临时置空 SCORE_ENGINE）
- 这是本次实现**最容易踩的坑**，写进验收

### 3.4 不做的（列 Later）

- 前端展示 cause 诊断标注（"套话无具体性"等）——诊断层功能，另排期
- benchmark/medium 用 `--engine` 参数化——评测脚本已支持对比，不动
- A 的 τ 对 bge-m3 重校准——B 上位后 A 仅兜底，不值得

## 4. 验证（三步）

```bash
# 1. 单测防递归：确认 judge_score 降级不无限递归（新增 1 条测试）
cd D:/AIWorkspace/OfferLoop/offerloop
.venv/Scripts/python.exe -m pytest tests/ -x -q

# 2. 引擎切换冒烟：SCORE_ENGINE=llm 跑一条 medium 样本
.venv/Scripts/python.exe -c "
import json
from src.shenlun.score import from_benchmark, score_answer
d = json.load(open('benchmark/data/henan_2025_city_3.json', encoding='utf-8'))
points = from_benchmark(d['gold']['reference_points'])
sr = score_answer(d['samples']['good']['text'], points, materials=d['task']['material'])
print('引擎默认走 LLM:', sr.hit_points[0].matched_by if sr.hit_points else '?')
"

# 3. 回归对比：--quick 应保持 B 指标（fuzzy 0%、nosource 36%、F1 84%）
.venv/Scripts/python.exe eval/compare_engines.py --quick
```

**验收标准**：
- [ ] `SCORE_ENGINE=llm`（默认）时，评分走 LLM 判定，`matched_by="llm"`
- [ ] LLM 挂/超时 → 降级 kw 分支，**无递归死循环**
- [ ] `--quick` 指标与切换前一致（B fuzzy 0%、nosource 36%、F1 84%）
- [ ] 后端 `/practice/submit` 接口行为不变（返回结构兼容）
- [ ] 全量 pytest 无回归

## 5. 回滚方案

```bash
# 一行回滚：环境变量切回 kw，不改代码
$env:SCORE_ENGINE = "kw"
# 或持久化：setx SCORE_ENGINE "kw"
```

## 6. 工作量拆解

| 任务 | 复杂度 |
|---|---|
| config 加 SCORE_ENGINE | 低（1 行） |
| score_answer 分发 + question 注入 | 中（查 Point 字段 + 改 1-2 处） |
| 防递归确认/修复 | 中（最易踩坑，先查 judge_score 降级实现） |
| 测试 + 冒烟 + --quick 回归 | 低 |

## 7. 决策记录（面试叙事）

> "我用同一人工金标集做了引擎级 A/B 对比：确定性引擎（关键词+语义）在同义改写上漏判 68%，LLM 评判引擎（rubric 三步 + 强制证据）把它打到 0%、F1 从 49% 到 84%，红线（no_fool）双守、一致性 100%。金标口径回归（把'质量评分'从'漏点识别传感器'里拆出去）是让对比成立的前提。最终我把评分引擎做成可插拔配置（SCORE_ENGINE），默认切 LLM，失败自动降级回确定性引擎——API/前端零改动。"

## 8. 完成标准

- SCORE_ENGINE 配置生效，默认 llm ✅
- LLM 挂时降级 kw 不递归、评分永不空转 ✅
- --quick 回归指标不变 ✅
- 更新 docs/26 选型结论为"B 上位"（附终局数据表）✅
