"""CLI 入口（07 计划 T6）：main()。recover 入口在此调用 runtime.recover。"""

import logging

import src.config as _cfg  # 活引用：CLI --space 在 import 后改 _cfg.SPACE
from src.config import space_dir
from src.mock import (
    get_weak_questions,
    plan_interview,
    run_dynamic_session,
    recover,
    summarize_behaviors,
    generate_review_report,
    _format_review,
    apply_verdict,
    _save_progress,
    _clear_progress,
    MAX_FOLLOWUPS,
)
from .plan import _read_profile


def main():
    print("=" * 60)
    print("OfferLoop 模拟面试 · 结构化面试官")
    print("=" * 60)

    profile = _read_profile(space=_cfg.SPACE)
    weak_items = get_weak_questions()

    if not profile["resume"] and not profile["jd"] and not weak_items:
        print("\n⚠️ 没有可面试的材料：")
        print("   · 简历：把内容贴到 data/resume.md")
        print("   · 岗位 JD：贴到 data/jd.md")
        print("   · 错题本：先记几道错题（说「今天面了 X 被问 Y 没答上」）")
        return

    # 记忆管家：读记忆状态 + 用户画像 → 注入出题（出题靠记忆的闭环）
    focus_topics: list[str] = []
    profile_text: str = ""
    user_profile = None  # 兜底：异常时保持 None，出题不依赖画像
    try:
        from src.memory import memory_keeper as keeper
        from src.memory import profile as profile_mod
        keeper_plan = keeper.run(_cfg.SPACE, notify=False)
        focus_topics = keeper_plan.get("focus_topics") or []
        # 用户画像（P1）：确定性聚合 + LLM 提炼，空画像降级（冷启动）
        user_profile = profile_mod.build_profile(_cfg.SPACE, save=True)
        if user_profile.summary:
            pass
        elif not user_profile.empty:
            user_profile.summary = profile_mod.refine_summary(user_profile)
            profile_mod._save(user_profile, _cfg.SPACE)
        profile_text = user_profile.to_prompt_text()
        if focus_topics:
            print(f"🧠 记忆管家薄弱主题：{'、'.join(focus_topics)} → 技术验证章优先覆盖")
        if profile_text:
            print("📋 已生成用户画像（弱点地图），面试官将据此出题")
    except Exception as e:
        logging.warning("记忆管家/画像读取失败，继续出题：%s", e)

    print("\n正在根据 简历 / JD / 错题本 / 用户画像 生成结构化面试...")
    sections = plan_interview(
        profile["resume"], profile["jd"], weak_items,
        focus_topics=focus_topics, profile_text=profile_text,
    )

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
        weak_topics=user_profile.weak_topic_names() if user_profile else None,
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
        apply_verdict(results, behaviors, space=_cfg.SPACE)
        _clear_progress()  # 写库成功，清掉落盘
    except Exception as e:
        logging.warning("写库失败：%s", e)
        _save_progress(questions, results, behaviors)
        print("⚠️ 写库失败，结果已存到本地。")
        print("   稍后重跑 `python -m src.mock --recover` 补写（不会重复涨分）。")
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