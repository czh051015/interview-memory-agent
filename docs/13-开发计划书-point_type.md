# 开发计划书：采分点角度维度（point_type）与跨题型诊断

> 版本：v1 · 2026-08-29 · 作者：产品通（与 hw 共建）
> 衔接：`docs/12-能力诊断下钻-PRD.md`（本计划落地其 **O1 阻塞项**，实现 R1+R2 后端部分）
> 关联：记忆生命周期 `docs/17`、逼近 `docs/18`、拆解 `docs/`（cleaner 模块）

---

## 1. 目标

1. **解决 PRD O1（阻塞项）**：明确 `point_type` 的来源 = **"拆解"阶段由 LLM 顺手标注**（分类即标签），**不引入向量检索/语义相似度**做打标。
2. **诊断能力升级**：让系统从「按题型说你弱」（L1）升级到「按角度说你总漏哪类」（L2），即 PRD 的 R1+R2。
3. **交付可单测的 `diagnose()` 服务**：确定性、可 benchmark、不调 LLM，复用现有 `weak_points` 数据。

一句话交付：**用户在诊断页能说出"我申论最该补的是『对策可行性』这种角度"，并且能从这句话直接练一道同类题。**

---

## 2. 范围

| | 内容 |
|---|------|
| **In** | ① `point_type` 数据模型（score/reflow/profile/cleaner 四处）；② 拆解阶段注入 `point_type`；③ `diagnose()` 聚合服务；④ `/api/diagnose` 端点；⑤ `react.search_questions` 支持按角度过滤（为 R4 闭环铺路）；⑥ 老库迁移 + 单测 |
| **Out（本计划不做）** | ① 前端下钻 UI（PRD R3，依赖本计划产出，另立项）；② 诊断→练习前端闭环（PRD R4 前端部分）；③ 语义检索增强（练同类题推荐 / 洞察 agent，见 §11，明确分离、不阻塞核心）；④ 趋势可视化 / 摘要文本（PRD P1） |

---

## 3. 现状盘点（事实，带 file:line）

| 模块 | 位置 | 现状 | 缺口 |
|------|------|------|------|
| 评分模型 | `src/shenlun/score.py:12` `class Point` | 字段 `id/point/keywords/score`，**无角度** | 加 `type` |
| 金标转 Point | `src/shenlun/score.py:54` `from_benchmark()` | 读 `id/point/keywords/score` | 读 `point_type` |
| 薄弱点表 | `src/shenlun/reflow.py:80` `weak_points` | 有 `qtype`（题型），**无 `point_type`** | 加列 |
| 入库写点 | `src/shenlun/reflow.py:161` `_upsert_weak()` | 写入 `label/qtype/...`，无角度 | 传 `ptype` 并写库 |
| 档案聚合 | `src/shenlun/profile.py:209` `stats()` | **仅按 `qtype` 聚合**（即 L1） | 新增按 `point_type` 聚合（L2） |
| 档案对象 | `src/shenlun/profile.py:47` `WeakPoint` | 有 `qtype`，无 `point_type` | 加字段 + 映射 |
| **参考点来源（注入点）** | `src/cleaner/decompose.py:179` + `src/cleaner/prompts.py:62` | LLM 把标准答案拆成 `reference_points`（含 id/point/keywords） | **让 LLM 顺带标 `point_type`** |
| 题库检索 | `src/shenlun/react.py:66` `search_questions()` | 按 `wp.qtype` 过滤候选 | 支持按 `point_type` 过滤 |

**关键事实**：`reference_points` 不是手工写死的，而是 `cleaner/decompose.py` 让 LLM 从标准答案拆解产出的（`cleaner/prompts.py:62` 的 `SHENLUN_DECOMPOSE_SYSTEM`）。**这正是 `point_type` 的最佳注入点**——LLM 已经在产出该点，顺带标一个角度标签即可，零新增基础设施，不碰向量库。

---

## 4. 关键设计决策

