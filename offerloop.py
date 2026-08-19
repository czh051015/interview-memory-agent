"""OfferLoop 统一入口 —— 一条命令，说人话，Agent 自动路由。

用法：
  python offerloop.py

你说一句话，Agent 判断意图并路由到对应模块：
  「今天面了字节，被问了 RAG 混合检索，没答上」→ 记错题
  「帮我模拟面试」→ 面试官追问
  「我该复习啥」→ 按遗忘分层提醒
  「退出 / quit」→ 退出
"""
import sys
import re
import json
import logging
import os
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

from src.config import DATA_DIR, space_dir
from src.llm import chat_json
from src.cleaner.decompose import decompose
from src.cleaner.schema import ItemStatus, KnowledgeItem, utcnow
from src.memory import knowledge_store as store
from src.memory.mastery import rank, effective_mastery, _elapsed_days
import run_mock_interview as mock

# ── AgentOps 埋点（可选接入：设置 AGENTOPS_INGEST_URL 且 agentops 可导入时启用）──
# 初始化放 main() 内（__main__ 保护）：避免 instrument 扫描「offerloop」模块时
# 重新执行模块级代码导致重复初始化（__main__ vs offerloop 双模块问题）。
_ao = None  # 接入成功 = (tracer, instrumentation)

try:
    from sdk.instrument import session_snapshot_hash  # 无 agentops 环境也可导入
except ImportError:  # pragma: no cover
    session_snapshot_hash = None


def _init_ao() -> None:
    """可选接入 AgentOps 埋点（幂等；失败仅告警，不阻塞主流程）。"""
    global _ao
    if _ao is not None or not os.getenv("AGENTOPS_INGEST_URL") or session_snapshot_hash is None:
        return
    try:
        from sdk import init_offerloop

        _ao = init_offerloop(
            ingest_url=os.getenv("AGENTOPS_INGEST_URL"),
            offerloop_root=str(Path(__file__).parent),
            agent="offerloop",
        )
        if _ao:
            logging.info("AgentOps 埋点已启用（ingest=%s）", os.getenv("AGENTOPS_INGEST_URL"))
    except Exception as _e:
        logging.warning("AgentOps 埋点未启用：%s", _e)

