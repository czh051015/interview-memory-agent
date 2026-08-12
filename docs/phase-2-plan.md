# 阶段二产品计划书 · v1.5 → v2.0

> 承接 `product-plan.md`（v1.0 正式基准）  
> 版本 v1.0 · 2026-08-12 · 状态：v1.0 已跑通，进入阶段二规划

---

## 0. 现状基线（v1.0 已完成）

| 能力                                   | 状态                         |
| ------------------------------------ | -------------------------- |
| Cleaner Agent 拆解面经 → KnowledgeItem   | ✅ 跑通（21/21 准确，unknown 14%） |
| status 打标（fail/partial/pass/unknown） | ✅ 关键词兜底 + LLM 推断双通道        |
| category 字段（knowledge/info）          | ✅ 已实现                      |
| Chroma 入库 + 批量嵌入                     | ✅ 已实现（B1 修复）               |
| 检索 + 相似度阈值过滤                         | ✅ 已实现（F1 修复）               |
| git 仓库 + GitHub 远程                   | ✅ 已推送（Private）             |

**待补**：v1.0.0 tag、issue 修复的独立 commit 历史、占位符保护（F3，低优先级）。

---

## 1. 阶段二目标

一句话：**从"记录错题"进化为"主动帮你复习"**。

v1 只是把错题存下来了。阶段二要让系统回答两个问题：

1. **这道题现在该不该复习？**（时间维度——mastery 衰减）
2. **这道题值不值得优先复习？**（外部验证——JD/题库交叉）

---

## 2. v1.5 —— JD 监控 + 交叉验证（先做）

### 2.1 Why

v1 的错题本只会告诉你"我错了什么"，不会告诉你"这个错误在当前市场里重不重要"。一道题你答错了，但如果它已经不在目标公司的考察范围内了，优先级应该降下来。反过来，一道你半懂不懂的题，如果正是今年 JD 里的高频要求，优先级应该顶上去。

### 2.2 用户故事

- 作为求职者，我希望系统能告诉我"我答错的题里，哪些是当前市场高频考点"，以便我把有限复习时间投在最值钱的地方。

### 2.3 功能范围

**In：**

- 引入第二数据源：`public_jingyan`（网上面经，只有题目，status=unknown）
- 引入第三数据源：`jd`（目标公司 JD，提取技能关键词）
- 交叉验证逻辑：错题 topic × 题库高频 × JD 要求 → 修正复习优先级
- `source` 字段三枚举：`self_review` / `public_jingyan` / `jd`

**Non-goals（明确不做）：**

- 不爬虫（数据手动粘贴或 CSV 导入）
- 不做 JD 自动抓取调度
- 不做多用户

### 2.4 交叉验证核心逻辑

```python
def adjust_priority(item: KnowledgeItem, market_stats: dict) -> float:
    """错题 × 市场信号，修正优先级。"""
    priority = 1.0

    # 你的错题 + 题库高频 = 优先级提升
    if item.topic in market_stats["high_freq_topics"]:
        priority *= 1.5
    # 你的错题 + 题库低频 = 优先级降低
    elif item.topic in market_stats["low_freq_topics"]:
        priority *= 0.5
    # 你的错题 + JD 明确要求 = 额外提升
    if item.topic in market_stats["jd_required_topics"]:
        priority *= 1.2

    return priority
```

### 2.5 验收标准（✅ 2026-08-12 全部达成，见 commit 2a27e2d~4e171bf，tag v1.5.0）

- [x] 导入 20 条网上面经（只有题目），全部 status=unknown，category=knowledge（`run_market.py jingyan`，seed: data/seed/public_jingyan.txt）
- [x] 导入 3 份目标公司 JD，提取技能关键词正确率 ≥ 80%（`eval/jd_extract_eval.py`：21/21 = 100%）
- [x] 交叉验证后，一道"答错的题"若 topic 命中 JD 关键词，优先级能从 1.0 提升到 ≥ 1.5（实测 4 道 fail 题 p=1.8）
- [x] source 三枚举在检索时可用 `where={"source": ...}` 正确过滤（self_review 21 / public_jingyan 20 / jd 29 条）

### 2.6 v1.5 实现记录（2026-08-12）

**代码结构**：新包 `src/market/`（jingyan.py 导入器 / jd.py 导入器 / cross_validate.py 交叉验证 / prompts.py）；`KnowledgeItem` 加 `source`（ItemSource 三枚举）与 `priority` 字段；CLI `run_market.py`（jingyan / jd / prioritize 子命令）；ISSUES E1（unknown 交互补标）E2（占位符日志）一并关闭。

**已校准**（E2E 实测发现并修复）：
- 聚类桥接顺序敏感：JD 关键词（如"Agent"）同时命中多个 cluster 时只桥接第一个，导致"Agent设计"fail 题被误降为 0.5 → 改为命中多个时全部合并（commit 4e171bf）。

