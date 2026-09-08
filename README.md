# PointLoop（逐点）

申论作答的逐点评分与错题回流工具。代码目录沿用历史包名 `offerloop`（演进自早期面试备考模块），产品名与包名不对应，属正常情况。

## 项目定位

申论按采分点给分。本项目做的事是：给定题目与**经人工审核**的标准答案，把标准答案拆成采分点，对作答逐点输出「命中 / 漏答」判定与可回溯证据，漏掉的点进入本地薄弱点档案，并按遗忘间隔出现在后续练习提醒中。

输入 / 输出边界：

- 输入：题目 + 标准答案（拆解后人工审核）；考生作答。
- 输出：逐点 hit/miss 判定与证据、漏点清单、基于薄弱档案的每日提醒。
- 不输出：精确分数、范文、押题内容。

评分定位是「漏点识别传感器」，只回答"这个点写了没有、证据在哪"，不回答"这句话写得好不好"。

## 当前能力与边界

| 能力 | 说明 | 状态 |
|------|------|------|
| 标准答案拆解为采分点 | LLM 拆解，默认不通过，人工审核后入库（来源标记 official / human_approved / llm_draft） | 已实现 |
| 门禁评分（库内真题） | 确定性规则判绿（命中）/ 黄（漏答，0 LLM token）；灰色带（部分命中）才交 LLM 标「疑似」，不产生证据字段 | 已实现 |
| 示证评分（即时录入的题） | 无 trusted 信号时做 0 判定 token 的差异配对（对应句 / 未见对应句），不做好坏判定 | 已实现 |
| 错题回流与薄弱点档案 | 规则可证的漏答（黄档）自动进入档案，带生命周期（毕业 / 隔离 / 置顶） | 已实现 |
| 每日提醒 | 按紧急度（弱点权重 × 遗忘程度）排序，动态推送 | 已实现 |
| 能力诊断下钻 | 角度 → 薄弱点 → 同类题推荐的逐级下钻 | 未完成 |
| 语义检索（练同类题） | 基于 embedding 的同类题召回 | 未完成 |

## 评分机制：为什么不是"LLM 直接判分"

早期版本由 LLM 直接判定采分点命中与否并生成证据，实测发现一类错误：作答中**没有写**的点被 LLM 判为命中，且填充的证据是**材料原文的句子**（作答里不存在、材料里逐字存在）——即"材料顶包"。根因是 LLM 同时承担证据生成与裁判两个角色，上下文里存在材料时，找不到作答证据就会借用。

修复方式是结构性拆分角色，而非增加提示词约束：

| 角色 | 职责 | 可伪造面 |
|------|------|----------|
| 规则层（0 token） | 生成全部证据：命中词 / 缺失词 / 材料锚句 | 无（字符串比对，可回溯） |
| LLM（灰带） | 仅输出 `label + reason` 的「疑似」标注 | 无（无证据字段） |
| LLM（建议卡） | 生成候选措辞，明示「供参考」 | 无（建议非事实） |

原则：**凡作为事实展示的内容（命中与否、漏了哪些词、对应材料哪句），全部由确定性规则生成；LLM 只保留不产出事实的职责。** 评分、回流、排序、毕业判定因此可复现、可测试。

## 双模式评分路由

| 模式 | 触发条件 | 行为 |
|------|----------|------|
| 门禁模式 | 提交带 `question_id`，且与库内真题的采分点逐点校验一致 | 规则判绿/黄；灰带交 LLM 标疑似；漏答（黄档）自动进错题本 |
| 示证模式 | 无 trusted 信号的即时录入题 | 0 判定 token 差异配对，只显示该点与作答哪些句有共现词 / 哪些点未见对应，由考生自行判断 |

前端声明 `question_id` 必须通过库题校验（在库 + 采分点一致），否则拒绝——防止以"自称真题"的方式进入门禁档。

## 数据与记忆

- 每次作答写入 `answers` 与 `answer_rounds`（逐轮轨迹）。
- 漏答（规则可证的黄档）更新薄弱点档案；AI 的「疑似」标注不直接入库为漏答。
- 薄弱点生命周期：连续命中 3 次 + 间隔验证 → 毕业（移出提醒池，档案保留）；长期补不上 → 隔离并提示检查题目质量。
- 提醒排序使用紧急度公式（弱点权重 × 遗忘程度），不是静态清单。

## 评测

`eval/` 下按套件评测（`python scripts/run_evals.py`），结果归档 `eval/results/<run_id>/`，支持 BEFORE→AFTER 对比。