# ── 意图路由 ──
_ROUTER_PROMPT = (
    "你是 OfferLoop 的入口路由。理解用户这句话的真实意图，输出结构化 JSON。只输出 JSON，不要任何解释文字。\n"
    '{"intent": "...", "filter": {...}, "mark": {"scope": ..., "range": ...}}\n'
    "\n"
    "## intent 取值（10 选 1）\n"
    "- record_review：用户在描述一次面试经历/复盘（被问了什么题、答得怎么样）。触发：公司/岗位 + 被问 + 具体题。\n"
    "- batch_record：用户要批量粘贴/导入一大段面经（多道题一起）。触发：「批量」「粘贴」「导入」。\n"
    "- mock_interview：用户要练习/模拟面试/练一练/考考我。\n"
    "- list_items：用户要查看/列出/查/问有哪些题。触发：「看」「有哪些」「多少」「查」。\n"
    "- review_remind：用户想知道该复习什么、有什么快忘了、该看什么。\n"
    "- mark_fail：用户要把某些题标成错题/不会/fail。\n"
    "- mark_pass：用户要把某些题标成会了/pass/已掌握。\n"
    "- maintenance：用户要整理/体检/查重复/清理数据。\n"
    "- quit：用户要退出/再见/结束。\n"
    "- unknown：以上都不是或含糊不清。\n"
    "\n"
    "## 易混淆边界（务必区分，含「错题」「面」的多义）\n"
    "- 「看错题」= list_items（查看）；「把X标成错题」「第N题不会」= mark_fail（标记）；「今天面了X被问了Y」= record_review（记录）。三者都含「错题」，动作不同：看 / 标 / 记。\n"
    "- 「帮我模拟面试」= mock_interview（练）；「今天面了字节」= record_review（记刚发生的）。\n"
    "- 「我该复习啥」= review_remind（带遗忘状态）；「看错题」= list_items（纯列出）。\n"
    "- 用户输入极短、无宾语、依赖上下文（如「看一下」「还有吗」「继续」「再看」「然后呢」），必须结合「最近上下文」判断：上下文提到「刚标错题」→ 多半要看错题；提到「刚列题」→ 多半要再看/继续。\n"
    "\n"
    "## mark 字段（仅 mark_fail / mark_pass 需要，其他 intent 填 {}）\n"
    "- scope：题的作用域。说「知识库的」「没标过的」「知识库里」→ \"unknown\"；说「错题的」「不会的」→ \"fail\"；没指定 → null。\n"
    "- 特别：mark_fail 且说「加入错题本」「标成错题」但没提作用域时，默认 scope=\"unknown\"（加入错题本的对象通常是知识库里还没标的题）。\n"
    "- range：编号范围 [起始, 结束]。「第3题」「3题」→ [3,3]；「1-20」「第1到20题」「前20题」→ [1,20]；「全部」「所有」「都」→ [1,9999]；没提编号 → null。\n"
    "\n"
    "## filter 字段（仅 list_items 需要，其他 intent 填 {}）\n"
    "- status：「看错题」「不会的」「fail的」→ \"fail\"；「看知识库」「没标过的」→ \"unknown\"。\n"
    "- topic：「跟X相关的」「X的题」→ \"X\"。\n"
    "- type：「八股文」→\"八股文\"，「项目题」→\"项目\"，「场景题」→\"场景\"，「行为题」→\"行为\"。\n"
    "- count_only：「一共多少」「几个」「几道」→ true。\n"
    "\n"
    "## few-shot 示例（严格照此格式输出）\n"
    '输入：把知识库的1-20加入错题本\n输出：{"intent":"mark_fail","filter":{},"mark":{"scope":"unknown","range":[1,20]}}\n'
    '输入：把1-20加入错题本\n输出：{"intent":"mark_fail","filter":{},"mark":{"scope":"unknown","range":[1,20]}}\n'
    '输入：第3题会了\n输出：{"intent":"mark_pass","filter":{},"mark":{"scope":null,"range":[3,3]}}\n'
    '输入：错题的前5题标成不会\n输出：{"intent":"mark_fail","filter":{},"mark":{"scope":"fail","range":[1,5]}}\n'
    '输入：把知识库所有题标成错题\n输出：{"intent":"mark_fail","filter":{},"mark":{"scope":"unknown","range":[1,9999]}}\n'
    '输入：今天面了字节，被问了RAG混合检索，没答上\n输出：{"intent":"record_review","filter":{},"mark":{}}\n'
    '输入：批量加面经\n输出：{"intent":"batch_record","filter":{},"mark":{}}\n'
    '输入：帮我模拟面试\n输出：{"intent":"mock_interview","filter":{},"mark":{}}\n'
    '输入：看错题\n输出：{"intent":"list_items","filter":{"status":"fail"},"mark":{}}\n'
    '输入：看知识库\n输出：{"intent":"list_items","filter":{"status":"unknown"},"mark":{}}\n'
    '输入：一共有多少题\n输出：{"intent":"list_items","filter":{"count_only":true},"mark":{}}\n'
    '输入：有哪些八股文\n输出：{"intent":"list_items","filter":{"type":"八股文"},"mark":{}}\n'
    '输入：跟RAG相关的题有哪些\n输出：{"intent":"list_items","filter":{"topic":"RAG"},"mark":{}}\n'
    '输入：我该复习啥\n输出：{"intent":"review_remind","filter":{},"mark":{}}\n'
    '输入：整理一下\n输出：{"intent":"maintenance","filter":{},"mark":{}}\n'
    '输入：看一下\n最近上下文：刚把知识库第1-20题标为错题\n输出：{"intent":"list_items","filter":{"status":"fail"},"mark":{}}\n'
    '输入：退出\n输出：{"intent":"quit","filter":{},"mark":{}}\n'
)


def route(text: str, context: str = "") -> tuple[str, dict, dict]:
    """判断意图 + 过滤条件 + 标记参数。失败兜底 (unknown, {}, {})。

    context 是最近一次操作的描述（短期记忆），用于消歧「看一下」「还有吗」这类无宾语表达。
    """
    try:
        user_msg = f"用户说：{text}"
        if context:
            user_msg += f"\n最近上下文：{context}"
        data = chat_json(_ROUTER_PROMPT, user_msg)
        return (
            data.get("intent", "unknown"),
            data.get("filter") or {},
            data.get("mark") or {},
        )
    except Exception as e:
        logging.warning("意图路由失败，兜底 unknown：%s", e)
        return "unknown", {}, {}


