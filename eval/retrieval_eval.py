"""检索余弦阈值校准（ISSUES E4）。
对 10 条标注查询，测试 4 个候选阈值，选 Recall@5 稳定 + 噪音归零的取值。
"""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from src.memory import knowledge_store as store

# ── 标注查询：query → 期望召回的 question 列表 ──
ANNOTATED_QUERIES = [
    {
        "query": "Agent框架 多智能体 工具调用",
        "relevant": [
            "如果让你设计一个Agent要考虑哪些模块？",
            "Agent的短期长期记忆是怎么实现的？",
            "有没有考虑用大模型自己排除api超时和报错？",
        ],
        "irrelevant_must_not_include": [
            "什么是两阶段提交？",
            "有实习过吗？",
            "多线程写一个死锁",
            "mysql的undolog，redolog，binlog区别和场景？",
        ],
    },
    {
        "query": "RAG 检索增强 知识库",
        "relevant": [
            "出现幻觉怎么处理？",  # 提到了RAG
        ],
        "irrelevant_must_not_include": [
            "多线程写一个死锁",
            "为什么要volatile关键字？",
        ],
    },
    {
        "query": "线程池 并发 多线程",
        "relevant": [
            "讲一下java线程池？",
            "如果你重新设计一个线程池会怎么设计？",
            "多线程写一个死锁",
        ],
        "irrelevant_must_not_include": [
            "什么是两阶段提交？",
            "合并两个有序数组",
        ],
    },
    {
        "query": "数据库 MySQL 事务",
        "relevant": [
            "mysql的undolog，redolog，binlog区别和场景？",
            "什么是两阶段提交？",
        ],
        "irrelevant_must_not_include": [
            "出现幻觉怎么处理？",
            "合并两个有序数组",
        ],
    },
    {
        "query": "提示词 Prompt工程",
        "relevant": [
            "提示词具体是怎么做？",
            "还有其他提示词吗？",
            "出现幻觉怎么处理？",
        ],
        "irrelevant_must_not_include": [
            "合并两个有序数组",
            "随便写一个单例模式",
        ],
    },
]

THRESHOLDS = [0.30, 0.40, 0.45, 0.50, 0.55, 0.60]


def evaluate_threshold(threshold: float) -> dict:
    """对给定阈值跑全部标注查询，计算 Recall@5 和噪音率。"""
    total_relevant = 0
    total_retrieved = 0
    total_noise = 0
    per_query = []

    for aq in ANNOTATED_QUERIES:
        results = store.search(
            query=aq["query"],
            top_k=5,
            similarity_threshold=threshold,
        )
        retrieved_questions = [item.question for item in results]

        # 召回的相关题数
        relevant_hits = sum(1 for q in aq["relevant"] if q in retrieved_questions)
        # 召回的噪音题数（明确不应出现的）
        noise_hits = sum(1 for q in aq["irrelevant_must_not_include"] if q in retrieved_questions)

        total_relevant += len(aq["relevant"])
        total_retrieved += relevant_hits
        total_noise += noise_hits

        per_query.append({
            "query": aq["query"][:30],
            "retrieved": retrieved_questions[:5],
            "relevant_hits": relevant_hits,
            "noise_hits": noise_hits,
        })

    recall = total_retrieved / total_relevant if total_relevant > 0 else 0
    noise_rate = total_noise / (len(ANNOTATED_QUERIES) * 5)  # 最多 25 条结果

    return {
        "threshold": threshold,
        "recall@5": round(recall, 3),
        "noise_rate": round(noise_rate, 3),
        "total_noise": total_noise,
        "per_query": per_query,
    }


def main():
    # 确保有数据
    stats = store.get_stats()
    if stats["total"] == 0:
        print("错题本为空，请先运行 run_interview.py")
        return

    print(f"数据量: {stats['total']} 题")
    print(f"标注查询: {len(ANNOTATED_QUERIES)} 条")
    print(f"候选阈值: {THRESHOLDS}")
    print("=" * 60)

    results = []
    for t in THRESHOLDS:
        r = evaluate_threshold(t)
        results.append(r)

    # ── 输出表格 ──
    print(f"\n{'阈值':<8} {'Recall@5':<10} {'噪音数':<8} {'噪音率':<8} {'推荐'}")
    print("-" * 50)

    best = None
    for r in results:
        # 推荐标准：Recall@5 >= 0.6 且噪音 = 0 的最小阈值
        ok = r["recall@5"] >= 0.6 and r["total_noise"] == 0
        mark = "✅" if ok else ""
        if ok and best is None:
            best = r
        print(f"{r['threshold']:<8.2f} {r['recall@5']:<10.3f} {r['total_noise']:<8} {r['noise_rate']:<8.3f} {mark}")

    # ── 推荐阈值 ──
    print()
    if best:
        print(f"推荐阈值: {best['threshold']} (Recall@5={best['recall@5']}, 噪音=0)")
    else:
        # 找噪音为 0 的候选中 Recall 最高的
        zero_noise = [r for r in results if r["total_noise"] == 0]
        if zero_noise:
            best = max(zero_noise, key=lambda r: r["recall@5"])
            print(f"推荐阈值: {best['threshold']} (Recall@5={best['recall@5']}, 噪音=0, 噪音非零但最优)")
        else:
            # 噪音都消不掉，选 Recall 最高的
            best = max(results, key=lambda r: r["recall@5"])
            print(f"警告: 所有阈值均有噪音。建议阈值: {best['threshold']} (Recall@5={best['recall@5']})")
            print("需增加数据量提升嵌入区分度（ISSUES F1）")

    # ── 保存结果 ──
    output = {
        "eval_time": __import__('datetime').datetime.utcnow().isoformat(),
        "data_count": stats["total"],
        "results": [{k: v for k, v in r.items() if k != "per_query"} for r in results],
        "recommended_threshold": best["threshold"] if best else None,
        "per_query_details": [r["per_query"] for r in results],
    }

    import os
    os.makedirs("eval", exist_ok=True)
    with open("eval/retrieval_results.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n详细结果已保存: eval/retrieval_results.json")


if __name__ == "__main__":
    main()
