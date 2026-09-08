# CHANGES.md — 共享记录（Claude Code ⇄ WorkBuddy）

> **读法**：顶部「当前快照」（精简，只记 README 没有的动态状态）；下方「变更流水」**前 3 条** = 近况。详细架构 / 命令 / 设计约定 / 坑 → 读 `README.md`，本文件不重复。
> **写法**：**每关闭一次对话 / 结束一轮工作，就按下方模板往流水区顶部写，一轮可写多条**。Claude Code 写开发结果，WorkBuddy 写规划 / 验收结论；WorkBuddy 验收后补「验收批注」。
> **事实源**：任何内容与 git / 代码冲突时，以代码为准，然后回来修正——发现过期就更新，不将就。

---

## 当前快照（覆盖式维护：只留 README 没有的；新增必删旧，别 append 历史）

- **项目**：PointLoop（逐点）= 申论逐点评分与错题回流 Agent（代码包名 offerloop，产品名≠包名，演进自早期面试备考模块）。评分定位「漏点识别传感器」，确定性规则产出全部事实证据、LLM 只保留无事实职责（灰带疑似标注 / 建议候选 / 拆解人审）。架构 / 命令 / 设计约定 / 坑 → `README.md`，不在此重复。
- **当前主线**（谁依赖谁，本文件独有的动态信息）：
  - `docs/42 评分单模式化 + 采分点来源分层`：**已落地**（2026-09-07）——评分恒 gate 三色（trusted 路由退役），可信度下沉为数据属性 `points_source`（L1 库题金标 / L2 手填 / L3 LLM 拆解「参考·未复核」）；内联漏点（L2/L3，P-A=②）只进错题本不进提醒池；reflow 入库判据按 B1 对齐 gate verdicts（verdicts 参数化，旧调用方不变）；guidance 对 L1/L2/L3 全放开（L3 带 caveat）。**取代 docs/38 的 D40（trusted 双模式路由）与 D48（示证档）；D41 防伪保留为 L1 定义，D42-D47（三态/灰带/建议区）全部保留**；`align_answer`/`SCORE_FORCE=align` 保留 deprecated 作回滚保底
  - `docs/38 双模式评分引擎`：主体代码已并入基线（`4ecba21`），产品口径被 docs/42 取代（见上行）；**收尾项仍开放**：D50 评测基线重建（门禁绿∪黄对金标一致性 + 灰带疑似标注质量）——不受 42 影响，另行重建
  - `docs/39 第 5 页签 + 录错题闭环`：wrongbook 内联通道（`inline_{hash}` ctx）已随基线入库，并作为 docs/42 L3「确认无误」闸门的复用点通过回归
  - `docs/40 seed 模拟练习历史`：**已落地**（2026-09-06）——`scripts/seed_weak_history.py` + `src/shenlun/seed/` 五小模块，真实库已 seed 两批 12 道真题（默认 seed=773），弱档案 49 漏点跨 13 题；42 落地 demo 走沙箱副本，seed 数据零污染（回滚点 `data/shenlun.db.bak42`）
  - **git 基线已收尾**（2026-09-07）：上一波 docs/32-40 在途改动已 commit 为 `4ecba21`（docs/38/39/40 落地 + 文档归档）；根目录 `_*.py`/`_pp_head.tsx`/`ocr_tmp.ps1` 调试草稿仍未跟踪未删除，待用户处置
- **评测口径**：`tests/` 403 用例（pytest）+ `eval/` 五套件（score/decompose/demo/medium/memory，`python scripts/run_evals.py`）。一票否决类指标 = 1.0 才发版；指标只验证「漏点识别可靠」，不是提分承诺。详见 README「评测」。

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

## [2026-09-08] memory 评测套件落地：记忆闭环生命周期回归入 eval 体系 — Claude Code
- 对应计划:计划外（用户提出「受控记忆闭环缺业务量化收口」并选定方案 B：照四套件模式补 memory 套件；本轮为简历材料语境下的数字补测，口径冻结于 `eval/memory_eval.py` docstring）
- 改动:新增 `eval/memory_eval.py`（10 场景 × 22 检查项，逐场景临时库隔离，确定性 0 token、真实参数不 patch：S1-S4 毕业闭环=候选判定/毕业考命中毕业/考砸连击归零/连击与间隔双拦截、S5-S6 隔离防死锁 30 轮真实参数与复活、S7 遗忘衰减排序、S8 提醒池过滤与档案保留、S9 疑似按 miss 入库必留 suspect 溯源行（docs/42 B1 口径）、S10 内联题 complete 404 零写入红线；红线 2 条=内联泄漏/疑似缺溯源）+ `scripts/run_evals.py`（SUITES 接入第 5 套件、extract_summary 扁平化 memory 块、HEADLINE 加「记忆闭环行为达标率」↑）+ `README.md` 评测表补 memory 行
- 验证:`python eval/memory_eval.py` → **22/22 达标率 100%，红线内联泄漏 0、疑似缺溯源 0，llm_calls=0**（结果归档 eval/results/baseline/memory_eval_results.json）；`ruff check eval/memory_eval.py scripts/run_evals.py` 零报错；`python scripts/run_evals.py --baseline` → 5/5 json 登记，后续真实 run 以此为对比基准
- 遗留:① 全套件 `python scripts/run_evals.py` 未跑（decompose/demo 需 DeepSeek key，本轮避免 LLM 成本），下次正常回归五套件同跑以验证 comparison 兼容；② 简历草稿「AI 疑似标注与未经人审采分点一律不固化为漏答」与 docs/42 B1 拍板（suspect 按 miss 入库 + events 溯源、内联零通道）存在口径差——前半句建议改「疑似不硬判命中、入库必留溯源、命中即复活」，后半句（内联/未人审零回流通道）成立，待用户定稿简历措辞；③ README「397 个 pytest 用例」实为 403，存量偏差未顺手改（非本轮范围）
- commit:待回填
- 验收批注:(待 WorkBuddy 填)

