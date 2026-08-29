"""【已废弃 · docs/18】面试官出题依据：读错题薄弱项 + 读简历/JD（07 计划 T2）。

申论练习不按章节出题（按 ReAct 推荐/题库抽），本文件保留可导入，
仅因 Web 模拟面试（app/api/mock.py）仍在引用；新代码不得使用。
（_PLAN_PROMPT 从 prompts.py 内联到本文件，随废弃模块共进退。）
"""

import logging

import src.config as _cfg  # 活引用：CLI --space 在 import 后改 _cfg.SPACE
from src.memory import knowledge_store as store
from src.memory import mastery
from . import WEAK_POOL_SIZE
# 活引用：DATA_DIR / space_dir / chat_json 一律经包取当前属性
# （测试 monkeypatch 的是 src.mock 包命名空间，如 setattr(mi, "DATA_DIR", tmp_path)；
# 模块级绑定会缓存旧值，patch 穿透不进来）
import src.mock as _mi

# ── 面试域 prompt（废弃模块自用，从 prompts.py 内联而来）──
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
    "记忆管家薄弱主题（如提供）：技术验证章出题时应优先覆盖这些主题。\n\n"
    "source 取值：generic / resume / jd / weak / behavior / motivation。\n"
    "item_id 规则（严格）：只有「技术验证」章里、且题目是直接抄错题原文的题，才允许 source=weak 并填对应 item_id；其余所有题（自我介绍/项目深挖/行为面/动机面）source 一律不能是 weak，item_id 一律 null。\n"
    "topic：每题一个简短主题标签（如 RAG、线程池、项目深挖、职业规划），用于归档。\n"
    "题目要求：具体、可深挖、贴合候选人材料，不要泛泛的背诵题。"
)


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


def plan_interview(
    resume: str,
    jd: str,
    weak_items,
    focus_topics: list[str] | None = None,
    profile_text: str = "",
) -> list[dict]:
    """LLM 生成章节化面试计划。失败返回 []（主流程提示重试）。

    focus_topics：记忆管家提炼的薄弱主题（可选），注入技术验证章出题优先覆盖。
    profile_text：用户画像文本（P1，可选），给面试官「候选人是谁」的全局视角。
    """
    weak_str = "\n".join(f"- [{it.id}] {it.question}" for it in weak_items) if weak_items else "（无）"
    topics_str = "、".join(focus_topics) if focus_topics else "（无）"
    user_prompt = (
        f"## 候选人简历\n{resume or '（未提供）'}\n\n"
        f"## 岗位 JD\n{jd or '（未提供）'}\n\n"
        f"## 历史薄弱项\n{weak_str}\n\n"
        f"## 记忆管家薄弱主题\n{topics_str}"
        + (f"\n\n## 候选人画像\n{profile_text}" if profile_text else "")
    )
    try:
        data = _mi.chat_json(_PLAN_PROMPT, user_prompt, max_tokens=4096)
        return data.get("sections", [])
    except Exception as e:
        logging.warning("生成面试计划失败：%s", e)
        return []


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


def _read_doc(name: str, space: str | None = None) -> str:
    """按 .pdf → .md → .txt 优先级读文档，命中一个非空就返回。

    若传 space，优先从 data/spaces/{space}/ 读取。
    非 default 空间不 fallback（新空间显示空）；default 空间 fallback 到 data/ 根目录（向后兼容）。
    """
    # 优先级 1：per-space 目录
    if space is not None:
        sp = _mi.space_dir(space)
        for ext in (".pdf", ".md", ".txt"):
            path = sp / f"{name}{ext}"
            if not path.exists():
                continue
            try:
                text = _read_pdf_text(path) if ext == ".pdf" else path.read_text(encoding="utf-8").strip()
            except Exception as e:
                logging.warning("读取 %s（space=%s）失败：%s", path.name, space, e)
                continue
            if text:
                return text
        # per-space 没有 → 非 default 空间直接返回空
        if space != "default":
            return ""
    # 优先级 2：data/ 根目录（仅 default 空间/无 space 时）
    for ext in (".pdf", ".md", ".txt"):
        path = _mi.DATA_DIR / f"{name}{ext}"
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


def _read_profile(space: str | None = None) -> dict:
    """读简历和 JD。支持 .pdf / .md / .txt，优先 .pdf；缺失/失败返回空（对应章节跳过）。

    若传 space，优先从 data/spaces/{space}/ 读取，找不到则 fallback 到 data/ 根目录。
    """
    return {"resume": _read_doc("resume", space=space), "jd": _read_doc("jd", space=space)}