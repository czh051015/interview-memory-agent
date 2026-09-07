# 41 · 开发计划书：bad-case 归因闭环 —— 评测回归从「报分数」升级为「留证据 · 分病因 · 可沉淀」

日期：2026-09-07 · 状态：**计划（待用户确认后落地）** · 性质：评测工具链升级，**业务代码零改动**（不碰评分内核/回流/前端）
前置：docs/38 双模式评分引擎（已落地）· D50 基线重建（进行中）· 决策来源：Agent 四机制迁移咨询（2026-09-06，归因闭环 = P1）

## 1. 背景与用户诉求

用户咨询「上下文压缩 / 长短期记忆 / 自进化 / bad-case 归因」哪些适合 PointLoop（2026-09-06）→ 结论：**bad-case 归因闭环最值得做（P1）**，理由是它直接顶护城河「评分可信」——现有评测能回答「这次掉了多少分」，回答不了「为什么掉、该修哪个组件」，坏例修完不沉淀，同类坏例下次再来一遍。用户确认落成本计划书。

## 2. 现状核查（代码事实，已钉死 2026-09-07）

| # | 事实 | 位置 |
|---|---|---|
| 1 | 判定来源只有**门禁模式**（trusted 题：规则绿/黄 + 灰带 LLM 疑似）；示证模式只摆差异不下判断 → **归因对象 = 门禁判定 vs 金标（参考答案）的偏差** | docs/38 §0/§3（D42/D43/D44） |
| 2 | 绿档判据 = 该点**全部 kw** 出现在作答（all-kw）；黄档 = **0 个 kw**；灰带 = 部分 kw → LLM 只输出 `suspect: null\|{label, reason}`，永不硬判 | docs/38 D42/D43/D45 |
| 3 | 现有评测 `eval/score_eval.py`：每题算 `good_ratio/bad_ratio/discrimination`，聚合 `no_fool`；已能输出两道**题级**粗信号——`bad_fooled`（跑题答被判全命中 → 打印"需修关键词"）与 good leak（好答命中<0.8 → 打印"采分点可能标漏"），但**只到题级、一次性打印、无逐点明细、无沉淀** | score_eval.py（fooled/leak 两处 warn） |
| 4 | D50 基线重建的口径 = 门禁 绿∪黄 对金标 hit/miss 一致性 + 灰带疑似标注质量 + no_fool/nosource 回归 → **与归因是同一比对对象**，只是输出形态停在聚合分数 | docs/38 状态行 / CHANGES.md |
| 5 | 评测结果目录 `eval/results/` 已有 `baseline/` 与时间戳子目录，但无 case 级沉淀位；benchmark 数据 36 道真题（河南/江苏，多 `meta.type`） | eval/results/、benchmark/data/ |
| 6 | 无任何"坏例 → 病因 → 修法"的结构化记录；修 bad case 靠人肉看 diff 猜原因 | 全库检索确认 |

## 3. 方案一句话

**把 D50 的一致性检查从「报一个分数」升级为四层流水线：逐点明细（M1）→ 规则归因（M2）→ 人拍板回归（M3）→ case 库沉淀复用（M4）**。归因用 0-token 规则启发式给「病因候选」，LLM 不参与判定与归因（判定可信由 docs/38 的结构性安全继承）。遵循 40 计划书同款纪律：**无上帝文件、职责单一、纯函数可单测**。

## 4. 方案设计

### 4.0 模块拆分与依赖（新增文件清单）

```
offerloop/
├── scripts/run_regression.py        # ① CLI 入口：跑回归 → 明细 → 归因 → 报告 → 提示开 case（薄）
└── src/shenlun/evalkit/             # 新包：评测归因核心（业务代码零改动，主流程不 import 它）
    ├── __init__.py                  # 空
    ├── detail.py                    # ② 明细生成：gate 判定 × gold → 逐点一致表（纯函数）
    ├── diagnose.py                  # ③ 规则归因：明细行 → 病因候选 + 修法文案（纯函数）
    ├── case_store.py                # ④ case 库：读/写/去重/按特征联想（唯一 IO 面）
    └── report.py                    # ⑤ 报告：按 bad_type 分组 top N + 修法清单（纯展示）
```

