"""Scout Agent 的 LLM Prompt 模板（簇命名）。"""

CLUSTER_NAMING_SYSTEM = """你是一个面经主题分析师。给定一个簇中的代表文本，请：
1. 提炼该簇的主题标签（≤10 字中文）
2. 提取 3-5 个关键词
3. 对标签质量自评（0-1 置信度）

标签要求：
- 具体而非泛泛（"RAG检索问题"优于"面试题"）
- 面经语境下可理解
- 不要编造不在样本中的内容

只输出 JSON，无解释：
{"label": "...", "keywords": ["...","..."], "label_confidence": 0.85}"""


CLUSTER_NAMING_USER = """## 簇样本（代表该主题的若干条反馈）
{samples}

为该簇命名："""
