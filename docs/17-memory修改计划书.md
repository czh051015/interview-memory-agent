# memory 修改计划书 · 提醒 TopK + 毕业机制

> 配套：docs/15（错题回流+ReAct 主线）、docs/16（cleaner 修改计划书）
> 定位：给申论 Agent 的记忆层加上「提醒 topK（入口）+ 三个出口（毕业/stuck/pin）」的完整闭环。
> 前提：错题本（档案）≠ 提醒池——毕业/隔离只移出提醒池，档案永远保留。

---

## 0. 一句话目标

**让薄弱点档案从"静态排序列表"变成"带生命周期的记忆系统"：按遗忘状态动态提醒 topK 练习，练到「连续命中 + 间隔验证」就毕业移出提醒池，补不上的隔离并建议干预，用户想留的永远留。**

没有出口的提醒列表会退化：旧点永远占着 topK 名额，新弱点排不进去，提醒失效——毕业机制是健康运转的必需，不是加分项。

---

## 1. 现状盘点（基于真实代码）

| 模块 | 现状 | 与目标的关系 |
|---|---|---|
| `src/shenlun/profile.py` | `read_weak_points()` 按 `miss_count DESC` 排序 + `_tier()` 红黄绿分层（`miss≥2` 红 / `miss≥1` 黄 / `STALE_DAYS=14` 遗忘风险） | **改造核心**：分层已有雏形，但只看 miss_count，无时间维度、无毕业/隔离状态 |
| `src/memory/mastery.py` | `decay()` 遗忘曲线（`mastery×e^(-0.05t)`）、`review()` 复习重置、`rank()` 双因子排序、`layer()` 按 gap 分层（`GAP_RED=0.5`/`GAP_YELLOW=0.2`） | **直接复用**：遗忘曲线就是"间隔验证"的理论依据，λ=0.05 现成 |
| `src/shenlun/react.py` | `decide()`：读档案快照 → `search_questions()` 按题型检索 → LLM 决策；失败 `_rule_fallback()` 按 miss_count 最高推题 | **改造点**：决策输入要带状态（毕业考候选/stuck），输出要支持"外部干预建议" |
| `src/shenlun/reflow.py` | `reflow_answer()` 写 `answers` + 更新 `weak_points`（miss_count/hit_count/last_miss_at）+ 写 `events` | **改造点**：落库时更新新字段（consecutive_hits/state 等），events 加 action 枚举 |

**结论**：骨架全在，本次是"加状态 + 换排序 + 加出口"，不动既有核心逻辑。

---

## 2. 核心概念：错题本（档案）≠ 提醒池

这是本设计的灵魂，先写死：

```
┌──────────────────── 错题本（档案，永久保留） ────────────────────┐
│ 所有采集到的点，永远在。毕业/隔离只是"不再提醒"，不删除。      │
│                                                                │
│  ┌── 提醒池（state=active 的点，今天会提醒你练） ──┐            │
│  │  只在这里面的点，才出现在 topK 提醒里            │            │
│  └────────────────────────────────────────────────┘            │
│                                                                │
│  state=graduated（毕业）/ stuck（隔离）/ pinned（手动钉住）      │
│  档案里照在，只是提醒策略不同                                   │
└────────────────────────────────────────────────────────────────┘
```

**约定**：
- `weak_points` 每一行 = 一个采分点，`state` 字段决定它是否进提醒池
- 任何状态变更**不改删行**，只改 `state` + 留痕（`events`）
- 用户随时可翻看/检索全部档案（毕业的点也在）

---

## 3. 三个出口（这是新增的核心机制）

### 出口1：毕业（graduated）—— 系统自动，证明掌握

```
提醒池 → 连续命中 ≥3 次 → 距 last_hit_at ≥7 天 → 系统主动推「毕业考」→ 命中 → graduated
                                                          └→ miss → consecutive_hits 归零，重来
```

| 规则 | 默认值 | 为什么 |
|---|---|---|
| 连续命中 | `consecutive_hits ≥ 3` | 防蒙对：一次命中不算，连着对三次才稳定 |
| 间隔验证 | 最后一次命中后 ≥ 7 天再考 | 能扛过遗忘衰减才是长期记忆，不是热记忆 |
| 难度调节 | 被引导 3 轮才补上的点 → 连续 5 次 | 难救的点毕业门槛更高；`miss_count=0` 的点直接毕业 |
| 毕业考 | ReAct 主动推一道含该点的题 | Agent 主动性：主动安排验证，不是被动等用户碰到 |

**毕业考也是练习**：写 `events`（action=`graduation_check`）+ 更新 weak_points，作为档案"封板证据"。

