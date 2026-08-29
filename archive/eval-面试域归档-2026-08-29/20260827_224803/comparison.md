# Eval 回归对比 — 20260827_224803

> 对比基准：baseline  →  本轮：20260827_224803
> 生成时间：20260827_224803

| 指标 | 上次 | 本次 | 变化 | 判定 |
|---|---|---|---|---|
| 检索 Recall@5 | 0.704 | 0.512 | -0.19 | ⚠️ 回退 |
| 阅卷 discrimination | 1.000 | 1.000 | +0.00 | — 持平 |
| 阅卷 strict_order | 0.636 | 0.636 | +0.00 | — 持平 |
| 阅卷 no_fool | 1.000 | 1.000 | +0.00 | — 持平 |
| 阅卷 question_pass | 0.909 | 0.909 | +0.00 | — 持平 |
| 拆解 category 准确率 | 0.963 | 0.963 | +0.00 | — 持平 |

## 套件状态
- retrieval: ok
- mock_interview: ok（modes: rubric, legacy, plain_inject, rubric_no_ref）
- llm_judge: ok
