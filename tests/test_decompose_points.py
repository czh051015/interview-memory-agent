"""docs/16：申论「标准答案 → 采分点」拆解 + 人审闸门 + 用户题库入库测试。"""

import json
from datetime import datetime
from unittest.mock import patch

from src.cleaner.decompose import decompose_points
from src.cleaner.annotate import annotate_points
from src.cleaner.schema import PointDecomposeResult, ReferencePoint
from src.shenlun.score import from_benchmark, score_answer


class FakePrompt:
    """按序列返回输入的 prompt_fn。"""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = 0

    def __call__(self, text):
        self.calls += 1
        return self.answers.pop(0) if self.answers else "x"


def make_result(points=None, max_score=20):
    return PointDecomposeResult(
        question_id="user_test_01", question="题目", requirements="要求",
        material="材料", max_score=max_score,
        reference_points=points or [
            ReferencePoint(id="c1", point="六尺巷·化解纠纷", keywords=["六尺巷", "土地纠纷", "谦让"], score=3),
            ReferencePoint(id="c2", point="河长制·治水", keywords=["河长", "水质", "清淤泥"], score=3),
            ReferencePoint(id="c3", point="生态理念·象群", keywords=["象群", "生态"], score=4),
        ],
        warnings=["示例警告"],
    )


# ── decompose_points ──────────────────────────────────────────────
class TestDecomposePoints:
    def test_parses_llm_output_into_draft_points(self):
        """正常拆解：approved=False、source=llm_draft、id 按序、出生留痕。"""
        llm_out = {
            "reference_points": [
                {"point": "六尺巷·化解纠纷", "keywords": ["六尺巷", "土地纠纷", "谦让"], "score": 3},
                {"point": "河长制·治水", "keywords": ["河长", "水质"], "score": 4},
            ],
            "warnings": ["第2点关键词较少，仅供参考"],
        }
        with patch("src.cleaner.decompose.chat_json", return_value=llm_out):
            result = decompose_points("标答全文", question="题", material="材", max_score=20,
                                      question_id="q1", max_tokens=4096)

        assert result.question_id == "q1"
        assert len(result.reference_points) == 2
        p1, p2 = result.reference_points
        assert p1.id == "c1" and p2.id == "c2"
        assert p1.point == "六尺巷·化解纠纷"
        assert p1.keywords == ["六尺巷", "土地纠纷", "谦让"]
        assert p1.score == 3
        # 防循环论证：默认不通过，待人工审核
        assert p1.approved is False
        assert p1.source == "llm_draft"
        # 出生留痕（time 是真实 utcnow，只校验其余字段）
        assert len(p1.history) == 1
        birth = {k: v for k, v in p1.history[0].items() if k != "time"}
        assert birth == {
            "from": None,
            "to": "llm_draft",
            "reason": "由 LLM 拆解生成，待人工审核",
            "actor": "decompose_points",
        }
        # LLM 自报 warnings 透传
        assert result.warnings == ["第2点关键词较少，仅供参考"]

    def test_llm_failure_returns_empty_result(self):
        """LLM 挂了 → 返回空结果而非崩溃（复用 decompose 的异常兜底）。"""
        with patch("src.cleaner.decompose.chat_json", side_effect=Exception("API down")):
            result = decompose_points("标答", question="题", max_score=20)
        assert result.reference_points == []
        assert result.question == "题"

    def test_invalid_point_skipped_with_warning(self):
        """单条点校验失败 → warnings 记录，不整体崩。"""
        llm_out = {
            "reference_points": [
                {"point": "有效点", "keywords": ["关键词"], "score": 3},
                {"point": "", "keywords": [], "score": "不是数字"},  # 非法
                {"point": "另一有效点", "keywords": ["词"], "score": 2},
            ],
        }
        with patch("src.cleaner.decompose.chat_json", return_value=llm_out):
            result = decompose_points("标答", question="题", max_score=20)
        assert len(result.reference_points) == 2
        # 非法点被跳过，id 连续
        assert [p.id for p in result.reference_points] == ["c1", "c2"]
        assert any("校验失败" in w for w in result.warnings)

    def test_empty_points_warns(self):
        with patch("src.cleaner.decompose.chat_json", return_value={"reference_points": []}):
            result = decompose_points("标答", question="题", max_score=20)
        assert result.reference_points == []
        assert any("未拆出任何采分点" in w for w in result.warnings)

    def test_too_few_points_warns_short_answer(self):
        llm_out = {"reference_points": [{"point": "唯一", "keywords": ["词"], "score": 5}]}
        with patch("src.cleaner.decompose.chat_json", return_value=llm_out):
            result = decompose_points("标答过简", question="题", max_score=20)
        assert len(result.reference_points) == 1
        assert any("标答过简" in w for w in result.warnings)