### 出口2：stuck（隔离）—— 系统自动，防死锁

```
提醒池 → 尝试轮次 ≥ 30 未毕业 → state=stuck（移出高频提醒池）
                                  └→ ReAct 建议「外部干预」：先看素材/讲解，别盲目再练
```

**触发场景**（关键认知）：正常用户练 30 轮还不会，人自己就放弃了（行为兜底）。所以 stuck **不是用户能力审判，是数据质量警报**——LLM 拆的采分点烂/关键词歪，会导致评分传感器永远 miss，卡死循环。stuck 把这类题暴露出来："可能是这题数据有问题，建议检查采分点或换题"。

**刻意不做成状态机**："外部干预"是 ReAct 的一个**建议动作**，不是新状态——`guided_count`/`rescue_rounds_sum`（答案逼近信号）高，本来就该输出"先补知识"而不是"再练一遍"。省一整个机制，行为不变。

### 出口3：pin（手动钉住）—— 用户否决权

```
某点达到毕业条件、系统正要移出提醒池 → 用户 pin → state=pinned（一直留在提醒池，永不自动移除）
```

**不是收藏夹**：收藏是"额外存一个想看的东西"；pin 是"**否决系统自动毕业**"——只在系统想把它拿下来的瞬间有意义。场景：某采分点已掌握，但这是报考岗位的高频考点，用户想让它永远保持提醒。

### 复活（共同机制）

`graduated`/`stuck` 的点，用户主动练到且 miss → 立即回 `active`，重新计数、重进提醒池。毕业不是终身制。

---

## 4. 逐文件改造方案

### 4.1 `reflow.py` —— 落库逻辑扩展（🟡 低改动）

`_upsert_weak()` 更新时，除现有 miss/hit 外：

```python
# 每次练习（无论 hit/miss）都更新：
state           # miss 时若为 graduated/stuck → 复活回 active
consecutive_hits # hit +1；miss 归零
last_practiced_at # 每次练习更新（遗忘曲线的锚点）
last_hit_at      # 仅 hit 更新（间隔验证的锚点）
attempts         # miss_count + hit_count 即尝试轮次（无需新字段）
```

`events.action` 枚举扩展：`answered` → 加 `graduation_check`（毕业考）、`revive`（复活）。

### 4.2 `profile.py` —— 紧急度公式 + 池子过滤 + 毕业判定（🔴 核心改动）

**① 紧急度公式（两级映射的第一级）**——替代现在的 `ORDER BY miss_count DESC`：

```
紧急度(point) = 弱点权重 × 遗忘程度

弱点权重 = miss_count + guided_rounds_weight   # 漏得越多越紧急；引导 3 轮才补上 > 引导 1 轮就会
遗忘程度 = 1 - e^(-0.05 × 距 last_practiced_at 天数)   # 复用 mastery.decay 的 λ

# guided_rounds_weight 来自答案逼近的 rescue_rounds_sum/guided_count（docs/16 配套）
# 本阶段未接逼近时先为 0，公式骨架预留
```

**② 池子过滤**：`read_weak_points()` 只返回 `state=active` 的点进提醒池；`graduated`/`stuck` 不进 topK（档案查询另开接口）。

**③ 毕业判定**（新增纯函数，可测）：

```python
def is_graduate_candidate(wp, now) -> bool:
    # 连续命中达标 + 距 last_hit_at ≥ 7 天 → 标记为「毕业考」候选（state 不变，进候选列表）

def apply_graduation(wp, hit: bool):
    # hit → state=graduated, graduated_at=now；miss → consecutive_hits=0
```

`_tier()` 保留用于展示，排序交给紧急度公式。

### 4.3 `react.py` —— 决策输入升级 + 毕业考/干预动作（🟡 中改动）

**① 决策输入**：快照加入状态信息——`read_weak_points()` 增加返回"毕业考候选"列表（`is_graduate_candidate` 命中者），`decide()` 的 user_prompt 里新增一段：

```
## 毕业考候选（连续命中达标，间隔验证点）
- [c7] 设施互通（jiangsu_2023_a_1）— 连续命中 3 次，7 天未练，建议安排验证
```

**② 输出动作**：`ReactOutput` 增加可选字段 `action: "practice" | "graduation_check" | "intervene"`：
- `practice`：常规推题练
- `graduation_check`：推毕业考候选的题
- `intervene`：对 stuck 点输出"建议先看素材/讲解，检查采分点质量"——**不是新状态机，是 ReAct 的建议动作**

**③ `_REACT_PROMPT`** 增加一行规则："有毕业考候选时优先安排验证；有 stuck 点时建议外部干预而非再练"。

