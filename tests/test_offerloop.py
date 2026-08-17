"""offerloop 统一入口测试（mock LLM 路由）。"""

import pytest

import offerloop
from src.cleaner.schema import KnowledgeItem, ItemStatus


@pytest.fixture(autouse=True)
def _no_session_write(monkeypatch):
    """测试不写真实 session 文件，避免污染用户数据目录。"""
    monkeypatch.setattr(offerloop, "_save_session", lambda: None)


class TestRoute:
    def test_route_maps_intent(self, monkeypatch):
        monkeypatch.setattr(
            offerloop, "chat_json",
            lambda *a, **k: {"intent": "mock_interview"},
        )
        intent, filter_, mark = offerloop.route("帮我模拟面试")
        assert intent == "mock_interview"
        assert filter_ == {}
        assert mark == {}

    def test_route_record_review(self, monkeypatch):
        monkeypatch.setattr(
            offerloop, "chat_json",
            lambda *a, **k: {"intent": "record_review"},
        )
        intent, _, _ = offerloop.route("今天面了字节被问了 RAG 没答上")
        assert intent == "record_review"

    def test_route_review_remind(self, monkeypatch):
        monkeypatch.setattr(
            offerloop, "chat_json",
            lambda *a, **k: {"intent": "review_remind"},
        )
        intent, _, _ = offerloop.route("我该复习啥")
        assert intent == "review_remind"

    def test_route_list_items(self, monkeypatch):
        monkeypatch.setattr(
            offerloop, "chat_json",
            lambda *a, **k: {"intent": "list_items"},
        )
        intent, _, _ = offerloop.route("我现在有哪些错题")
        assert intent == "list_items"

    def test_route_extracts_filter(self, monkeypatch):
        monkeypatch.setattr(
            offerloop, "chat_json",
            lambda *a, **k: {
                "intent": "list_items",
                "filter": {"status": "fail", "topic": None, "count_only": False},
            },
        )
        intent, filter_, _ = offerloop.route("fail的题有哪些")
        assert intent == "list_items"
        assert filter_["status"] == "fail"

    def test_route_extracts_mark(self, monkeypatch):
        """LLM 理解「把知识库的1-20加入错题本」→ mark 提取 scope + range。"""
        monkeypatch.setattr(
            offerloop, "chat_json",
            lambda *a, **k: {
                "intent": "mark_fail",
                "mark": {"scope": "unknown", "range": [1, 20]},
            },
        )
        intent, _, mark = offerloop.route("把知识库的1-20加入错题本")
        assert intent == "mark_fail"
        assert mark["scope"] == "unknown"
        assert mark["range"] == [1, 20]

    def test_route_unknown_on_error(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("no llm")

        monkeypatch.setattr(offerloop, "chat_json", boom)
        intent, filter_, mark = offerloop.route("xxx")
        assert intent == "unknown"
        assert filter_ == {}
        assert mark == {}


class TestListItems:
    def test_count_only(self, monkeypatch, capsys):
        items = [KnowledgeItem(id="1", question="q1", status=ItemStatus.FAIL)]

        def fake_search(**kw):
            return items if kw.get("status") == "fail" else []

        monkeypatch.setattr(offerloop.store, "search", fake_search)
        offerloop.do_list_items({"count_only": True})
        out = capsys.readouterr().out
        assert "一共 1 道题" in out

    def test_filter_by_status(self, monkeypatch, capsys):
        items = [
            KnowledgeItem(id="1", question="fail题", status=ItemStatus.FAIL),
            KnowledgeItem(id="2", question="partial题", status=ItemStatus.PARTIAL),
        ]

        def fake_search(**kw):
            return [i for i in items if i.status.value == kw.get("status")]

        monkeypatch.setattr(offerloop.store, "search", fake_search)
        offerloop.do_list_items({"status": "fail"})
        out = capsys.readouterr().out
        assert "fail题" in out
        assert "partial题" not in out

    def test_filter_no_match_helpful(self, monkeypatch, capsys):
        """过滤无匹配：明确拒绝 + 列出可用 topic + 给建议。"""
        items = [
            KnowledgeItem(id="1", question="线程池", topic="线程池原理", status=ItemStatus.FAIL),
        ]

        def fake_search(**kw):
            if kw.get("query"):
                return []  # 语义检索：模拟没找到 rag 相关
            return [i for i in items if i.status.value == kw.get("status")]

        monkeypatch.setattr(offerloop.store, "search", fake_search)
        offerloop.do_list_items({"topic": "rag"})
        out = capsys.readouterr().out
        assert "没有匹配" in out
        assert "线程池原理" in out  # 列出可用主题
        assert "fail 的题" in out  # 给替代建议


class TestMark:
    def test_parse_mark_range(self):
        assert offerloop._parse_mark_range("第 3 题不会") == (3, 3)
        assert offerloop._parse_mark_range("第10题会了") == (10, 10)
        assert offerloop._parse_mark_range("1-20道加入错题") == (1, 20)
        assert offerloop._parse_mark_range("第1到20题不会") == (1, 20)
        assert offerloop._parse_mark_range("3~5题会了") == (3, 5)
        assert offerloop._parse_mark_range("你好") is None

    def test_do_mark_fail(self, monkeypatch, capsys):
        """「第 N 题不会」→ 从最近列表找到题，标 fail。"""
        items = [
            KnowledgeItem(id="1", question="题一", status=ItemStatus.UNKNOWN),
            KnowledgeItem(id="2", question="题二", status=ItemStatus.UNKNOWN),
        ]
        monkeypatch.setattr(offerloop, "_last_listed", items)
        stored = []
        monkeypatch.setattr(offerloop.store, "store_items", lambda its: stored.extend(its))

        offerloop.do_mark("第 2 题不会", {}, ItemStatus.FAIL)
        assert stored[0].status == ItemStatus.FAIL
        assert stored[0].question == "题二"
        out = capsys.readouterr().out
        assert "题二" in out

    def test_do_mark_out_of_range(self, monkeypatch, capsys):
        """编号越界 → 提示，不标。"""
        monkeypatch.setattr(offerloop, "_last_listed", [KnowledgeItem(id="1", question="题一")])
        monkeypatch.setattr(offerloop.store, "store_items", lambda its: None)

        offerloop.do_mark("第 9 题不会", {}, ItemStatus.FAIL)
        out = capsys.readouterr().out
        assert "没有第 9 题" in out

    def test_do_mark_range(self, monkeypatch, capsys):
        """「1-3道加入错题」→ 批量标 fail。"""
        items = [
            KnowledgeItem(id="1", question="题一", status=ItemStatus.UNKNOWN),
            KnowledgeItem(id="2", question="题二", status=ItemStatus.UNKNOWN),
            KnowledgeItem(id="3", question="题三", status=ItemStatus.UNKNOWN),
            KnowledgeItem(id="4", question="题四", status=ItemStatus.UNKNOWN),
        ]
        monkeypatch.setattr(offerloop, "_last_listed", items)
        stored = []
        monkeypatch.setattr(offerloop.store, "store_items", lambda its: stored.extend(its))

        offerloop.do_mark("1-3道加入错题", {}, ItemStatus.FAIL)
        assert len(stored) == 3
        assert all(it.status == ItemStatus.FAIL for it in stored)
        out = capsys.readouterr().out
        assert "共 3 道" in out

    def test_do_mark_scope(self, monkeypatch, capsys):
        """「知识库的1-2加入错题」→ scope=unknown 时按知识库查询，不依赖上次列表。"""
        kb = [
            KnowledgeItem(id="k1", question="知识库题一", status=ItemStatus.UNKNOWN),
            KnowledgeItem(id="k2", question="知识库题二", status=ItemStatus.UNKNOWN),
        ]
        stored = []
        monkeypatch.setattr(
            offerloop.store, "search",
            lambda **kw: kb if kw.get("status") == "unknown" else [],
        )
        monkeypatch.setattr(offerloop.store, "store_items", lambda its: stored.extend(its))
        # 故意把 _last_listed 设成空，验证走的是 scope 查询而不是上次列表
        monkeypatch.setattr(offerloop, "_last_listed", [])

        offerloop.do_mark("把知识库的1-2加入错题本", {"scope": "unknown", "range": [1, 2]}, ItemStatus.FAIL)
        assert len(stored) == 2
        assert all(it.status == ItemStatus.FAIL for it in stored)
        out = capsys.readouterr().out
        assert "知识库里的第 1-2 题" in out


class TestFastRoute:
    """规则 fast-path：零歧义高频命令走规则短路（LLM 挂了的兜底），模糊表达回落 LLM。"""

    def test_quit(self):
        assert offerloop._fast_route("退出") == ("quit", {}, {})
        assert offerloop._fast_route("quit") == ("quit", {}, {})

    def test_zero_ambiguity_commands(self):
        """零歧义查看/动作命令走规则，不依赖 LLM。"""
        assert offerloop._fast_route("看错题") == ("list_items", {"status": "fail"}, {})
        assert offerloop._fast_route("看知识库") == ("list_items", {"status": "unknown"}, {})
        assert offerloop._fast_route("看一下面试复盘")[0] == "show_review"
        assert offerloop._fast_route("该复习啥")[0] == "review_remind"
        assert offerloop._fast_route("帮我模拟面试")[0] == "mock_interview"

    def test_falls_back_to_llm(self):
        """带作用域/指代/上下文的表达，规则不拦，交给 LLM。"""
        assert offerloop._fast_route("把知识库的1-20加入错题本") == (None, None, None)
        assert offerloop._fast_route("错题的前5题标成不会") == (None, None, None)
        assert offerloop._fast_route("今天面了字节被问了RAG没答上") == (None, None, None)
        assert offerloop._fast_route("第3题会了") == (None, None, None)