def _parse_mark_range(text: str):
    """从文本解析要标记的题号范围，返回 (start, end) 或 None。

    支持：「第 3 题」「3 题」「1-20 道」「第1到20题」「3~5题」等。
    """
    # 范围：1-20 / 1到20 / 1至20 / 1~20
    m = re.search(r"(\d+)\s*[-~–—到至]\s*(\d+)", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    # 单题：第3题 / 3题
    m = re.search(r"(\d+)\s*[题道]", text)
    if m:
        n = int(m.group(1))
        return n, n
    return None


def _fast_route(text: str):
    """规则 fast-path：零歧义的高频命令直接命中，不调 LLM。

    双重作用：① LLM 不可用（余额不足/断网）时核心命令仍可用；② 高频命令省一次 LLM 调用。
    规则只拦「动作词+目标词」的零歧义组合（看错题/看知识库/看复盘/看提醒/退出/模拟面试），
    带作用域/指代/上下文的表达（如「把知识库的1-20标错题」）一律回落 LLM 语义路由。
    返回 (intent, filter, mark) 三元组；未命中返回 (None, None, None)。
    """
    tl = text.strip().lower()

    if tl in ("退出", "quit", "exit", "q", "再见", "拜拜", "结束", "88"):
        return "quit", {}, {}

    # 看复盘
    if re.search(r"看.{0,4}复盘|复盘报告|面试复盘|上次.{0,2}面试", tl):
        return "show_review", {}, {}

    # 看错题 / 看知识库（「看」开头的查看动作，避免误命中「加入错题本」「标错题」）
    if re.search(r"看.{0,3}错题", tl):
        return "list_items", {"status": "fail"}, {}
    if re.search(r"看.{0,3}知识库", tl):
        return "list_items", {"status": "unknown"}, {}

    # 看提醒
    if re.search(r"该复习|复习啥|看提醒", tl):
        return "review_remind", {}, {}

    # 模拟面试
    if re.search(r"模拟面试|面试我|开始面试", tl):
        return "mock_interview", {}, {}

    return None, None, None


# ── 功能 1：记错题 ──
def do_record_review(text: str) -> None:
    """导入面经：拆解入库。疑似错题（明说"没答上"）先确认，其余进知识库。"""
    result = decompose(text)
    items = result.items
    if not items:
        print("没拆出题，请确认内容。")
        return

    # 分流：疑似错题先让用户确认一次，否则全部进知识库（unknown）
    if result.suspected_fail:
        print(f"\n识别到整段「没答上」，疑似 {len(items)} 道错题：")
        for idx, it in enumerate(items, 1):
            print(f"  {idx}. {it.question}")
        confirm = input("\n都标成错题吗？(回车=全部 / 输入「排除2,5」去掉某些 / n=都不标): ").strip()
        if confirm.lower() not in ("n", "no", "否"):
            exclude = set()
            for part in confirm.replace("排除", "").replace("，", ",").split(","):
                part = part.strip()
                if part.isdigit():
                    exclude.add(int(part))
            items = [
                it.model_copy(update={"status": ItemStatus.FAIL}) if (i + 1) not in exclude else it
                for i, it in enumerate(items)
            ]

    # 维护 Agent：入库前去重（批内精确 + 对库向量）
    items, dup_reports = store.dedupe_items(items)
    if dup_reports:
        print(f"\n维护 Agent 跳过 {len(dup_reports)} 道重复题：")
        for r in dup_reports:
            if r["kind"] == "within_batch":
                print(f"  · 「{r['question']}」与同批重复，只留一道")
            else:
                print(f"  · 「{r['question']}」≈ 已有「{r['existing']}」({r['sim']:.0%})")
    if not items:
        print("没有新题入库（全是重复题）。")
        return

    try:
        store.store_items(items)
    except KeyboardInterrupt:
        print("\n已取消入库。")
        return

    fails = [it for it in items if it.status == ItemStatus.FAIL]
    unknowns = [it for it in items if it.status == ItemStatus.UNKNOWN]
    print(f"记下了 {len(items)} 道题：")
    if fails:
        print(f"  ❌ 错题 {len(fails)} 道（进提醒池）：")
        for it in fails:
            print(f"    {it.question}")
    if unknowns:
        print(f"  📚 知识库 {len(unknowns)} 道（待你标错题）：")
        for it in unknowns:
            print(f"    {it.question}")
    print("说「看错题」核对，说「第 N 题不会」标错题。")


# ── 功能 1.5：批量加面经 ──
def do_batch_record() -> None:
    """批量加面经：多行粘贴，单独一行「结束」收尾，一次拆解。"""
    print("把面经粘贴进来（可多行、多题），最后单独一行输入「结束」回车：")
    lines = []
    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            break
        if line.strip() in ("结束", "done", "EOF"):
            break
        if line.strip():
            lines.append(line)
    text = "\n".join(lines)
    if not text.strip():
        print("没收到内容，已取消。")
        return
    do_record_review(text)


# ── 功能 2：模拟面试 ──
def do_mock_interview() -> None:
    """复用结构化面试官（章节化 + 简历/JD/错题本出题，追问，评估写回）。"""
    mock.main()


# 最近一次列出的题（带编号），供「第 N 题不会/会了」用
_last_listed: list = []

# 最近一次操作的可读描述（短期工作记忆），供路由消歧「看一下」「还有吗」这类无宾语表达
_last_context: str = ""

# 短期记忆落盘文件（内存态 → 持久态，重启不丢；对应 checkpointer 的 InMemorySaver→SqliteSaver 思想）
# 按空间分目录：session 是「短期记忆」，属于当前空间，不跨空间共享
def _session_file():
    return space_dir() / "session.json"


def _save_session() -> None:
    """把短期记忆（最近上下文 + 最近列出的题）落盘。失败只告警，不打断主流程。"""
    try:
        f = _session_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "context": _last_context,
            "listed": [it.model_dump(mode="json") for it in _last_listed],
        }
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logging.warning("短期记忆落盘失败：%s", e)


