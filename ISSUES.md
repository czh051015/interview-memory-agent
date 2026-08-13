# Issues · 秋招 Copilot v1 Cleaner Demo

> 发现日期：2026-08-12
> 数据来源：`data/seed/interview.txt`（字节 AI 应用开发 一面，778 字，21 题）
> 基线：拆解准确率 100%（21/21），unknown 率 14%（3/21），均达标
> 最后更新：2026-08-12（全部关闭）

---

## Bug

| # | 严重 | 描述 | 根因 | 解决方案 | 状态 |
| --- | --- | --- | --- | --- | --- |
| B1 | 中 | **嵌入调用次数过多**：21 条 KnowledgeItem 逐条调了 21 次 Ollama embed API（约 50s 耗时） | `embed_ollama()` 逐条调 `/api/embeddings` | 改为批量 `/api/embed` 端点，一次 HTTP 请求传入全部文本。21 条 ~50s → ~3s | ✅ 已关闭 |

---

## 功能修复

| # | 严重 | 描述 | 解决方案 | 状态 |
| --- | --- | --- | --- | --- |
| F1 | 中 | **检索噪音**：搜"Agent"返回"多线程写一个死锁"（cosine ≈ 0.12）。21 条数据量太小，768 维向量区分度不够 | `search()` 加 `similarity_threshold` 参数；`_parse_results` 附加 `_similarity` 属性；阈值经 eval 校准 | ✅ 已关闭 |
| F2 | 低 | **信息性题目进了薄弱主题**："有实习过吗？"是信息性问题，不应纳入错题本统计 | `KnowledgeItem` 加 `category` 字段（knowledge/info）；`get_stats()` 过滤 info 类；`run_interview.py` 标记 `[ℹ️信息]` 且不计入 fail/partial 计数 | ✅ 已关闭 |
| F3 | 低 | **占位符被 LLM 推断补全**：`*********` 被 Cleaner 推断为 `volatile` | `prompts.py` 加规则："题目含占位符（***、...、略）时保留原样，不要推断补全" | ✅ 已关闭 |

---

## 增强（非阻塞 v1）

| # | 优先级 | 描述 | 状态 |
| --- | --- | --- | --- |
| E1 | P1 | **unknown 状态催用户补标**：3 条 unknown 仅在日志输出建议，无实际交互 | ✅ 已关闭（v1.5）：`src/cleaner/annotate.py` 交互补标 f/p/x，`run_interview.py` 仅 TTY 触发，EOF 安全 |
| E2 | P2 | **部分脱敏文本还原标记**：输入含 `***` 等占位符时，Cleaner 应在日志中记录 | ✅ 已关闭（v1.5）：`decompose.py has_placeholder()` + warning 日志 |
| E3 | P2 | **检索结果按 metadata 排序**：当前仅按相似度，应支持 topic / company / status 组合过滤 + 排序 | ✅ 部分达成（v1.5）：`search()` 已支持 topic/company/status/source 组合过滤；按 priority 排序见 `run_market.py prioritize` 复习列表 |
| E4 | P1 | **余弦阈值校准**：通过 eval 脚本跑出最优阈值 | ✅ 已关闭：`eval/retrieval_eval.py`，5 条标注查询 × 6 个候选阈值 → Recall@5=0.667 稳定 + 噪音归零 → **推荐阈值 0.45**；`search.py` 已更新默认值 |

---

# Issues · v1.5 市场信号（2026-08-12 验收后）

> 验收：20 条网上面经 ✅ · JD 提取 21/21=100% ✅ · 交叉验证 4 道 fail 题 p=1.8 ✅ · source 三枚举过滤 ✅

| # | 严重 | 描述 | 状态 |
| --- | --- | --- | --- |
| V1 | 低 | **聚类桥接顺序敏感**：JD 关键词同时命中多个 cluster 只桥接第一个，"Agent设计"fail 题被误降 0.5 | ✅ 已关闭（commit 4e171bf）：命中多个 cluster 时全部合并 |
| V2 | 低 | **topic 匹配只做精确/包含**：语义相近但拼写无关的 pair 命中不了（"类加载"×"JVM"、"拒绝策略"×"线程池"），相关 fail 题优先级偏保守 | 🔲 待校准：攒够数据后考虑向量相似度匹配 |
| V3 | 低 | **权重 1.5/0.5/1.2 与高频阈值 N=2 为初值**（计划书风险表） | 🔲 待校准：≥50 条后用 eval 校准 |

---

## 校准结果（E4）

```
阈值     Recall@5    噪音
0.30     0.667       1 题    ← 原始默认
0.45     0.667       0 题    ← ✅ 最优：噪音清零，Recall 不掉
0.50     0.667       0 题
0.60     0.417       0 题    ← 阈值过高，砍掉有效结果
```

**结论**：默认阈值设为 0.45。21 条数据量下，自然语言查询偶尔有噪音（~20%），属数据量不足的正常现象，数据量达到 50+ 条后重新校准。

---

# Issues · v1.5 测试结果（2026-08-13）

> 数据：public_jingyan 326 条 + JD 关键词
> 命令：`run_preprocess.py --view --top-n 10` · `search.py RAG` · `run_market.py prioritize`

| # | 严重 | 描述 | 证据 | 修法方向 | 状态 |
| --- | --- | --- | --- | --- | --- |
| V4 | 高 | **去重失效**：同一条文本重复入库，高频统计虚高 | `search.py RAG` 返回 3 条完全相同 `RAG (RAG) [jd]`，sim=1.00 | 预处理加去重：文本规范化 + hash/相似度，跨 source 也要去重（尤其 JD） | 🔲 待修 |
| V5 | 高 | **JD 关键词与面经题目混池**：JD 的"RAG"（技能关键词）被当题目入库，与面经题混算 | 搜 RAG 前 3 条全是无意义 `RAG [jd]`，挤掉真正的面经题 | 数据源分池：JD 提取成"技能标签"，面经才拆"题目"，两个 collection 分开统计 | 🔲 待修 |
| V6 | 中 | **流程/行为题混入考点榜**：category 未区分技术考点 vs 行为流程 | Top 榜第 4"自我介绍"、第 5"项目介绍" | topic 分类法加 category 层（技术/行为/流程/信息），Top 榜只统计技术类 | 🔲 待修 |
| V7 | 中 | **topic 粒度碎，聚合失效**：326 条数据 342 topics / 271 clusters，几乎一条一簇 | `run_market.py` 日志 `342 pool topics, 271 clusters` | 定固定 topic 分类法（10~15 大类），Cleaner 从枚举选而非自由发挥 | 🔲 待修 |
| V8 | 低 | **嵌入又逐条调用（B1 复发）**：market 模块未复用批量 embed | 10 次 `POST /api/embed` 一次一条 | market 模块复用 memory 的批量 `embed_texts` | 🔲 待修 |
