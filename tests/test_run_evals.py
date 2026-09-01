"""run_evals 纯函数单测：extract_summary / build_comparison / first_run_md / .latest 指针。

docs/19 §7：保留纯函数测试框架（extract_summary / build_comparison 不依赖 subprocess），
字段全换成申论域四套件（score / decompose / demo / medium，docs/22 §6 + docs/24 接入后），并新增方向断言。
"""

import json
import sys
from pathlib import Path

from scripts.run_evals import (
    HEADLINE,
    LATEST_POINTER,
    SUITES,
    _read_latest,
    build_comparison,
    extract_summary,
    first_run_md,
)


def _write(tmp: Path, name: str, data: dict) -> Path:
    d = tmp / name
    d.parent.mkdir(parents=True, exist_ok=True)
    d.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return d


def _min_score(no_fool=1.0, disc=0.899, count=36, n_points=209):
    return {
        "data_count": count,
        "n_points": n_points,
        "mean_discrimination": disc,
        "no_fool": no_fool,
        "per_type": {"提出对策": 1.0, "综合分析": 0.951, "归纳概括": 0.929, "应用文": 0.788},
        "good_leak_count": 1,
        "bad_fooled_ids": [],
    }


def _min_decompose(recall=0.85, fab=0.05, n=36, dirty=1.0, calls=52):
    return {
        "summary": {
            "decomposed_count": n,
            "point_recall": recall,
            "fabrication_rate": fab,
            "structural_ok": 1.0,
            "score_deviation": {"mean": 0.12, "max": 0.45},
            "over_split_flags": [],
            "dirty_robustness": dirty,
            "calibrated": False,
            "llm_calls": calls,
        }
    }


def _min_medium(fuzzy=0.40, nosrc=0.20, samples=9):
    """docs/24 接入：中间态两档（fuzzy 漏判率 / nosource 假阳性率，方向 ↓）。"""
    return {
        "summary": {
            "sample_count": samples,
            "fuzzy_n": 6,
            "fuzzy_total_exp": 30,
            "fuzzy_total_fn": 12,
            "fuzzy_miss_rate": fuzzy,
            "nosource_n": 3,
            "nosource_total_sys": 15,
            "nosource_total_fp": 3,
            "nosource_fp_rate": nosrc,
            "llm_calls": 0,
        }
    }


def _min_demo(full=1.0, fab=1.0, anchored=1.0, samples=19, calls=38):
    return {
        "summary": {
            "sample_count": samples,
            "material_anchored": anchored,
            "anchored_coverage": 0.95,
            "no_full_answer": full,
            "no_fabrication": fab,
            "leading_ok": 1.0,
            "hit_snippet_ok": 1.0,
            "demo_generated": 19,
            "empty_demo_count": 0,
            "llm_calls": calls,
        }
    }


def _full_summary():
    return {
        "run_id": "20260829_120000",
        "created_at": "2026-08-29T12:00:00",
        "labels": {"llm_calls": 90},
        "suites": {
            "score": {"ok": True, "data_count": 36, "n_points": 209,
                      "mean_discrimination": 0.899, "no_fool": 1.0,
                      "per_type": {"提出对策": 1.0}, "good_leak_count": 1, "bad_fooled_ids": []},
            "decompose": {"ok": True, "decomposed_count": 36, "point_recall": 0.85,
                          "fabrication_rate": 0.05, "structural_ok": 1.0,
                          "score_deviation_mean": 0.12, "over_split_flags": [],
                          "dirty_robustness": 1.0, "calibrated": False},
            "demo": {"ok": True, "sample_count": 19, "material_anchored": 1.0,
                     "anchored_coverage": 0.95, "no_full_answer": 1.0,
                     "no_fabrication": 1.0, "leading_ok": 1.0, "hit_snippet_ok": 1.0,
                     "demo_generated": 19, "empty_demo_count": 0},
            "medium": {"ok": True, "sample_count": 9, "fuzzy_n": 6,
                       "fuzzy_miss_rate": 0.40, "nosource_n": 3, "nosource_fp_rate": 0.20},
        },
    }