def _load_session() -> None:
    """启动时读回短期记忆。文件缺失或损坏则保持空。"""
    global _last_context, _last_listed
    f = _session_file()
    if not f.exists():
        return
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        _last_context = data.get("context", "")
        _last_listed = [KnowledgeItem(**d) for d in data.get("listed", [])]
    except Exception as e:
        logging.warning("短期记忆读取失败，已重置：%s", e)
        _last_context = ""
        _last_listed = []


def _set_context(desc: str) -> None:
    global _last_context
    _last_context = desc
    _save_session()


# ── 功能 3：列出错题 ──
def do_list_items(filter_: dict | None = None) -> None:
    """列出错题，支持按 status 过滤、topic 语义检索，或只报数量。"""
    filter_ = filter_ or {}
    status = filter_.get("status")
    topic = (filter_.get("topic") or "").strip()
    statuses = [status] if status else ["fail", "unknown"]

    # 全量（用于空判断 + 兜底列可用 topic）
    all_items = []
    for s in ["fail", "unknown"]:
        all_items.extend(store.search(status=s, top_k=1000))
    if not all_items:
        print("错题本还是空的，先说一句「今天面了 X，被问了 Y，没答上」记几道题。")
        return

    # 取题：有 topic 走语义检索（向量召回），失败退回子串匹配
    if topic:
        try:
            items = []
            for s in statuses:
                items.extend(
                    store.search(query=topic, status=s, top_k=50, similarity_threshold=0.3)
                )
        except Exception as e:
            logging.warning("语义检索失败，退回子串匹配：%s", e)
            items = [it for it in all_items if topic.lower() in (it.topic or "").lower()]
    else:
        items = [it for it in all_items if not status or it.status.value == status]

    # 题型过滤（精确匹配 question_type）
    qtype = (filter_.get("type") or "").strip()
    if qtype:
        items = [it for it in items if it.question_type == qtype]

    # 只报数量
    if filter_.get("count_only"):
        print(f"一共 {len(items)} 道题。")
        return

    # 过滤后为空：有信息量的兜底拒绝
    if not items:
        cond = []
        if status:
            cond.append(f"状态「{status}」")
        if topic:
            cond.append(f"主题「{topic}」")
        if qtype:
            cond.append(f"题型「{qtype}」")
        cond_str = "、".join(cond)
        print(f"没有匹配 {cond_str} 的题。")
        topics = sorted({it.topic for it in all_items if it.topic})
        if topics:
            print(f"你的错题按主题是这些：{'、'.join(topics)}")
        print("也可以试试「fail 的题」「一共有多少题」。")
        return

    global _last_listed
    _last_listed = items
    scope_label = "错题" if status == "fail" else "知识库"
    print(f"共 {len(items)} 道题（说「第 N 题不会/会了」可标）：")
    for idx, it in enumerate(items, 1):
        emoji = "❌" if it.status == ItemStatus.FAIL else "📚"
        topic_tag = f"（{it.topic}）" if it.topic else ""
        print(f"  {idx}. {emoji} {it.question} {topic_tag}")
    _set_context(f"刚列出了{len(items)}道{scope_label}题")


