# CHANGES.md — 共享记录（Claude Code ⇄ WorkBuddy）

> **读法**：顶部「当前快照」（精简，只记 README 没有的动态状态）；下方「变更流水」**前 3 条** = 近况。详细架构 / 命令 / 设计约定 / 坑 → 读 `README.md`，本文件不重复。
> **写法**：**每关闭一次对话 / 结束一轮工作，就按下方模板往流水区顶部写，一轮可写多条**。Claude Code 写开发结果，WorkBuddy 写规划 / 验收结论；WorkBuddy 验收后补「验收批注」。
> **事实源**：任何内容与 git / 代码冲突时，以代码为准，然后回来修正——发现过期就更新，不将就。

---

## 当前快照（覆盖式维护：只留 README 没有的；新增必删旧，别 append 历史）

- **项目**：PointLoop（逐点）= 申论逐点评分与错题回流 Agent（代码包名 offerloop，产品名≠包名，演进自早期面试备考模块）。评分定位「漏点识别传感器」，确定性规则产出全部事实证据、LLM 只保留无事实职责（灰带疑似标注 / 建议候选 / 拆解人审）。架构 / 命令 / 设计约定 / 坑 → `README.md`，不在此重复。
- **当前主线**（谁依赖谁，本文件独有的动态信息）：
  - `docs/38 双模式评分引擎（门禁+示证）`：主体已落地（HEAD=`19250ad` 2026-09-01「评分引擎切 LLM 默认 + 前后端对齐 + eval 体系收尾」）。**收尾项进行中**：D50 评测基线重建（门禁绿∪黄对金标 hit/miss 一致性 + 灰带疑似标注质量 + no_fool/nosource 回归）——README 里 score/medium 旧基线（LLM 判官时代口径）已退役待替换，口径按 docs/38 重建
  - `docs/39 第 5 页签 + 录错题闭环`：状态行「待复核 → 复核后交 Claude Code 落地」（2026-09-02 定稿）——申论错题本入口归位、录入默认 = 录错题流。复核后即下一轮执行候选
  - `docs/40 seed 模拟练习历史`：**已落地**（2026-09-06）——`scripts/seed_weak_history.py` + `src/shenlun/seed/` 五小模块（业务代码零改动），真实库已 seed 两批 12 道真题（默认 seed=773，`--seed` 换批），弱档案 49 漏点跨 13 题、红/黄/绿分层可演示；同 seed 重跑幂等跳过
  - `docs/42 评分单模式化 + 采分点来源分层`：**已拍板待落地**（2026-09-07）——用户确认绕回单模式（内联题也要有三态判定），P-A~P-D 已定案（② 内联只进错题本不进提醒池 / B1 reflow 收 gate verdicts 对齐判据 / ① L3 漏点行内确认按钮 / ① guidance 全放开）。执行入口 = `docs/43-开工交接-42单模式化落地准备.md`（含 git 基线确认 / 必读 / 硬约束 / 口径差提示），等用户说「做」并指定执行 Agent
  - ⚠️ **git 工作区存在大量未提交改动**（docs/32-40 计划书 + CHANGES 未跟踪；README / src / app / frontend / eval 多处 M；本轮新增 seed 工具未提交）——上一会话产物尚未收尾提交，任何 Agent 开工前先 `git status` 确认归属，勿覆盖在途工作；**`app/api/shenlun.py` 当前即 M 状态，42 落地前必须先与用户确认其 diff 归属**
- **评测口径**：`tests/` 397 用例（pytest）+ `eval/` 四套件（score/decompose/demo/medium，`python scripts/run_evals.py`）。一票否决类指标 = 1.0 才发版；指标只验证「漏点识别可靠」，不是提分承诺。详见 README「评测」。

---

## 变更流水

> 模板（复制到本区**顶部**；一轮可写多条，最新在上）：

