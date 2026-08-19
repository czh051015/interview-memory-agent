"""模拟面试 · 面试官 Agent（v2：章节化结构化面试）。

用法：
  python run_mock_interview.py            # 开始面试
  python run_mock_interview.py --recover  # 补写上次崩溃未写库的结果

流程：读简历/JD → 读错题薄弱项 → LLM 生成章节化面试计划（自我介绍 / 项目深挖 /
技术验证 / 行为面 / 动机面）→ 逐题追问 → 评估写回（weak 题更新 mastery + 新题答差自动采集）。

出题依据（四层）：
  · 简历   —— 项目深挖、查真实性（不是背技能点，是往下钻细节）
  · JD     —— 能力项验证
  · 错题本 —— 薄弱项验证 + 难度调节（会的少问，薄弱的重点问）
  · 结构化方法论 —— STAR / 宝洁八大问 / 动机面兜底
"""

import sys
import json
import logging
import uuid

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

import src.config as _cfg  # noqa: E402  （SPACE 全局：CLI --space 切换）
from src.config import DATA_DIR, space_dir
from src.cleaner.schema import KnowledgeItem, ItemStatus, ItemSource, utcnow
from src.cleaner.state_machine import record_birth
from src.llm import chat_json
from src.memory import knowledge_store as store
from src.memory import mastery
from src.memory import review_log

# ── 面试规模 ──
WEAK_POOL_SIZE = 5   # 薄弱项候选池（供 LLM 从错题本挑技术验证题）
MAX_FOLLOWUPS = 2    # 每题最多追 2 轮
MAX_ROUNDS = MAX_FOLLOWUPS + 1  # 首答 + 2 次追问 = 3 轮
MAX_TOTAL_QUESTIONS = 12   # 动态循环：整场总题数上限
MAX_SECTION_QUESTIONS = 5  # 动态循环：单章节题数上限（项目深挖/技术验证）
MIN_SECTION_QUESTIONS = 1  # 动态循环：单章节最少题数（保证章节骨架完整）

# ── 数据文件（面试官出题依据，支持 .pdf / .md / .txt，优先 .pdf）──


# ══════════ 工具 1：读错题薄弱项 ══════════
def get_weak_questions(top_k: int = WEAK_POOL_SIZE, space: str | None = None):
    """读错题本 fail/partial，rank 排序取最薄弱的前 top_k（作为技术验证章的候选）。

    space：Web 版多租户过滤（CLI 默认 None=当前 config.SPACE 空间）。
    """
    space = space or _cfg.SPACE
    fails = store.search(status="fail", space=space, top_k=1000)
    partials = store.search(status="partial", space=space, top_k=1000)
    items = fails + partials
    if not items:
        return []
    return mastery.rank(items)[:top_k]


# ══════════ 工具 2：读简历 / JD ══════════
def _read_pdf_text(path) -> str:
    """提取 PDF 文本：PyMuPDF（强，中文/复杂排版更好）→ 回退 pypdf → 都空则提示可能扫描件。"""
    text = ""
    try:
        try:
            import pymupdf as fitz  # PyMuPDF 1.24+ 推荐
        except ImportError:
            import fitz  # PyMuPDF 旧版
        with fitz.open(path) as doc:
            text = "\n".join(page.get_text() for page in doc).strip()
    except Exception as e:
        logging.warning("PyMuPDF 提取失败 %s：%s，回退 pypdf", path.name, e)

    if not text:
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        except Exception as e:
            logging.warning("pypdf 提取失败 %s：%s", path.name, e)

    if not text:
        logging.warning("%s 提取不到文字，可能是扫描件/图片型 PDF，需要 OCR（或改用 .md/.txt）", path.name)
    return text


def _read_doc(name: str) -> str:
    """按 .pdf → .md → .txt 优先级读文档，命中一个非空就返回。"""
    for ext in (".pdf", ".md", ".txt"):
        path = DATA_DIR / f"{name}{ext}"
        if not path.exists():
            continue
        try:
            text = _read_pdf_text(path) if ext == ".pdf" else path.read_text(encoding="utf-8").strip()
        except Exception as e:
            logging.warning("读取 %s 失败：%s", path.name, e)
            continue
        if text:
            return text
    return ""


def _read_profile() -> dict:
    """读简历和 JD。支持 .pdf / .md / .txt，优先 .pdf；缺失/失败返回空（对应章节跳过）。"""
    return {"resume": _read_doc("resume"), "jd": _read_doc("jd")}


# ══════════ 工具 3：LLM 生成章节化面试计划 ══════════
_PLAN_PROMPT = (
    "你是资深面试官，为一位候选人设计一场结构化面试。你会收到三份材料：候选人简历、岗位 JD、"
    "历史薄弱项（候选人面试中答错的题，含 id）。请按固定章节出题，只输出 JSON。\n\n"
    "输出格式：\n"
    '{"sections": [{"name": "章节名", "questions": [{"question": "面试题", "source": "来源", "item_id": null, "topic": "主题"}]}]}\n\n'
    "章节（按顺序，数量固定）：\n"
    "1. 自我介绍：1 题，开放式破冰。\n"
    "2. 项目深挖：3 题，从简历项目里挑最值得深挖的，追问实现细节/难点/取舍，查真实性。简历为空则跳过本章。\n"
    "3. 技术验证：3 题，混合「JD 能力项」和「历史薄弱项」。薄弱项优先用给定错题（item_id 填对应 id，source=weak，question 直接抄错题原文）；JD 能力项现场出题（source=jd，item_id=null）。\n"
    "4. 行为面：1 题，用 STAR（情境-任务-行动-结果）考察软素质。\n"
    "5. 动机面：1 题，为什么投这个岗 / 职业规划。\n\n"
    "source 取值：generic / resume / jd / weak / behavior / motivation。\n"
    "item_id 规则（严格）：只有「技术验证」章里、且题目是直接抄错题原文的题，才允许 source=weak 并填对应 item_id；其余所有题（自我介绍/项目深挖/行为面/动机面）source 一律不能是 weak，item_id 一律 null。\n"
    "topic：每题一个简短主题标签（如 RAG、线程池、项目深挖、职业规划），用于归档。\n"
    "题目要求：具体、可深挖、贴合候选人材料，不要泛泛的背诵题。"
)