| 套件 | 测什么 | 最近登记（2026-08-31） |
|------|--------|------------------------|
| score | 评分区分力：好答 vs 跑题答 | no_fool 1.0 / discrimination 0.899（36 题 · 213 点）⚠️ |
| decompose | 拆解质量：金标对照 + 脏标答鲁棒性 | recall 0.884 / fabrication 0.048 / structural 1.0 / dirty 1.0 |
| demo | 引导质检：材料锚定 / 红线 | material_anchored 1.0 / no_full_answer 1.0 / no_fabrication 1.0 |
| medium | 语义冒烟：fuzzy 漏判 / nosource 假阳 | fuzzy_miss 0.75 / nosource_fp 1.0 ⚠️ |
| memory | 记忆闭环生命周期：毕业 / 隔离 / 复活 / 遗忘排序 / 疑似溯源 / 内联零通道 | 达标 22/22（10 场景 · 0 token）· 红线 0（2026-09-08） |

口径说明：

- ⚠️ `score` / `medium` 两条基线基于已退役的旧引擎（LLM 判官时代，即暴露"材料顶包"的版本）。双模式落地后，评分口径按 `docs/38` 的 D50 重建中：规则层（绿∪黄）对金标 hit/miss 的一致性 + 灰带疑似标注质量 + no_fool/nosource 回归。
- `decompose`（拆解）与 `demo`（引导措辞）口径未变，仍有效。
- 指标设计：一票否决类（no_fool / no_fabrication / dirty）需等于 1.0 才发版；能力类（recall / discrimination）在阈值之上追求更高。这些指标用于验证"漏点识别是否可靠"，不是对提分效果的承诺。

## 测试

`tests/` 下 397 个 pytest 用例，覆盖评分门禁、示证配对、拆解、回流、档案、API 等模块。

```bash
python -m pytest -q
ruff check src tests
```

## 安装

前置条件：Python 3.13+，一个 DeepSeek API Key（用于拆解 / 灰带标注 / 建议候选 / 决策）。评分门禁的绿/黄档与示证配对是本地确定性代码，不调用 LLM。

```bash
# 1. 后端
cd offerloop
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -e .                 # 运行时依赖
pip install -e ".[dev]"          # 开发模式（pytest / ruff）

# 2. 环境变量：仓库不提交 .env，需手动创建（offerloop/ 下）
# .env 内容：
#   DEEPSEEK_API_KEY=sk-xxx
#   （可选 SCORE_FORCE=gate|align，仅测试/演示用，默认按 trusted 自动分发）

# 3. 前端（可选，只用 CLI 可跳过）
cd frontend
npm install
npm run build                    # 静态导出到 frontend/out，由后端托管
```

## 使用

```bash
# CLI
python scripts/run_shenlun.py --demo        # 完整闭环演示：拆解 → 评分 → 回流 → 建议
python scripts/run_shenlun.py --advice      # 今日建议（该练什么）
python scripts/run_shenlun.py --list        # 列出题库
python scripts/run_decompose_question.py    # 拆解 + 逐点人工审核（确认/改分/删/新增）

# Web（工作台）
uvicorn app.main:app --host 0.0.0.0 --port 8000
# 浏览器打开 http://localhost:8000/workbench
```

Web 模式默认只起后端（前端 `frontend/out` 由 `app/main.py` 托管）。开发时热更新前端：另开终端 `cd frontend && npm run dev`（端口 3000，自动代理 `/api` 到 8000）。

## 系统架构

```mermaid
flowchart TB
    subgraph 入口层
        CLI["CLI 脚本<br/>scripts/run_shenlun.py"]
        WEB["FastAPI<br/>app/main.py :8000"]
        FE["前端 Next.js 工作台<br/>frontend/out（静态导出）"]
    end

    subgraph API 层["API 层（app/api/shenlun.py）"]
        PRAC["practice/start·submit·complete"]
        REMIND["remind 今日提醒"]
        WEAK["weakpoints 档案"]
        DIAG["diagnose 角度诊断"]
        REC["record 录入拆解 + 入库"]
    end

    subgraph 双模式评分["双模式评分（trusted 路由）"]
        GATE["门禁 gate<br/>规则绿/黄 + 灰带 judge_suspect"]
        ALIGN["示证 align<br/>0 token 差异配对"]
    end

    subgraph 确定性核心["确定性核心（src/shenlun，0 token）"]
        SCORE["score.py<br/>kw 硬匹配/材料锚/gate_score"]
        ALIGN2["align.py 配对器"]
        REFLOW["reflow.py 回流"]
        PROF["profile.py 档案/毕业判定/diagnose"]
    end

    subgraph 语义层["语义层（LLM · DeepSeek，不产出证据）"]
        DECOMP["cleaner.decompose<br/>标准答案 → 采分点（人审闸门）"]
        SUSPECT["judge_suspect<br/>灰带疑似标注 label+reason"]
        GUIDE["runtime.guidance<br/>建议卡候选措辞"]
        REACT["react.decide<br/>按档案推题"]
    end

    subgraph 存储层["存储层"]
        DB[("SQLite · shenlun.db")]
    end

    CLI & WEB --> PRAC & REMIND & WEAK & DIAG & REC
    WEB --> FE
    PRAC --> GATE & ALIGN
    GATE --> SCORE & SUSPECT & GUIDE
    ALIGN --> ALIGN2
    SCORE --> REFLOW --> PROF --> REMIND & WEAK & DIAG
    DECOMP --> REC
    DB --> SCORE & ALIGN2 & REFLOW & PROF
```