- **D1（解 O1）：`point_type` 在"拆解"阶段注入，不用检索。**
  角度词典很小且固定（问题 / 原因 / 影响 / 对策 / 意义 / 危害 / 其他），属于**固定小类目分类**，不是开放式语义聚类。最适合的做法是：**让已经在产出该点的 LLM 顺带输出 `point_type`**（`cleaner/prompts.py` 改 prompt + `cleaner/schema.py` 的 `ReferencePoint` 加字段）。`score.from_benchmark` → `reflow.weak_points` 只是搬运，全程确定性。
  → 这**明确否决**了"用 embedding/向量相似度去给历史漏点聚类打标"的做法（那是过度设计，且不可靠）。

- **D2：诊断分两级，L2 才是护城河。**
  - L1 题型层（已有 `stats()`）：哪种题型漏点多 → "归纳概括是重灾区"。
  - L2 角度层（本计划新增）：把漏的点按角度归类 → 跨题型对比 → "你不是某题型弱，是总漏『对策可行性』这种角度"。
  - L2 揭示**可迁移的薄弱能力**，是区别于粉笔/SLB 的核心叙事。

- **D3：语义检索是独立后续能力，不用于打标。**
  用户提到的"语义相似度/检索"思路**有价值，但用错了位置**。它服务于诊断**之后**的闭环（练同类题推荐、采分点洞察 agent、评分近义匹配），见 §11，**不阻塞、也不参与核心打标**。核心打标走 D1。

---

## 5. 数据模型变更

### 5.1 `score.Point`（`src/shenlun/score.py:12`）
```python
@dataclass
class Point:
    id: str
    point: str
    keywords: list[str]
    score: int = 1
    type: str = ""   # 新增：采分角度（问题/原因/影响/对策/意义/危害/其他）
```

### 5.2 金标转换 `from_benchmark`（`src/shenlun/score.py:54`）
```python
return [Point(id=p["id"], point=p["point"], keywords=p["keywords"],
              score=int(p.get("score", 1)), type=p.get("point_type", ""))
        for p in reference_points]
```

### 5.3 拆解注入点（`src/cleaner/`）
- `schema.py` 的 `ReferencePoint` 增加 `point_type: str = ""`。
- `prompts.py:73` 的 `reference_points` 示例数组，每个点增加 `point_type` 字段，并在 system prompt 中说明枚举与标注口径（"按该采分点回答的是问题/原因/影响/对策/意义/危害中的哪一类"）。
- `decompose.py` 产出 `PointDecomposeResult` 时，`reference_points` 已带 `point_type`，下游 `reflow_answer` 直接消费。

### 5.4 `weak_points` 表加列（`src/shenlun/reflow.py:80`）
```sql
-- _SCHEMA 的 weak_points 定义增加：
point_type TEXT NOT NULL DEFAULT ''
```
并在 `_MIGRATION_COLUMNS["weak_points"]` 增加：
```python
("point_type", "TEXT NOT NULL DEFAULT ''"),
```
（老库平滑升级，缺列则 ALTER 补，数据不丢；已有行默认 `''` = 未分类，见 §10 风险。）

### 5.5 `profile.WeakPoint`（`src/shenlun/profile.py:47`）
```python
@dataclass
class WeakPoint:
    ...
    qtype: str
    point_type: str = ""   # 新增
    ...
```
`_row_to_weak()`（:121）增加 `point_type=r["point_type"] if "point_type" in r.keys() else ""`。

---

## 6. 改动清单（函数级）