def plan_interview(resume: str, jd: str, weak_items: list) -> list[dict]:
    """LLM 生成章节化面试计划。失败返回 []（主流程提示重试）。"""
    weak_str = "\n".join(f"- [{it.id}] {it.question}" for it in weak_items) if weak_items else "（无）"
    user_prompt = (
        f"## 候选人简历\n{resume or '（未提供）'}\n\n"
        f"## 岗位 JD\n{jd or '（未提供）'}\n\n"
        f"## 历史薄弱项\n{weak_str}"
    )
    try:
        data = chat_json(_PLAN_PROMPT, user_prompt, max_tokens=4096)
        return data.get("sections", [])
    except Exception as e:
        logging.warning("生成面试计划失败：%s", e)
        return []


# ══════════ 工具 3b：动态智能体循环 —— 下一步决策 + 现场出题 ══════════
# 面试官不是执行固定题单：每答完一题，根据当场表现决定 深挖 / 换题 / 进下一章 / 结束。
# 系统只卡安全边界（章节顺序 / 章节题数上限 / 总题数上限），决策全在 LLM。
_DECIDE_NEXT_PROMPT = (
    "你是一位资深面试官，正在一场结构化面试进行中。刚答完一道题，现在决定下一步怎么走。\n"
    "你会收到：当前章节、刚答完的题与表现、本章已问题数、剩余章节、本场已问题目。\n"
    "只输出 JSON：\n"
    '{"action": "deep_dive"|"switch"|"next_section"|"end", '
    '"guidance": "继续时下一题的方向（一段话，具体、可深挖）", "reason": "一句决策依据"}\n'
    "决策原则：\n"
    "- 答得差（fail/partial 且理由显示不会）→ 优先 deep_dive：同主题换角度确认是真不会还是紧张；\n"
    "- 答得好（pass）→ 一般 switch 换话题或 next_section，不浪费时间；\n"
    "- 本章已问够（主题已充分考察）→ next_section；\n"
    "- 只剩动机面/行为面且已问 → end。\n"
    "- 保证每章至少 1 题；章节顺序和题数上限由系统卡，你只管合理决策。"
)


def decide_next(
    section: str,
    last_question: str,
    performance: str,
    reason: str,
    section_asked: int,
    remaining_sections: list[str],
    asked_before: list[str],
) -> dict:
    """动态循环决策：LLM 输出 {action, guidance, reason}，兜底 switch。"""
    user_prompt = (
        f"当前章节：{section}\n"
        f"刚答完的题：{last_question}\n"
        f"本题表现：{performance}\n"
        f"判断依据：{reason}\n"
        f"本章已问题数：{section_asked}\n"
        f"剩余章节：{remaining_sections or '（无，本章是最后一章）'}\n"
        f"本场已问题目：{asked_before or '（无）'}"
    )
    try:
        data = chat_json(_DECIDE_NEXT_PROMPT, user_prompt)
        action = data.get("action", "switch")
        if action not in ("deep_dive", "switch", "next_section", "end"):
            action = "switch"
        return {
            "action": action,
            "guidance": str(data.get("guidance", "")),
            "reason": str(data.get("reason", "")),
        }
    except Exception as e:
        logging.warning("下一步决策失败，兜底 switch：%s", e)
        return {"action": "switch", "guidance": "", "reason": "决策失败"}


_DYNAMIC_QUESTION_PROMPT = (
    "你是资深面试官，在面试进行中现场出一道新题。你会收到：当前章节、出题指引（面试官决策）、"
    "候选人简历、JD、历史薄弱项、本场已问题目。\n"
    "任务：出一道符合章节和指引的题，具体、可深挖、贴合候选人材料，不要与已问题目重复。\n"
    "只输出 JSON：\n"
    '{"question": "面试题", "source": "resume"|"jd"|"weak"|"behavior"|"motivation"|"generic", "topic": "主题标签"}'
)


def generate_dynamic_question(
    section: str,
    guidance: str,
    resume: str,
    jd: str,
    weak_items: list,
    asked_before: list[str],
) -> dict:
    """现场出题：deep_dive/switch 时按决策指引生成新题。失败返回 {}（调用方跳过）。"""
    weak_str = "\n".join(f"- [{it.id}] {it.question}" for it in weak_items) if weak_items else "（无）"
    user_prompt = (
        f"当前章节：{section}\n"
        f"出题指引：{guidance or '（无，自行判断）'}\n"
        f"候选人简历：{resume or '（未提供）'}\n"
        f"岗位 JD：{jd or '（未提供）'}\n"
        f"历史薄弱项：{weak_str}\n"
        f"本场已问题目：{asked_before or '（无）'}"
    )
    try:
        data = chat_json(_DYNAMIC_QUESTION_PROMPT, user_prompt, max_tokens=1024)
        q = str(data.get("question", "")).strip()
        if not q:
            return {}
        return {
            "question": q,
            "source": str(data.get("source", "generic")),
            "topic": str(data.get("topic", "")),
        }
    except Exception as e:
        logging.warning("现场出题失败：%s", e)
        return {}


