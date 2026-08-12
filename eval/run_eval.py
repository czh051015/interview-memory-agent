"""Eval 入口 —— 跑全量质量门基线。"""

import json
import logging
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("eval")

EVAL_DIR = Path(__file__).parent


def eval_dedup() -> dict:
    """去重准确率评估。"""
    # v1 简化：用内置用例
    test_pairs = [
        # (text_a, text_b, expected_duplicate)
        ("腾讯AI岗问了RAG项目的向量检索选型", "腾讯面试AI岗，问RAG向量检索选型", True),
        ("百度面试问了如何做混合检索", "腾讯面试问如何做混合检索", False),
        ("字节面试问到了RRF重排序", "字节面试问到了RRF重排序的原理和实现", True),
        ("今天面了腾讯AI岗，主要问了Agent框架", "面了腾讯AI岗，主要问了Agent框架设计思路", True),
        ("面试问了Prompt Engineering最佳实践", "面试问了如何处理大模型幻觉问题", False),
    ]

    correct = 0
    results = []
    from src.cleaner.dedup import llm_dedup_check

    for i, (text_a, text_b, expected) in enumerate(test_pairs):
        try:
            is_dup, reason = llm_dedup_check(text_a, text_b)
            ok = is_dup == expected
            if ok:
                correct += 1
            results.append({
                "pair": i + 1,
                "text_a": text_a[:40],
                "text_b": text_b[:40],
                "expected": expected,
                "actual": is_dup,
                "reason": reason,
                "pass": ok,
            })
        except Exception as e:
            results.append({
                "pair": i + 1,
                "error": str(e),
                "pass": False,
            })

    accuracy = correct / len(test_pairs) if test_pairs else 0
    return {
        "metric": "dedup_accuracy",
        "baseline": ">= 0.95",
        "value": round(accuracy, 4),
        "details": results,
        "pass": accuracy >= 0.95,
    }


def eval_pii() -> dict:
    """PII 检出率评估。"""
    from src.cleaner.pii import regex_scan

    test_cases = [
        # (text, expected_pii_count)
        ("请联系13812345678获取更多信息", 1),  # phone
        ("我的邮箱是test@example.com", 1),      # email
        ("13800001111和13900002222都试试", 2),  # 2 phones
    ]

    correct = 0
    total_expected = sum(t[1] for t in test_cases)
    total_found = 0

    for text, expected_count in test_cases:
        found = regex_scan(text)
        total_found += len(found)
        if len(found) == expected_count:
            correct += 1

    recall = total_found / total_expected if total_expected > 0 else 0

    return {
        "metric": "pii_regex_recall",
        "baseline": "1.0",
        "value": recall,
        "pass": recall >= 1.0,
    }


def eval_retrieval() -> dict:
    """检索 Recall@5 评估（v1 占位）。"""
    return {
        "metric": "retrieval_recall@5",
        "baseline": ">= 0.8",
        "value": None,
        "note": "需要先入库标注查询，见 eval/ 目录下的标注数据集",
        "pass": None,
    }


def eval_clustering() -> dict:
    """聚类纯度评估（v1 占位）。"""
    return {
        "metric": "cluster_purity",
        "baseline": ">= 0.7",
        "value": None,
        "note": "需要 50 条人工标注主题数据",
        "pass": None,
    }


def eval_consistency() -> dict:
    """评估一致性评估。"""
    from src.evaluator.pipeline import check_consistency

    hypothesis = "Agent框架成为近期高频考察方向"
    evidence = [
        "腾讯面试问到了LangGraph的Agent编排原理",
        "百度面试问到了多Agent协作模式",
        "字节面试问到了Function Call实现",
        "面试要求设计一个多智能体系统",
    ]

    result = check_consistency(hypothesis, evidence, n_runs=3)

    return {
        "metric": "evaluator_consistency",
        "baseline": "max_diff <= 1",
        "value": {
            "max_diff_coverage": result["max_diff_coverage"],
            "max_diff_falsifiability": result["max_diff_falsifiability"],
        },
        "pass": result["pass"],
    }


def run_all_evals() -> dict:
    """运行所有评估，输出汇总。"""
    logger.info("Running all evaluations...")
    start = time.time()

    results = {}

    # 去重评估
    try:
        results["dedup"] = eval_dedup()
        logger.info("Dedup: accuracy=%.4f, pass=%s", results["dedup"]["value"], results["dedup"]["pass"])
    except Exception as e:
        results["dedup"] = {"error": str(e), "pass": False}
        logger.error("Dedup eval failed: %s", e)

    # PII 评估
    try:
        results["pii"] = eval_pii()
        logger.info("PII: recall=%.4f, pass=%s", results["pii"]["value"], results["pii"]["pass"])
    except Exception as e:
        results["pii"] = {"error": str(e), "pass": False}
        logger.error("PII eval failed: %s", e)

    # 检索评估（占位）
    results["retrieval"] = eval_retrieval()

    # 聚类评估（占位）
    results["clustering"] = eval_clustering()

    # 一致性评估
    try:
        results["consistency"] = eval_consistency()
        logger.info("Consistency: max_diff=%s, pass=%s",
                    results["consistency"]["value"], results["consistency"]["pass"])
    except Exception as e:
        results["consistency"] = {"error": str(e), "pass": False}
        logger.error("Consistency eval failed: %s", e)

    # 汇总
    passed = sum(1 for v in results.values() if v.get("pass") is True)
    total = sum(1 for v in results.values() if v.get("pass") is not None)
    failed = sum(1 for v in results.values() if v.get("pass") is False)

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "duration_s": round(time.time() - start, 1),
        "metrics": results,
        "summary": {
            "passed": passed,
            "failed": failed,
            "skipped": total - passed - failed,
            "total_defined": total,
        },
    }

    # 输出
    logger.info("Eval summary: %d passed, %d failed, %d skipped", passed, failed, total - passed - failed)

    # 写入文件
    output_path = EVAL_DIR / "results.json"
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    logger.info("Results written to %s", output_path)

    return summary


if __name__ == "__main__":
    run_all_evals()
