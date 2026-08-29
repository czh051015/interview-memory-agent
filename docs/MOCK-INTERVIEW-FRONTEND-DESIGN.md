# OfferLoop 模拟面试 · 前端设计文档（grill v1 单轮版）

> 对应文件：`frontend/mock-interview-prototype.html`（可交互原型，双击即开）
> 本文档讲清：4 条 grill 推荐 → 前端交互决策 → 组件树 → API 契约 → v1.1 扩展位。
> 每一节都写「输入 / 输出 / 为什么」，面试时能对着讲。

---

## 1. 四条 grill 推荐 → 前端决策映射

| # | grill 推荐 | 前端落地 |
|---|-----------|---------|
| Q1 | (a) 只考 fail/partial 错题 | 开场页展示「本场题目」= 错题本 fail/partial 按 gap 排序 top N，不提供面经池入口 |
| Q2 | (c) LLM 给参考要点 + 差距 + 建议判定，用户确认 | 判定卡三段式：✅应该答到 / ✗你漏掉的 / ⚠️面试官的话，底部三选判定（LLM 建议已预选，可改） |
| Q3 | (a) LLM 现场生成期望要点 | 判卷阶段调 `POST /api/mock/verdict`，后端 LLM 生成 points，前端零录入 |
| Q4 | (c) 先单轮后多轮 | v1 状态机是「出题→回答→判定→下一题」直线；追问入口（v1.1）在文档 §7 预留 |

一句话总纲：**前端是「面试官的对话台」，判定卡是灵魂**——它把"自评无对照"的死结，变成"LLM 对照 + 你拍板"。

---

## 2. 页面状态机（v1）

```
setup ──开始面试──▶ question ──提交──▶ judging ──LLM返回──▶ verdict
  ▲                    │  ▲                                  │
  │                  退出 │ 重答                              │ 确认
  │                    ▼  └──────────────────────────────────┘
  └──────────再来一场◀── report ◀─────── 最后一题确认 ──────────
```

| 状态 | 触发 | 输入 | 输出 |
|------|------|------|------|
| setup | 进入页面 | — | 本场题目预览（错题 gap 排序） |
| question | 点「开始面试」 | 错题原文 + 考点标签 | 面试官气泡出题 + 输入框 |
| judging | 提交回答 | 题 + 回答 | 判卷动画（模拟 LLM 延迟） |
| verdict | LLM 返回 | 期望要点 / 差距 / 建议判定 / 理由 | 判定卡 + 三选确认 |
| report | 全部答完 | 逐题判定结果 | 统计 + 行为特征 + 写回说明 + 逐题复盘 |

为什么是直线状态机：v1 单轮没有分支（不追问、不跳题），直线最简单、最能聚焦验证"LLM 判断靠不靠谱"这个地基。分支复杂度留给 v1.1 追问。

---

## 3. 判定卡（Q2 核心，整个前端的灵魂）

三区块 + 一确认：

```
┌─ 🧑💼 面试官判定 ──────────────── LLM建议: 没答上 ❌ ─┐
│  理由：核心考点是"具体到型号+输入形态"，回答只到        │
│  "多模态模型"这一层，没有落点。                        │
│                                                       │
│  ✅ 这道题应该答到                                     │
│   ✓ 说清模型名称与厂商                                 │
│   ✓ 说明模型输入模态                                   │
│   ✓ 点出选型上下文                                     │
│                                                       │
│  ✗ 你漏掉的 / 差距                                     │
│   ✗ 模型名称模糊，只说"多模态大模型"                   │
│   ✗ 没说明是逐帧抽帧还是整段输入                       │
│                                                       │
│  ⚠️ 面试官的话                                         │
│   （同理由，突出可执行的改进方向）                      │
└───────────────────────────────────────────────────────┘
┌─ 🏁 最终判定（LLM建议已预选，你说了算）─────────────────┐
│  (•) 答对了 ✅   [•] 一半 ⚠️   [ ] 没答上 ❌            │
│  [重答此题]                [确认，下一题 →]             │
└───────────────────────────────────────────────────────┘
```

设计要点：
- **LLM 建议 = 预选，不是锁定**：用户可直接改判，这是"你最终拍板"的交互表达。
- **「重答此题」**：用户看完要点后想再试一次，不污染掌握度（answers 弹栈重来）。
- **建议判定徽章**放在判定卡头部，让"建议 vs 最终"对比一目了然。

---

## 4. 组件树（将来在 Next.js `app/mock-interview/` 落地）

```
MockInterviewPage（客户端组件，持有状态机）
├── Header（logo + 状态 pill + 阶段）
├── ProgressBar（第 X/N 题 + gap 提示）
├── SetupCard（本场题目预览 / 开始按钮）
├── QuestionStage
│   ├── InterviewerBubble（出题气泡）
│   └── AnswerBox（textarea + 提交）
├── JudgingStage（loading dots + 文案）
├── VerdictCard（Q2 灵魂，三区块 + 三选判定）
└── ReportView
    ├── StatGrid（pass/partial/fail 计数）
    ├── BehaviorTags（整场行为特征）
    ├── WriteBackNote（写回说明）
    └── ReviewList（逐题复盘）
```

