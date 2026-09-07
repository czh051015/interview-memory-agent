"""seed 演示数据确定性核心（docs/40）。

一次性数据工具包：用真实回流链路（reflow_answer）把 benchmark 真题灌成
「过去几周的模拟练习历史」，填充薄弱档案、演示记忆机制动态分层。
业务代码零改动：主流程不 import 本包；脚本入口 = scripts/seed_weak_history.py。
"""