## [2026-09-07] docs/42 落地：评分单模式化 + 采分点来源分层 — Claude Code
- 对应计划:docs/42 §4 全部（M1-M5 + 交互/建议，P-A~P-D = ②/B1/①/①）+ §8 执行清单
- 改动:后端 `app/api/shenlun.py`（_resolve 去trusted路由改 L1/L2/L3 分层、_mode 恒 gate、InlineGold 加 `points_source`、submit 响应带 `tier`、guidance 对 L1/L2/L3 全放开且 L3 带 caveat、parse/decompose_and_cache 响应带 `points_source=llm_parse`、无 points 内联 400 明确提示、complete 透传 verdicts）+ `src/shenlun/score.py`（新增纯函数 `result_from_verdicts`：verdicts→ScoreResult）+ `src/shenlun/reflow.py`（`reflow_answer` 加 verdicts 参数：hit=绿含LLM放行/miss=黄/suspect记miss+events追`suspect`标注行；不传回退旧口径）+ `src/shenlun/align.py`（标 deprecated，本期不删）。前端 `frontend/lib/types.ts`（InlineGold.points_source/GateResult.tier/GuidanceResult.caveat/ParseResult.points_source）+ `PracticePanel.tsx`（删模式角标与示证对照视图、题面配置改分层说明、L3 行「参考·未复核」标记、内联漏点「确认无误·入错题本」（P-C=① 单点粒度，走 docs/39 wrongbook 通道）、resolveGold 按 JSON/文字带 points_source）。测试 `tests/test_shenlun_api.py`（align 双模式用例改写为单模式分层用例；新增内联 L2/L3、无 points 400、guidance L2/L3、M5 三题判据一致性、suspect 事件标注等用例）
- 验证:`python -m pytest -q tests/` → **403 passed**（基线 398 + 净增 5）；ruff 对改动文件零新增（存量 62 与基线持平，顺手修 shenlun.py 1 个 F401）；`tsc --noEmit` 通过；三路手工 demo（真实 uvicorn + DB/Chroma 沙箱副本，真实库 md5 零污染）：库内题 gate+L1 三色含真 LLM 灰带疑似、内联手填 L2+guidance 放开、LLM 拆 L3+caveat+确认入错题本 `sl_inline_{hash}`；M5 demo：complete 带 verdicts 后 9/9 增量与 submit 判定一致 + events suspect 标注 1 行；P-A=② demo：内联题 weak_points 行数 0
- 遗留:① workbench 前端目前不调 practice/complete（本轮前即如此）——M5 的前端 verdicts 透传仅后端契约就绪，待前端接入 complete 流时回传；② ruff 存量 62 报错与本轮无关（基线即有，疑 ruff 版本规则漂移），建议单独清理一轮；③ 根目录 `_*.py`/`ocr_tmp.ps1` 等草稿未删未入库，待用户处置；④ 回滚路径：路由改回 `_mode(trusted)` 一行（align_answer/SCORE_FORCE 未删），DB 回滚点 `data/shenlun.db.bak42`；⑤ 简历条目 2/3「示证档/双模式」表述可启用路线 A 目标稿（WorkBuddy 事项，未动简历文件）
- commit:`2fddf5c`（2026-09-08 用户确认后提交；开工基线 `4ecba21`）
- 验收批注:**✅ 通过（WorkBuddy 2026-09-08 定向核对）**——① git/流水吻合：基线 4ecba21 存在，42 改动 9 文件 M 未提交属实；② 代码抽查逐条属实：score.py:316 `result_from_verdicts` 纯函数、reflow.py:289 verdicts 参数 + events `suspect` 标注行（:350-357）、shenlun.py `_resolve` 三层 tier（:149-197）+ 无 points 400 提示（:189）+ submit 响应 `tier`（:264）+ L3 caveat（:354）+ `points_source`（:116）、align.py deprecated 标注（docstring :3）；③ 干净重跑 `python -m pytest -q tests/ --basetemp=.pytest_tmp` → **403 passed**（首次 326+77 errors 系 .pytest_tmp 残留污染，mv 清后复跑即绿，非代码问题）；④ docs/42 状态行「已落地」+ §4.3 口径差修正留档属实。遗留项 ①~⑤ 与本批注一致，照单跟进即可

## [2026-09-07] 开工基线收尾：在途改动 commit 为干净基线（docs/43 §0 用户确认）— Claude Code
- 对应计划:计划外（docs/43 §0 开工准备：git 在途清单 + app/api/shenlun.py diff 经用户确认归属后收尾）
- 改动:将上一波 docs/38 双模式 + docs/39 错题本 + 录题入库/seed 的全部在途产物（26 个 M 文件 + align/question_store/seed/测试/WrongbookPanel/docs/32-43/CHANGES 等）commit 为基线 `4ecba21`；`.gitignore` 补 `.pytest_tmp/`；根目录 `_*.py` 等调试草稿与 `data/shenlun.db.bak` 按用户选择**未入库**
- 验证:基线 commit 前 `python -m pytest -q tests/` → 398 passed（与 docs/43 口径一致；沙箱环境需 `--basetemp` 指到工作区内，系统 Temp 权限受限所致，本机正常 shell 不受影响）
- 遗留:根目录草稿文件（_al/_scan*/_sg*/_sapi*/_s38*/_cfg.py、_pp_head.tsx、ocr_tmp.ps1）仍未删除，待用户处置
- commit:4ecba21
- 验收批注:

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