| 模块 | 输入 | 输出 | 职责边界（不做的事） |
|---|---|---|---|
| ① `run_regression.py` | 命令行参数（跑哪批、阈值） | 控制台报告 | 只编排；**不含归因/落盘逻辑** |
| ② `detail.py` | benchmark 题 JSON + 该题好/坏作答的 gate 判定结果 | `[{qid, point_id, kw, gate, gold, consistency, bad_type, evidence}]` | 只比对生成明细；**不判病因、不落盘** |
| ③ `diagnose.py` | 一条明细行（bad_type≠—） | `{cause: [候选…], fix_hint}` | 只按规则表给病因候选与修法建议；**不改任何数据** |
| ④ `case_store.py` | case 记录 | cases.jsonl 落盘 / 去重结果 / 联想命中 | 唯一读写 case 库；**无归因逻辑** |
| ⑤ `report.py` | 明细 + 归因结果 | 分组报告文本 | 只排版打印 |

依赖方向（单向，无环）：`① → ④ → ③ → ② →（score 判定结果/benchmark 金标）`，report 被 ① 直调。②③⑤ 纯函数无 IO 可单测；④ 唯一 IO 面。单文件 ≤80 行。

> M1 与 docs/38 D50 重建的关系（关键衔接）：D50 本就要做逐点一致性比对。**落地时不改 score_eval 旧逻辑**，由新包 `detail.py` 消费同一次判定结果产出明细；旧聚合报告保留兼容（一次性脚本，无长期负担）。

### 4.1 M1 · 明细化：坏例的原材料（先于一切归因逻辑）

一次回归后产出 `eval/results/<run_id>/detail.jsonl`，每行一个「题 × 采分点」判定：

```json
{"run_id":"20260907_0030","qid":"henan_2024_city_1","meta_type":"归纳概括",
 "point_id":"p3","kw":["多元共治"],"kw_count":1,
 "gate":"黄","suspect":null,
 "gold":"hit","consistency":false,"bad_type":"假阴",
 "evidence":{"answer_kw_hit":0,"answer_has_partial":true,"kw_in_bad_text":false}}
```

- `gate` 三态取门禁判定：`绿`（规则 all-kw 命中）/ `黄`（0 kw）/ `灰带`（部分 kw，附 `suspect`：null=放行绿 · 或 {label,reason}）。
- `bad_type` 判定规则（确定性，见下表）——只有 `consistency=false` 的行进入 M2。

### 4.2 bad case 定义（先定「什么算错」，三种 + 边界）

| bad_type | 判定（确定性规则） | 对应 docs/38 | 处理顺序 |
|---|---|---|---|
| 假阴（漏判） | `gold=hit` 且 `gate=黄` | D43 黄档过严 | 第一批（纯规则可比） |
| 假阳（误判） | `gold=miss` 且 `gate=绿` | D42 绿档过宽 | 第一批 |
| 灰带错标 | `gold=hit` 且 `suspect≠null`；或 `gold=miss` 且 `suspect=null`（放行绿） | D44/D45 灰带质量 | 第二批（涉 LLM，归因模糊） |
| 边界：no_source | `gate=黄` 但该点材料锚缺失 | D50 no_source 回归 | 归为数据缺失，不进病因链 |

> 范围限定（与 docs/38 决策一致）：**只归因 trusted 题**（有金标可比的题）。内联/示证题无判定语义，天然排除。

### 4.3 M2 · 规则归因：病因候选（0-token，LLM 不参与）

对每条 `bad_type≠—` 的行，按特征表给 `cause` 候选（按概率排序）+ `fix_hint` 文案。**只给候选与线索，不自动修任何东西**——修是人的动作（M3）。

| bad_type | 自动特征检查（evidence 扩展） | 病因候选（排序） | 修哪个组件 |
|---|---|---|---|
| 假阴 | 作答里该点 kw 全缺，但作答含该 kw 的词根/子串（如写"治理"、kw"多元共治"） | ① kw 过严、缺同义/近义覆盖 ② kw 含过长材料原句串 | 参考答案 keywords（数据层） |
| 假阴 | 作答里连词根都无（good 样本也没覆盖） | 金标标注可疑 → 升格「金标待复核」 | 参考答案标注（数据层） |
| 假阳 | kw ≤2 字 或 kw 在 bad 文本中高频 或 同一 kw 跨多题/多点复用 | 泛词、无领域区分度 | keywords 替换为有区分度短语 +（可选）排除词机制（规则层） |
| 假阳 | kw 是材料高频词 且 bad 作答照抄材料句 | 抄材料即中（需核对锚句而非作答自写） | 命中判据核查（规则层，一般已由 all-kw 缓解） |

`fix_hint` 文案示例：`假阳 · p3 kw「建议」过泛 → 改为「提出可行性建议」+ 该坏例入 benchmark 防回归`。

> 诚实标注：假阴「同义改写」判断用词根/子串启发式（0-token），**可能误报 → 输出标注「待人工确认」**，由 M3 人拍板兜底。不追求自动诊断 100% 准，追求把 20 个人肉 case 缩到 5 个高置信候选。