### 4.4 `mastery.py` —— 零改动（🟢 直接复用）

`decay(mastery, days, lam=0.05)` 的 λ 就是遗忘曲线参数；"间隔 ≥ 7 天"= 半个衰减周期的工程化近似。不改任何代码。

---

## 5. 表结构变更（`weak_points` 补 5 列）

| 新增列 | 类型 | 作用 |
|---|---|---|
| `state` | TEXT DEFAULT 'active' | `active` / `graduated` / `stuck` / `pinned` |
| `consecutive_hits` | INTEGER DEFAULT 0 | 连续命中计数（miss 归零）|
| `last_practiced_at` | TEXT | 每次练习更新，遗忘曲线的锚点 |
| `last_hit_at` | TEXT | 仅命中更新，间隔验证的锚点 |
| `graduated_at` | TEXT | 毕业时间（复活后清空）|

**刻意不加**：
- `attempts` —— 用 `miss_count + hit_count` 现算
- `mastery_score` —— 紧急度公式从 `last_practiced_at` 现算遗忘度，不需要存储值

`answers`/`events` 结构不动（events 只扩 action 枚举）。

---

## 6. 实施顺序（每步独立可验收）

| 步 | 改动 | 文件 | 验收标准 |
|---|---|---|---|
| 1 | 表结构：weak_points 加 5 列（迁移脚本）| `reflow.py` | 老库升级后 pytest 全绿，数据不丢 |
| 2 | 紧急度公式 + 池子过滤 | `profile.py` | 单测：miss_count 相同但更久没练的点排更前；graduated 点不进池 |
| 3 | 毕业判定纯函数 | `profile.py` | 单测：连续 3 命中+7 天→候选；中途 miss→归零；毕业/复活状态流转正确 |
| 4 | 落库逻辑扩展（consecutive_hits/state 更新 + events 新 action）| `reflow.py` | 交互演练：练 3 次全对→出现毕业考候选；毕业考 miss→复活 |
| 5 | ReAct 接入（毕业考候选入 prompt + action 字段 + stuck 干预建议）| `react.py` | 快照含毕业考候选；LLM 决策输出带 action；规则回退不崩 |

**建议节奏**：1+4 一起（都是落库侧），2+3 一起（都是档案侧），5 单独。参数（3 次/7 天/30 轮）全部定义为模块常量，跑起来再调。

---

## 7. 风险与规避

| 风险 | 规避 |
|---|---|
| **参数拍脑袋**（3 次/7 天/30 轮） | 全部模块常量 + `# 初值待校准` 注释（对齐 mastery.py 现状）；结构先定死，数字跑起来再调 |
| **毕业考打扰用户**（系统主动推题被当骚扰）| 毕业考候选每天最多 1-2 个，且用户可拒绝（跳过=不算 miss，只延后）|
| **stuck 误判**（好点被隔离）| stuck 不删档案、可复活；ReAct 输出的是"建议"不是"判决"，用户可无视 |
| **紧急度公式和 _tier 双轨混乱** | `_tier()` 只留作展示标签，排序唯一来源是紧急度公式（代码里注释写明）|
| **数据质量差放大**（LLM 拆点烂 → 全员 stuck）| stuck 恰好是警报器——建议里提示"检查采分点"，与 docs/16 的人审闸门形成闭环 |

---

## 8. 面试讲点

1. **"我处理了 leech 问题"**：借鉴 Anki 的隔离思想，但用档案里已有的引导信号（guided_count/rescue_rounds_sum）触发，不需要额外状态机——比"我做了个错题本"值钱十倍
2. **毕业 = 系统能证明你记住了**：连续命中 + 间隔验证（spaced repetition 思想），不是"时间到了就移走"
3. **毕业 ≠ 删除，可复活**：比朴素设计的"移出错题本=删除"多一层——用户不会因为误操作丢了画像
4. **stuck 是数据质量警报，不是能力审判**：说明你理解"评分传感器的输入不可全信"——和 cleaner 的人审闸门（docs/16）是同一套信任逻辑
5. **三个出口，一个都不移出错题本**：错题本是全集，动的只是"要不要提醒你"——档案价值与提醒价值解耦

---

## 9. 待确认事项

- [ ] 毕业考候选每天上限（1-2 个？）与"跳过=延后不算 miss"的交互是否 OK
- [ ] 参数初值（3 次/7 天/30 轮）是否先按此落地，跑起来再校准
- [ ] guided_rounds_weight 是否等「答案逼近」落地后再接（本阶段先为 0）
- [ ] `state=pinned` 的 UI 入口（CLI 命令还是配置），本阶段是否只留数据层接口