# ══════════ 工具 4：检索答案对照 ══════════
_EXPECTED_POINTS_PROMPT = (
    "你是一位严格的面试官。下面是一道面试题，请列出候选人「应该答到的关键点」。\n"
    "要求：只输出 JSON，格式 {\"points\": [\"要点1\", \"要点2\", ...]}，3-5 个要点，每个一句话。"
)


def get_expected_points(question: str, answer: str = "") -> list[str]:
    """期望要点：有参考答案就用参考答案，否则 LLM 现场生成。"""
    if answer.strip():
        return [answer.strip()]
    try:
        data = chat_json(_EXPECTED_POINTS_PROMPT, f"面试题：{question}")
        return data.get("points", [])
    except Exception as e:
        logging.warning("生成期望要点失败，跳过对照：%s", e)
        return []


# ══════════ 追问判断（LLM 结构化输出，系统只卡轮次上限）══════════
_FOLLOWUP_PROMPT = (
    "你是一位严格的面试官，正在考察候选人。你会收到：面试题、期望要点、候选人的回答。\n"
    "任务：判断是否追问，并评价表现。只输出 JSON：\n"
    "{\"need_followup\": true/false, \"followup_question\": \"追问问题\", "
    "\"reason\": \"判断依据\", \"performance\": \"pass\"|\"partial\"|\"fail\"}\n"
    "标准：覆盖大部分要点且条理清晰→pass 不再追问；漏关键点或含糊→partial 追问；明显不会或跑题→fail。\n"
    "追问要具体、往下钻，围绕候选人回答里的细节/数字/取舍往下问（可追问情境-任务-行动-结果），不要泛泛地问。"
)

# ── 量规版（L1）。追问判断同样四维约束 + 引原文证据，输出格式不变。 ──
_RUBRIC_FOLLOWUP_PROMPT = (
    "你是一位严格的面试官，正在依据固定评分量规考察候选人。你会收到：面试题、期望要点（可能为无）、候选人的回答。\n"
    "评分量规（四个维度，判定必须逐维对照，判断依据必须引用回答原文）：\n"
    "1. 正确性：核心事实与原理是否准确，有无硬伤；\n"
    "2. 完整性：是否覆盖期望要点中的关键点（无期望要点时，自行判断这道题应包含哪些关键点）；\n"
    "3. 深度：是否讲清机制/细节/取舍，而非泛泛而谈；\n"
    "4. 表达：结构是否清晰，是否答非所问。\n"
    "只输出 JSON：\n"
    '{"need_followup": true/false, "followup_question": "追问问题", '
    '"reason": "判断依据（必须引用原文，如：回答只说「…」未提「…」）", "performance": "pass"|"partial"|"fail"}\n'
    "判定标准：四维均达标→pass 不再追问；1-2 个维度不足→partial 追问；存在事实错误或大段缺失→fail。\n"
    "追问要具体、往下钻，围绕回答里的细节/数字/取舍，不要泛泛地问。"
)


def judge_followup(
    question: str,
    points: list[str],
    answer: str,
    round_num: int,
    *,
    use_rubric: bool = True,
    cross_on_partial: bool = False,
    asked_before: list[str] | None = None,
) -> dict:
    """追问判断：LLM 输出结构化判断，兜底为 partial。

    use_rubric=True 时用量规版（四维约束 + 引原文证据），输出格式不变。
    cross_on_partial=True 时：主判官判 partial（拿不准）→ 第二判官复核，
    复核给出明确判定（pass/fail）则采纳并标注；复核仍 partial 则保留。
    asked_before：本场已问题目列表（session 级上下文，短期记忆最小版）——
    让面试官记得前面问过什么，追问时可参考、不重复提问。
    """
    prompt = _RUBRIC_FOLLOWUP_PROMPT if use_rubric else _FOLLOWUP_PROMPT
    ctx = ""
    if asked_before:
        ctx = "\n本场已问过的题目（面试官记忆，追问可参考、请勿重复提问）：\n" + "\n".join(
            f"- {q[:80]}" for q in asked_before
        ) + "\n"
    user_prompt = (
        f"面试题：{question}\n"
        f"期望要点：{points}\n"
        f"候选人回答（第{round_num}轮）：{answer}"
        f"{ctx}"
    )
    try:
        result = chat_json(prompt, user_prompt)
    except Exception as e:
        logging.warning("追问判断失败，兜底 partial：%s", e)
        return {"need_followup": False, "followup_question": "", "reason": "判断失败", "performance": "partial"}

    if cross_on_partial and result.get("performance") == "partial":
        try:
            review = chat_json(prompt, user_prompt, cross=True)
            if review.get("performance") in ("pass", "fail"):
                result = review
                result["reason"] = f"【第二判官复核】{result.get('reason', '')}"
                result["cross_reviewed"] = True
        except Exception as e:
            logging.warning("第二判官复核失败，保留主判官 partial：%s", e)
    return result