| # | 文件 | 函数/位置 | 改动 |
|---|------|-----------|------|
| 6.1 | `score.py` | `Point` / `from_benchmark` | 加 `type` 字段并读取 `point_type`（§5.1–5.2） |
| 6.2 | `cleaner/schema.py` | `ReferencePoint` | 加 `point_type` 字段 |
| 6.3 | `cleaner/prompts.py` | `SHENLUN_DECOMPOSE_SYSTEM` | 示例数组加 `point_type` + 标注口径说明 |
| 6.4 | `cleaner/decompose.py` | 产出解析 | 确保 `reference_points` 透传 `point_type`（通常 pyDantic 自动） |
| 6.5 | `reflow.py` | `_SCHEMA` / `_MIGRATION_COLUMNS` | `weak_points` 加 `point_type` 列（§5.4） |
| 6.6 | `reflow.py` | `_upsert_weak()` | 签名加 `ptype: str = ""`；INSERT/UPDATE 写入 `point_type` |
| 6.7 | `reflow.py` | `reflow_answer()` | 调用 `_upsert_weak(..., ptype=p.type, ...)` |
| 6.8 | `profile.py` | `WeakPoint` / `_row_to_weak` | 加 `point_type` 字段与映射（§5.5） |
| 6.9 | `profile.py` | 新增 `stats_by_angle()` | 按 `point_type` 聚合（L2），结构与 `stats()` 对齐 |
| 6.10 | `profile.py` | `weakness_snapshot()` | 展示追加 `[{qtype}/{point_type}]`（可选，增强 ReAct 快照） |
| 6.11 | `react.py` | `search_questions()` | 支持按 `point_type` 过滤候选（为 R4 "练同类题"铺路） |

**核心数据流（改动后）**：
```
标准答案 ─▶ cleaner.decompose (LLM 标 point_type) ─▶ reference_points[]
   └─▶ score.from_benchmark ─▶ Point.type ─▶ reflow._upsert_weak ─▶ weak_points.point_type
                                                                    │
                                                          profile.stats_by_angle() / diagnose()
                                                                    │
                                                          /api/diagnose ─▶ 前端诊断页（PRD R3）
```

---

## 7. 新增 `diagnose()` 聚合服务

在 `src/shenlun/profile.py` 新增：
```python
def diagnose() -> dict:
    """三层诊断聚合（确定性，复用 weak_points）：题型 → 角度 → 薄弱点。"""
    pts = read_all_weak_points()
    by_type: dict[str, dict] = {}      # L1 题型层（已有 stats() 的逻辑）
    by_angle: dict[str, dict] = {}     # L2 角度层（本计划新增）
    for wp in pts:
        t = by_type.setdefault(wp.qtype, {"total":0,"red":0,"miss_sum":0})
        t["total"] += 1; t["miss_sum"] += wp.miss_count
        if wp.tier == "red": t["red"] += 1
        a = by_angle.setdefault(wp.point_type or "未分类",
                                {"total":0,"red":0,"miss_sum":0})
        a["total"] += 1; a["miss_sum"] += wp.miss_count
        if wp.tier == "red": a["red"] += 1
    return {"by_type": by_type, "by_angle": by_angle, "total_points": len(pts)}
```
- 纯 JSON，供前端与 ReAct 共用；不调 LLM。
- 落点：`app/api/` 新增 `/api/diagnose`（复用 `dashboard.py` 的 FastAPI 模式），返回 `diagnose()` 结果。

---

## 8. 测试计划（全部确定性，不调 LLM）

| 测试 | 覆盖 | 断言 |
|------|------|------|
| `test_from_benchmark_carries_type` | 6.1–6.2 | `from_benchmark([{...,"point_type":"对策"}])[0].type == "对策"` |
| `test_upsert_stores_point_type` | 6.5–6.7 | 入库后 `weak_points.point_type == "对策"` |
| `test_migration_idempotent` | 6.5 | 老库二次 `_conn()` 不报错、列存在 |
| `test_stats_by_angle` | 6.9 | 3 个"对策"类点 → `by_angle["对策"]["total"]==3` |
| `test_diagnose_structure` | §7 | mock `weak_points` 下 `diagnose()` 含 `by_type`+`by_angle`，结构稳定 |
| `test_search_by_angle` | 6.11 | 给定 red 点含 `point_type="对策"` → 候选优先返回对策类题 |
| `test_empty_state` | §7 | 0 作答 → `diagnose()` 返回空聚合、不抛异常 |

> 注意：`mock/cli.py:67` 用的 `item["gold"]["reference_points"]` 测试数据需补 `point_type` 字段（或测试时 tolerant 默认 `""`），防既有测试裂掉。

---

## 9. 里程碑 / 排期

