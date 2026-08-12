"""ISSUES E1：unknown 条目交互补标测试。"""

from src.cleaner.schema import KnowledgeItem, ItemStatus
from src.cleaner.annotate import annotate_unknown


def make_items(statuses):
    return [
        KnowledgeItem(id=f"ki_{i:03d}", question=f"题目{i}", status=s, user_note="备注")
        for i, s in enumerate(statuses)
    ]


class FakePrompt:
    """按序列返回输入的 prompt_fn。"""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = 0

    def __call__(self, text):
        self.calls += 1
        return self.answers.pop(0) if self.answers else "x"


class TestAnnotateUnknown:
    def test_f_p_x_mapping(self):
        items = make_items([ItemStatus.UNKNOWN, ItemStatus.UNKNOWN, ItemStatus.UNKNOWN])
        prompt = FakePrompt(["f", "p", "x"])
        result = annotate_unknown(items, prompt_fn=prompt)
        assert result[0].status == ItemStatus.FAIL
        assert result[1].status == ItemStatus.PARTIAL
        assert result[2].status == ItemStatus.UNKNOWN
        assert prompt.calls == 3

    def test_only_unknown_items_are_prompted(self):
        items = make_items([ItemStatus.FAIL, ItemStatus.UNKNOWN])
        prompt = FakePrompt(["f"])
        result = annotate_unknown(items, prompt_fn=prompt)
        assert result[0].status == ItemStatus.FAIL  # 不动
        assert result[1].status == ItemStatus.FAIL
        assert prompt.calls == 1

    def test_invalid_input_retries_then_keeps_unknown(self):
        items = make_items([ItemStatus.UNKNOWN])
        prompt = FakePrompt(["bad", "also_bad", "nope"])  # 3 次非法输入 → 用尽重试
        result = annotate_unknown(items, prompt_fn=prompt, max_retries=3)
        assert result[0].status == ItemStatus.UNKNOWN
        assert prompt.calls == 3

    def test_no_unknown_no_prompt(self):
        items = make_items([ItemStatus.FAIL])
        prompt = FakePrompt(["f"])
        result = annotate_unknown(items, prompt_fn=prompt)
        assert prompt.calls == 0
        assert result[0].status == ItemStatus.FAIL

    def test_does_not_mutate_input(self):
        items = make_items([ItemStatus.UNKNOWN])
        prompt = FakePrompt(["f"])
        result = annotate_unknown(items, prompt_fn=prompt)
        assert items[0].status == ItemStatus.UNKNOWN
        assert result[0].status == ItemStatus.FAIL