# ══════════ 单轮判定（Web v1：无追问，LLM 出要点+差距+建议判定）══════════
_SINGLE_JUDGE_PROMPT = (
    "你是一位严格的面试官，正在考察候选人。你会收到：面试题、候选人的回答。\n"
    "任务：判定回答质量，并给候选人对照。只输出 JSON：\n"
    '{"points": ["应该答到的要点1", "要点2", ...], '
    '"misses": ["回答里漏掉的点1", ...], '
    '"suggested": "pass"|"partial"|"fail", '
    '"reason": "一句判断依据"}\n'
    "标准：覆盖大部分要点且条理清晰→pass；漏关键点或含糊→partial；明显不会或跑题→fail。\n"
    "points 给 3-5 个（这道题应该答到什么），misses 只列确实漏掉/答错的（0-3 个，没有就给空数组）。\n"
    "reason 一句话，指出最致命的差距。"
)

# ── 量规版（L1：出卷/阅卷解耦）。四维约束 + 必须引原文证据 + 三态输出不变。
#    eval 达标后产品默认启用（use_rubric=True）；无参考答案时量规版自行判断应答要点。 ──
_RUBRIC_SINGLE_PROMPT = (
    "你是一位严格的面试官，正在依据固定评分量规考察候选人。你会收到：面试题、参考答案要点（可能为无）、候选人的回答。\n"
    "评分量规（四个维度，判定必须逐维对照，misses 必须引用回答原文作为证据）：\n"
    "1. 正确性：核心事实与原理是否准确，有无硬伤；\n"
    "2. 完整性：是否覆盖参考答案要点中的关键点（无参考答案时，自行判断这道题应包含哪些关键点）；\n"
    "3. 深度：是否讲清机制/细节/取舍，而非泛泛而谈；\n"
    "4. 表达：结构是否清晰，是否答非所问。\n"
    "只输出 JSON：\n"
    '{"points": ["应该答到的要点1", ...], "misses": ["漏掉/答错的点，必须引用原文，如：回答只说「…」未提「…」", ...], '
    '"suggested": "pass"|"partial"|"fail", "reason": "依据量规的一句判断"}\n'
    "判定标准：四维均达标→pass；1-2 个维度明显不足→partial；存在事实错误或大段缺失→fail。\n"
    "points 给 3-5 个，misses 只列确实漏掉/答错的（0-3 个，没有就给空数组）。"
)


def judge_single_round(
    question: str,
    answer: str,
    *,
    expected_points: list[str] | None = None,
    use_rubric: bool = True,
    cross: bool = False,
    cross_on_partial: bool = False,
) -> dict:
    """单轮判定（Web 版）：LLM 生成期望要点 + 差距 + 建议判定。失败兜底 partial。

    expected_points：L2 独立金标准——传入参考答案要点时阅卷人对照金标准（不再自己现编）；
                    不传则维持现状（LLM 自行生成要点，产品路径默认）。
    use_rubric=True 时用量规版（L1 量规解耦：四维约束 + 引原文证据）。
    cross=True 时直接走第二判官模型（eval --cross-model 用，不再主判）。
    cross_on_partial=True 时：主判官判 partial（拿不准）→ 第二判官复核，
    复核给出明确判定（pass/fail）则采纳并标注；复核仍 partial 则保留。
    输出：{points: [...], misses: [...], suggested: pass|partial|fail, reason: str}
    """
    points_section = ""
    if expected_points:
        points_section = "参考答案要点：\n" + "\n".join(f"- {p}" for p in expected_points) + "\n"
    user_prompt = f"面试题：{question}\n{points_section}候选人回答：{answer}"

    def _judge(cross_call: bool) -> dict:
        data = chat_json(
            _RUBRIC_SINGLE_PROMPT if use_rubric else _SINGLE_JUDGE_PROMPT,
            user_prompt,
            cross=cross_call,
        )
        if not isinstance(data.get("points"), list) or not isinstance(data.get("misses"), list):
            raise ValueError("points/misses 必须为数组")
        suggested = data.get("suggested", "partial")
        if suggested not in ("pass", "partial", "fail"):
            suggested = "partial"
        return {
            "points": [str(p) for p in data["points"]],
            "misses": [str(m) for m in data["misses"]],
            "suggested": suggested,
            "reason": str(data.get("reason", "")),
        }

    try:
        result = _judge(cross)
        if cross_on_partial and not cross and result["suggested"] == "partial":
            try:
                review = _judge(cross_call=True)
                if review["suggested"] in ("pass", "fail"):
                    result = review
                    result["reason"] = f"【第二判官复核】{result['reason']}"
                    result["cross_reviewed"] = True
            except Exception as e:
                logging.warning("第二判官复核失败，保留主判官 partial：%s", e)
        return result
    except Exception as e:
        logging.warning("单轮判定失败，兜底 partial：%s", e)
        return {"points": [], "misses": [], "suggested": "partial", "reason": "LLM 判定失败"}


# ══════════ 工具 5：写回 ══════════
def record_result(item, performance: str, behaviors: list[str]):
    """weak 题按表现更新 mastery（pass 涨 / partial 保持 / fail 降），并合并行为特征。"""
    if performance == "pass":
        updated = mastery.review(item)
    elif performance == "fail":
        updated = mastery.review_fail(item)
    else:
        updated = mastery.review_partial(item)
    merged = list(set(updated.behavior_tags + behaviors))
    return updated.model_copy(update={"behavior_tags": merged})


