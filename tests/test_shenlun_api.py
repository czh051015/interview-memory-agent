"""docs/20 Step A + docs/22 §3.5/§3.6 + docs/38 §6：申论工作台 API 测试（TestClient + mock LLM）。

覆盖（docs/38 双模式契约后）：
  1. practice/start    → ReAct 推题返回题目/材料/题型/推荐理由（mock react.chat_json）
  2. practice/submit   → 双模式分发：
                          · 纯 question_id → trusted → gate：mode + verdicts（§6 PointVerdict
                            全量字段：status/matched_by/terms/evidence/anchor/official/suspect/reason；
                            anchor 全量下发，docs/36 老缺口修复）
                          · 灰带点走 judge_suspect（mock：放行绿·语义 / 标疑似两条路都断言）
                          · gold.question_id 与库题一致 → gate；不一致/查无 → 400（D41 防伪造）
                          · 内联无 qid → align（docs/37 配对结构，无三色）
                          · SCORE_FORCE 强制 gate/align（docs/38 D49，monkeypatch src.config）
  3. practice/guidance → 仅 gate 路由：③ 改进建议 gap/how/rewrite；align 模式 → 400 明确提示
  4. wrongbook         → 按漏点一条入库（mock knowledge_store，docs/22 §3.6 口径保留）
  5. practice/complete → 回流写 weak_points（临时 DB 验证）
  6. remind            → 返回毕业考候选 + 该练 topK，且按紧急度排序

注意：不 import app.main（会经 app.api.chat 链触发 chromadb —— pytest 环境 numpy
access violation 坑，同 test_mock_api 注释）；用「独立 FastAPI + 本 router」构造 TestClient。
DB 隔离照抄 test_shenlun_rounds：swap reflow.DB_PATH 到 tmp_path。
LLM 隔离：灰带 judge_suspect 默认 mock 成全放行（API 只管路由/契约，LLM 语义由
tests/test_judge_llm.py 覆盖）——本机有 key 也不真调，保证确定性。
"""
import sqlite3
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.config as cfg
from app.api.shenlun import router
from src.shenlun import reflow
from src.shenlun.reflow import load_question

# 独立 app：只挂申论 router（不触发面试域 import）
_sl = FastAPI()
_sl.include_router(router, prefix="/api")
client = TestClient(_sl)

QID = "henan_2025_city_1"


@pytest.fixture(autouse=True)
def _no_real_llm():
    """灰带 LLM 默认隔离：mock 成全部放行（marks 空 = wanted 补 None），不真调。"""
    with patch("app.api.shenlun.judge_suspect", return_value=({}, [])):
        yield


@pytest.fixture()
def db(tmp_path):
    """每个测试用独立临时 DB（不污染 data/shenlun.db）。"""
    old_path = reflow.DB_PATH
    reflow.DB_PATH = tmp_path / "test_shenlun_api.db"
    yield tmp_path / "test_shenlun_api.db"
    reflow.DB_PATH = old_path


def _full_answer(qid: str) -> str:
    """把题目全部采分点的关键词拼成作答 → 必然全命中。"""
    item = load_question(qid)
    return " ".join(k for p in item["gold"]["reference_points"] for k in p["keywords"])


class TestPracticeStart:
    @patch("src.shenlun.react.chat_json")
    def test_start_returns_question(self, mock_llm):
        """start 返回题目/材料/题型/推荐理由（LLM 决策 → plan）。"""
        mock_llm.return_value = {
            "focus": "补对策角度",
            "action": "practice",
            "plan": [{"question_id": QID, "why": "对策角度漏点最多"}],
            "advice": "先看材料再作答",
        }
        r = client.post("/api/shenlun/practice/start")
        assert r.status_code == 200
        data = r.json()
        assert data["question_id"] == QID
        assert data["question"]
        assert data["material"]
        assert data["type"] == "归纳概括"
        assert data["max_score"] is not None
        assert "漏点" in data["recommend_reason"]
        assert data["focus"] == "补对策角度"

    @patch("src.shenlun.react.chat_json")
    def test_start_falls_back_to_rules(self, mock_llm):
        """LLM 决策失败 → decide 规则回退（不抛 500）。"""
        mock_llm.side_effect = RuntimeError("network")
        r = client.post("/api/shenlun/practice/start")
        assert r.status_code == 200
        data = r.json()
        assert data["question_id"]  # 规则回退也推了题