与现有 `app/page.tsx`（通用聊天）的关系：**独立路由 `/mock-interview`，不塞进聊天**。原因：模拟面试是「有状态机的多阶段流程」，聊天是「无状态轮询」，混在一起会互相污染状态（工作记忆：Agent 内核是记忆+主动性，前端要有对应的一等公民入口）。

---

## 5. API 契约（前端 ← → FastAPI）

现状：`app/api/chat.py` 只有 `/chat`，`mock_interview` intent 是占位符（返回"第二版"）。v1 需要两个新端点：

### POST `/api/mock/start`
```
请求：{} （可选：{ n: 5 } 题数）
响应：{ questions: [{ id, question, topic, status, gap, days }] }
```
- 后端逻辑：复用 `src.mock.get_weak_questions()`（fail+partial → mastery.rank 排序 → top N）
- 为什么单独端点而不是复用 `/chat`：出题是「读库 + rank」的确定性操作，不需要 LLM 语义路由，快且稳。

### POST `/api/mock/verdict`
```
请求：{ question_id, question, answer }
响应：{
  points: ["应该答到的要点1", ...],
  misses: ["你漏掉的1", ...],
  suggested: "fail" | "partial" | "pass",
  reason: "判断理由"
}
```
- 后端逻辑：复用 `src.mock.get_expected_points()` + `judge_followup()`（去掉 need_followup 分支即单轮）
- `points` 对应 Q3(a)：LLM 现场生成，零录入负担。

### 写回（复用时序）
前端 report 页点「确认」后，可调 `/api/mock/complete`（或并入 verdict 逐题写回）：
```
请求：{ results: [{ question_id, question, verdict, answer }], behaviors: [...] }
```
- 复用 `_write_back()` + `record_result()`，fail→review_fail / partial→review_partial / pass→review。
- v1 建议**逐题写回**而非结束统一写：断了进度也在（已有 `interview_progress.json` 断点保护可参考）。

---

## 6. 数据流全图

```
用户 ──文字回答──▶ QuestionStage
                        │
                        ▼
               POST /api/mock/verdict ──▶ FastAPI ──▶ src/llm.chat_json（单轮，温度0）
                        │                              （多轮历史 v1.1 在这里加）
                        ▼
              { points, misses, suggested, reason } ◀── LLM JSON
                        │
                        ▼
               VerdictCard（预选 suggested，用户可改）
                        │ 确认
                        ▼
               POST /api/mock/complete ──▶ mastery.review/_fail/_partial
                        │                  + behavior_tags 合并
                        ▼
               错题本 mastery 更新 ──▶ run_remind 下次提醒抓到新弱点
```

闭环：**考（错题）→ 判（LLM+你）→ 写回（mastery）→ 下次提醒**。这就是"模拟面试的价值锚点"——它不只是练习，是给记忆系统喂新数据。

---

## 7. v1.1 追问扩展位（Q4 第二步）

v1.1 把 `verdict` 拆成两阶段：

```
question ──回答──▶ 追问判断（LLM: need_followup?）
                     ├─ true ──▶ 面试官追问气泡 + 再回答（循环，上限 2 轮）
                     └─ false ─▶ 判定卡（不变）
```

前端只需改三处：
1. **verdict API 响应加字段**：`need_followup: bool` + `followup_question: string`（后端 `judge_followup()` 已有现成输出！）
2. **QuestionStage 支持多轮**：`state.round` 计数，气泡列表变成 `[{interviewer, user} × n]`，轮次上限（MAX_FOLLOWUPS=2）由前端 + 后端双保险
3. **判定卡复用**：追问结束后进入同一个 VerdictCard，无需新组件

> 为什么 v1.1 改动这么小：CLI 版 `src.mock` 包已经把追问逻辑做完了（`interview_one` / `judge_followup`），前端 v1 先不接它验证判定可靠度，v1.1 直接把判定的输入换成"多轮拼接后的回答"即可。这不是返工，是故意分两半——先把"LLM 判定准不准"这个地基测了，再盖追问的楼。

---

## 8. 下一轮 grill 待定项（前端侧预埋）

| 待定项 | 前端影响 | v1 默认 |
|--------|---------|--------|
| 追问深度/轮数上限 | 仅 v1.1 生效 | 2 轮（复用 CLI 常量） |
| 会话历史落盘 | 决定是否要"恢复面试"按钮 | 不落盘，中断重来（CLI 已有 progress 机制可借鉴） |
| 掌握度用 LLM 判定还是最终确认结果 | 判定卡三选的结果就是写回输入 | 用**最终确认**结果（已在原型中实现） |
| 一场考几题 | setup 页题数 + 进度条分母 | 5 题（原型默认），建议做成可选 3/5/8 |

为什么 v1 用「最终确认结果」写回：LLM 建议只作预选，人确认的才是 ground truth——这跟 Q2 的哲学一致（LLM 不当你记忆的主人）。

---

## 9. 验收清单（做完能讲）

- [ ] `GET /mock-interview` 独立路由，复用 Header/风格，不塞进聊天页
- [ ] `/api/mock/start` 返回 gap 排序的 fail/partial 错题
- [ ] `/api/mock/verdict` 返回 points/misses/suggested/reason，前端判定卡三区块完整
- [ ] 判定三选可改，写回用最终确认值
- [ ] 报告页统计 + 行为特征 + 写回说明
- [ ] 原型（HTML）与真实页面交互一致——先拿原型跟用户过一遍，再写 Next.js 组件