def _collect_new_item(r: dict) -> KnowledgeItem:
    """面试中答差的新题（简历/JD/行为/动机来源），自动采集进错题本，来源可追溯。

    answer 用 r["feedback"] 作首个参考答案（模拟面试判定文本），没有则为空；
    space 跟随当前空间（r["space"] 优先，缺省 CLI 当前 _cfg.SPACE——Web 版显式传）。
    """
    status = ItemStatus.FAIL if r["performance"] == "fail" else ItemStatus.PARTIAL
    ki = KnowledgeItem(
        id=f"ki_{utcnow():%Y%m%d}_{uuid.uuid4().hex[:6]}_{r.get('source', 'mock')[:3]}",
        question=r["question"],
        answer=r.get("feedback") or "",  # 模拟面试 LLM 判定可作首个答案对照
        topic=r.get("topic", ""),
        status=status,
        source=ItemSource.MOCK_INTERVIEW,
        mastery_score=mastery.INITIAL_MASTERY[status],
        created_at=utcnow(),
        space=r.get("space") or _cfg.SPACE,
    )
    return record_birth(ki, reason=f"模拟面试表现 {r['performance']}", actor="mock_interview")


def _feedback_text(performance: str, judge: dict) -> str:
    """把 LLM 判定拼成可读文本，作为题目的「参考答案/面试官反馈」存 answer 字段。

    judge: {points: [...], misses: [...], reason: str}；performance: fail/partial。
    时间戳用本地时间（用户可读，不用 utcnow）。
    """
    from datetime import datetime

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    parts = [f"【模拟面试 {ts} · {performance}】"]
    points = judge.get("points") or []
    misses = judge.get("misses") or []
    if points:
        parts.append("应该答到：\n" + "\n".join(f"- {p}" for p in points))
    if misses:
        parts.append("漏掉的：\n" + "\n".join(f"- {m}" for m in misses))
    if judge.get("reason"):
        parts.append(f"面试官的话：{judge['reason']}")
    return "\n".join(parts)


def _write_back(results: list[dict], behaviors: list[str]):
    """写回：weak 题更新 mastery，新题答差自动采集。返回 (updated, new)。"""
    updated = []
    new = []
    for r in results:
        if r.get("source") == "weak" and r.get("item") is not None:
            updated.append(record_result(r["item"], r["performance"], behaviors))
        elif r.get("performance") in ("fail", "partial"):
            new.append(_collect_new_item(r))
    return updated, new


_ACTION_OF = {"pass": "review", "fail": "review_fail", "partial": "review_partial"}


def _log_write_back(results: list[dict], updated_items: list):
    """写库成功后，把 weak 题的 mastery 变化记进复习日志（演变动态的种子）。

    只在 store 成功后调用，避免写库失败 + recover 重跑导致日志重复。
    """
    after_by_id = {u.id: u for u in updated_items}
    for r in results:
        it = r.get("item")
        if it is not None and it.id in after_by_id:
            u = after_by_id[it.id]
            review_log.append(item_id=it.id, question=it.question,
                              before=it.mastery_score, after=u.mastery_score,
                              action=_ACTION_OF.get(r.get("performance", ""), "review_partial"),
                              actor="mock_interview")


# ══════════ 行为特征总结 ══════════
_BEHAVIOR_PROMPT = (
    "你是面试官，回顾整场面试，总结候选人的行为特征。只输出 JSON：{\"tags\": [\"标签1\", ...]}\n"
    "维度（可多个，也可空数组）：答不到点（知识缺口）、表达绕弯（逻辑不清）、回避问题（转移话题）。\n"
    "只输出确实暴露的问题，没有就输出空数组。"
)


def summarize_behaviors(records: list[dict]) -> list[str]:
    """整场面试结束，总结行为特征标签。"""
    summary = "\n".join(
        f"题：{r['question']}\n答：{r['answer'][:120]}\n表现：{r['performance']}" for r in records
    )
    try:
        data = chat_json(_BEHAVIOR_PROMPT, summary)
        return data.get("tags", [])
    except Exception as e:
        logging.warning("行为特征总结失败：%s", e)
        return []


# ══════════ 面试复盘报告 ══════════
_REVIEW_PROMPT = (
    "你是资深面试官，刚面完一位候选人。下面是整场面试的完整记录（题目、逐轮问答、追问理由、最终表现）。\n"
    "请输出一份复盘报告，要具体、可执行，指出候选人每道题哪里没答到点、为什么、下次怎么改进。\n"
    "只输出 JSON：\n"
    '{"overall": "整体评价（2-3句，点出最致命的问题）", '
    '"items": [{"question": "题", "performance": "pass|partial|fail", "problem": "核心问题", "suggestion": "改进建议"}], '
    '"common": "共性建议（跨题总结的1-2个系统性问题）"}'
)


def generate_review_report(records: list[dict], behaviors: list[str]) -> dict | None:
    """面试结束后生成复盘报告。失败返回 None。"""
    lines = []
    for i, r in enumerate(records, 1):
        lines.append(f"第{i}题：{r['question']}")
        for t in r.get("transcript", []):
            lines.append(f"  第{t['round']}轮回答：{t['answer'][:200]}")
            lines.append(f"  面试官判断：{t.get('reason', '')}")
            if t.get("followup_question"):
                lines.append(f"  追问：{t['followup_question']}")
        lines.append(f"  最终表现：{r['performance']}")
    if behaviors:
        lines.append(f"行为特征：{', '.join(behaviors)}")
    try:
        data = chat_json(_REVIEW_PROMPT, "\n".join(lines), max_tokens=4096)
        return data if data.get("overall") or data.get("items") else None
    except Exception as e:
        logging.warning("复盘报告生成失败：%s", e)
        return None


