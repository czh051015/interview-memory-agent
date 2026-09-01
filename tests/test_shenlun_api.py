"""docs/20 Step A + docs/22 §3.5/§3.6：申论工作台 API 测试（FastAPI TestClient + mock LLM）。

覆盖（docs/22 示证范式后）：
  1. practice/start    → ReAct 推题返回题目/材料/题型/推荐理由（mock react.chat_json）
  2. practice/submit   → 全命中 → passed=true、hits 全量、misses 空；漏点 → L1 每点挂材料锚定 + 推 1 个
  3. practice/guidance → 按需示证：单漏点 L3 锚定 + L2 示范 + L4 错因（mock src.mock.chat_json）
  4. wrongbook         → 按漏点一条入库（mock knowledge_store），material_source 服务端重算
  5. practice/complete → 回流写 weak_points（临时 DB 验证）
  6. remind            → 返回毕业考候选 + 该练 topK，且按紧急度排序

注意：不 import app.main（会经 app.api.chat 链触发 chromadb —— pytest 环境 numpy
access violation 坑，同 test_mock_api 注释）；用「独立 FastAPI + 本 router」构造 TestClient。
DB 隔离照抄 test_shenlun_rounds：swap reflow.DB_PATH 到 tmp_path。
"""
import sqlite3
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.shenlun import router
from src.shenlun import reflow
from src.shenlun.reflow import load_question

# 独立 app：只挂申论 router（不触发面试域 import）
_sl = FastAPI()
_sl.include_router(router, prefix="/api")
client = TestClient(_sl)

QID = "henan_2025_city_1"


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


class TestPracticeSubmit:
    def test_submit_full_hit(self, db):
        """全关键词作答 → passed=true、hits 全量带 matched_text、misses 空、无 leading。"""
        n = len(load_question(QID)["gold"]["reference_points"])
        r = client.post("/api/shenlun/practice/submit",
                        json={"question_id": QID, "answer": _full_answer(QID)})
        assert r.status_code == 200
        data = r.json()
        assert data["passed"] is True
        assert data["hit_ratio"] == 1.0
        assert len(data["hits"]) == n
        assert data["misses"] == []
        assert data["leading"] is None
        assert all(h.get("matched_text") for h in data["hits"]), "命中点应带作答片段（L1 标红定位）"

    def test_submit_miss_returns_l1_with_material(self, db):
        """漏点作答 → 纯确定性 L1：每漏点挂材料原话（material_source）+ 推 1 个最该补（不调 LLM）。"""
        r = client.post("/api/shenlun/practice/submit",
                        json={"question_id": QID, "answer": "随便写两句，不涉及采分点"})
        assert r.status_code == 200
        data = r.json()
        assert data["passed"] is False
        assert data["hits"] == []
        assert len(data["misses"]) == len(load_question(QID)["gold"]["reference_points"])
        assert all(m.get("material_source") for m in data["misses"]), "每个漏点都应锚到材料原话"
        lead = data["leading"]
        assert lead is not None
        assert lead["point_id"] in {m["id"] for m in data["misses"]}, "推 1 个必须出自漏点集"
        assert lead["material_source"]

    def test_submit_unknown_question_404(self, db):
        r = client.post("/api/shenlun/practice/submit",
                        json={"question_id": "not_exist", "answer": "x"})
        assert r.status_code == 404


class TestPracticeGuidance:
    @patch("src.mock.chat_json")
    def test_guidance_on_demand(self, mock_llm, db):
        """点开某漏点 → L3 材料锚定（score）+ L2 示范 + L4 错因（LLM 一次调用生成）。"""
        mock_llm.side_effect = [
            {"demo": "写到产业协同时，可表述为：围绕新能源项目落地推动产业链协作。"},
            {"cause_type": "完全没提", "cause": "作答未涉及产业。", "fix": "回材料第1段抓新能源项目。"},
        ]
        r = client.post("/api/shenlun/practice/guidance",
                        json={"question_id": QID, "point_id": "c2", "answer": "不相关"})
        assert r.status_code == 200
        g = r.json()
        assert g["point"] == "产业协同"
        assert g["material_source"] and "材料第1段" in g["material_source"]
        assert g["demo"] and "产业链" in g["demo"]
        assert g["cause_type"] == "完全没提"
        assert mock_llm.call_count == 2

    @patch("src.mock.chat_json")
    def test_guidance_llm_failure_keeps_l3(self, mock_llm, db):
        """LLM 失败 → demo/cause 空，L3 材料锚定仍返回（不阻断）。"""
        mock_llm.side_effect = RuntimeError("network")
        r = client.post("/api/shenlun/practice/guidance",
                        json={"question_id": QID, "point_id": "c2", "answer": "不相关"})
        assert r.status_code == 200
        g = r.json()
        assert g["material_source"]
        assert g["demo"] == "" and g["cause"] == ""

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
            "demo": "示范表述", "cause_type": "完全没提", "cause": "没写产业协同。",
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
        assert "示范表述" in ki.feedback and "没写产业协同" in ki.feedback
        assert ki.date  # 当天

    def test_wrongbook_unknown_point_404(self, db):
        r = client.post("/api/shenlun/wrongbook",
                        json={"question_id": QID, "point_id": "zz"})
        assert r.status_code == 404


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
