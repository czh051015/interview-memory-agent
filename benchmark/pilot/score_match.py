#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
slb_w_huatu_001 最小评分验证脚本（Phase 0 / 模式 A：纯关键词匹配）

目的：验证"把阅卷规则拆成 reference_points(point+keywords+score) + format_checklist"
      之后，确定性踩点匹配能否复现人工阅卷的档位与分数。

这是你之前定的 benchmark「客观踩点比对」引擎的最小雏形，只实现 A 模式
（纯关键词子串命中）。B(关键词+LLM模糊)/C(embedding语义)/D(混合+Rerank)
用于后续消融，专门补 A 对"同义/拆分表述"的漏判。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ITEM = os.path.join(HERE, "slb_w_huatu_001.json")
SAMPLES = os.path.join(HERE, "slb_w_huatu_001_samples.json")


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def match_content(answer, points):
    """模式 A：任一 keyword 作为子串出现在作答中即命中。"""
    hits, misses = [], []
    for p in points:
        if any(kw in answer for kw in p["keywords"]):
            hits.append(p)
        else:
            misses.append(p)
    return hits, misses


def match_format(answer, checklist):
    """格式要素启发式检查（仅用于展示分档，非硬踩点）。"""
    results = {}
    results["标题正确"] = ("汇报提纲" in answer) or answer.strip().startswith("关于")
    results["含背景定位"] = ("智能经济" in answer) and ("转型升级" in answer)
    results["含三层面结构"] = all(x in answer for x in ["一、", "二、", "三、"])
    results["含总结"] = ("呈现良好发展态势" in answer) or ("使我市" in answer) or ("总结" in answer)
    return results


def predict_grade(content_ratio, format_complete):
    if format_complete == 4 and content_ratio >= 0.85:
        return "一类"
    if format_complete >= 2 and content_ratio >= 0.45:
        return "二类"
    return "三类"


def main():
    item = load(ITEM)
    data = load(SAMPLES)
    points = item["reference_points"]
    total_content = sum(p["score"] for p in points)
    fmt_total = sum(c["weight"] for c in item["format_checklist"])

    print("=" * 64)
    print(f"ITEM {item['id']}  | 题型={item['type']} | 满分=20")
    print(f"内容采分点 {len(points)} 个，合计 {total_content} 分；格式要素 {fmt_total} 分")
    print("=" * 64)

    for s in data["samples"]:
        ans = s["answer_text"]
        hits, misses = match_content(ans, points)
        content_score = sum(p["score"] for p in hits)
        fmt = match_format(ans, item["format_checklist"])
        fmt_complete = sum(1 for v in fmt.values() if v)
        ratio = content_score / total_content
        grade = predict_grade(ratio, fmt_complete)

        print(f"\n样卷 {s['sample_id']}  | 人工={s['human_score']}分/{s['grade']}")
        print(f"  内容命中 {len(hits)}/{len(points)} 点，得分 {content_score}/{total_content} "
              f"(recall={ratio:.2f})")
        print(f"  格式完整 {fmt_complete}/{fmt_total}：{fmt}")
        print(f"  → 预测档位：{grade}  | 复现人工档位：{'✓' if grade == s['grade'] else '✗'}")

        miss_ids = [m["id"] for m in misses]
        print(f"  漏答采分点：{miss_ids}")
        # 暴露 A 模式漏判：拆分/同义表述
        if "c4" in miss_ids:
            print("    ⚠ A模式漏判示例：作答'机器人产业学院…工业小镇'未含连续'机器人小镇'→ c4 漏")
        if "c9" in miss_ids:
            print("    ⚠ A模式漏判示例：作答'政府发挥有为之手…互动'未含'辅助生态'→ c9 漏")


if __name__ == "__main__":
    main()