def _format_review(report: dict) -> str:
    """把复盘报告格式化成 markdown 文本（终端打印 + 落盘共用）。"""
    lines = ["📋 面试复盘报告", "=" * 40, ""]
    if report.get("overall"):
        lines += ["【整体评价】", report["overall"], ""]
    lines.append("【逐题复盘】")
    for it in report.get("items", []):
        emoji = {"pass": "✅", "partial": "⚠️", "fail": "❌"}.get(it.get("performance"), "❓")
        lines.append(f"  {emoji} {it.get('question', '')}")
        if it.get("problem"):
            lines.append(f"     问题：{it['problem']}")
        if it.get("suggestion"):
            lines.append(f"     建议：{it['suggestion']}")
    if report.get("common"):
        lines += ["", "【共性建议】", report["common"]]
    return "\n".join(lines)


# ══════════ 单题面试（可测试的纯逻辑）══════════
def interview_one(question: str, answer_fn, answer: str = "", asked_before: list[str] | None = None) -> tuple[str, str, list]:
    """面试一道题，返回 (最终表现, 全部回答拼接, 逐轮对话记录)。

    answer 是错题本里的参考答案（如果有），追问判断时优先用它做对照。
    asked_before：本场已问题目列表（session 上下文），注入追问判断。
    transcript 每轮记录 {round, answer, reason, followup_question, performance}，供复盘报告用。
    """
    points = get_expected_points(question, answer)
    answers = []
    transcript = []
    performance = "partial"

    for round_num in range(1, MAX_ROUNDS + 1):
        answer = answer_fn(round_num).strip()
        if not answer:
            performance = "fail"
            break
        answers.append(answer)

        judge = judge_followup(question, points, answer, round_num,
                               cross_on_partial=True, asked_before=asked_before)
        performance = judge.get("performance", "partial")
        transcript.append({
            "round": round_num,
            "answer": answer,
            "reason": judge.get("reason", ""),
            "followup_question": judge.get("followup_question", ""),
            "performance": judge.get("performance", "partial"),
        })

        if judge.get("need_followup") and round_num < MAX_ROUNDS:
            fq = judge.get("followup_question", "").strip()
            if fq:
                print(f"\n💬 面试官追问：{fq}")
                continue
        break

    return performance, "\n".join(answers), transcript


# ══════════ 断点保护：边答边落盘 + 写库幂等重跑 ══════════
# 面试结果每答完一题就落盘本地，任何一步崩溃最多丢「正在答的那一题」。
# 写回用 record_result（纯函数）+ store_items（按 id 覆盖），且落盘存「原始 item 快照」，
# 重跑结果一致 → 幂等，可重复恢复不重复涨 mastery。
def _progress_file():
    """当前空间的面试进度落盘文件（按空间分目录）。"""
    return space_dir() / "interview_progress.json"


def _q_dump(q: dict) -> dict:
    return {
        "question": q.get("question", ""),
        "source": q.get("source", ""),
        "topic": q.get("topic", ""),
        "item_id": q.get("item_id"),
        "section": q.get("section", ""),
        "item": q["item"].model_dump(mode="json") if q.get("item") else None,
    }


def _r_dump(r: dict) -> dict:
    return {
        "question": r.get("question", ""),
        "source": r.get("source", ""),
        "topic": r.get("topic", ""),
        "performance": r.get("performance", ""),
        "answer": r.get("answer", ""),
        "item": r["item"].model_dump(mode="json") if r.get("item") else None,
    }


def _save_progress(questions, answered, behaviors):
    """把当前面试进度落盘。item 用快照序列化，None 保持 None。"""
    try:
        data = {
            "questions": [_q_dump(q) for q in questions],
            "answered": [_r_dump(r) for r in answered],
            "behaviors": behaviors,
        }
        _progress_file().write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logging.warning("面试进度落盘失败：%s", e)


def _load_progress():
    """读回上次的面试进度。文件缺失或损坏返回 None。"""
    if not _progress_file().exists():
        return None
    try:
        data = json.loads(_progress_file().read_text(encoding="utf-8"))
        questions = [dict(q) for q in data.get("questions", [])]
        for q in questions:
            q["item"] = KnowledgeItem(**q["item"]) if q.get("item") else None
        answered = [dict(r) for r in data.get("answered", [])]
        for r in answered:
            r["item"] = KnowledgeItem(**r["item"]) if r.get("item") else None
        return {"questions": questions, "answered": answered, "behaviors": data.get("behaviors", [])}
    except Exception as e:
        logging.warning("面试进度读取失败：%s", e)
        return None


def _clear_progress():
    """写库成功后清掉落盘，表示本场面试已完成。"""
    try:
        _progress_file().unlink(missing_ok=True)
    except Exception as e:
        logging.warning("清理面试进度失败：%s", e)


