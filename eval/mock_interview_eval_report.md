# 模拟面试判卷质量 eval 报告（L1+L3 判别 eval）

> 日期：2026-08-19 · 脚本：`eval/mock_interview_eval.py` · 样本：`eval/samples/`
> 一句话：**用判别样本证明阅卷人稳定区分好坏答案，量规版全面达标，产品已切换。**

---

## 1. 为什么要做这个 eval

- 疑点 1/5/6 的答案都挂在这里：187 个单元测试只测确定性机制（LLM 全 mock），语义层证据薄，**最 Agent 的部分（判卷/追问）没有量化**。
- 出题与判卷同源（同一 DeepSeek），评分可信度没有独立锚点——L3 判别 eval 是置信度的唯一证明。

## 2. 方法（判别 eval，不靠主观打分）

对 11 道人工定题（错题 8 + 简历 2 + JD 1，题源不经被测出题器，防自指上层），每题构造 4 类答案：

| 类别 | 要求 | 谁生成/校准 |
|---|---|---|
| good | 覆盖全部要点、有细节有取舍 | LLM 生成 + **用户校准** |
| mediocre | 覆盖一半、含糊 | LLM 生成 |
| bad | 明显不会/跑题 | LLM 生成 |
| confident | 篇幅同 good、语气自信但核心事实错 | LLM 生成 + **用户校准** |

**断言**（三态映射 pass=2/partial=1/fail=0）：
- `discrimination`：judge(good) > judge(bad) —— 核心区分力
- `order_ok` / `strict_order`：弱序 / 严格递减
- `no_fool`：confident 不得判 pass —— 不被自信错答骗
- `question_pass`：good→pass 且 bad→fail —— 题本身可判

**门槛（grill 定稿）**：discrimination ≥ 0.8，no_fool = 1.0。校准 fail-closed：good/confident 未人工确认则拒绝运行。

## 3. 结果（两轮）

**第一轮**（初版样本）：

| 指标 | 量规版 | 旧版 |
|---|---|---|
| discrimination | 100% | 100% |
| no_fool | 100% | 100% |
| strict_order | 64% | 82% |
| question_pass | 64% | 100% |

**发现问题**：量规版把 A1/A2/A3/A8 的 good 判 partial。根因是**样本自相矛盾**——LLM 同批生成的 expected_points 比 good 答案要求更高（A1 要求讲 execute/submit 区别但 good 没讲；A2 要求写死锁代码但 good 只描述）。旧版 100% 恰恰是自指的证据：它自己现编要点、自圆其说。

**修复**：重写这 4 题的 good，逐条覆盖要点（A2 真的写了 Java 死锁代码），用户确认后重跑。

**第二轮**（升级样本）：

| 指标 | 量规版 | 旧版 | 门槛 |
|---|---|---|---|
| discrimination | **100%** | 100% | ≥80% ✅ |
| no_fool | **100%** | 100% | =100% ✅ |
| strict_order | **91%** | 82% | — |
| question_pass | **100%** | 100% | — |

**结论**：量规版全部达标且在 strict_order 上反超旧版。旧版高分 = 自指（自己定要点自己判），量规版对照金标准后反而更严更准。

## 4. 产品切换（Q8 落地）

- `run_mock_interview.py`：`judge_single_round` / `judge_followup` 默认 `use_rubric=True`（量规版：四维约束 + misses 引原文证据 + 无参考答案时自判要点）。
- `use_rubric=False` 仍可显式选旧版（eval --compare 用）。
- **187 个单元测试全绿**，切换是单点默认值翻转，可回滚。
- 前端 `app/api/mock.py` 复用这两个函数，**Web 端同步生效**。

## 5. 已知边界（诚实清单）

- 样本 11 题、每类 1 条答案——是"门槛性"证明（能区分），不是"校准性"证明（判分尺度与真人一致）。
- expected_points 仍为 LLM 生成 + 用户粗校，未逐条人工打磨（L2 完整版：人工补参考答案，推荐但未做）。
- no_fool 用"不判 pass"定义，未要求判到 fail（partial 也算过）——后续可收紧。
- 未做跨模型对照（DeepSeek 自评自）；如预算允许可加第二模型复核。

## 6. 面试讲法（30 秒版）

> "判卷质量我用判别 eval 量化：11 道人工定题、每题 4 类答案（好/中/差/自信错答），断言阅卷人能严格区分好坏（100%）且不被自信错答骗（100%）。量规版对照金标准评分，strict 序 91% 反超旧版——旧版高分恰是自指的证据。达标后我把产品判卷切到了量规版，187 测试全绿。"
