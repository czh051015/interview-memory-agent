# 错题回流 + ReAct 决策层 · 实现说明

> 申论评审 Agent 的主线闭环（v1）：**作答 → 漏点识别 → 错题回流 → 薄弱点档案 → ReAct 决策 → 计划/建议**
> 评分只是传感器，价值全在 Agent 主线。

## 模块一览

| 模块 | 职责 | 复用资产 | LLM? |
|---|---|---|---|
| `src/shenlun/score.py` | 评分传感器：作答+采分点 → hit/miss | benchmark 的匹配逻辑 | ❌ 确定性 |
| `src/shenlun/reflow.py` | 错题回流：作答即入库（answers + weak_points + events）| 无 | ❌ 确定性 |
| `src/shenlun/profile.py` | 薄弱点档案：聚合 miss → 采分点级弱点画像 + 分层 | mastery 遗忘思想 | ❌ 确定性 |
| `src/shenlun/react.py` | ReAct 决策：读档案 → 检索题库 → 计划/建议 | memory_keeper 范式 + llm.py | ✅ 决策 |
| `scripts/run_shenlun.py` | 演示闭环：抽题→作答→回流→建议 | — | — |

## 数据流

```
用户作答
  → score.score_answer()          # 纯关键词匹配，输出 hit/miss 采分点
  → reflow.reflow_answer()        # 写 SQLite：answers + weak_points(采分点级累计) + events
  → profile.weakness_snapshot()   # 聚合出"谁弱/弱多久/什么题型"快照
  → react.decide()                # LLM 读快照 → 输出 {focus, plan, advice}
      └─ 失败 → _rule_fallback()  # 按 miss_count 最高的薄弱点直接推题（Agent 不挂）
```

## 存储（data/shenlun.db）

- `answers`：每次作答（question_id, answer, hit_ids, miss_ids, hit_ratio, ts）
- `weak_points`：采分点级薄弱档案（point_key, label, qtype, miss_count, hit_count, last_miss_at）—— **记忆单元是采分点，不是整道题**
- `events`：作答事件时间序列（未来诊断/可视化用）

## 为什么这样设计（面试讲点）

1. **评分是确定性工具，不进 ReAct** —— 否则不可 benchmark，毁了"漏点识别可验证"（recall/no_fool 14/14）
2. **ReAct 只做决策**（选哪道题/给什么建议）—— 这才是"主动 Agent"：不是"存了什么给你什么"，是"根据你的弱点状态决定推什么"
3. **记忆单元 = 采分点** —— "归纳概括连续3次漏'对策可行性'"比"这题你不会"精细一个量级，这是市面没有的
4. **LLM 决策 + 规则回退双保险** —— LLM 挂掉时按 miss_count 最高的弱点直接推题，Agent 不会失效（对齐 memory_keeper 范式）

## 运行方式（用 Anaconda Python）

```bash
D:/ProgramData/anaconda3/python.exe scripts/run_shenlun.py --list     # 列题库
D:/ProgramData/anaconda3/python.exe scripts/run_shenlun.py --demo     # 自动演示闭环
D:/ProgramData/anaconda3/python.exe scripts/run_shenlun.py --advice   # 只出今日建议
D:/ProgramData/anaconda3/python.exe scripts/run_shenlun.py            # 交互作答
```

## 换壳说明

- `score.py` / `reflow.py` / `profile.py` / `react.py` **全部 domain 无关**（输入是采分点+作答，不认题型）
- 换壳 = 换 `benchmark/data/` 里的题目（如换成面试题：reference_points 换成知识点，samples 换好/坏作答）
- `react.py` 的 `_REACT_PROMPT` 里"申论"字样需随壳微调，其余零改动

## 下一步（待用户确认）

1. **记忆提醒**：把 `run_remind.py` 的间隔重复接到采分点档案上（"设施互通快忘了，建议重练"）
2. **多轮 ReAct**：当前是单轮决策，可扩展为思考→工具→观察→再决策
3. **真实作答**：用户用自己的作答跑一遍，验证采集体验
