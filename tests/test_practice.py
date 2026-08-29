"""docs/18 §4.2：practice_one 逼近循环 + 断点续练测试（mock LLM）。

覆盖：
  · 轮1 达标 → 直接回流（1 轮，不调 LLM）
  · 引导后轮2 补上 → 3 轮内达标（只调 1 次 LLM，guided_point_ids 记录）
  · 一直差一个点 → 超轮次上限退出（不达标，不再调 LLM）
  · 防代写：喂给 LLM 的漏点不含关键词（只传 id/名称/分值）
  · 断点：退出后恢复 → 从第 N 轮继续；进度版本不兼容 → 重新开始
  · KeyboardInterrupt：已完成轮次已落盘
"""

import json

import pytest
from unittest.mock import patch

import src.mock as mi
from src.shenlun.score import from_benchmark
from src.mock.runtime import (
    practice_one, PracticeRound, PASS_HIT_RATIO,
    _save_practice, _load_practice, _clear_practice, _format_guidance,
)

# 单题采分点（3 个，便于分别控制 hit/miss）
REFS = [
    {"id": "c1", "point": "六尺巷·化解纠纷", "keywords": ["六尺巷"], "score": 3},
    {"id": "c2", "point": "河长制·治水", "keywords": ["河长"], "score": 3},
    {"id": "c3", "point": "生态理念·象群", "keywords": ["象群"], "score": 4},
]
Q = "概括基层治理经验"
M = "材料：六尺巷化解邻里纠纷，河长制守护碧水，象群回归印证生态理念深入人心。"


class TestPracticeOne:
    def test_pass_on_first_round_no_llm(self):
        """首答全命中 → 1 轮达标，不调 LLM，无引导。"""
        with patch.object(mi, "chat_json") as llm:
            r = practice_one("q1", Q, M, from_benchmark(REFS), lambda q, m, g: "六尺巷 河长 象群")
        assert r.passed is True
        assert len(r.rounds) == 1
        assert r.rounds[0].hit_ratio == 1.0
        assert r.rounds[0].guided_point_ids == []
        assert llm.call_count == 0

    def test_approach_until_pass_within_3_rounds(self):
        """轮1 漏点 → 引导后轮2 补上 → 达标，只调一次 LLM，引导点被记录。"""
        answers = iter(["六尺巷", "河长 象群"])
        with patch.object(mi, "chat_json",
                          return_value={"guidance": [{"point_id": "c2", "hint": "材料第2段想想"}]}) as llm:
            r = practice_one("q1", Q, M, from_benchmark(REFS), lambda q, m, g: next(answers))
        assert r.passed is True
        assert len(r.rounds) == 2
        assert r.rounds[1].hit_ratio == 1.0
        assert r.rounds[1].guided_point_ids == ["c2"]
        assert "河长制·治水" in r.rounds[1].guidance
        assert llm.call_count == 1

    def test_max_rounds_exhausted(self):
        """一直差一个点 → 3 轮上限退出不达标；引导只在未达标轮次调（共 2 次）。"""
        with patch.object(mi, "chat_json",
                          return_value={"guidance": [{"point_id": "c3", "hint": "材料第3段"}]}) as llm:
            r = practice_one("q1", Q, M, from_benchmark(REFS), lambda q, m, g: "六尺巷 河长")
        assert r.passed is False
        assert len(r.rounds) == 3
        assert llm.call_count == 2
        assert r.rounds[-1].hit_ratio < PASS_HIT_RATIO
        assert r.rounds[-1].full_answer == "六尺巷 河长\n六尺巷 河长\n六尺巷 河长"

    def test_llm_guidance_failure_does_not_block(self):
        """引导 LLM 挂了 → 本轮无引导，练习继续（不阻断）。"""
        def ask(q, m, g):
            nonlocal calls
            calls += 1
            return "六尺巷 河长 象群" if calls > 1 else "六尺巷"
        calls = 0
        with patch.object(mi, "chat_json", side_effect=RuntimeError("network")):
            r = practice_one("q1", Q, M, from_benchmark(REFS), ask)
        assert r.passed is True
        assert len(r.rounds) == 2
        assert r.rounds[1].guided_point_ids == []

    def test_guidance_input_excludes_keywords(self):
        """防代写：喂给 LLM 的漏点只含 id/名称/分值，不含关键词字段。"""
        with patch.object(mi, "chat_json", return_value={"guidance": []}) as llm:
            practice_one("q1", Q, M, from_benchmark(REFS), lambda q, m, g: "六尺巷")
        user_prompt = llm.call_args.args[1]
        assert "keywords" not in user_prompt          # 不传关键词表
        assert "河长制·治水" in user_prompt            # 漏点点名可传（提示方向用）
        assert "[c2]" in user_prompt                  # 带 id，供 guided_point_ids 回填

    def test_guidance_invalid_point_dropped(self):
        """LLM 输出不存在的点 id → 丢弃；按点名匹配的合法输出保留。"""
        with patch.object(mi, "chat_json", return_value={"guidance": [
            {"point_id": "c9", "hint": "不存在的点"},
            {"point": "河长制·治水", "hint": "材料第2段"},
        ]}) as llm:
            r = practice_one("q1", Q, M, from_benchmark(REFS),
                             lambda q, m, g: ("河长 象群" if g else "六尺巷"))
        assert r.rounds[1].guided_point_ids == ["c2"]  # 只保留合法引导

    def test_pass_ratio_parameterizable(self):
        """达标阈值可调：默认 0.8 不达标，调低后同答案达标。"""
        ask = lambda q, m, g: "六尺巷 河长"  # 命中 2/3 ≈ 0.667
        r1 = practice_one("q1", Q, M, from_benchmark(REFS), ask)
        assert r1.passed is False
        r2 = practice_one("q1", Q, M, from_benchmark(REFS), ask, pass_ratio=0.6)
        assert r2.passed is True
        assert len(r2.rounds) == 1