# ── 功能 3.5：标错题 / 标会 ──
def do_mark(text: str, mark: dict, status: ItemStatus) -> None:
    """按 mark 参数标记题：scope 决定作用域（知识库/错题/上次列出），range 决定编号范围。

    mark 由 LLM 路由提取，形如 {"scope": "unknown"|"fail"|None, "range": [start, end]}。
    """
    rng = mark.get("range")
    if not rng:
        rng = _parse_mark_range(text)  # LLM 没给时，本地正则兜底
    if not rng:
        print("没听懂第几题，说「第 3 题不会」或「把知识库的 1-20 加入错题」这种。")
        return
    start, end = int(rng[0]), int(rng[1])

    # 作用域：知识库/错题按 scope 重新查询（编号与「看知识库/看错题」一致），否则用上次列出的
    scope = mark.get("scope")
    if scope in ("fail", "unknown"):
        items = store.search(status=scope, top_k=1000)
    else:
        items = _last_listed

    if not items:
        print("先「看错题」或「看知识库」列出题，再说第几题。")
        return
    if start < 1 or start > len(items):
        print(f"只有 {len(items)} 道题，没有第 {start} 题。")
        return
    if end > len(items):  # 「全部」等超界表达，自动截断到实际数量
        end = len(items)
    if start > end:
        print(f"只有 {len(items)} 道题，没有第 {start} 题。")
        return

    targets = items[start - 1:end]
    store.store_items([it.model_copy(update={"status": status}) for it in targets])
    label = "错题（进提醒池）" if status == ItemStatus.FAIL else "会了（退出提醒池）"
    scope_label = {"fail": "错题", "unknown": "知识库"}.get(scope, "")
    if len(targets) == 1:
        print(f"已把「{targets[0].question}」标为 {label}。")
    else:
        prefix = f"{scope_label}里的" if scope_label else ""
        print(f"已把{prefix}第 {start}-{end} 题（共 {len(targets)} 道）标为 {label}。")
    _set_context(f"刚把{scope_label}第{start}-{end}题（共{len(targets)}道）标为{label}")


# ── 功能 4：看提醒 ──
def do_review_remind() -> None:
    """按遗忘状态分层提醒。"""
    now = utcnow()
    items = (
        store.search(status="fail", top_k=1000)
        + store.search(status="partial", top_k=1000)
    )
    if not items:
        print("错题本还是空的，先去记几道题。")
        return

    red, yellow = [], []
    for it in rank(items, now=now):
        gap = 1.0 - effective_mastery(it, now)
        if gap >= 0.5:
            red.append(it)
        elif gap >= 0.2:
            yellow.append(it)

    if not red and not yellow:
        print("都掌握得不错，暂时没有要复习的。")
        return
    if red:
        print(f"🔴 快忘了（{len(red)} 道，优先看）：")
        for it in red:
            days = int(_elapsed_days(it, now))
            print(f"   [{it.status.value.upper():>7}] {it.question}  {days} 天没复习")
            if it.behavior_tags:
                print(f"      ⚠️ 行为提醒：{', '.join(it.behavior_tags)}")
    if yellow:
        print(f"🟡 该看看（{len(yellow)} 道）：")
        for it in yellow:
            days = int(_elapsed_days(it, now))
            print(f"   [{it.status.value.upper():>7}] {it.question}  {days} 天没复习")


# ── 功能 4.5：看面试复盘 ──
def do_show_review() -> None:
    """读上次模拟面试的复盘报告（复盘落盘在当前空间的 last_review.md）。"""
    path = space_dir() / "last_review.md"
    if not path.exists():
        print("还没有面试复盘。先「模拟面试」跑一场，面完会自动生成复盘报告。")
        return
    try:
        print("\n" + path.read_text(encoding="utf-8"))
    except Exception as e:
        logging.warning("读复盘报告失败：%s", e)
        print("复盘报告读取失败。")