- **Phase A（数据层，~2–3 天）**：6.1–6.9（score/cleaner/reflow/profile 四处模型 + 迁移）+ 单测。可独立验证：`diagnose()` 在真实库上返回 by_angle。
- **Phase B（服务 + API，~1–2 天）**：§7 `diagnose()` 落 `profile.py` + `/api/diagnose` 端点 + 6.11 `search_questions` 角度过滤。
- **Phase C（前端下钻，PRD R3，另立项）**：依赖本计划 A/B 的 `by_angle` 输出，做总览/下钻 UI。
- **Phase D（后续，§11）**：语义检索增强，不阻塞。

---

## 10. 风险与开放问题

| # | 风险/问题 | 处置 |
|---|-----------|------|
| R1 | **老库 `weak_points` 无 `point_type`** | 迁移默认 `''`（展示为"未分类"）；提供一次性 backfill 脚本：对已有题重跑 `cleaner.decompose` 补标，或粗粒度按"该点所属题型常见角度"默认。不阻塞上线。 |
| R2 | 角度枚举是否覆盖全部题型（PRD O2） | 先 6 类 + "其他"兜底；教研复核后扩。 |
| R3 | LLM 标错 `point_type` | **不影响评分**（`point_type` 仅用于聚合展示，不参与 hit/miss 判定）；`annotate.py` 已有 `approved` 人工环节可改。 |
| R4 | 用户题（`USER_QUESTIONS_DIR`）无 `point_type` | 经 `decompose` 生成时自带；纯手工题默认"未分类"。 |
| R5 | 与 PRD 排期关系 | 本计划 = PRD Phase 1 的**后端骨架**（R1+R2）；R3 前端、R4 闭环前端、P1 均在其后。 |

---

## 11. 后续：语义检索增强（用户提出的探索方向，明确分离）

> **定位**：这是诊断**之后**的能力层，用于"练同类题推荐 / 采分点洞察 agent / 评分近义匹配"，**不参与核心打标**（核心打标走 §4 D1）。不阻塞本计划。

| 场景 | 为何要检索 | 候选方法 |
|------|-----------|----------|
| ① 练同类题推荐 | 从历史漏点里找"语义相近的同类角度"，推一道题/相关点 | 本地 embedding 最合适 |
| ② 采分点洞察 agent（P1 R6 升级） | 检索"某题型通常从哪些角度出题"，告诉用户该盯哪些角度 | LLM + 检索混合 |
| ③ 评分近义匹配 | 用户写"健全配套" vs 标准点"完善基础设施" | LLM 判 or 轻量 embedding |

**检索方法对比（待 Phase D 细评）**：

| 方法 | 优点 | 缺点 | 适用 |
|------|------|------|------|
| 关键词/规则 | 快、零成本 | "对策可行性"等抽象角度词不常显式出现，召回低 | 预筛 |
| 本地 embedding（Ollama `dmeta-embedding-zh` 768 维 + Chroma，项目已有） | 语义准、免费、离线 | 需建索引 | ① 最合适 |
| LLM 分类 | 最准 | 慢/贵，不适合批量点 | ② 的推理层 |
| 混合（规则预筛 + embedding 精排） | 工程最稳 | 复杂度高 | 生产推荐 |

**结论**：核心 `point_type` 用 D1「拆解阶段分类」解决；语义检索是独立增强，放到 Phase D，方法选型按上表评估，优先验证 ①（embedding 推荐同类题）以闭合"诊断→练习"链路。

---

## 附：改动影响面速查

```
score.Point.type            ← 新增字段
score.from_benchmark        ← 读 point_type
cleaner.ReferencePoint      ← 新增 point_type
cleaner.prompts             ← LLM 顺手标 point_type（注入点★）
reflow._SCHEMA              ← weak_points 加 point_type 列
reflow._MIGRATION_COLUMNS   ← 老库补列
reflow._upsert_weak         ← 写 point_type
reflow.reflow_answer        ← 传 p.type
profile.WeakPoint           ← 新增 point_type
profile._row_to_weak        ← 映射 point_type
profile.stats_by_angle      ← 新增（L2）
profile.diagnose            ← 新增（三层聚合）
app/api/diagnose            ← 新增端点
react.search_questions      ← 支持按角度过滤（R4 铺路）
```
