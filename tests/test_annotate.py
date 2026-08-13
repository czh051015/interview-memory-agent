"""ISSUES E1：unknown 条目交互补标测试。"""

from datetime import datetime, timedelta

from src.cleaner.schema import KnowledgeItem, ItemStatus
from src.cleaner.annotate import annotate_unknown
from src.memory.mastery import rank


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

    def test_annotate_sets_last_reviewed_at(self):
        """标 fail/partial 时写入 last_reviewed_at 作为衰减起点；x 跳过则不设。"""
        now = datetime(2026, 8, 13, 12, 0, 0)
        items = make_items([ItemStatus.UNKNOWN, ItemStatus.UNKNOWN])
        prompt = FakePrompt(["f", "x"])
        result = annotate_unknown(items, prompt_fn=prompt, now=now)
        assert result[0].status == ItemStatus.FAIL
        assert result[0].last_reviewed_at == now          # 标 fail 设了衰减起点
        assert result[1].last_reviewed_at is None          # x 跳过的不设

    def test_annotated_fail_enters_rank(self):
        """闭环：刚标 fail 的题（0 天）比 3 天前 fail 的题更新鲜，排后面。"""
        now = datetime(2026, 8, 13, 12, 0, 0)
        items = make_items([ItemStatus.UNKNOWN])
        prompt = FakePrompt(["f"])
        [item] = annotate_unknown(items, prompt_fn=prompt, now=now)

        older = KnowledgeItem(
            id="ki_old", question="旧题", status=ItemStatus.FAIL,
            last_reviewed_at=now - timedelta(days=3),
        )
        ranked = rank([older, item], now=now)
        # 3 天前的 fail recency 更高（更该复习），应排前面
        assert ranked[0].id == "ki_old"
