"""记忆管家 Agent —— 维护候选人记忆、按遗忘安排复习（run_remind 的 Agent 化）。

设计：LLM 做「语义活」（为什么提醒、复习顺序、薄弱主题、维护建议），
系统做「确定性活」（gap 计算、分层、发送、日志）——沿「LLM 语义活 + 系统确定性约束」原则。

工具集（全部纯函数，可测）：
  · read_memory_state(space)    → 遗忘分层快照（红/黄/绿 + gap/days/行为标签）
  · read_review_history(space)  → review_log 最近复习轨迹
  · send_notify(title, body)    → 桌面提醒（复用 run_remind._notify_windows）

Agent 循环：
  读状态 → LLM 生成 {focus_note, plan, focus_topics} → 输出/发送
  LLM 失败 → 回退规则版（gap≥0.5 直接提醒），记忆管家不会因为 LLM 挂掉而失效。

与面试官协同：读写同一个错题本（隐式，无 Agent 间通信）。
面试官出题靠它：get_weak_questions 的输入（fail/partial + rank 排序）= 记忆管家的状态产物。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from src.memory import knowledge_store as store
from src.memory.mastery import rank, effective_mastery, _elapsed_days
from src.cleaner.schema import utcnow
from src.llm import chat_json
from src.config import space_dir

logger = logging.getLogger(__name__)

# 分层阈值（与 run_remind 一致）
GAP_RED = 0.5    # 快忘了
GAP_YELLOW = 0.2  # 该看看

_KEEPER_PROMPT = (
    "你是 OfferLoop 的记忆管家，负责维护候选人的面试记忆、安排复习。你会收到："
    "候选人的记忆状态快照（按遗忘程度分层的错题：题目、掌握度、gap、距离上次复习天数、行为标签、状态）。\n"
    "任务：规划今天的复习，并给出一段记忆维护建议。只输出 JSON：\n"
    '{"focus_note": "一句话记忆维护建议（如：线程池和缓存两处缺口最大，优先补）", '
    '"plan": [{"question": "题目原文", "why": "为什么今天提醒它（引用 gap/天数/行为标签）"}], '
    '"focus_topics": ["薄弱主题1", "薄弱主题2"]}\n'
    "要求：\n"
    "- plan 最多列 5 道，按紧急度排序，优先 gap 大的和带行为标签的（行为标签说明是稳定弱点）；\n"
    "- focus_topics 从 plan 的题目里提炼 1-3 个主题（如 线程池 / RAG / Agent记忆），供面试官出题参考；\n"
    "- 只基于快照里的事实，不要臆造掌握度或日期。"
)


@dataclass
class MemorySnapshot:
    """记忆状态快照：遗忘分层 + 每道题的关键事实。"""
    red: list[dict] = field(default_factory=list)   # 快忘了
    yellow: list[dict] = field(default_factory=list)  # 该看看
    green: list[dict] = field(default_factory=list)  # 刚看过
    total_weak: int = 0

    def to_prompt_text(self) -> str:
        parts = []
        for tier, label in (("red", "🔴 快忘了"), ("yellow", "🟡 该看看"), ("green", "✅ 刚看过")):
            items = getattr(self, {"red": "red", "yellow": "yellow", "green": "green"}[tier])
            if not items:
                continue
            parts.append(f"{label}（{len(items)} 道）：")
            for it in items:
                parts.append(
                    f"  - [{it['status'].upper()}] {it['question']}"
                    f"（掌握度 {it['mastery']}，gap {it['gap']}，{it['days']} 天没复习"
                    + (f"，行为：{','.join(it['behavior_tags'])}" if it["behavior_tags"] else "")
                    + "）"
                )
        return "\n".join(parts) if parts else "（当前没有需要复习的错题）"


def read_memory_state(space: str | None = None) -> MemorySnapshot:
    """工具 1：读错题本 → 遗忘分层快照。确定性，不调 LLM。"""
    now = utcnow()
    space = space or "default"
    items = (
        store.search(status="fail", space=space, top_k=1000)
        + store.search(status="partial", space=space, top_k=1000)
    )
    snap = MemorySnapshot(total_weak=len(items))
    for it in rank(items, now=now):
        em = effective_mastery(it, now)
        gap = round(1.0 - em, 3)
        row = {
            "id": it.id,
            "question": it.question,
            "status": it.status.value,
            "mastery": round(em, 3),
            "gap": gap,
            "days": int(_elapsed_days(it, now)),
            "behavior_tags": list(it.behavior_tags or []),
        }
        if gap >= GAP_RED:
            snap.red.append(row)
        elif gap >= GAP_YELLOW:
            snap.yellow.append(row)
        else:
            snap.green.append(row)
    return snap


def read_review_history(space: str | None = None, limit: int = 10) -> list[dict]:
    """工具 2：读 review_log 最近复习轨迹。只读不写。"""
    path = space_dir() / "review_log.jsonl"
    if not path.exists():
        return []
    events = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return events[-limit:]


def _notify_windows(title: str, body: str) -> bool:
    """工具 3：桌面提醒（复用 run_remind 的实现，避免循环依赖则内联）。"""
    import base64
    import subprocess
    from xml.sax.saxutils import escape as _xml_escape

    _TOAST_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
    xml = (
        '<toast><visual><binding template="ToastText02">'
        f'<text id="1">{_xml_escape(title)}</text>'
        f'<text id="2">{_xml_escape(body)}</text>'
        "</binding></visual></toast>"
    )
    b64 = base64.b64encode(xml.encode("utf-8")).decode("ascii")
    ps = (
        f"$b64 = '{b64}'\n"
        "$xmlStr = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($b64))\n"
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null\n"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime] | Out-Null\n"
        "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument\n"
        "$xml.LoadXml($xmlStr)\n"
        "$toast = New-Object Windows.UI.Notifications.ToastNotification $xml\n"
        f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{_TOAST_APP_ID}').Show($toast)\n"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
            capture_output=True, timeout=30,
        )
        if r.returncode != 0:
            err = (r.stderr or b"").decode("utf-8", errors="ignore").strip()
            logger.warning("toast 失败（exit %s）: %s", r.returncode, err[:200])
        return r.returncode == 0
    except Exception as e:
        logger.warning("toast 异常: %s", e)
        return False


def plan_review(snap: MemorySnapshot, history: list[dict]) -> dict:
    """Agent 决策：LLM 读快照 → 输出 {focus_note, plan, focus_topics}。失败回退规则版。"""
    user_prompt = (
        f"## 记忆状态快照\n{snap.to_prompt_text()}\n\n"
        f"## 最近复习轨迹（review_log 尾部 {len(history)} 条）\n"
        + (json.dumps(history, ensure_ascii=False) if history else "（无）")
    )
    try:
        data = chat_json(_KEEPER_PROMPT, user_prompt, max_tokens=2048)
        plan = data.get("plan", [])
        if not isinstance(plan, list):
            plan = []
        return {
            "focus_note": str(data.get("focus_note", "")),
            "plan": [
                {"question": str(p.get("question", "")), "why": str(p.get("why", ""))}
                for p in plan[:5]
            ],
            "focus_topics": [str(t) for t in (data.get("focus_topics") or [])][:3],
        }
    except Exception as e:
        logger.warning("记忆管家 LLM 规划失败，回退规则版：%s", e)
        return _rule_fallback(snap)


def _rule_fallback(snap: MemorySnapshot) -> dict:
    """规则回退：gap≥0.5 的直接列出来（现在的行为），不依赖 LLM。"""
    return {
        "focus_note": f"{len(snap.red)} 道题快忘了，优先复习。",
        "plan": [
            {"question": it["question"], "why": f"gap {it['gap']}，{it['days']} 天没复习"}
            for it in snap.red[:5]
        ],
        "focus_topics": [],
    }


def run(space: str | None = None, *, notify: bool = False) -> dict:
    """记忆管家主循环：读状态 → LLM 规划 → 输出/发送。返回规划结果。

    notify=True 时桌面提醒；否则打印。任何一步失败都回退规则版，不抛异常。
    """
    space = space or "default"
    snap = read_memory_state(space)
    history = read_review_history(space)
    plan = plan_review(snap, history)

    title = f"OfferLoop 记忆管家 · {len(snap.red)} 道题快忘了"
    lines = [plan.get("focus_note") or ""]
    for p in plan.get("plan", []):
        lines.append(f"· {p['question'][:40]}（{p['why'][:40]}）")
    if plan.get("focus_topics"):
        lines.append("🎯 薄弱主题：" + "、".join(plan["focus_topics"]))
    body = "\n".join(x for x in lines if x) or "（今天没有要提醒的题）"

    if notify:
        if snap.red:
            _notify_windows(title, body)
        else:
            return plan  # 没有快忘的题，静默
    else:
        print(f"\n🧠 记忆管家（{space}）")
        print(f"   {plan.get('focus_note') or '（无建议）'}")
        for p in plan.get("plan", []):
            print(f"   - {p['question'][:50]}")
            if p.get("why"):
                print(f"     因为：{p['why'][:60]}")
        if plan.get("focus_topics"):
            print(f"   🎯 薄弱主题：{'、'.join(plan['focus_topics'])}")
    return plan


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    sp = None
    if "--space" in sys.argv:
        i = sys.argv.index("--space")
        if i + 1 < len(sys.argv):
            sp = sys.argv[i + 1]
    run(sp, notify="--notify" in sys.argv)