## 目录结构

```
offerloop/
├── app/
│   ├── main.py              # FastAPI 入口（托管 /api/* + 前端静态页）
│   └── api/
│       ├── shenlun.py       # 申论 API（练习/提醒/档案/录入/双模式路由）
│       └── …                # 面试域 API（遗留）
├── src/
│   ├── shenlun/             # 申论核心（确定性层 + 双模式）
│   │   ├── score.py         # kw 硬匹配/材料锚/gate_score/assemble_gate
│   │   ├── judge_llm.py     # 灰带疑似标注（无证据字段）
│   │   ├── align.py         # 示证档配对器（0 判定 token）
│   │   ├── reflow.py        # 回流（answers/weak_points/events）
│   │   ├── wrongbook.py     # 错题本（只收规则可证漏答）
│   │   ├── profile.py       # 档案聚合 + 毕业判定 + diagnose
│   │   ├── question_store.py# 题库加载 + 用户题入库
│   │   └── react.py         # 决策（按档案推题）
│   ├── cleaner/             # 拆解（decompose/precheck/annotate）
│   └── mock/                # 练习会话运行态（runtime/guidance/report）
├── eval/                    # 评测套件 + results 归档
├── benchmark/data/          # 金标题库（36 题：河南官方 2024/2025 + 江苏）
├── frontend/                # Next.js 工作台
├── scripts/                 # CLI 入口
└── docs/                    # 开发记录（01-39 计划书 + 实施计划）
```

遗留说明：`src/memory`、`src/market`、部分 mock 面试模块来自早期的面试备考域（项目前身），保留未删，不参与申论主链路。

## 技术栈

- 后端：Python 3.13 · FastAPI · SQLite
- LLM：DeepSeek API（拆解 / 灰带标注 / 建议候选 / 决策，温度 0）
- 前端：Next.js（静态导出）· Tailwind 4 · React 19
- 数据：全部本地 SQLite（`data/shenlun.db`），不出本机

## 开发计划

- Now：docs/38 双模式收尾——D50 评测基线重建（门禁绿∪黄一致性 + 灰带疑似质量回归）、工作台三项闭环优化（录入预览可编辑、档案页直达错题、练习页示例题文字版）
- Next：能力诊断下钻、备考提醒增强
- Later：进步可视化、套卷模式、语义检索（同类题推荐）

## 不做的事（Non-goals）

- 不爬取题库内容
- 不生成范文 / 代写作答
- 不做社区 / 排行榜
- 不承诺保过或提分

## 常见问题

**门禁档的绿 / 黄判定可靠吗？**
绿（全部关键词命中）与黄（一个关键词未写）由确定性规则判定，可复现；只有灰带（部分命中）会标「疑似」且不硬判。系统不对"写得好不好"做精确判断。

**为什么不用 LLM 直接判命中 / 漏答？**
见上文"材料顶包"事故：LLM 在材料存在时会借用材料原文把未写的点判为命中。LLM 适合软标注（疑似），不适合产出要作为事实展示的证据。

**LLM 拆的采分点可信吗？**
默认不可信。拆解结果 `approved=False`，人工审核（确认 / 改分 / 删 / 新增）通过后才入库评分。

**练习会忘怎么办？**
薄弱点按紧急度公式排序进入每日提醒；连续命中 + 间隔验证后毕业；补不上会隔离。提醒只覆盖规则可证的漏答，AI 的疑似不直接入档。

**需要 GPU 或本地模型吗？**
不需要。确定性判定在本地执行，其余走 DeepSeek API。Ollama 嵌入模型仅面试域遗留模块使用。

## License

MIT
