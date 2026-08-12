# AI求职教练：技能分析、知识库与模拟面试 架构蓝图

> AgentLoop 蓝图 v0 · 导出于 2026-08-12T07:14:36.103Z
>
> 仅包含架构元数据，不包含可执行的 Agent 业务代码。

## 节点

| ID | 类型 | 名称 | 职责 | 位置 |
| --- | --- | --- | --- | --- |
| `inbox` | trigger | 反馈入箱 | Webhook / CSV | 44, 168 |
| `cleaner` | agent | 语义清洗 Agent | 去重、脱敏、标准化 | 280, 168 |
| `memory` | memory | 反馈记忆库 | Vector + metadata | 516, 60 |
| `scout` | agent | 信号探测 Agent | 聚类与趋势偏移 | 516, 274 |
| `approval` | approval | 产品人审批 | 确认证据与优先级 | 752, 168 |
| `evaluator` | evaluator | 假设评估器 | 证据覆盖 / 可证伪 | 988, 60 |
| `output` | output | 项目候选简报 | Markdown + JSON | 988, 274 |

## 连线

| ID | 起点 | 终点 | 流类型 |
| --- | --- | --- | --- |
| `e1` | `inbox` | `cleaner` | control |
| `e2` | `cleaner` | `memory` | data |
| `e3` | `cleaner` | `scout` | control |
| `e4` | `memory` | `scout` | data |
| `e5` | `scout` | `approval` | control |
| `e6` | `approval` | `evaluator` | control |
| `e7` | `approval` | `output` | control |
| `e8` | `evaluator` | `output` | data |