# ── 功能 5：维护 Agent 体检 ──
def do_maintenance() -> None:
    """全库体检：报告数据健康 + 疑似重复题对 + 缺主题标签的题。"""
    print("=" * 40)
    print("维护 Agent · 数据体检")
    print("=" * 40)
    stats = store.get_stats(space=_cfg.SPACE)
    print(
        f"总数 {stats['total']} 道："
        f"❌ 错题 {stats['by_status']['fail']} · "
        f"📚 知识库 {stats['by_status']['unknown']} · "
        f"✅ 已会 {stats['by_status']['pass']}"
    )

    pairs = store.find_intra_duplicates()
    if pairs:
        print(f"\n发现 {len(pairs)} 对疑似重复：")
        for a, b, sim in pairs:
            print(f"  · 「{a}」 ≈ 「{b}」({sim:.0%})")
        print("  （用「看错题」+「第 N 题会了」或重新整理来处理）")
    else:
        print("\n没有发现重复题。")

    all_items = store.search(top_k=1000)
    no_topic = [it for it in all_items if not it.topic]
    if no_topic:
        print(f"\n{len(no_topic)} 道题缺主题标签（不影响使用，检索时可能召回不准）。")


# ── 主循环 ──
_HELP = (
    "我会根据你说的话自动判断要做什么：\n"
    "  · 记错题：今天面了字节，被问了 RAG 混合检索，没答上\n"
    "  · 模拟面试：帮我模拟面试\n"
    "  · 看提醒：我该复习啥\n"
    "  · 整理一下：体检数据、查重复\n"
    "  · 退出：退出 / quit"
)


def _dispatch(text: str) -> bool:
    """处理一条用户输入，返回是否继续循环（False = 退出）。

    从 main() 循环体抽出：既保持主流程不变，又为 AgentOps 埋点提供
    「一次任务 = 一个 trace」的边界（M1 接入）。
    """
    # 规则 fast-path 只拦「退出」，其余走 LLM 语义理解（含作用域/编号提取 + 上下文消歧）
    intent, filter_, mark = _fast_route(text)
    if intent is None:
        intent, filter_, mark = route(text, _last_context)
    if intent == "quit":
        print("再见。")
        return False
    elif intent == "record_review":
        do_record_review(text)
    elif intent == "batch_record":
        do_batch_record()
    elif intent == "mock_interview":
        do_mock_interview()
    elif intent == "list_items":
        do_list_items(filter_)
    elif intent == "review_remind":
        do_review_remind()
    elif intent == "show_review":
        do_show_review()
    elif intent == "mark_fail":
        do_mark(text, mark, ItemStatus.FAIL)
    elif intent == "mark_pass":
        do_mark(text, mark, ItemStatus.PASS)
    elif intent == "maintenance":
        do_maintenance()
    else:
        print("没太听懂。你可以：记一道错题 / 模拟面试 / 看错题 / 看提醒 / 退出。")
    return True


def main() -> None:
    _init_ao()  # AgentOps 可选接入（幂等）
    print("=" * 50)
    print("OfferLoop —— 记得你的面试错题本")
    print("=" * 50)
    print("说人话就行：")
    print(_HELP)
    print()

    # 启动自动维护：静默清理完全相同的重复题（确定性，无需你触发）
    try:
        result = store.auto_clean()
        if result["removed"]:
            print(f"🧹 自动清理了 {result['removed']} 条重复题（{result['groups']} 组）。")
            print()
    except Exception as e:
        logging.warning("自动维护失败：%s", e)

    # 读回上次的短期记忆（重启后还能接上「上次在干嘛」）
    _load_session()
    if _last_context:
        print(f"🧠 接着上次：{_last_context}")
        print()

    while True:
        try:
            text = input("OfferLoop > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break
        if not text:
            continue

        # AgentOps：一次任务 = 一个 trace（根 span 记录任务前记忆快照 hash，供 M4 重放恢复）
        if _ao is not None:
            tracer, _ = _ao
            with tracer.trace("offerloop.task", memory_snapshot=session_snapshot_hash(space_dir())):
                if not _dispatch(text):
                    break
        else:
            if not _dispatch(text):
                break

    # AgentOps：退出前排空 exporter 缓冲（异步上报不丢根 span）
    if _ao is not None:
        try:
            _ao[0].flush(timeout=3)
        except Exception:
            pass


if __name__ == "__main__":
    # 解析 --space 参数，设置当前空间（在 main 之前，保证所有 space 相关路径/collection 生效）
    import src.config as _cfg
    if "--space" in sys.argv:
        idx = sys.argv.index("--space") + 1
        if idx < len(sys.argv):
            _cfg.SPACE = sys.argv[idx]
    main()