def recover():
    """把上次未写库的面试结果补写进知识库。幂等：可重复执行，不重复涨 mastery。"""
    prog = _load_progress()
    if not prog or not prog["answered"]:
        print("没有需要恢复的面试。")
        return
    answered = prog["answered"]
    behaviors = prog.get("behaviors", [])
    print(f"发现上次未完成的面试：已答 {len(answered)} 题，正在补写...")
    updated, new = _write_back(answered, behaviors)
    store.store_items(updated + new)
    _log_write_back(answered, updated)
    _clear_progress()
    print(f"补写完成（更新 {len(updated)} 题掌握度，新采集 {len(new)} 题进错题本）。")


# ══════════ 动态智能体循环（可测试的纯状态机）══════════
def run_dynamic_session(
    section_order: list[str],
    pool_by_section: dict[str, list[dict]],
    resume: str,
    jd: str,
    weak_items: list,
    *,
    ask_fn,
    on_save=None,
    interrupted: bool = False,
) -> tuple[list[dict], list[dict]]:
    """动态面试状态机：选下一题 → 出题 → 等回答 → 追问 → 决策 → 循环。

    硬约束（系统侧）：章节顺序不跳（sec_idx 只前进）、每章 ≥1 题、
    单章 ≤MAX_SECTION_QUESTIONS、整场 ≤MAX_TOTAL_QUESTIONS。
    决策全在 LLM（decide_next / generate_dynamic_question），系统只卡边界。

    返回 (questions, results)。ask_fn 由调用方注入（CLI=stdin，测试=脚本答案）。
    interrupted=True 时遇到 KeyboardInterrupt/EOFError 静默退出（已答保存）。
    """
    questions: list[dict] = []       # 实际问过的全部题（含现场生成的，供落盘/复盘）
    results = []
    asked_before: list[str] = []     # session 级上下文：本场已问题目
    sec_idx = 0                      # 当前章节下标（只前进）
    sec_asked: dict[str, int] = {}   # 每章已问题数
    next_action: str | None = None   # 决策结果（deep_dive / switch / next_section）

    while sec_idx < len(section_order):
        if len(questions) >= MAX_TOTAL_QUESTIONS:
            print("\n（达到整场题数上限，面试结束）")
            break
        section = section_order[sec_idx]
        if sec_asked.get(section, 0) >= MAX_SECTION_QUESTIONS:
            print(f"\n（{section} 已达章节上限，进入下一章）")
            sec_idx += 1
            continue
        # 章节开始：打印章节头
        if sec_asked.get(section, 0) == 0:
            print(f"\n{'=' * 50}\n【{section}】\n{'=' * 50}")

        # ── 选下一题 ──
        if sec_asked.get(section, 0) == 0:
            # 章节首题：优先用计划种子题，池空则现场出
            q = pool_by_section[section].pop(0) if pool_by_section.get(section) else {}
            if not q:
                q = generate_dynamic_question(section, "", resume, jd, weak_items, asked_before)
        elif next_action == "deep_dive":
            # 答得差 → 同主题深挖：现场换角度出题
            q = generate_dynamic_question(section, "深挖上一题主题", resume, jd, weak_items, asked_before)
        else:
            # switch / next_section / 兜底：优先种子池，池空现场出
            q = pool_by_section[section].pop(0) if pool_by_section.get(section) else {}
            if not q:
                q = generate_dynamic_question(section, "", resume, jd, weak_items, asked_before)

        if not q or not q.get("question"):
            print(f"\n⚠️ 出题失败，{section} 章节结束。")
            sec_idx += 1
            continue
        q["section"] = section
        q.setdefault("source", "generic")
        q.setdefault("topic", "")
        q.setdefault("item", None)
        questions.append(q)

        print(f"\n[第 {len(questions)}/{MAX_TOTAL_QUESTIONS} 题 · {section}] {q['question']}")

        try:
            ref_answer = q["item"].answer if q["item"] else ""
            performance, answer_text, transcript = interview_one(
                q["question"], ask_fn, ref_answer, asked_before=asked_before
            )
        except (KeyboardInterrupt, EOFError):
            if not interrupted:
                raise
            print("\n\n已退出模拟面试（已答的题会保存）。")
            break

        asked_before.append(q["question"])  # 答完记入面试官记忆
        results.append({
            "question": q["question"], "source": q.get("source", ""),
            "topic": q.get("topic", ""), "item": q.get("item"),
            "performance": performance, "answer": answer_text,
            "transcript": transcript,
        })
        sec_asked[section] = sec_asked.get(section, 0) + 1
        if on_save:
            on_save(questions, results)  # 每答完一题就落盘，最多丢正在答的这一题

        emoji = {"pass": "✅", "partial": "⚠️", "fail": "❌"}.get(performance, "❓")
        print(f"\n{emoji} 本题表现：{performance.upper()}")

        # ── 决策点：下一步怎么走（LLM 决策，系统卡边界）──
        last_judge = (transcript or [{}])[-1]
        remaining = section_order[sec_idx + 1:]
        if sec_idx == len(section_order) - 1 and sec_asked.get(section, 0) >= MIN_SECTION_QUESTIONS:
            decision = {"action": "end", "guidance": "", "reason": "最后一章已问，面试结束"}
        else:
            decision = decide_next(
                section, q["question"], performance, last_judge.get("reason", ""),
                sec_asked.get(section, 0), remaining, asked_before,
            )
        next_action = decision["action"]
        if decision.get("reason"):
            print(f"      → 面试官决策：{next_action}（{decision['reason'][:60]}）")

        if next_action == "end" and sec_asked.get(section, 0) >= MIN_SECTION_QUESTIONS:
            break
        if next_action == "next_section" and sec_asked.get(section, 0) >= MIN_SECTION_QUESTIONS:
            sec_idx += 1
        elif next_action == "deep_dive" and sec_asked.get(section, 0) >= MAX_SECTION_QUESTIONS:
            sec_idx += 1  # 章节已到上限，深挖转为进下一章（硬约束）
        # switch：留在本章换话题（系统只在章节/整场上限处强制推进）

    return questions, results


