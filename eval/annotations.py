"""检索标注集 —— query → 期望召回的题（relevant）+ 明确不该召回的题（irrelevant）。

- relevant / irrelevant 用「题目原文的唯一子串」标识，匹配逻辑 `frag in question`。
- 片段足够长以保证唯一；同一 fragment 命中多道相关题是允许的（本就都该召回）。
- 这是检索质量的 ground truth，20 条覆盖：Agent/RAG/线程池/DB/提示词/向量库/上下文压缩/
  记忆/幻觉/API超时/长视频/代码搜索/JVM/切分/RRF/审批状态机/采样参数/Transformer/SSE/评测。
- 2026-08-17 经人工校对：删除「api超时归 Agent框架」的误标（其余语义沾边的软相关保留）。
"""
ANNOTATED_QUERIES = [
    {
        "query": "Agent 框架 多智能体 工具调用",
        "relevant": [
            "如果让你设计一个Agent要考虑哪些模块",
            "Agent的短期长期记忆是怎么实现的",
        ],
        "irrelevant": ["什么是两阶段提交", "多线程写一个死锁"],
    },
    {
        "query": "RAG 检索增强 知识库 召回",
        "relevant": [
            "出现幻觉怎么处理",
            "介绍一下完整的 RAG 流程",
            "在 RAG 系统中，如何评估检索质量",
        ],
        "irrelevant": ["多线程写一个死锁", "随便写一个单例模式"],
    },
    {
        "query": "线程池 并发 多线程",
        "relevant": ["讲一下java线程池", "如果你重新设计一个线程池", "多线程写一个死锁"],
        "irrelevant": ["什么是两阶段提交", "出现幻觉怎么处理"],
    },
    {
        "query": "数据库 事务 一致性 消息队列",
        "relevant": ["多级缓存和数据库的数据一致性问题", "RocketMQ 事务消息的原理"],
        "irrelevant": ["出现幻觉怎么处理", "简单讲下 Transformer 底层原理"],
    },
    {
        "query": "提示词 Prompt 工程",
        "relevant": ["提示词具体是怎么做", "还有其他提示词吗", "模型不按格式输出、乱加戏幻觉"],
        "irrelevant": ["多线程写一个死锁", "随便写一个单例模式"],
    },
    {
        "query": "向量数据库 相似度 检索",
        "relevant": ["向量数据库是干嘛用的", "判断向量的相似度", "除了余弦相似度，还了解其他相似度算法"],
        "irrelevant": ["多线程写一个死锁", "随便写一个单例模式"],
    },
    {
        "query": "上下文压缩 长对话 token 超限 总结",
        "relevant": [
            "长时间编程任务很容易超出模型上下文窗口",
            "参考 Claude Code 等产品后，你如何在压缩上下文",
            "Append-only Session Tree、Compaction",
            "快到上限",
        ],
        "irrelevant": ["讲一下java线程池", "手撕：实现一个支持 TTL 的 LRU"],
    },
    {
        "query": "Agent 长短期记忆 实现",
        "relevant": [
            "Agent的短期长期记忆是怎么实现的",
            "请介绍你的长期记忆 + 短期记忆是怎么实现的",
            "短期记忆的具体实现方式是什么",
        ],
        "irrelevant": ["讲一下java线程池", "展开介绍一下长视频理解项目"],
    },
    {
        "query": "幻觉 怎么处理 降低",
        "relevant": ["出现幻觉怎么处理", "如何降低 Agent & 模型幻觉", "如何控制模型的幻觉问题"],
        "irrelevant": ["多线程写一个死锁", "多级缓存和数据库的数据一致性"],
    },
    {
        "query": "API 超时 重试 熔断 降级 幂等",
        "relevant": [
            "如果遇到api超时和报错怎么解决",
            "有没有考虑用大模型自己排除api超时",
            "如何设计重试、熔断、幂等和降级",
        ],
        "irrelevant": ["多线程写一个死锁", "简单讲下 Transformer 底层原理"],
    },
    {
        "query": "长视频理解 视频分析 模型选型 token",
        "relevant": [
            "展开介绍一下长视频理解项目",
            "视频分析使用了什么模型",
            "为什么选择这个模型",
            "一段十几分钟或五十分钟的视频",
            "视频转写后的 Token",
            "如果不考虑 Token 消耗和成本",
        ],
        "irrelevant": ["讲一下java线程池", "多线程写一个死锁"],
    },
    {
        "query": "代码搜索 关键词 vs 语义 Embedding",
        "relevant": ["基于关键词的命令行代码搜索与基于 Embedding/RAG 的代码搜索"],
        "irrelevant": ["展开介绍一下长视频理解项目", "随便写一个单例模式"],
    },
    {
        "query": "Java 类加载 JVM 并发集合",
        "relevant": ["怎么把class文件加载到jvm中", "你使用的 Java 版本是多少", "Java 并发包线程安全集合"],
        "irrelevant": ["出现幻觉怎么处理", "展开介绍一下长视频理解项目"],
    },
    {
        "query": "RAG 文档切分 chunking 父子块 分块策略",
        "relevant": ["Root + Leaf Hierarchy Chunking", "文档切分你是怎么做的", "介绍一下完整的 RAG 流程"],
        "irrelevant": ["多线程写一个死锁", "讲一下java线程池"],
    },
    {
        "query": "混合检索 RRF 重排 rerank 多路召回",
        "relevant": ["RRF 的原理", "在 RAG 系统中，如何评估检索质量", "基于关键词的命令行代码搜索"],
        "irrelevant": ["展开介绍一下长视频理解项目", "随便写一个单例模式"],
    },
    {
        "query": "Human-in-the-loop 审批 状态机 Checkpoint 中断恢复",
        "relevant": ["Human-in-the-loop 审批状态机", "基于 Eino Interrupt/Resume"],
        "irrelevant": ["讲一下java线程池", "出现幻觉怎么处理"],
    },
    {
        "query": "temperature top_p 模型参数 采样",
        "relevant": ["temperature、top_p 吗", "temperature 设置为 0"],
        "irrelevant": ["展开介绍一下长视频理解项目", "多线程写一个死锁"],
    },
    {
        "query": "Transformer 大模型 底层原理 注意力",
        "relevant": ["简单讲下 Transformer 底层原理"],
        "irrelevant": ["讲一下java线程池", "手撕：实现一个支持 TTL 的 LRU"],
    },
    {
        "query": "SSE WebSocket 流式回复 长连接",
        "relevant": ["SSE 和 WebSocket 有什么区别"],
        "irrelevant": ["多线程写一个死锁", "展开介绍一下长视频理解项目"],
    },
    {
        "query": "Agent 评测 如何证明效果更好 对比",
        "relevant": ["如何科学评测 Agent 系统效果", "对比 React、Plan&Execute、Reflection", "在 RAG 系统中，如何评估检索质量"],
        "irrelevant": ["展开介绍一下长视频理解项目", "随便写一个单例模式"],
    },
]