```markdown
## [YYYY-MM-DD] <一句话标题> — <Claude Code|WorkBuddy>
- 对应计划:<计划书名 §小节>(如 docs/38 §3.2)/ 计划外(说明理由)
- 改动:<文件> + 逻辑,若干行
- 验证:<跑了什么命令> → <结果>
- 遗留:<未完成 / 风险 / 待决策>
- commit:<短 hash>
- 验收批注:(WorkBuddy 填:通过 / 返工原因)
```

## [2026-09-07] docs/42 拍板定案 + 开工交接建档（docs/43）— WorkBuddy
- 对应计划:docs/42（开发计划书-评分单模式化与采分点来源分层）
- 改动:P-A~P-D 按建议拍板（P-A=② 内联只进错题本不进提醒池 / P-B=B1 reflow 收 gate verdicts / P-C=① 漏点行内确认按钮 / P-D=① guidance 全放开）写入 §5 拍板记录表，状态行改「已拍板·待落地」；新增 `docs/43-开工交接-42单模式化落地准备.md`（执行 Agent 开工清单：git 基线确认 / 必读文件 / 环境命令 / 硬约束 / 计划书内部口径差提示 / 验收 / 不做清单）；CHANGES 快照补 docs/42 主线行
- 验证:未跑测试（纯文档 + 计划书状态更新，无代码改动）
- 遗留:代码落地等用户说「做」并指定执行 Agent；⚠️ 发现 docs/42 内部口径差——§4.3 图写「L2 内联直入 weak_points」与拍板 P-A=②「内联一律只进错题本」冲突，已写入 docs/43 §4 要求执行 Agent 落代码前向用户确认；git 在途改动（含 app/api/shenlun.py M）归属仍待用户收尾
- commit:无
- 验收批注:(待 Claude Code 落地后 WorkBuddy 填)

## [2026-09-06] docs/40 落地：seed 模拟练习历史，填充薄弱档案演示动态分层 — Claude Code
- 对应计划:docs/40（开发计划书-seed模拟练习历史填充弱档案）
- 改动:新增 `scripts/seed_weak_history.py`（薄 CLI：抽题/编排/汇报）+ `src/shenlun/seed/` 包（sampler 题型轮转抽题 / scenario 场景构造 / builder 关键词组织句 / loader 时间回拨+语义禁用+幂等清单，唯一写库 IO 面）；业务代码零改动。真实库 data/shenlun.db 已 seed 两批共 12 道真题（seed=773 默认批 6 题 + seed=26 演示换批 6 题），弱档案 miss>=1 达 49 点/13 题，红 40/黄 9/绿 34 分层可演示
- 验证:dry-run 计划 22 漏点；同 seed 重跑=跳过（幂等）；换 seed=新一批仍收敛；profile 分层预览红/黄同现 + urgency 梯度；remind 等价输出 top3 来自 3 道不同题、毕业考候选 0；`python -m pytest -q` → 398 passed；ruff check 通过
- 遗留:本轮按「不主动 commit」约束未提交（hash 待定）；DB 侧产物 data/shenlun.db* / data/seed/weak_history_seed.json 均 gitignore；回滚=还原 shenlun.db.bak 并删 seed 清单后重跑；数据为模拟练习非真实作答，仅演示用
- commit:待定
- 验收批注:
## [2026-09-04] 建档：引入 AGENTS.md / CLAUDE.md / CHANGES.md 协作体系 — WorkBuddy
- 对应计划:计划外(对齐 kbops 双 Agent 协作模式,由用户发起;本项目此前无 CHANGES 流水,开发记录散在 docs/NN-* 计划书内)
- 改动:新增 `AGENTS.md`(执行侧手册)、`CLAUDE.md`(协作模式 / 文件地图 / 铁律)、`docs/CHANGES.md`(本文件,快照 + 流水);纯文档,无代码改动
- 验证:未跑测试(无代码变更);当前状态核对自 README + `git log`(HEAD=19250ad)+ `git status`(58 项未提交)
- 遗留:docs/38 D50 基线重建 + docs/39 复核落地 = 下轮候选;58 项在途改动归属待收尾
- commit:待定(小改动攒着,等下一个功能点或用户指示)
- 验收批注:
