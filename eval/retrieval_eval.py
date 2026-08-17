"""检索质量 eval —— Recall@k 曲线 + PR 曲线 + 阈值校准（检索层唯一有 ground truth 的部分）。

20 条标注查询（eval/annotations.py），每条的 relevant/irrelevant 用题目原文唯一子串标识。
指标：
  - Recall@k：检索 top-k 里命中 relevant 的比例（k=1..10），反映「纯相似度排序」质量。
  - Precision@k：top-k 里 relevant 占比。
  - 噪音：明确不该召回的 irrelevant 题是否被召回（定性检查）。
  - PR 曲线：扫描相似度阈值，看阈值过滤对 precision/recall 的权衡。

实现要点：每条查询只检索一次 top_k=10（拿到问题+相似度），Recall@k 和阈值 PR 都在内存里
模拟——既避免重复 embed，也规避 chromadb 累积 query 崩溃（约 40-50 次触发 access violation）。

用法：python eval/retrieval_eval.py   （或 python -m eval.retrieval_eval）
输出：eval/retrieval_eval_results.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

from src.memory import knowledge_store as store
from eval.annotations import ANNOTATED_QUERIES

K_MAX = 10
THRESHOLDS = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]


def _hits(frags: list[str], questions: list[str]) -> int:
    return sum(1 for q in questions if any(f in q for f in frags))


def _retrieve_once(query: str, top_k: int = K_MAX) -> list[dict]:
    """每条查询只检索一次，返回 [{q, sim}]（按相似度降序）。"""
    results = store.search(query, top_k=top_k, similarity_threshold=None)
    return [{"q": it.question, "sim": getattr(it, "_similarity", 0.0)} for it in results]


def _collect_all() -> list[dict]:
    """一次性检索全部标注查询（20 次 search，避免累积崩溃）。"""
    out = []
    for aq in ANNOTATED_QUERIES:
        out.append({"aq": aq, "hits": _retrieve_once(aq["query"])})
    return out


def recall_at_k(collected: list[dict], k: int) -> dict:
    recall_sum = prec_sum = 0.0
    noise_total = 0
    per_query = []

    for c in collected:
        aq = c["aq"]
        qs = [h["q"] for h in c["hits"][:k]]
        r_hit = _hits(aq["relevant"], qs)
        i_hit = _hits(aq["irrelevant"], qs)
        recall_sum += r_hit / len(aq["relevant"]) if aq["relevant"] else 0.0
        prec_sum += r_hit / k
        noise_total += i_hit
        per_query.append({"query": aq["query"][:24], "recall": round(r_hit / len(aq["relevant"]), 3), "noise": i_hit})

    n = len(collected)
    return {
        "k": k,
        "recall_at_k": round(recall_sum / n, 3),
        "precision_at_k": round(prec_sum / n, 3),
        "total_noise": noise_total,
        "per_query": per_query,
    }


def pr_at_threshold(collected: list[dict], threshold: float) -> dict:
    """内存模拟阈值过滤：保留 sim>=threshold 的结果，算平均 precision/recall。"""
    tp = fp = fn = 0
    for c in collected:
        aq = c["aq"]
        kept = [h["q"] for h in c["hits"] if h["sim"] >= threshold]
        r_hit = _hits(aq["relevant"], kept)
        tp += r_hit
        fn += len(aq["relevant"]) - r_hit
        fp += len(kept) - r_hit

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    return {"threshold": threshold, "precision": round(precision, 3), "recall": round(recall, 3)}


def main():
    stats = store.get_stats()
    if stats["total"] == 0:
        print("错题本为空，先跑 run_interview.py / annotate_jingyan.py。")
        return

    print(f"数据量: {stats['total']} 题 · 标注查询: {len(ANNOTATED_QUERIES)} 条")
    print("=" * 60)

    collected = _collect_all()

    # ── Recall@k 曲线 ──
    print(f"\n{'k':<4} {'Recall@k':<10} {'Precision@k':<12} {'噪音题数'}")
    print("-" * 40)
    recall_curve = [recall_at_k(collected, k) for k in range(1, K_MAX + 1)]
    for r in recall_curve:
        print(f"{r['k']:<4} {r['recall_at_k']:<10.3f} {r['precision_at_k']:<12.3f} {r['total_noise']}")

    # ── 阈值扫描 + PR ──
    print(f"\n{'阈值':<8} {'Precision':<10} {'Recall':<8}")
    print("-" * 30)
    pr_curve = [pr_at_threshold(collected, t) for t in THRESHOLDS]
    for r in pr_curve:
        print(f"{r['threshold']:<8.2f} {r['precision']:<10.3f} {r['recall']:<8.3f}")

    # ── 落盘 ──
    out = {
        "data_count": stats["total"],
        "annotated_queries": len(ANNOTATED_QUERIES),
        "recall_at_k": [{k: v for k, v in r.items() if k != "per_query"} for r in recall_curve],
        "pr_curve": pr_curve,
    }
    with open("eval/retrieval_eval_results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: eval/retrieval_eval_results.json")


if __name__ == "__main__":
    main()