**待校准**（按风险表约定，攒够数据后用 eval 校准）：
- 权重 1.5/0.5/1.2、高频阈值 N=2 为初值
- topic 匹配只做精确/包含，语义相近但拼写无关的 pair 命中不了（如"类加载"×"JVM"、"拒绝策略"×"线程池"）→ 后续可加向量相似度匹配

---

## 3. v2.0 —— Memory Agent（核心，等数据够再做）

### 3.1 前置条件

**KnowledgeItem 池 ≥ 50 条真实自评数据才启动 v2。** 理由：mastery 衰减曲线需要在足够多的"答错→复习→再答"数据上才有意义，21 条数据跑衰减函数是自欺欺人。

### 3.2 Why

v1.5 让系统知道"该优先复习什么"。v2.0 让系统知道"你忘没忘"——这是产品的灵魂。

### 3.3 核心能力

| 能力         | 实现                                                | 面试讲法                           |
| ---------- | ------------------------------------------------- | ------------------------------ |
| **掌握度衰减**  | `mastery_score(t) = e^(-λt)`，λ=0.05               | "艾宾浩斯遗忘曲线用在 Agent 长期记忆层"       |
| **复习重置**   | `mastery = min(1.0, 上次 × 1.2)`                    | "每次复习后掌握度非线性回升，符合间隔重复原理"       |
| **三元召回排序** | `relevance×0.5 + importance×0.3 + time_decay×0.2` | "Personalized RAG——检索后按用户状态重排" |
| **成长报告**   | Markdown：攻克/预警/新错题/优先复习                           | "不是静态简报，是随时间变化的个人状态机"          |

### 3.4 功能范围

**In：**

- mastery_score 衰减函数 + 复习重置
- 三元排序召回
- 成长报告生成（Markdown + JSON）
- 复习打卡入口（更新 last_reviewed_at / review_count）

**Non-goals：**

- 不做模拟面试（v3）
- 不做学习路径规划（v2.5）
- 不做多用户

### 3.5 验收标准

- [ ] 一条 fail 题入库 30 天后，mastery_score 从 1.0 衰减到约 0.22（λ=0.05）
- [ ] 用户复习后，mastery_score 回升且 review_count +1，last_reviewed_at 更新
- [ ] 三元排序：同 topic 下，"8 天未复习的题"排在"昨天刚复习的题"前面
- [ ] 成长报告四板块齐全：攻克 / 预警 / 新错题 / 优先复习

---

## 4. 技术实现要点

| 层  | v1.5                     | v2.0                               |
| -- | ------------------------ | ---------------------------------- |
| 数据 | 手动导入网上面经 + JD            | 复用 v1.5 数据 + 自己的新面试                |
| 存储 | Chroma 加 source metadata | KnowledgeItem 加 mastery 字段         |
| 逻辑 | 交叉验证函数                   | 衰减函数 + 排序函数                        |
| 编排 | 纯函数                      | LangGraph（state 管理，体现"Agent 长期记忆"） |
| 展示 | 终端输出                     | Streamlit 或 Markdown 报告            |



---

## 5. 里程碑

| 里程碑 | 内容                | 产出                             |
| --- | ----------------- | ------------------------------ |
| M1  | 补 v1 收尾           | ✅ tag v1.0.0 + issue 修复 |
| M2  | v1.5 交叉验证         | ✅ 导入网上面经 + JD，交叉验证函数 + 验收 4 条（tag v1.5.0，2026-08-12）    |
| M3  | 攒数据               | 🔲 真实面试 ≥ 50 条 KnowledgeItem（当前 21）      |
| M4  | v2.0 Memory Agent | 🔲 衰减 + 三元排序 + 成长报告 + tag v2.0.0  |

---

## 6. 风险

| 风险                      | 缓解                            |
| ----------------------- | ----------------------------- |
| 网上面经导入后 source 混淆       | source 三枚举严格区分，检索必须带 where 过滤 |
| v2 数据不足硬上衰减函数           | 严格执行 ≥50 条门槛，先攒数据             |
| 成长报告变成"看起来漂亮的 LLM 输出"   | 报告所有数字来自可复现的字段计算，不靠 LLM 编     |
| 交叉验证的权重（1.5/0.5/1.2）拍脑袋 | 先定初值，攒够数据后用 eval 校准           |

---

## 7. 面试叙事衔接

> v1 我证明了"系统能准确记住我的错题"。阶段二我让它"知道该不该提醒我复习"——v1.5 引入 JD 和网上面经做交叉验证，v2.0 把艾宾浩斯遗忘曲线接进 Agent 的长期记忆层。整条线讲下来，是一个系统从"记事本"长成"私人教练"的完整过程，而 commit 历史就是这个进化过程的证据链。