class TestBreakpoint:
    def test_save_load_roundtrip(self, tmp_path):
        """进度落盘 → 读回：字段齐全、版本为 2。"""
        p = tmp_path / "practice_progress.json"
        r0 = PracticeRound(round_no=0, answer="六尺巷", hit_ids=["c1"], miss_ids=["c2", "c3"],
                           hit_ratio=round(1 / 3, 4), guided_point_ids=[], guidance="",
                           full_answer="六尺巷")
        _save_practice(str(p), question_id="q1", question=Q, material=M, points=REFS,
                       max_rounds=3, pass_ratio=PASS_HIT_RATIO, rounds=[r0])
        data = _load_practice(str(p))
        assert data["v"] == 2
        assert data["question_id"] == "q1"
        assert data["points"][0]["keywords"] == ["六尺巷"]   # 采分点随档存档
        assert data["rounds"][0]["hit_ratio"] == pytest.approx(round(1 / 3, 4))

    def test_resume_continues_from_saved_round(self, tmp_path):
        """轮1 中断 → 恢复后从轮2 继续：resume_rounds 只补新轮次，轮1 数据保留。"""
        p = tmp_path / "practice_progress.json"
        r0 = PracticeRound(round_no=0, answer="六尺巷", hit_ids=["c1"], miss_ids=["c2", "c3"],
                           hit_ratio=round(1 / 3, 4), guided_point_ids=[], guidance="",
                           full_answer="六尺巷")
        _save_practice(str(p), question_id="q1", question=Q, material=M, points=REFS,
                       max_rounds=3, pass_ratio=PASS_HIT_RATIO, rounds=[r0])
        loaded = _load_practice(str(p))
        with patch.object(mi, "chat_json",
                          return_value={"guidance": [{"point_id": "c2", "hint": "材料第2段"}]}):
            r = practice_one("q1", Q, M, from_benchmark(REFS), lambda q, m, g: "河长 象群",
                             resume_rounds=loaded["rounds"], progress_path=str(p))
        assert len(r.rounds) == 2
        assert r.rounds[0].hit_ratio == pytest.approx(round(1 / 3, 4))  # 恢复的轮1 原样保留
        assert r.passed is True
        # 落盘进度已更新到轮2
        again = _load_practice(str(p))
        assert len(again["rounds"]) == 2
        assert again["rounds"][1]["guided_point_ids"] == ["c2"]

    def test_old_version_progress_ignored(self, tmp_path):
        """版本不兼容（v:1 旧文件）→ 读失败返回 None（提示重新开始而非静默崩）。"""
        p = tmp_path / "practice_progress.json"
        p.write_text(json.dumps({"v": 1, "rounds": []}), encoding="utf-8")
        assert _load_practice(str(p)) is None

    def test_corrupt_progress_ignored(self, tmp_path):
        """损坏文件 → 返回 None，不抛。"""
        p = tmp_path / "practice_progress.json"
        p.write_text("{not json", encoding="utf-8")
        assert _load_practice(str(p)) is None

    def test_interrupt_mid_round_saves_completed_rounds(self, tmp_path):
        """轮1 后中断：已完成轮次已落盘（可续练），异常向上传播。"""
        p = tmp_path / "practice_progress.json"
        calls = {"n": 0}

        def ask(q, m, g):
            calls["n"] += 1
            if calls["n"] == 2:
                raise KeyboardInterrupt
            return "六尺巷"

        with pytest.raises(KeyboardInterrupt):
            practice_one("q1", Q, M, from_benchmark(REFS), ask, progress_path=str(p))
        prog = _load_practice(str(p))
        assert len(prog["rounds"]) == 1

    def test_clear_practice(self, tmp_path):
        """回流成功后清断点。"""
        p = tmp_path / "practice_progress.json"
        p.write_text(json.dumps({"v": 2}), encoding="utf-8")
        _clear_practice(str(p))
        assert not p.exists()


class TestApproachPrompt:
    def test_prompt_forbids_writing_answer(self):
        """红线在 prompt 里：不直接给答案/不代写句子/只提示位置。"""
        from src.mock.prompts import _APPROACH_PROMPT
        assert "不直接给答案" in _APPROACH_PROMPT
        assert "不代写" in _APPROACH_PROMPT
        assert "1-2 个漏点" in _APPROACH_PROMPT
        assert "guidance" in _APPROACH_PROMPT

    def test_format_guidance(self):
        guided = [{"point_id": "c2", "point": "河长制·治水", "hint": "材料第2段"}]
        text = _format_guidance(guided)
        assert "河长制·治水" in text and "材料第2段" in text