# ── annotate_points 人审闸门 ───────────────────────────────────────
class TestAnnotatePoints:
    def test_k_confirms_point(self):
        """k=确认 → approved=True, source=human_approved，留痕。"""
        now = datetime(2026, 8, 28, 12, 0, 0)
        result = make_result()
        out = annotate_points(result, FakePrompt(["k", "x", "x"]), now=now)
        p = out.reference_points[0]
        assert p.approved is True
        assert p.source == "human_approved"
        assert p.history[-1]["reason"] == "人工确认通过"
        assert p.history[-1]["actor"] == "annotate_points"
        assert p.history[-1]["from"] == "llm_draft"

    def test_all_k_confirmed_is_publishable(self):
        """全部 k 确认 → all_approved=True（可入库）。"""
        result = make_result(points=[make_result().reference_points[0]])
        out = annotate_points(result, FakePrompt(["k"]))
        assert out.all_approved is True

    def test_s_changes_score_but_stays_draft(self):
        """s=改分值 → score 更新 + 留痕，但不自动 approved（仍需 k）。"""
        now = datetime(2026, 8, 28, 12, 0, 0)
        result = make_result(points=[make_result().reference_points[0]])
        out = annotate_points(result, FakePrompt(["s", "5", "x"]), now=now)
        p = out.reference_points[0]
        assert p.score == 5
        assert p.approved is False
        assert p.history[-1]["reason"] == "人工改分值：3.0 → 5.0"
        assert p.history[-1]["actor"] == "annotate_points"

    def test_s_rejects_score_out_of_range(self):
        """改分值超满分 → 拒绝，重试输入。"""
        result = make_result(points=[make_result().reference_points[0]], max_score=20)
        out = annotate_points(result, FakePrompt(["s", "99", "6", "x"]))
        assert out.reference_points[0].score == 6

    def test_w_changes_keywords(self):
        """w=改关键词：逗号（含中文逗号）分隔。"""
        now = datetime(2026, 8, 28, 12, 0, 0)
        result = make_result(points=[make_result().reference_points[0]])
        out = annotate_points(result, FakePrompt(["w", "礼让,邻里纠纷，让墙诗", "x"]), now=now)
        p = out.reference_points[0]
        assert p.keywords == ["礼让", "邻里纠纷", "让墙诗"]
        assert p.history[-1]["reason"].startswith("人工改关键词")
        assert p.approved is False

    def test_d_deletes_point(self):
        """d=删除 → 点不落库。"""
        result = make_result()
        out = annotate_points(result, FakePrompt(["d"]))
        assert [p.id for p in out.reference_points] == ["c2", "c3"]
        assert out.reference_points[0].id == "c2"  # 下一条顶上，继续审

    def test_a_adds_point_as_human_approved(self):
        """a=新增 → 人工补点直接 human_approved，id 接续最大编号。"""
        now = datetime(2026, 8, 28, 12, 0, 0)
        result = make_result(points=[make_result().reference_points[0]])
        out = annotate_points(result, FakePrompt(["a", "耕读传家", "耕读,阅读,书香", "4", "x"]), now=now)
        added = out.reference_points[1]
        assert added.id == "c2"
        assert added.point == "耕读传家"
        assert added.keywords == ["耕读", "阅读", "书香"]
        assert added.score == 4
        assert added.approved is True
        assert added.source == "human_approved"

    def test_x_keeps_draft(self):
        """x=跳过 → 保持 approved=False，整批不可入库。"""
        result = make_result()
        out = annotate_points(result, FakePrompt(["x", "x", "x"]))
        assert all(not p.approved for p in out.reference_points)
        assert out.all_approved is False

    def test_partial_approval_keeps_batch_draft(self):
        """部分确认 ≠ 可入库：整批语义，有一条没过就保持草稿。"""
        result = make_result(points=[make_result().reference_points[0]])
        out = annotate_points(result, FakePrompt(["k"]))
        assert out.approved_count == 1
        assert out.all_approved is True  # 单点全过即可发布

        result2 = make_result(points=make_result().reference_points[:2])
        out2 = annotate_points(result2, FakePrompt(["k", "x"]))
        assert out2.approved_count == 1
        assert out2.all_approved is False

    def test_invalid_input_retries_then_skips(self):
        result = make_result(points=[make_result().reference_points[0]])
        out = annotate_points(result, FakePrompt(["bad", "bad", "bad"]), max_retries=3)
        assert out.reference_points[0].approved is False
        assert out.reference_points[0].history == []  # 无留痕

    def test_eof_stops_review_keeps_draft(self):
        """stdin 不可交互（EOF）→ 停止审核，已处理保留、其余草稿。"""
        result = make_result(points=make_result().reference_points[:2])

        def raising_prompt(text):
            raise EOFError("no input")

        out = annotate_points(result, raising_prompt)
        assert all(not p.approved for p in out.reference_points)

    def test_does_not_mutate_input(self):
        result = make_result(points=[make_result().reference_points[0]])
        annotate_points(result, FakePrompt(["k"]))
        assert result.reference_points[0].approved is False  # 原对象不动

    def test_empty_result_no_prompt(self):
        result = PointDecomposeResult()
        out = annotate_points(result, FakePrompt(["k"]))
        assert out.reference_points == []


