"""脏标答规则预检 —— 在 decompose 之前用确定性规则识别劣质标准答案（docs/19 §4.2 的确定性兜底）。

背景（docs/实现说明/02 未达标项）：LLM 对 SHENLUN_DECOMPOSE_SYSTEM 的「残缺/过简红线」服从不稳定
（同一抄错样本四连跑：预警✓ → 预警✓ → 无预警 → 无预警），dirty_robustness==1.0 依赖 LLM 措辞不可达成。
本模块在 decompose 之前用规则识别脏标答，命中即提示人审「疑似脏标答」，绕过 LLM 服从问题。

规则（2026-08-29 按 eval/dirty_gold.json 6 个脏样本 + benchmark/data 36 个 good 标答实测标定）：
  1. 抄错/乱码：文本含「×」字符（复制粘贴乱码的典型标记；36 个正常标答 0 出现）
  2. 口语化：强口语词「我觉得 / 挺有意思 / 嘛」（正常申论标答为正式书面语，36 个 0 出现）
  3. 过简/残缺：文本长度 < 120 字（good 标答 min 196 字，dirty 残缺/口语化样本 ≤70 字，120 留安全边界）

任一命中 → dirty=True + signals。预检只提示不拦截：命中结果随 decompose warnings 给人审，
最终由人审闸门（annotate_points）决定是否换标答。
"""

# 口语化强标记词：独立成词出现才算（避免「嘛」误伤 "嘛" 罕见用字场景已实测 0 误报，词表刻意收窄）
_COLLOQUIAL_WORDS = ("我觉得", "挺有意思", "嘛")

# good 标答长度下界（实测 min 196）与脏样本长度上界（实测 max 70）之间的安全线
_TOO_SHORT_CHARS = 120

# 抄错/乱码：× 为复制粘贴乱码的典型残字符
_GARBLED_CHAR = "×"


def detect_dirty(text: str) -> dict:
    """确定性规则预检：text 是否为疑似脏标答（残缺/口语化/抄错）。

    Args:
        text: 用户提供的标准答案全文

    Returns:
        {"dirty": bool, "signals": [str, ...], "length": int}
        signals 按规则命中顺序列出（"含×乱码符号" / "口语化标记" / "过简(长N字)"），
        未命中时 signals 为空列表。
    """
    text = str(text or "")
    signals: list[str] = []

    if _GARBLED_CHAR in text:
        signals.append("含×乱码符号")

    if any(w in text for w in _COLLOQUIAL_WORDS):
        signals.append(f"口语化标记（{_COLLOQUIAL_WORDS} 命中）")

    if len(text) < _TOO_SHORT_CHARS:
        signals.append(f"过简（仅 {len(text)} 字）")

    return {"dirty": bool(signals), "signals": signals, "length": len(text)}