class TestPracticeParse:
    """docs/24 §4.2：文字版标准答案 → 采分点（LLM 拆解 + trace，评分链路不动）。"""

    @patch("src.cleaner.decompose.chat_json")
    def test_parse_text_returns_points_with_trace(self, mock_llm):
        """纯文字 → 200：points 补 p1/p2 编号 + source_snippet，trace 回显原文/点/warnings。"""
        mock_llm.return_value = {
            "reference_points": [
                {"point": "设施互通", "keywords": ["城际公交", "高速免费"], "score": 2,
                 "point_type": "对策", "source_snippet": "两地开通了城际公交，实现了高速公路免费互通"},
                {"point": "产业协同", "keywords": ["新兴产业", "新能源"], "score": 2,
                 "point_type": "对策", "source_snippet": "新能源项目相继落地B县"},
            ],
            "warnings": ["第2点关键词偏少"],
        }
        r = client.post("/api/shenlun/practice/parse", json={
            "standard_answer": "一是设施互通：两地开通了城际公交……",
            "question": "梳理概括A区与B县同城化发展的举措和成效",
            "material": "材料全文",
        })
        assert r.status_code == 200
        data = r.json()
        assert [p["id"] for p in data["points"]] == ["p1", "p2"]
        assert data["points"][0]["source_snippet"] == "两地开通了城际公交，实现了高速公路免费互通"
        assert data["warnings"] == ["第2点关键词偏少"]
        # trace：原文 + 同批点 + warnings（dev 前端展示用）
        assert data["trace"]["standard_answer"] == "一是设施互通：两地开通了城际公交……"
        assert data["trace"]["points"] == data["points"]
        assert data["trace"]["warnings"] == data["warnings"]

    @patch("src.cleaner.decompose.chat_json")
    def test_parse_llm_failure_400(self, mock_llm):
        """LLM 挂了（decompose_points 吞异常返回空结果）→ 400，提示切回 JSON 手填。"""
        mock_llm.side_effect = RuntimeError("network")
        r = client.post("/api/shenlun/practice/parse", json={
            "standard_answer": "标准答案全文", "question": "题", "material": "材",
        })
        assert r.status_code == 400
        assert "JSON" in r.json()["detail"]

    @patch("src.cleaner.decompose.chat_json")
    def test_parse_incomplete_points_keeps_200(self, mock_llm):
        """拆点不完整（LLM 成功但没拆出点）→ 200 + warnings，不阻断练习。"""
        mock_llm.return_value = {"reference_points": [], "warnings": []}
        r = client.post("/api/shenlun/practice/parse", json={
            "standard_answer": "过简", "question": "题", "material": "材",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["points"] == []
        assert any("未拆出任何采分点" in w for w in data["warnings"])


class TestPracticeSubmitGate:
    """纯 question_id → trusted → 门禁：§6 PointVerdict 契约（含 anchor 全量下发）。"""

    def test_submit_full_hit_gate_contract(self, db):
        """全关键词作答 → mode=gate，verdicts 全绿·关键词，契约字段齐全。"""
        n = len(load_question(QID)["gold"]["reference_points"])
        r = client.post("/api/shenlun/practice/submit",
                        json={"question_id": QID, "answer": _full_answer(QID)})
        assert r.status_code == 200
        data = r.json()
        assert data["mode"] == "gate"
        assert len(data["verdicts"]) == n            # 顺序 = 采分点顺序（§6 按 point_order 逐点）
        assert data["warnings"] == []
        first = data["verdicts"][0]
        assert set(first) == {"point_id", "point_name", "mode", "status", "matched_by",
                              "terms", "evidence", "anchor", "official", "suspect", "reason"}
        assert first["mode"] == "gate"
        assert first["status"] == "hit" and first["matched_by"] == "kw"
        assert first["terms"]["missing"] == [] and first["terms"]["matched"]
        assert first["evidence"], "命中点带作答原句（规则定位）"
        assert first["anchor"] and "材料第" in first["anchor"]  # 老缺口修复：hits 的 anchor 一并下发
        assert first["suspect"] is None and first["reason"]

    def test_submit_all_miss_gate_verdicts(self, db):
        """全缺 → 每点黄·漏答：terms.missing 全列、evidence 空、reason 固定文案。"""
        refs = load_question(QID)["gold"]["reference_points"]
        r = client.post("/api/shenlun/practice/submit",
                        json={"question_id": QID, "answer": "随便写两句，不涉及采分点"})
        data = r.json()
        assert data["mode"] == "gate"
        assert all(v["status"] == "miss" and v["matched_by"] == "kw"
                   for v in data["verdicts"])
        for v in data["verdicts"]:
            assert v["evidence"] == ""                            # §8.1：黄行 evidence 为空
            assert v["terms"]["matched"] == [] and v["terms"]["missing"]
            assert v["reason"].startswith("作答中未找到关键词：")
            assert v["anchor"] and "材料第" in v["anchor"]         # miss 也带锚（D51 下发）
        assert [v["point_id"] for v in data["verdicts"]] == [p["id"] for p in refs]

    def test_submit_gray_released_green(self, db):
        """灰带点 LLM 放行（marks 缺键/显式 null）→ 绿·语义（matched_by=llm）。"""
        r = client.post("/api/shenlun/practice/submit",
                        json={"question_id": QID, "answer": "开通了城际公交。"})  # c1 部分命中
        data = r.json()
        v = next(v for v in data["verdicts"] if v["point_id"] == "c1")
        assert v["status"] == "hit" and v["matched_by"] == "llm"
        assert v["reason"].startswith("该点关键词部分出现（城际公交），比对官方写法无存疑")
        assert v["suspect"] is None and v["evidence"]

    def test_submit_gray_suspect_blue(self, db):
        """灰带点 LLM 标疑似 → status=suspect，suspect/reason 透传（蓝·疑似）。"""
        mark = {"label": "疑似宽泛", "reason": "只写了获得感口号，没写就医消费等具体内容"}
        with patch("app.api.shenlun.judge_suspect",
                   return_value=({"c8": mark}, [])):
            r = client.post("/api/shenlun/practice/submit",
                            json={"question_id": QID, "answer": "增强了获得感幸福感。"})
        data = r.json()
        v = next(v for v in data["verdicts"] if v["point_id"] == "c8")
        assert v["status"] == "suspect" and v["matched_by"] == "llm"
        assert v["suspect"] == mark and v["reason"] == mark["reason"]
        assert v["terms"]["matched"] == ["幸福感"]      # 疑似行也带规则命中证据

    def test_submit_llm_down_gate_unblocked(self, db):
        """LLM 挂（warnings 透传）→ 灰带全放行，响应仍 200 完整（安全方向）。"""
        with patch("app.api.shenlun.judge_suspect",
                   return_value=({}, ["LLM 不可用，灰带点全部按放行处理（降级绿·语义）: boom"])):
            r = client.post("/api/shenlun/practice/submit",
                            json={"question_id": QID, "answer": "开通了城际公交。"})
        data = r.json()
        assert r.status_code == 200
        assert any("LLM 不可用" in w for w in data["warnings"])
        v = next(v for v in data["verdicts"] if v["point_id"] == "c1")
        assert v["status"] == "hit" and v["matched_by"] == "llm"

    def test_submit_unknown_question_404(self, db):
        r = client.post("/api/shenlun/practice/submit",
                        json={"question_id": "not_exist", "answer": "x"})
        assert r.status_code == 404


class TestPracticeSubmitTrusted:
    """docs/38 D41：gold.question_id 声明 → 与库题全量比对，trusted 语义底线。"""

    @staticmethod
    def _gold_for(qid: str) -> dict:
        item = load_question(qid)
        return {"question_id": qid,
                "points": item["gold"]["reference_points"],
                "material": item["task"]["material"],
                "question": item["task"]["question"],
                "qtype": item["meta"]["type"]}

    def test_gold_with_consistent_qid_is_gate(self, db):
        """gold.question_id 与库题逐点一致 → trusted → 门禁模式。"""
        r = client.post("/api/shenlun/practice/submit",
                        json={"gold": self._gold_for(QID), "answer": "开通了城际公交。"})
        assert r.status_code == 200
        assert r.json()["mode"] == "gate"

    def test_gold_qid_forged_points_400(self, db):
        """声称库题 qid 但塞了自造 points → 400（防伪造 qid 蹭门禁）。"""
        gold = self._gold_for(QID)
        gold["points"] = [{"id": "c1", "point": "自造点", "keywords": ["随便"],
                           "score": 1, "point_type": "对策"}]
        r = client.post("/api/shenlun/practice/submit",
                        json={"gold": gold, "answer": "随便"})
        assert r.status_code == 400
        assert "不一致" in r.json()["detail"]

    def test_gold_qid_partial_point_tamper_400(self, db):
        """只改一个点的 keywords → 400（全量比对 id+point+keywords，§10 注意3）。"""
        gold = self._gold_for(QID)
        gold["points"] = [dict(p, keywords=["偷改的关键词"]) if p["id"] == "c1" else p
                          for p in gold["points"]]
        r = client.post("/api/shenlun/practice/submit",
                        json={"gold": gold, "answer": "随便"})
        assert r.status_code == 400
        assert "c1" in r.json()["detail"]

    def test_gold_qid_not_in_bank_400(self, db):
        """声明的题目不在题库 → 400（不是 404，防伪造语义要显式）。"""
        gold = self._gold_for(QID)
        gold["question_id"] = "henan_2099_fake_1"
        r = client.post("/api/shenlun/practice/submit",
                        json={"gold": gold, "answer": "随便"})
        assert r.status_code == 400
        assert "不存在" in r.json()["detail"]


class TestPracticeSubmitAlign:
    """内联 gold 无 question_id → trusted=False → 示证（docs/37 §6 配对结构）。"""

    @staticmethod
    def _inline_gold() -> dict:
        return {"points": [
            {"id": "c1", "point": "设施互通", "keywords": ["城际公交"], "score": 1,
             "point_type": "对策"},
            {"id": "c2", "point": "产业协同", "keywords": ["新能源"], "score": 1,
             "point_type": "对策"},
        ], "material": "A区开通城际公交，实现互联互通。新能源项目落地B县。",
            "question": "概括举措", "qtype": "归纳概括"}

    def test_inline_no_qid_returns_align(self, db):
        """无 qid 内联 → mode=align：配对结构齐全，无三色/疑似/建议。"""
        r = client.post("/api/shenlun/practice/submit",
                        json={"gold": self._inline_gold(), "answer": "A区开了城际公交。"})
        assert r.status_code == 200
        data = r.json()
        assert data["mode"] == "align"
        assert set(data) == {"mode", "official_points", "answer_chunks",
                             "alignments", "gaps", "orphans", "meta"}
        assert data["meta"]["engine"] == "align" and data["meta"]["semantic_used"] is False
        c1 = next(a for a in data["alignments"] if a["point_id"] == "c1")
        assert c1["method"] == "kw" and c1["kws_hit"] == ["城际公交"]
        assert "c2" in {g["point_id"] for g in data["gaps"]}    # 未见对应候选
        assert data["official_points"][0]["material_ref"]        # 出处附注随点返回

    def test_gold_qid_consistent_plus_inline_points_used(self, db):
        """trusted 的评分用提交的内联 points（校验一致过），响应仍是 gate。"""
        gold = self._inline_gold()
        gold["question_id"] = QID                                # 声称库题但内容不一致 → 400
        r = client.post("/api/shenlun/practice/submit",
                        json={"gold": gold, "answer": "A区开了城际公交。"})
        assert r.status_code == 400                              # 库题 9 点 ≠ 内联 2 点


class TestScoreForce:
    """docs/38 D49：SCORE_FORCE 强制模式（测试/演示锁定，防 trusted 逻辑漂移）。"""

    def test_force_align_overrides_trusted_qid(self, db, monkeypatch):
        monkeypatch.setattr(cfg, "SCORE_FORCE", "align")
        r = client.post("/api/shenlun/practice/submit",
                        json={"question_id": QID, "answer": "开通了城际公交。"})
        assert r.status_code == 200
        assert r.json()["mode"] == "align"

    def test_force_gate_on_inline_no_qid(self, db, monkeypatch):
        monkeypatch.setattr(cfg, "SCORE_FORCE", "gate")
        gold = TestPracticeSubmitAlign._inline_gold()
        r = client.post("/api/shenlun/practice/submit",
                        json={"gold": gold, "answer": "A区开了城际公交。"})
        assert r.status_code == 200
        data = r.json()
        assert data["mode"] == "gate"
        assert all("status" in v for v in data["verdicts"])


class TestPracticeGuidance:
    """docs/38 §4.3：③改进建议只对门禁题开放（mode=gate），gap/how/rewrite 三字段。"""

    @patch("src.mock.chat_json")
    def test_guidance_gate_returns_improvement(self, mock_llm, db):
        """门禁题点开 → official 规则层回传 + 建议三件套（单次 LLM，不判因/不回放②）。"""
        mock_llm.return_value = {
            "gap": "该点只写了产业，没落到协同机制上",
            "how": "回到材料中「新能源项目」句，把做法展开成产业链协作",
            "rewrite": "依托新能源项目落地，牵引上下游企业形成协作链条",
        }
        r = client.post("/api/shenlun/practice/guidance",
                        json={"question_id": QID, "point_id": "c2", "answer": "不相关"})
        assert r.status_code == 200
        g = r.json()
        assert set(g) == {"point_id", "point", "official", "gap", "how", "rewrite"}
        assert g["point_id"] == "c2" and g["point"] == "产业协同"
        assert g["official"] and not g["official"].startswith("材料第")  # D46 锚句原文
        assert g["gap"] and g["how"] and g["rewrite"]
        assert mock_llm.call_count == 1

    @patch("src.mock.chat_json")
    def test_guidance_llm_failure_keeps_official(self, mock_llm, db):
        """LLM 失败 → gap/how/rewrite 空串，official 规则层仍返回（不阻断）。"""
        mock_llm.side_effect = RuntimeError("network")
        r = client.post("/api/shenlun/practice/guidance",
                        json={"question_id": QID, "point_id": "c2", "answer": "不相关"})
        assert r.status_code == 200
        g = r.json()
        assert g["official"]
        assert g["gap"] == "" and g["how"] == "" and g["rewrite"] == ""

    @patch("src.mock.chat_json")
    def test_guidance_hit_point_guidable(self, mock_llm, db):
        """命中点也可点开（核对官方写法）——guidance 不限漏点（§4.3 ③ 三态入口一致）。"""
        mock_llm.return_value = {"gap": "无", "how": "核对官方写法", "rewrite": ""}
        r = client.post("/api/shenlun/practice/guidance",
                        json={"question_id": QID, "point_id": "c1", "answer": _full_answer(QID)})
        assert r.status_code == 200
        assert mock_llm.call_count == 1

    @patch("src.mock.chat_json")
    def test_guidance_align_mode_rejected_400(self, mock_llm, db):
        """内联无 qid（示证模式）→ 400 明确拒绝：不生成改进建议（红线，不越过差异标注）。"""
        gold = TestPracticeSubmitAlign._inline_gold()
        r = client.post("/api/shenlun/practice/guidance",
                        json={"gold": gold, "point_id": "c1", "answer": "A区开了城际公交。"})
        assert r.status_code == 400
        assert "示证模式" in r.json()["detail"]
        mock_llm.assert_not_called()   # 模式路由先行，根本没机会调 LLM

    def test_guidance_unknown_point_404(self, db):
        r = client.post("/api/shenlun/practice/guidance",
                        json={"question_id": QID, "point_id": "nope", "answer": "x"})
        assert r.status_code == 404


class TestWrongbook:
    @patch("src.memory.knowledge_store.store_items")
    def test_wrongbook_stores_one_item_per_point(self, mock_store, db):
        """加入错题本：按漏点一条入库，material_source 服务端重算，字段映射齐全。"""
        mock_store.return_value = 1
        r = client.post("/api/shenlun/wrongbook", json={
            "question_id": QID, "point_id": "c2",
            "answer": "H市开通了城际公交。", "answer_snippet": "",
            "demo": "示范表述", "cause_type": "文本比对",
            # docs/35 §4.5：cause 传徽章口径句（原因即判定结论，由前端按 miss_cause 映射）
            "cause": "没写上：这个采分点你的作答里完全没有体现",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["stored"] == 1
        assert data["item_id"] == f"sl_{QID}_c2"
        ki = mock_store.call_args.args[0][0]
        assert ki.point_id == "c2" and ki.question_id == QID
        assert ki.topic == "产业协同"
        assert ki.status.value == "fail"
        assert ki.reflow_tier == "red"                      # 初始红档（docs/22 §3.6）
        assert "材料第1段" in ki.material_source            # 服务端重算，保证可溯源
        # 【错因】文本比对：没写上：这个采分点…；【示范】… —— 徽章句经 cause_type 前缀入库
        assert "示范表述" in ki.feedback
        assert "文本比对" in ki.feedback and "没写上：这个采分点" in ki.feedback
        assert ki.date  # 当天

    def test_wrongbook_unknown_point_404(self, db):
        r = client.post("/api/shenlun/wrongbook",
                        json={"question_id": QID, "point_id": "zz"})
        assert r.status_code == 404

    @patch("src.memory.knowledge_store.store_items")
    def test_wrongbook_inline_id_hashed_per_question(self, mock_store, db):
        """docs/39 §7.1：单题 ctx.id 带题面 hash → 不同手写题同漏点条目 id 各异（防互覆）；
        同题同点 → 同 id（upsert 语义保留）。此前 ctx.id 恒 "inline" 会互相覆盖丢题面。"""
        mock_store.return_value = 1

        def _gold(q: str) -> dict:
            return {"question": q, "qtype": "归纳概括",
                    "material": "两地开通了城际公交，实现高速公路免费互通。",
                    "points": [{"id": "c1", "point": "设施互通",
                                "keywords": ["城际公交", "互通"], "score": 1, "point_type": "对策"}]}

        r1 = client.post("/api/shenlun/wrongbook", json={
            "gold": _gold("根据材料，概括两地同城化发展的举措。"),
            "point_id": "c1", "answer": "开通了城际公交。"})
        r2 = client.post("/api/shenlun/wrongbook", json={
            "gold": _gold("根据材料，概括另一件事的做法。"),
            "point_id": "c1", "answer": "开通了城际公交。"})
        assert r1.status_code == 200 and r2.status_code == 200
        id1, id2 = r1.json()["item_id"], r2.json()["item_id"]
        assert id1.startswith("sl_inline_") and id2.startswith("sl_inline_")
        assert id1 != id2, "不同手写题同漏点不得共用 id（会互相覆盖）"
        r3 = client.post("/api/shenlun/wrongbook", json={
            "gold": _gold("根据材料，概括两地同城化发展的举措。"),
            "point_id": "c1", "answer": "开通了城际公交。"})
        assert r3.json()["item_id"] == id1, "同题同点应保留 upsert 语义（重复回流覆盖旧条目）"


class TestPracticeComplete:
    def test_complete_writes_reflow(self, db):
        """complete 回流 → weak_points 表有写入（临时 DB 验证）。"""
        rounds = [
            {"round_no": 0, "answer": "城际公交免费互通", "hit_ids": ["c1"], "miss_ids": [],
             "hit_ratio": 1.0, "guided_point_ids": []},
        ]
        r = client.post("/api/shenlun/practice/complete",
                        json={"question_id": QID, "rounds": rounds})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        conn = sqlite3.connect(str(db))
        n = conn.execute("SELECT COUNT(*) FROM weak_points").fetchone()[0]
        rounds_n = conn.execute("SELECT COUNT(*) FROM answer_rounds").fetchone()[0]
        conn.close()
        assert n > 0
        assert rounds_n == 1

    def test_complete_empty_rounds_422(self, db):
        r = client.post("/api/shenlun/practice/complete",
                        json={"question_id": QID, "rounds": []})
        assert r.status_code == 422


class TestRemind:
    def test_remind_ordered(self, db):
        """remind：毕业考候选 + 该练 topK，to_practice 按紧急度降序（漏得多的在前）。"""
        refs = load_question(QID)["gold"]["reference_points"]
        # 造两条档案：miss 2 次的 vs miss 1 次的
        reflow.reflow_answer(QID, "归纳概括", "不相关", refs)          # 全 miss ×1
        reflow.reflow_answer(QID, "归纳概括", "不相关", refs)          # 全 miss ×2
        reflow.reflow_answer("jiangsu_2023_a_1", "归纳概括",
                             _full_answer("jiangsu_2023_a_1"),
                             load_question("jiangsu_2023_a_1")["gold"]["reference_points"])  # 全 hit ×1
        # 把 last_practiced_at 改成 30 天前 → forgetting 非 0，紧急度可排序
        conn = sqlite3.connect(str(db))
        conn.execute("UPDATE weak_points SET last_practiced_at='2026-07-30T00:00:00'")
        conn.commit()
        conn.close()

        r = client.get("/api/shenlun/remind")
        assert r.status_code == 200
        data = r.json()
        assert set(data) == {"graduation_candidates", "to_practice"}
        assert len(data["to_practice"]) >= 2
        first = data["to_practice"][0]
        assert first["days"] >= 1  # 30 天前的练习
        # 全 miss ×2 的点紧急度最高 → 第一条是它（miss_count=2 的点 label）
        assert data["to_practice"][0]["point"] == refs[0]["point"]


class TestRecord:
    @patch("src.cleaner.decompose.chat_json")
    def test_record_previews_points(self, mock_llm):
        """录入预览：标准答案 → 拆采分点（mock LLM 固定输出），不落库。"""
        mock_llm.return_value = {
            "reference_points": [
                {"point": "设施互通", "keywords": ["城际公交"], "score": 4, "point_type": "对策"},
                {"point": "服务升级", "keywords": ["增值化"], "score": 3, "point_type": "对策"},
            ],
            "warnings": ["标准答案偏短"],
        }
        r = client.post("/api/shenlun/record", json={
            "question": "谈谈政务服务如何转变",
            "standard_answer": "一是设施互通，开通城际公交；二是服务升级，提供增值服务。",
            "max_score": 20,
        })
        assert r.status_code == 200
        data = r.json()
        assert [p["point"] for p in data["points"]] == ["设施互通", "服务升级"]
        assert data["warnings"] == ["标准答案偏短"]


class TestWeakpoints:
    def test_weakpoints_full_list(self, db):
        """weakpoints 返回全量档案 + state 筛选。"""
        refs = load_question(QID)["gold"]["reference_points"]
        reflow.reflow_answer(QID, "归纳概括", "不相关", refs)
        r = client.get("/api/shenlun/weakpoints")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == len(refs)
        assert set(items[0]) == {"point_key", "label", "qtype", "point_type", "question_id",
                                 "miss_count", "hit_count", "consecutive_hits", "tier",
                                 "urgency", "state", "last_miss_at"}

        r2 = client.get("/api/shenlun/weakpoints", params={"state": "active"})
        assert len(r2.json()["items"]) == len(refs)
        r3 = client.get("/api/shenlun/weakpoints", params={"state": "graduated"})
        assert r3.json()["items"] == []
