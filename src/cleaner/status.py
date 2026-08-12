"""status 关键词推断 —— LLM 兜底用，非主判断逻辑。

decompose.py 的实际顺序：
1. LLM 先做 status 推断（prompt 里写了规则）
2. LLM 返回 unknown → 本模块关键词兜底，再判一次
3. 本模块也判不出 → 保持 unknown，提示用户手动标注"""

import re
from src.cleaner.schema import ItemStatus

# 规则关键词映射（优先级从上到下）
FAIL_PATTERNS = [
    r"忘了", r"不会", r"没答", r"没答上", r"答不出", r"不知道",
    r"没写出来", r"一坨", r"凉了", r"答得不好", r"答的不好",
    r"没答上来", r"不会做", r"完全没思路", r"想不到了",
    r"悔不当初",  # "以前刷到过，没在意，悔不当初"
]

PARTIAL_PATTERNS = [
    r"答了一半", r"漏了", r"追问没接住", r"补上了", r"答了.*但",
    r"说了.*但", r"答得不全", r"没答全", r"答了一部分",
    r"吟唱八股",  # 能背但没深度
    r"说了SKILL", r"说了\w+和",  # 提了方案名但没细节
    r"根据重要程度", r"看情况",  # 敷衍式回答
    r"老实承认",  # 承认了但没正面答
    r"^[A-Za-z一-鿿]+-[A-Za-z一-鿿]+",  # 关键词列表如"提示词-工具-RAG"
    r"没听懂",  # 面试官没理解
]

PASS_PATTERNS = [
    r"答了", r"过了", r"完整", r"秒了", r"写出来了",
    r"吟唱",  # 能流畅背出八股
    r"双检查锁", r"直接写了",  # 手写代码且写出来了
]


def infer_status(user_note: str) -> ItemStatus:
    """关键词兜底推断 status——只在 LLM 判了 unknown 之后调用。

    优先级：fail > partial > pass
    三个都匹配不到 → unknown（提示用户手动标注）
    """
    if not user_note or not user_note.strip():
        return ItemStatus.UNKNOWN

    note = user_note.strip()

    # 先检查 fail（最高优先级，因为"忘了"最明确）
    for pattern in FAIL_PATTERNS:
        if re.search(pattern, note):
            return ItemStatus.FAIL

    # 再检查 partial
    for pattern in PARTIAL_PATTERNS:
        if re.search(pattern, note):
            return ItemStatus.PARTIAL

    # 最后检查 pass
    for pattern in PASS_PATTERNS:
        if re.search(pattern, note):
            return ItemStatus.PASS

    return ItemStatus.UNKNOWN
