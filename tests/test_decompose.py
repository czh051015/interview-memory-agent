"""面经消化 Agent 单元测试。"""

import pytest
from src.cleaner.status import infer_status
from src.cleaner.decompose import has_placeholder
from src.cleaner.schema import ItemStatus


class TestHasPlaceholder:
    """ISSUES E2：占位符检测真值表。"""

    def test_matches_placeholders(self):
        assert has_placeholder("volatile的***是什么？")
        assert has_placeholder("答案是...，略")
        assert has_placeholder("题目里有个略字")

    def test_plain_text_no_match(self):
        assert not has_placeholder("volatile关键字的作用？")
        assert not has_placeholder("RRF原理")
        assert not has_placeholder("")

    def test_single_asterisk_no_match(self):
        # 单个 * 可能是强调符，不算占位符
        assert not has_placeholder("a * b 的运算")


class TestStatusInference:
    """status 推断规则测试。"""

    def test_fail_forgot(self):
        assert infer_status("忘了") == ItemStatus.FAIL
        assert infer_status("RRF原理忘了") == ItemStatus.FAIL

    def test_fail_cant(self):
        assert infer_status("不会") == ItemStatus.FAIL
        assert infer_status("完全没思路") == ItemStatus.FAIL
        assert infer_status("没答上来") == ItemStatus.FAIL

    def test_fail_mess(self):
        assert infer_status("答得一坨") == ItemStatus.FAIL
        assert infer_status("答得不好") == ItemStatus.FAIL
        assert infer_status("没写出来") == ItemStatus.FAIL

    def test_fail_cant_think(self):
        assert infer_status("想不到了") == ItemStatus.FAIL

    def test_fail_regret(self):
        assert infer_status("以前刷到过没在意，悔不当初") == ItemStatus.FAIL

    def test_partial_half(self):
        assert infer_status("答了一半") == ItemStatus.PARTIAL
        assert infer_status("答了但漏了追问") == ItemStatus.PARTIAL

    def test_partial_skill(self):
        assert infer_status("说了SKILL") == ItemStatus.PARTIAL
        assert infer_status("说了SKILL和压缩") == ItemStatus.PARTIAL

    def test_partial_vague(self):
        assert infer_status("答根据重要程度处理") == ItemStatus.PARTIAL
        assert infer_status("老实承认") == ItemStatus.PARTIAL

    def test_partial_keywords(self):
        assert infer_status("提示词-工具-RAG-微调") == ItemStatus.PARTIAL

    def test_partial_recite_shallow(self):
        assert infer_status("吟唱八股") == ItemStatus.PARTIAL

    def test_pass_answered(self):
        assert infer_status("答了") == ItemStatus.PASS
        assert infer_status("秒了") == ItemStatus.PASS
        assert infer_status("写出来了") == ItemStatus.PASS
        assert infer_status("直接写了") == ItemStatus.PASS

    def test_pass_recite(self):
        assert infer_status("开始吟唱") == ItemStatus.PASS

    def test_pass_code(self):
        assert infer_status("写的双检查锁") == ItemStatus.PASS

    def test_unknown_empty(self):
        assert infer_status("") == ItemStatus.UNKNOWN
        assert infer_status("   ") == ItemStatus.UNKNOWN

    def test_unknown_ambiguous(self):
        # 纯粹的描述性备注，没有表达掌握程度
        assert infer_status("面试官追问了实现细节") == ItemStatus.UNKNOWN
        assert infer_status("聊了20分钟") == ItemStatus.UNKNOWN


class TestStatusPriority:
    """status 推断优先级：fail > partial > pass。"""

    def test_fail_over_partial(self):
        # "忘了" 更接近 fail
        assert infer_status("答了一半但忘了") == ItemStatus.FAIL

    def test_partial_over_pass(self):
        # "答了但漏了" → partial
        assert infer_status("答了但漏了关键点") == ItemStatus.PARTIAL
