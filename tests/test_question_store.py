"""docs/实施计划 任务一：用户题入库闭环测试 —— question_store + POST /shenlun/questions。

覆盖：
  1. question_store 模块：save_user_question 写库后 load_question 可读、doc 结构与
     CLI 契约一致（authority=user / task 布局 / points 补 approved=True+human_approved）；
     next_user_question_id 按当天已入库数递增（含目录不存在/已有文件两种情况）。
  2. API 端点：happy path（自动 id / 注入 id）；语义校验 400（空点集 / 点名为空 /
     关键词为空 / 分值为负 / 满分 <1）；id 归一（空/重复 → p{N}）。
  3. 目录隔离：monkeypatch reflow.USER_QUESTIONS_DIR → tmp_path，不污染真实
     data/user_questions/（question_store 活引用模块属性，patch 即生效）。
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.shenlun import router
from src.cleaner.schema import utcnow
from src.shenlun import reflow
from src.shenlun.question_store import next_user_question_id, save_user_question
from src.shenlun.reflow import load_question

# 独立 app：只挂申论 router（同 test_shenlun_api 先例，不触发面试域 import）
_sl = FastAPI()
_sl.include_router(router, prefix="/api")
client = TestClient(_sl)


@pytest.fixture(autouse=True)
def user_dir(tmp_path, monkeypatch):
    """USER_QUESTIONS_DIR 指向临时目录（隔离真实题库；两端点/模块共用 patch）。"""
    d = tmp_path / "user_questions"
    monkeypatch.setattr(reflow, "USER_QUESTIONS_DIR", d)
    return d


def _points(n=2) -> list[dict]:
    return [
        {"id": "c1", "point": "设施互通", "keywords": ["城际公交", "互通"], "score": 2,
         "point_type": "对策"},
        {"id": "c2", "point": "产业协同", "keywords": ["新兴产业"], "score": 1,
         "point_type": "对策"},
    ][:n]


def _doc(id_: str, points=None) -> dict:
    return {
        "question": "根据给定资料，谈谈同城化发展的举措。",
        "requirements": "要求：全面准确。",
        "material": "材料全文。",
        "max_score": 10,
        "points": points if points is not None else _points(),
        "question_id": id_,
    }


# ── question_store 模块 ────────────────────────────────────────────

def test_save_and_load_roundtrip_contract(user_dir):
    """写库 → load_question 可读；doc 字段与 CLI 契约一致（authority/task/gold）。"""
    path = save_user_question(question_id="user_test_1", question="题干？",
                              requirements="要求", material="材料",
                              max_score=20, points=_points())
    assert path == str(user_dir / "user_test_1.json")
    item = load_question("user_test_1")
    assert item is not None
    assert item["id"] == "user_test_1" and item["domain"] == "shenlun"
    assert item["meta"]["authority"] == "user"
    assert item["task"] == {"question": "题干？", "requirements": "要求",
                            "material": "材料", "max_score": 20}
    pts = item["gold"]["reference_points"]
    assert [p["id"] for p in pts] == ["c1", "c2"]
    assert pts[0]["point"] == "设施互通" and pts[0]["keywords"] == ["城际公交", "互通"]
    assert all(p["approved"] is True for p in pts)          # 页面确认 = 全点人工通过
    assert all(p["source"] == "human_approved" for p in pts)
    assert pts[0]["point_type"] == "对策"


def test_next_question_id_increments_with_existing_files(user_dir):
    """id 递增语义：目录不存在 → _01；已有文件 → 按当天前缀数 +1（CLI 原语义）。"""
    assert next_user_question_id() == f"user_{utcnow().strftime('%Y%m%d')}_01"
    user_dir.mkdir()
    (user_dir / f"user_{utcnow().strftime('%Y%m%d')}_01.json").write_text("{}", encoding="utf-8")
    (user_dir / f"user_{utcnow().strftime('%Y%m%d')}_03.json").write_text("{}", encoding="utf-8")
    assert next_user_question_id() == f"user_{utcnow().strftime('%Y%m%d')}_04"


# ── API 端点 ───────────────────────────────────────────────────────

def test_api_save_auto_id(user_dir):
    """POST 成功：自动生成 user_YYYYMMDD_NN，落库后可被 load_question 读取。"""
    body = _doc("")
    body.pop("question_id")
    r = client.post("/api/shenlun/questions", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["stored"] == 2
    assert data["question_id"].startswith("user_")
    assert load_question(data["question_id"]) is not None


def test_api_save_with_injected_id(user_dir):
    """question_id 注入：用指定 id 落盘（CLI/测试用）。"""
    r = client.post("/api/shenlun/questions", json=_doc("manual_slug"))
    assert r.status_code == 200
    assert r.json() == {"question_id": "manual_slug", "stored": 2}
    assert (user_dir / "manual_slug.json").exists()


def test_api_save_normalizes_bad_ids(user_dir):
    """空 id / 重复 id → 补 p{N}（LLM 拆点风格 p1/p2…），不拒绝也不崩。"""
    pts = _points(2)
    pts[0]["id"] = ""
    pts[1]["id"] = "p1"  # 与归一后的 pts[0] 撞 → 顺延 p2
    r = client.post("/api/shenlun/questions", json=_doc("norm_id", points=pts))
    assert r.status_code == 200
    item = load_question("norm_id")
    assert [p["id"] for p in item["gold"]["reference_points"]] == ["p1", "p2"]


@pytest.mark.parametrize("mut,detail", [
    (lambda pts: pts.clear(), "采分点不能为空"),
    (lambda pts: pts[0].update({"point": "  "}), "采分点名称为空"),
    (lambda pts: pts[0].update({"keywords": []}), "未填关键词"),
    (lambda pts: pts[0].update({"score": -1}), "分值不能为负"),
    (lambda pts: pts[0].update({"score": "abc"}), "分值不是整数"),
])
def test_api_save_validation_400(user_dir, mut, detail):
    """语义校验统一 400（detail 可直接展示给前端）。"""
    pts = _points(2)
    mut(pts)
    r = client.post("/api/shenlun/questions", json=_doc("bad", points=pts))
    assert r.status_code == 400
    assert detail in r.json()["detail"]
    assert not (user_dir / "bad.json").exists()


def test_api_save_max_score_zero_400(user_dir):
    body = _doc("bad")
    body["max_score"] = 0
    r = client.post("/api/shenlun/questions", json=body)
    assert r.status_code == 400
    assert "满分" in r.json()["detail"]


def test_saved_question_usable_by_practice_chain(user_dir):
    """落库题可被练习链路读取（load_question 覆盖 USER_QUESTIONS_DIR 的关键收益）。"""
    r = client.post("/api/shenlun/questions", json=_doc("practice_ready"))
    assert r.status_code == 200
    item = load_question("practice_ready")
    assert item["gold"]["reference_points"][0]["point_type"] == "对策"
    # 与库题同一读取路径（reflow._question_dirs 已含 USER_QUESTIONS_DIR）
    assert item["id"] == "practice_ready"