### 4.4 M3 · 人拍板 + 回归 gate（质量信号闸门）

闭环流程固定成链，坏例修完不丢：

```
回归(带 detail.jsonl) → 自动归因报告（按 bad_type 分组 top N）
  → 人看 top cases（每题附 evidence 证据）→ 确认/纠正病因
  → 人修（改 kw / 改标注 / 改规则 / 加 benchmark 样例）
  → 重跑回归：该 case 必须转绿（consistency=true）→ 不转绿 = 病因猜错，打回重判
  → 写入 case 库（M4）
```

- 「人拍板」是本方案的**质量信号**（对应自进化咨询结论：进化入口必须带人，否则 20 道 benchmark 上全自动改 = 过拟合）。
- 回归 gate：修完必须全量回归无退化 + 该坏例转绿，两条同时满足才算 closed。

### 4.5 M4 · case 库沉淀（= bad-case 记忆）

落盘位置：`benchmark/badcases/cases.jsonl`（跟 benchmark 走、进 git、不污染业务库 `shenlun.db`）。唯一键 `qid+point_id` upsert 幂等，重复写不膨胀。

```json
{"id":"BC-0007","qid":"henan_2024_city_1","meta_type":"归纳概括","point_id":"p3",
 "kw":["建议"],"gold":"miss","gate":"绿","bad_type":"假阳","cause":"泛词",
 "fix":"kw 改为「提出可行性建议」","fix_component":"keywords",
 "status":"closed","date":"2026-09-07","run_id":"20260907_0030","regression":"pass"}
```

联想（M4 后置）：新坏例先按 `(qid, point_id)` 精确查、再按 `(bad_type, kw 特征)` 模糊查——命中即带出「上次怎么修的」给人当参考。

## 5. 待拍板点（用户确认后才进 §8）

| # | 拍板项 | 建议默认 |
|---|---|---|
| P-A | 归因范围：只做确定性两类（假阴/假阳，0-token 可辩护）还是含灰带错标 | **先假阴/假阳**；灰带并入第二批 |
| P-B | 明细落盘：随每次回归自动产出 `eval/results/<run_id>/detail.jsonl` | 自动产出（不另设开关） |
| P-C | case 库位置：`benchmark/badcases/cases.jsonl` | 跟 benchmark 走 |
| P-D | 与 docs/38 D50 的耦合：detail.py 独立实现、不改 score_eval 旧聚合逻辑 | 独立实现（旧脚本保留，兼容一次性） |

## 6. 验收标准

1. 一次回归产出 `detail.jsonl`：行数 = Σ(题 × 该题采分点数)，每行 gate/gold/consistency/bad_type 四字段齐全可查。
2. `diagnose` 单测（构造样例）：已知假阴点 → 候选含「kw 过严/数据漏」；已知假阳点 → 候选含「泛词」；已知无问题点不误报（确定性断言）。
3. D50 基线跑完后人工抽查 top 5 bad cases，病因与直觉一致 ≥4/5（启发式标注「待人工确认」的除外）。
4. `case_store` upsert 幂等：同 `qid+point_id` 重复写不产生重复行。
5. `python -m pytest -q` 全量无回归；`git diff --stat` 只含新包文件 + 新 CLI，业务零改动。

## 7. 关键风险与对策

| 风险 | 对策 |
|---|---|
| M1 改动影响 D50 重建进度 | detail.py 独立实现，不动 score_eval 旧逻辑；D50 的比对仍按原口径跑 |
| 「同义改写」启发式误报假阴 | 归因只给候选并标注「待人工确认」，M3 人拍板兜底；不自动改数据 |
| 修坏例过拟合 benchmark（改了 A 坏 B） | 回归 gate 全量 + 该 case 转绿双条件；修法必须落 `fix_component` 可追踪 |
| case 库膨胀/过期 | 唯一键 upsert；closed 后保留（历史即证据），按 run_id 可溯源 |
| 归因范围失控（灰带 LLM 类混入第一批） | P-A 拍板钉死：第一批只做 0-token 可辩护的两类 |

## 8. 执行清单（等用户说「做」再动）

1. 确认 §5 拍板点（P-A~P-D）
2. 写 `src/shenlun/evalkit/`（detail / diagnose / case_store / report 四模块，每文件 ≤80 行）+ `scripts/run_regression.py` 薄入口
3. 单测：diagnose 构造样例断言 + case_store 幂等
4. 跑一次真实回归：产出 detail.jsonl → 归因报告 → 人工抽查 top cases
5. 汇报：首轮坏例分布（假阴/假阳各多少、top 病因）、抽查一致性、附 case 库首条样例
