"""annotate_jingyan CLI 测试。"""

from unittest.mock import patch

from src.cleaner.schema import KnowledgeItem, ItemStatus, ItemSource


class FakePrompt:
    def __init__(self, answers):
        self._answers = list(answers)

    def __call__(self, prompt=""):
        if not self._answers:
            raise EOFError
        return self._answers.pop(0)


def make_item(qid, question):
    return KnowledgeItem(
        id=qid, question=question, topic="",
        source=ItemSource.PUBLIC_JINGYAN, status=ItemStatus.UNKNOWN,
    )


def test_only_writes_changed_items():
    """只写回标了 fail/partial 的条目，x 跳过的保持 unknown 不写回。"""
    items = [
        make_item("jy_1", "Chroma vs Milvus 怎么选"),
        make_item("jy_2", "RRF 重排序原理"),
        make_item("jy_3", "线程池参数"),
    ]
    prompt = FakePrompt(["f", "x", "p"])  # 标1=fail, 2跳过, 3=partial

    with patch("src.memory.knowledge_store.search", return_value=items), \
         patch("src.memory.knowledge_store.store_items") as mock_store, \
         patch("builtins.input", prompt):
        import annotate_jingyan
        rc = annotate_jingyan.main([])

    assert rc == 0
    mock_store.assert_called_once()
    written = mock_store.call_args[0][0]
    assert len(written) == 2  # 只写回 2 条变化
    assert {i.status for i in written} == {ItemStatus.FAIL, ItemStatus.PARTIAL}


def test_no_unknown_returns_without_write():
    """库里没有待标面经题时，不写库，正常返回。"""
    with patch("src.memory.knowledge_store.search", return_value=[]), \
         patch("src.memory.knowledge_store.store_items") as mock_store:
        import annotate_jingyan
        rc = annotate_jingyan.main([])

    assert rc == 0
    mock_store.assert_not_called()