# ── 用户题库入库：score_answer 能吃（docs/16 §5 步4 验收）────────────
class TestUserQuestionRoundTrip:
    def test_written_user_json_is_scoreable(self, tmp_path, monkeypatch):
        """人审通过后写入的 user_questions JSON 能被 from_benchmark + score_answer 正常评分。"""
        # 模拟 _save_user_question 的产出（与脚本同格式）
        doc = {
            "id": "user_20260828_01",
            "meta": {"authority": "user", "province": "用户上传", "year": "", "type": "用户上传"},
            "task": {"question": "题", "requirements": "", "material": "材", "max_score": 20},
            "gold": {"reference_points": [
                {"id": "c1", "point": "六尺巷·化解纠纷", "keywords": ["六尺巷", "谦让"], "score": 3,
                 "approved": True, "source": "human_approved"},
                {"id": "c2", "point": "河长制·治水", "keywords": ["河长", "水质"], "score": 4,
                 "approved": True, "source": "human_approved"},
            ]},
        }
        # 写入用户题库目录（monkeypatch 到临时目录，不碰真实 data/）
        from src.shenlun import reflow
        monkeypatch.setattr(reflow, "USER_QUESTIONS_DIR", tmp_path)
        (tmp_path / "user_20260828_01.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

        from src.shenlun.reflow import load_question, list_questions
        loaded = load_question("user_20260828_01")
        assert loaded["meta"]["authority"] == "user"

        points = from_benchmark(loaded["gold"]["reference_points"])
        result = score_answer("村里依托六尺巷的谦让精神化解了纠纷", points)
        assert result.hit_ids == ["c1"]
        assert result.miss_ids == ["c2"]

        # list_questions 同时列出官方 + 用户，带 authority
        monkeypatch.setattr(reflow, "BENCHMARK_DIR", tmp_path)  # 官方目录也指到临时目录避免读真实题库
        listed = list_questions()
        assert any(q["id"] == "user_20260828_01" and q["authority"] == "user" for q in listed)

    def test_load_question_falls_back_to_benchmark(self, tmp_path, monkeypatch):
        """官方金标目录的题照常能加载（平行新增不破坏旧链路）。"""
        from src.shenlun import reflow
        official = {
            "id": "jiangsu_2023_a_1",
            "meta": {"authority": "training", "province": "江苏", "year": 2023, "type": "归纳概括"},
            "task": {"question": "题", "requirements": "", "material": "材", "max_score": 20},
            "gold": {"reference_points": [{"id": "c1", "point": "六尺巷", "keywords": ["六尺巷"], "score": 3}]},
        }
        (tmp_path / "jiangsu_2023_a_1.json").write_text(json.dumps(official, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(reflow, "BENCHMARK_DIR", tmp_path)
        monkeypatch.setattr(reflow, "USER_QUESTIONS_DIR", tmp_path / "user_q")
        from src.shenlun.reflow import load_question, list_questions
        assert load_question("jiangsu_2023_a_1")["meta"]["authority"] == "training"
        assert list_questions()[0]["authority"] == "training"
