"""对话端点 —— 复用 offerloop 的意图路由，执行「读」类意图。

第一版：接「读」类（看提醒 / 看错题 / 看复盘 / 体检），写类（记题/标错/模拟面试）后续接。
路由逻辑：先规则 fast-path（零歧义命令不调 LLM），未命中走 LLM 语义路由（复用 offerloop.route）。
"""
from fastapi import APIRouter
from pydantic import BaseModel

from offerloop import route, _fast_route
from src.memory import knowledge_store as store
from src.memory.mastery import layer, _elapsed_days
from src.cleaner.schema import utcnow, ItemStatus, not_info

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    space: str = "default"  # 记忆空间（严格隔离：只在该空间内读/标）


class ChatResponse(BaseModel):
    reply: str
    intent: str = ""
    cards: list = []  # 预留：提醒分层 / 复习 / 报告卡片


# ── 读类意图执行（逻辑照抄 offerloop.do_*，print 改 return）──
def _remind_text(space: str) -> str:
    now = utcnow()
    items = store.search(status="fail", space=space, top_k=1000) + store.search(
        status="partial", space=space, top_k=1000
    )
    items = not_info(items)
    if not items:
        return "错题本还是空的，先去记几道题。"

    red, yellow, _ = layer(items, now=now)

    if not red and not yellow:
        return "都掌握得不错，暂时没有要复习的。"
    lines = []
    if red:
        lines.append(f"🔴 快忘了（{len(red)} 道，优先看）：")
        for it in red:
            days = int(_elapsed_days(it, now))
            lines.append(f"   [{it.status.value.upper()}] {it.question}（{days} 天没复习）")
    if yellow:
        lines.append(f"🟡 该看看（{len(yellow)} 道）：")
        for it in yellow:
            days = int(_elapsed_days(it, now))
            lines.append(f"   [{it.status.value.upper()}] {it.question}（{days} 天没复习）")
    return "\n".join(lines)


def _list_text(filter_: dict, space: str) -> str:
    status = (filter_ or {}).get("status") or "fail"
    items = not_info(store.search(status=status, space=space, top_k=1000))
    if not items:
        return f"没有 {status} 状态的题。"
    scope = "错题" if status == "fail" else "知识库"
    lines = [f"共 {len(items)} 道{scope}："]
    for i, it in enumerate(items[:20], 1):
        tag = f"（{it.topic}）" if it.topic else ""
        lines.append(f"   {i}. {it.question} {tag}")
    if len(items) > 20:
        lines.append(f"   ……还有 {len(items) - 20} 道")
    return "\n".join(lines)


def _review_text() -> str:
    from src.config import space_dir
    p = space_dir() / "last_review.md"
    if not p.exists():
        return "还没有面试复盘。先「模拟面试」跑一场。"
    return p.read_text(encoding="utf-8")


def _maintenance_text(space: str) -> str:
    s = store.get_stats(space=space)
    return (
        f"总数 {s['total']} 道：❌ 错题 {s['by_status']['fail']} · "
        f"📚 知识库 {s['by_status']['unknown']} · ✅ 已会 {s['by_status']['pass']}"
    )


def _mark_text(mark: dict, status: ItemStatus, space: str) -> str:
    """Web 版标注：只支持带作用域的（「把知识库的第N题标成不会」）。

    CLI 的 mark 依赖 _last_listed 会话上下文，Web 无状态 → 不带 scope 时引导去页面。
    space：只在当前空间内检索可标条目（严格隔离）。
    """
    from app.api.items import mark_item

    scope = (mark or {}).get("scope")
    rng = (mark or {}).get("range")
    if scope not in ("fail", "unknown") or not rng or not isinstance(rng, list):
        return "Web 版不支持「第 N 题」这种依赖上次列出的标法——直接去错题本页点按钮标注，或说「把知识库的第N题标成不会」这类带作用域的。"

    try:
        start, end = int(rng[0]), int(rng[1])
    except (TypeError, ValueError):
        return "没听懂第几题，说「把知识库的第 3 题标成不会」这种。"

    items = store.search(status=scope, space=space, top_k=1000)
    items = not_info(items)  # 与 CLI annotate 一致：只标知识点，过滤 info 行为题
    if not items:
        return "没有可标的题——错题本还是空的，或知识库没有待标的题。"
    if start < 1 or start > len(items):
        return f"只有 {len(items)} 道题，没有第 {start} 题。"
    if end > len(items):
        end = len(items)
    if start > end:
        return f"只有 {len(items)} 道题，没有第 {start} 题。"

    targets = items[start - 1:end]
    updated = [mark_item(it, status) for it in targets]
    store.store_items(updated)
    label = "错题（进提醒池）" if status == ItemStatus.FAIL else "会了（退出提醒池）"
    if len(targets) == 1:
        return f"已把「{targets[0].question}」标为 {label}。"
    return f"已把第 {start}-{end} 题（共 {len(targets)} 道）标为 {label}。"


def _execute(intent: str, text: str, filter_: dict, mark: dict, space: str) -> str:
    if intent == "review_remind":
        return _remind_text(space)
    if intent == "list_items":
        return _list_text(filter_, space)
    if intent == "show_review":
        return _review_text()
    if intent == "maintenance":
        return _maintenance_text(space)
    if intent in ("record_review", "batch_record"):
        return "「记错题」用页面的粘贴→拆解→确认更顺手（顶部「＋ 记错题」）。"
    if intent == "mock_interview":
        return "「模拟面试」在 /mock-interview 页面，跑一场会自动标错题并更新掌握度。"
    if intent in ("mark_fail", "mark_pass"):
        status = ItemStatus.FAIL if intent == "mark_fail" else ItemStatus.PASS
        return _mark_text(mark, status, space)
    return "没太听懂。试试：记一道错题 / 看错题 / 我该复习啥 / 整理一下。"


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    intent, filter_, mark = _fast_route(req.message)
    if intent is None:
        intent, filter_, mark = route(req.message, "")
    reply = _execute(intent, req.message, filter_, mark, req.space)
    return ChatResponse(reply=reply, intent=intent)