# ══════════ 主流程 ══════════
def main():
    print("=" * 60)
    print("OfferLoop 模拟面试 · 结构化面试官")
    print("=" * 60)

    profile = _read_profile()
    weak_items = get_weak_questions()

    if not profile["resume"] and not profile["jd"] and not weak_items:
        print("\n⚠️ 没有可面试的材料：")
        print("   · 简历：把内容贴到 data/resume.md")
        print("   · 岗位 JD：贴到 data/jd.md")
        print("   · 错题本：先记几道错题（说「今天面了 X 被问 Y 没答上」）")
        return

    print("\n正在根据 简历 / JD / 错题本 生成结构化面试...")
    sections = plan_interview(profile["resume"], profile["jd"], weak_items)

    # 展开成章节化题目池（动态循环的「种子题」：每章先用计划题，深挖/换题时现场出）
    weak_by_id = {it.id: it for it in weak_items}
    pool_by_section: dict[str, list[dict]] = {}
    section_order: list[str] = []
    for sec in sections:
        name = sec.get("name", "")
        if not name or not sec.get("questions"):
            continue
        section_order.append(name)
        qs = []
        for q in sec.get("questions", []):
            q = dict(q)
            q["section"] = name
            # 防御 LLM 标错：weak 题必须「题目 == 错题原文」才绑定 item，否则降级为 generic
            if q.get("source") == "weak" and q.get("item_id"):
                item = weak_by_id.get(q.get("item_id"))
                if item and (q.get("question") or "").strip() == item.question.strip():
                    q["item"] = item
                else:
                    q["item"] = None
                    q["source"] = "generic"
            else:
                q["item"] = None
            qs.append(q)
        pool_by_section[name] = qs

    if not section_order:
        print("⚠️ 出题失败（可能 LLM 没返回计划），请重试。")
        return

    print(f"\n动态面试：{len(section_order)} 个章节，按表现动态调整题量与深度。每题最多追问 {MAX_FOLLOWUPS} 轮。")

    # ── 动态智能体循环：选下一题 → 出题 → 等回答 → 追问 → 决策 → 循环 ──
    _save_progress([], [], [])  # 面试开始：先落盘（动态题会逐步追加）
    questions, results = run_dynamic_session(
        section_order, pool_by_section, profile["resume"], profile["jd"], weak_items,
        ask_fn=lambda _round: input("\n你的回答："),
        on_save=lambda qs, rs: _save_progress(qs, rs, []),
        interrupted=True,
    )

    if not results:
        print("没有已答的题，本次不保存。")
        _clear_progress()
        return

    # ── 总结行为特征 + 写回 ──
    print("\n" + "=" * 60)
    print("面试结束，总结行为特征...")
    behaviors = summarize_behaviors([
        {"question": r["question"], "answer": r["answer"], "performance": r["performance"]}
        for r in results
    ])
    _save_progress(questions, results, behaviors)  # 总结后落盘（恢复时不重调 LLM）

    try:
        updated_items, new_items = _write_back(results, behaviors)
        store.store_items(updated_items + new_items)
        _log_write_back(results, updated_items)
        _clear_progress()  # 写库成功，清掉落盘
    except Exception as e:
        logging.warning("写库失败：%s", e)
        _save_progress(questions, results, behaviors)
        print("⚠️ 写库失败，结果已存到本地。")
        print("   稍后重跑 `python run_mock_interview.py --recover` 补写（不会重复涨分）。")
        return

    # ── 本场总结 ──
    print("\n" + "=" * 60)
    print("📊 本场总结：")
    for r in results:
        emoji = {"pass": "✅", "partial": "⚠️", "fail": "❌"}.get(r["performance"], "❓")
        if r.get("source") == "weak" and r.get("item"):
            note = "（已更新掌握度）"
        elif r["performance"] in ("fail", "partial"):
            note = "（已采集进错题本）"
        else:
            note = ""
        print(f"  {emoji} {r['question']}  {note}")

    if behaviors:
        print(f"\n🧠 你的行为特征：{', '.join(behaviors)}")
        print("   （已写入错题本，下次面试前会提醒你注意）")
    else:
        print("\n本次未发现明显行为问题。")

    # ── 复盘报告 ──
    report = generate_review_report(results, behaviors)
    if report:
        text = _format_review(report)
        print("\n" + text)
        # 落盘复盘报告，供 offerloop「看复盘」事后查阅
        try:
            (space_dir() / "last_review.md").write_text(text, encoding="utf-8")
        except Exception as e:
            logging.warning("复盘报告落盘失败：%s", e)
    else:
        print("\n（复盘报告生成失败）")

    print("\n完成。可用 python run_remind.py --notify 查看后续提醒。")


if __name__ == "__main__":
    # 解析 --space 参数（在 main/recover 之前，保证所有 space 相关路径/collection 生效）
    if "--space" in sys.argv:
        idx = sys.argv.index("--space") + 1
        if idx < len(sys.argv):
            _cfg.SPACE = sys.argv[idx]
    if "--recover" in sys.argv:
        recover()
    else:
        main()