class TestExtractSummary:
    def test_score_top_level_fields(self, tmp_path):
        _write(tmp_path, "score_eval_results.json", _min_score(no_fool=1.0, disc=0.899, count=36))
        s = extract_summary(tmp_path)["suites"]["score"]
        assert s["ok"]
        assert s["no_fool"] == 1.0
        assert s["mean_discrimination"] == 0.899
        assert s["data_count"] == 36
        assert s["per_type"]["提出对策"] == 1.0

    def test_decompose_fields(self, tmp_path):
        _write(tmp_path, "decompose_eval_results.json", _min_decompose(recall=0.82, fab=0.07, n=36))
        s = extract_summary(tmp_path)["suites"]["decompose"]
        assert s["ok"]
        assert s["point_recall"] == 0.82
        assert s["fabrication_rate"] == 0.07
        assert s["decomposed_count"] == 36
        assert s["dirty_robustness"] == 1.0

    def test_demo_fields(self, tmp_path):
        _write(tmp_path, "demo_eval_results.json", _min_demo(full=0.95, anchored=1.0))
        s = extract_summary(tmp_path)["suites"]["demo"]
        assert s["ok"]
        assert s["no_full_answer"] == 0.95
        assert s["material_anchored"] == 1.0
        assert s["no_fabrication"] == 1.0
        assert s["leading_ok"] == 1.0

    def test_medium_fields(self, tmp_path):
        _write(tmp_path, "medium_eval_results.json", _min_medium(fuzzy=0.35, nosrc=0.25))
        s = extract_summary(tmp_path)["suites"]["medium"]
        assert s["ok"]
        assert s["sample_count"] == 9
        assert s["fuzzy_miss_rate"] == 0.35
        assert s["nosource_fp_rate"] == 0.25
        assert s["fuzzy_n"] == 6 and s["nosource_n"] == 3

    def test_llm_calls_aggregated(self, tmp_path):
        _write(tmp_path, "decompose_eval_results.json", _min_decompose(calls=52))
        _write(tmp_path, "demo_eval_results.json", _min_demo(calls=38))
        assert extract_summary(tmp_path)["labels"]["llm_calls"] == 90

    def test_missing_json_marks_fail(self, tmp_path):
        s = extract_summary(tmp_path)
        assert s["suites"]["score"]["ok"] is False
        assert s["suites"]["decompose"]["ok"] is False
        assert s["suites"]["demo"]["ok"] is False
        assert s["suites"]["medium"]["ok"] is False
        assert "error" in s["suites"]["demo"]


class TestWiring:
    """docs/24 接入：SUITES/HEADLINE 条目与 extract_summary 字段必须一致。"""

    def test_medium_suite_wired(self):
        assert ("medium", "eval/medium_eval.py", "medium_eval_results.json") in SUITES

    def test_medium_headline_wired(self):
        by_name = {n: (s, p, d) for n, s, p, d in HEADLINE}
        assert by_name["中间态漏判率（fuzzy）"] == ("medium", "fuzzy_miss_rate", "down")
        assert by_name["中间态假阳性率（nosource）"] == ("medium", "nosource_fp_rate", "down")


class TestBuildComparison:
    def test_up_metric_direction(self):
        prev = _full_summary()
        cur = _full_summary()
        cur["suites"]["score"]["no_fool"] = 1.0
        cur["suites"]["decompose"]["point_recall"] = 0.92  # 0.92-0.85=+0.07
        md = build_comparison(cur, prev)
        assert "+0.07" in md
        assert "✅ 提升" in md
        assert "⚠️ 回退" not in md

    def test_down_metric_direction(self):
        """新增方向断言：臆造点率是 ↓ 类指标，Δ<0 才算提升（docs/19 §7）。"""
        prev = _full_summary()
        cur = _full_summary()
        cur["suites"]["decompose"]["fabrication_rate"] = 0.03  # 0.03-0.05=-0.02
        md = build_comparison(cur, prev)
        assert "-0.02" in md
        assert "✅ 提升" in md
        assert "⚠️ 回退" not in md

    def test_down_metric_regression(self):
        """臆造点率上升（Δ>0）必须标回退。"""
        prev = _full_summary()
        cur = _full_summary()
        cur["suites"]["decompose"]["fabrication_rate"] = 0.09
        md = build_comparison(cur, prev)
        assert "⚠️ 回退" in md

    def test_medium_down_direction(self):
        """docs/24：fuzzy 漏判率/假阳性率是 ↓ 类指标——下降（Δ<0）才标提升。"""
        prev = _full_summary()
        cur = _full_summary()
        cur["suites"]["medium"]["fuzzy_miss_rate"] = 0.30   # 0.30-0.40=-0.10
        cur["suites"]["medium"]["nosource_fp_rate"] = 0.10  # 0.10-0.20=-0.10
        md = build_comparison(cur, prev)
        assert "中间态漏判率（fuzzy）" in md and "-0.10" in md
        assert md.count("✅ 提升") >= 2
        assert "⚠️ 回退" not in md

    def test_medium_down_metric_regression(self):
        """fuzzy 漏判率上升（Δ>0）必须标回退。"""
        prev = _full_summary()
        cur = _full_summary()
        cur["suites"]["medium"]["fuzzy_miss_rate"] = 0.55
        md = build_comparison(cur, prev)
        assert "⚠️ 回退" in md

    def test_missing_yields_na(self):
        prev = _full_summary()
        cur = _full_summary()
        cur["suites"]["demo"] = {"ok": False, "error": "json 缺失或损坏"}
        md = build_comparison(cur, prev)
        assert "N/A" in md
        assert "— 缺失" in md


class TestFirstRun:
    def test_absolutes_listed(self):
        md = first_run_md(_full_summary())
        assert "首次运行，无历史对比" in md
        assert "0.899" in md  # 评分 discrimination 绝对值
        assert "0.85" in md   # 拆解点覆盖率绝对值


class TestLatestPointer:
    def test_absent_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys.modules["scripts.run_evals"], "LATEST_POINTER", tmp_path / ".latest")
        assert _read_latest() is None

    def test_read_written(self, tmp_path, monkeypatch):
        f = tmp_path / ".latest"
        f.write_text("baseline", encoding="utf-8")
        monkeypatch.setattr(sys.modules["scripts.run_evals"], "LATEST_POINTER", f)
        assert _read_latest() == "baseline"
