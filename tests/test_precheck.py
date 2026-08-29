"""docs/19 §4.2 脏标答预检（src/cleaner/precheck.py）测试。

precheck 是 decompose 的确定性兜底：LLM 对「残缺/过简红线」的服从不稳定（实测同一抄错样本
四连跑 预警✓→✓→无→无），规则预检绕开该不稳定（docs/实现说明/02 建议③）。

契约（2026-08-29 实测标定）：
  - eval/dirty_gold.json 6 个脏标答 → 全部命中（6/6）
  - benchmark/data 36 个 good 标答 → 全部干净（0 误报）
  - 规则：×乱码符号 / 口语化标记 / 过简（<120 字）
"""

import json
from pathlib import Path

from src.cleaner.precheck import detect_dirty

ROOT = Path(__file__).resolve().parent.parent


# ── 规则单元 ─────────────────────────────────────────────────────
class TestDetectRules:
    def test_garbled_x_symbol(self):
        """× 符号（复制粘贴乱码）→ 命中抄错信号。"""
        r = detect_dirty("一要服务理念转向增值化；二是服雾方式从被动受礼转向主动批配，智×能×分×析。")
        assert r["dirty"] is True
        assert any("乱码" in s for s in r["signals"])

    def test_colloquial_marker(self):
        """强口语词「我觉得/挺有意思/嘛」→ 命中口语化信号。"""
        r = detect_dirty("我觉得这个题挺有意思的，就是讲大山村化解纠纷嘛。")
        assert r["dirty"] is True
        assert any("口语化" in s for s in r["signals"])

    def test_too_short_answer(self):
        """过简（<120 字，残缺只留一个点）→ 命中过简信号。"""
        r = detect_dirty("一是设施互通，开通城际公交、实现高速免费互通，并规划新建提升改造道路。")
        assert r["dirty"] is True
        assert any("过简" in s for s in r["signals"])

    def test_clean_long_formal_answer(self):
        """正常长度的正式书面标答 → 干净。"""
        text = ("一、善于听取群众建议与批评。细心观察百姓生活，真诚耐心听取骂声，善于反思，"
                "从群众意见中发现问题、解决困难，把骂声当作改进工作的动力。二、不断提高思想觉悟"
                "与执法能力。以人为本，不怕难烦累，对工作有责任心、热心、细心；注重公平公正，"
                "重视调研，换位思考、多沟通讲道理，培养感情，创新方式方法，提升专业性。"
                "三、不断革新，用发展满足百姓需求。顺应时代潮流创新理念，深入基层了解需求，"
                "重视专业人才、善于动员群众力量。")
        r = detect_dirty(text)
        assert r["dirty"] is False
        assert r["signals"] == []

    def test_empty_text_dirty(self):
        """空文本 → 过简命中（安全方向：宁误报不放过）。"""
        r = detect_dirty("")
        assert r["dirty"] is True
        assert any("过简" in s for s in r["signals"])

    def test_returns_length(self):
        assert detect_dirty("abc")["length"] == 3


# ── 契约：脏样本全命中 + 正常标答零误报 ────────────────────────────
class TestPrecheckContract:
    def test_dirty_gold_all_hit(self):
        """eval/dirty_gold.json 的 6 个脏标答（残缺/口语化/抄错）全部命中。"""
        data = json.loads((ROOT / "eval" / "dirty_gold.json").read_text(encoding="utf-8"))
        items = data["items"]
        assert len(items) == 6
        for it in items:
            r = detect_dirty(it["text"])
            assert r["dirty"] is True, f"{it['id']}（{it['dirty_type']}）未被预检命中"

    def test_good_texts_all_clean(self):
        """benchmark/data 36 个 good 标答全部干净（precheck 不得误伤正常流程）。"""
        n = 0
        for f in sorted((ROOT / "benchmark" / "data").glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            good = d.get("samples", {}).get("good", {}).get("text", "")
            if not good:
                continue
            n += 1
            r = detect_dirty(good)
            assert r["dirty"] is False, f"{d['id']} 的 good 标答被误判为脏: {r['signals']}"
        assert n == 36
