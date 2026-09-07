# -*- coding: utf-8 -*-
"""docs/38 §8.1 验证路径：SAMPLE 三路径真实跑 API handler，锁定演示稿。

数据与 frontend/components/workbench/PracticePanel.tsx 的 SAMPLE 常量同源
（v2 作答，2026-09-02；points 与 benchmark/data/henan_2025_city_1.json 的
reference_points 全量一致 → D41 trusted 可过，跑前可自查 _tmp_sync_check.py）。

走真实 app/api/shenlun 的 handler（SubmitRequest/InlineGold → practice_submit），
覆盖 D41 trusted 校验 / SCORE_FORCE 活引用 / §6 响应契约全链路。

路径（§8.1 三路径 + 补充 D41 400 两例）：
  1  门禁 trusted：gold.question_id="henan_2025_city_1" → 9 点
     status/matched_by/terms/evidence/anchor + 对照 §8.1 预期打点
  2  D41 400：伪造 qid（查无）· 篡改 points（与库题不一致）→ 400 detail 打印
  3  示证：同题去掉 question_id → 配对结果（无三色，c4/c9 应未见对应）
  4  强制示证：SCORE_FORCE="align" + qid → 仍走示证（演示录屏路径，D49）

用法（在 offerloop 根目录）：
  PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -X utf8 eval/calibrate_sample.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.api.shenlun import InlineGold, SubmitRequest, practice_submit  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from src import config as _cfg  # noqa: E402

QUESTION = "请根据“给定资料1”，梳理概括A区与B县在推动同城化发展中的举措和成效。"

# ── 与 SAMPLE.question/material 同源（PracticePanel.tsx SAMPLE）──
MATERIAL = (
    "清晨，A 区居民小陈准备烧饭，打开水龙头，清冽的自来水哗哗流出。这股来自 13 公里外 B 县最大饮用水源保护地三合水库的清泉，让 A 区 3 个街道的 16 万人“解了渴”。同饮一库水，得益于两地的同城化发展。A 区和 B 县地域相连且同属 C 市，主城区相距不到 20 公里，A 区人口众多、商贸发达，B 县人文和生态资源丰富。2018 年，在市政府主导下，两地签署战略合作协议，全力推动同城化发展，推进了 80 余项合作。B 县中医院的骨科远近闻名，这两年，从 A 区到 B 县来看骨伤的患者明显增多了。A 区商贸业发达，经常能看到成群结队的 B 县年轻人到 A 区逛街、消费。而 B 县的农家乐也很受A 区居民欢迎，去年前往 B 县乡村游的 A 区游客占总量的 50%。“这几年两地开通了城际公交，实现了高速公路免费互通，两地的互联互通还在进一步加速，未来将新建、提升改造 3条道路。”A 区交通运输局相关负责人介绍。2020 年 4 月，两地组织部门签署了人才协同发展战略合作框架协议，建立年轻干部互派挂职机制。现挂职 A 区文旅局副局长的 B 县青阳街道办马副主任在漫步 A 区文创街区时，想到青阳特色美食街，突然冒出一个想法，“两地各有优势，何不强强联手？”想到就干，他与同事合作，促成 A 区与 B 县召开文旅共建联席会议，积极推动两地开展“美食文创街区”旅游营销活动，协同打造县域消费目的地。“这几年，A 区高速发展对 B 县的辐射带动正在逐步增强，两地产业互补性、协调性还在加深。”B 县孙县长表示，“2024 年，B 县制造业投资增长超过 50%，增速位列全市第一。在 A 区新兴产业带动下，一批与其紧密关联的新能源项目相继落地 B 县，不仅完善了产业结构，也带动了装备制造、光伏光电、电子信息等新兴产业投资。”走进毗邻 A 区的 B 县黄龙工业园区，一栋栋现代化新厂房映入眼帘。近几年，该园区共落地企业 218 家，其中企业法人为 A 区籍的有 86 家。A 区某面膜生产企业负责人表示，2020年看准两地同城合作机遇，她在 B 县投资建起了新工厂。在市场需求带动下，A 区和 B 县之间已经形成了面膜上下游供应链企业紧密合作的生态圈。近期，两地的物流公司正积极谋划，在黄龙工业园区开展综合货运枢纽共建等项目。“我们在黄龙工业园建有物流仓库，在此集货后，可通过 A 区中欧班列、水运发往全世界。”A 区某物流公司负责人说，在 B 县建仓成本低、发货效率高。B 县某商业小区因地理位置优越、价格适中，项目一开盘就吸引了 500 余户 A 区市民前来投资置业。“在 A 区赚钱，在 B 县生活。”在 A 区做服装生意的小江选择将家安在 B 县，生活成本低、舒适度高，一家人在一起，幸福甜蜜。今年，B 县人社部门帮助推广 A 区的“找零工”App，将 A 区实时响应的零工招聘信息推送到 B 县用户手中，已帮助 1000 余名 B 县籍务工人员在 A 区找到了打短工的机会。B 县人社局就业科负责人说，家住 B 县城乡接合部的邹先生，忙时在家务农，闲时出门打工。这几年 A 区对零工需求很多，打包的、配货的、装运的，有时一干就是十天半个月，增加了不少收入。据统计，2019-2024 年 A 区 GDP 增幅达 31%，增幅高出 B 县约 11 个百分点。但在 A 区的带动下，B 县二三产业协同驱动的经济增长方式逐渐形成，多项经济指标增速在 C 市 9 个区县中名列前茅，显示出强劲的发展势头。虽然 2024 年 A 区 GDP 增速仍然高于 B 县，但两地增幅的差距，已由去年的 1.6 个百分点缩小到了 1.1 个百分点，目前“1+1>2”的区域发展格局初步形成。"
)

# ── 与 SAMPLE.points 同源（9 点，与库题 reference_points 全量一致）──
RAW_POINTS = [
    {"id": "c1", "point": "设施互通", "keywords": ["城际公交", "高速免费", "道路", "互通"], "score": 1, "point_type": "对策"},
    {"id": "c2", "point": "产业协同", "keywords": ["新兴产业", "新能源", "物流枢纽", "供应链"], "score": 1, "point_type": "对策"},
    {"id": "c3", "point": "服务共享", "keywords": ["医疗", "文旅", "营销活动"], "score": 1, "point_type": "对策"},
    {"id": "c4", "point": "人才共育", "keywords": ["干部互派", "人才协同", "挂职"], "score": 1, "point_type": "对策"},
    {"id": "c5", "point": "民生联动", "keywords": ["灵活就业", "置业", "零工"], "score": 1, "point_type": "对策"},
    {"id": "c6", "point": "经济共进", "keywords": ["GDP增长", "制造业投资", "差距缩小"], "score": 1, "point_type": "影响"},
    {"id": "c7", "point": "产业升级", "keywords": ["二三产业", "产业结构"], "score": 1, "point_type": "影响"},
    {"id": "c8", "point": "民生提质", "keywords": ["就医", "消费", "就业", "幸福感"], "score": 1, "point_type": "影响"},
    {"id": "c9", "point": "格局初成", "keywords": ["1+1>2", "协同效应"], "score": 1, "point_type": "影响"},
]

# ── 与 SAMPLE.answer 同源（2026-09-02 v2 重构稿）──
ANSWER = (
    "A区与B县地域相连、同属C市，在市政府主导下签署战略合作协议，全力推动同城化发展。"
    "举措方面：一是设施互通，两地开通城际公交，实现高速公路免费互通，并规划新建、提升改造3条道路。"
    "二是产业协同，在A区新兴产业带动下，一批新能源项目相继落地B县，双方共建综合货运枢纽，形成面膜上下游供应链生态圈。"
    "三是服务共享，推动医疗、文旅等资源互通共享，方便群众跨区使用。"
    "四是民生保障，促进两地群众就业增收。"
    "成效方面：一是经济共进，A区GDP增幅达31%，B县制造业投资增速位列全市第一，两地增速差距由1.6个百分点缩小到1.1个百分点。"
    "二是产业升级，两地积极培育数字经济、人工智能等新兴产业动能。"
    "三是民生提质，不断增强两地群众的获得感、幸福感、安全感。"
)

QID = "henan_2025_city_1"


def gold_of(points: list[dict] | None = None, qid: str | None = QID) -> InlineGold:
    """SAMPLE gold（qid 缺省带库题声明；points 缺省 = 与库题一致的 9 点）。"""
    return InlineGold(
        question_id=qid or "",
        qtype="归纳概括",
        question=QUESTION,
        material=MATERIAL,
        points=points or RAW_POINTS,
    )


def _flag(ok: bool) -> str:
    return "✓" if ok else "✗"


def _run(req: SubmitRequest, title: str):
    """跑一次评分请求，返回 dict（HTTPException 向上抛，由调用方按 400 处理）。"""
    print(f"\n{'─' * 70}\n▶ {title}")
    return practice_submit(req)


def path1_gate():
    """§8.1-1 门禁 trusted：9 点 status/terms/evidence/anchor + 预期对照。"""
    out = _run(SubmitRequest(gold=gold_of(), answer=ANSWER), "路径1 门禁 trusted（qid + 与库题一致的 points）")
    assert out["mode"] == "gate", f"期望 gate，实测 {out['mode']}"
    print(f"mode=gate · warnings={out['warnings'] or '（无）'}\n")

    print(f"{'id':<4}{'点':<8}{'status':<9}{'matched_by':<5}terms.matched / terms.missing   evidence     anchor")
    counts = {"hit_kw": 0, "hit_llm": 0, "miss": 0, "suspect": 0}
    for v in out["verdicts"]:
        s = v["status"]
        if s == "hit":
            counts["hit_kw" if v["matched_by"] == "kw" else "hit_llm"] += 1
        elif s == "miss":
            counts["miss"] += 1
        else:
            counts["suspect"] += 1
        ev = v["evidence"] or "（空）"
        anc = "有锚" if v["anchor"] else "无锚"
        extra = f" suspect={v['suspect']['label']}" if v["suspect"] else ""
        print(f"{v['point_id']:<4}{v['point_name']:<8}{s:<9}{v['matched_by']:<5}"
              f"命中[{','.join(v['terms']['matched']) or '—'}] 缺失[{','.join(v['terms']['missing']) or '—'}]  {ev[:18]!r:<22}{anc}{extra}")
    print(f"\n分布：绿·关键词 {counts['hit_kw']} · 绿·语义放行 {counts['hit_llm']} · 黄·漏答 {counts['miss']} · 蓝·疑似 {counts['suspect']}（共 {len(out['verdicts'])} 点）")

    # §8.1 预期对照（v2 作答）：LLM 依赖项打 ? 待人工验收
    by = {v["point_id"]: v for v in out["verdicts"]}
    print("\n§8.1 预期对照：")
    for pid, want in [("c1", "绿"), ("c2", "绿"), ("c3", "绿"), ("c6", "绿")]:
        got = by[pid]
        ok = got["status"] == "hit"
        kind = "关键词" if ok and got["matched_by"] == "kw" else ("语义放行" if ok else got["status"])
        print(f"  {_flag(ok)} {pid} 期望绿（{want}），实测 {got['status']}/{kind}" + ("" if ok else " — 见 §8.3 偏差汇报"))
    for pid in ["c4", "c9"]:
        v = by[pid]
        ok = v["status"] == "miss" and v["evidence"] == "" and v["terms"]["missing"]
        print(f"  {_flag(ok)} {pid} 期望黄·漏答且 evidence 空、missing 列缺失词，实测 {v['status']} evidence={v['evidence'] or '空'!r} missing={v['terms']['missing']}")
    gray_actual = [pid for pid in ["c5", "c7", "c8"] if by[pid]["status"] == "gray"]
    print(f"  ? c5/c7/c8 文档预期进灰带 → LLM 判定；实测灰带（运行前规则层）与 LLM 结果见上（LLM 依赖，人工验收）")
    return out


def path2_d41():
    """§8.1 补充：D41 两道 400（伪造 qid · 篡改 points）应被拒，不蹭门禁。"""
    import json
    for title, req in [
        ("D41-1 伪造 qid（查无此题）", SubmitRequest(gold=gold_of(qid="henan_fake"), answer=ANSWER)),
        ("D41-2 声明 qid 但篡改 points（c1 删一个 keyword）",
         SubmitRequest(gold=gold_of(points=[{**p, "keywords": p["keywords"][:-1] if p["id"] == "c1" else p["keywords"]} for p in RAW_POINTS]), answer=ANSWER)),
        ("D41-3 声明 qid 但点集不同（自造 2 点蹭 c1/c2）",
         SubmitRequest(gold=gold_of(points=[RAW_POINTS[0], RAW_POINTS[1]]), answer=ANSWER)),
    ]:
        try:
            out = practice_submit(req)
            print(f"\n✗ {title} —— 未被拦截！mode={out.get('mode')}")
        except HTTPException as e:
            print(f"\n✓ {title}\n  HTTP {e.status_code}: {e.detail}")
        except Exception as e:  # noqa: BLE001
            print(f"\n✗ {title} —— 非预期异常: {type(e).__name__}: {e}")
    print("\n（json 引用仅供人工核对 detail 文案）")


def path3_align():
    """§8.1-2 示证：同题去掉 question_id → 差异配对，无三色。"""
    out = _run(SubmitRequest(gold=gold_of(qid=""), answer=ANSWER), "路径3 示证（无 qid 内联同题）")
    assert out["mode"] == "align", f"期望 align，实测 {out['mode']}"
    pairs = out["alignments"]
    gapped = {g["point_id"] for g in out["gaps"]}
    orphans = out["orphans"]
    print(f"mode=align · 配对 {len(pairs)} 组 · 未见对应 {len(out['gaps'])} 点 · 无对应句 {len(orphans)} 句 · meta={out['meta']}")
    for p in out["official_points"]:
        items = [a for a in pairs if a["point_id"] == p["id"]]
        if items:
            for a in items:
                if a["method"] == "kw":
                    print(f"  {p['id']} {p['point']}: ◎ 作答句 {a['chunk_id']} 含关键词 {a['kws_hit']}")
                else:
                    print(f"  {p['id']} {p['point']}: ~ 作答句 {a['chunk_id']} 语义弱对应（相似度 {a['similarity']}）")
        else:
            print(f"  {p['id']} {p['point']}: ○ 未见对应句（候选）")
    ok_c4c9 = {"c4", "c9"} <= gapped
    print(f"\n§8.1-2 检查：c4/c9 标「未见对应」→ {_flag(ok_c4c9)}（gaps={sorted(gapped)}）")
    return out


def path4_force_align():
    """§8.1-3 SCORE_FORCE=align：带 qid 也强制示证（演示录屏路径，D49 活引用）。"""
    _cfg.SCORE_FORCE = "align"  # api 层活引用 src.config → 直接改属性即生效
    try:
        out = _run(SubmitRequest(gold=gold_of(), answer=ANSWER),
                   "路径4 强制示证 SCORE_FORCE=align（带 qid，应仍走示证）")
        print(f"mode={out['mode']}" + (" ✓ 被强制" if out["mode"] == "align" else " ✗ 未生效"))
    finally:
        _cfg.SCORE_FORCE = None


if __name__ == "__main__":
    print("═" * 70)
    print("docs/38 §8.1 验证路径 · SAMPLE（henan_2025_city_1，v2 作答，9 点）")
    print("═" * 70)
    g1 = path1_gate()
    path2_d41()
    a1 = path3_align()
    path4_force_align()
    print("\n═" * 70)
    print(f"gate: {g1['mode']}（{len(g1['verdicts'])} 点） · align: {a1['mode']}（配对 {len(a1['alignments'])} 组）")
    print("LLM 依赖行（灰带标注）请与 docs/38 §8.3 演示预期人工核对后再锁演示稿。")
