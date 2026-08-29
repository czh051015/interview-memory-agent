"""申论题目入库工具 —— 上传题目+标答 → LLM 拆采分点 → 人工审核 → 入库（docs/16）。

用法：
    python scripts/run_decompose_question.py                                # 交互：题目/要求/材料/满分/标答
    python scripts/run_decompose_question.py --from-benchmark jiangsu_2023_a_1   # 语境取官方金标，只输标答（验收步1）
    python scripts/run_decompose_question.py --standard 标答.txt            # 标答从文件读（支持 .txt/.md）

流程（对应 docs/16 §5）：
    1. decompose_points()：LLM 拆标准答案为采分点（approved=False）
    2. annotate_points()：人工审核闸门（k确认/s改分/w改词/d删除/a新增/x跳过）
    3. 全部通过 → 写 data/user_questions/{id}.json（benchmark 格式，meta.authority="user"）
       未全部通过 → 整批保持草稿，不入库

用 Anaconda Python 跑：D:/ProgramData/anaconda3/python.exe scripts/run_decompose_question.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from src.config import DATA_DIR
from src.cleaner.decompose import decompose_points
from src.cleaner.annotate import annotate_points
from src.cleaner.schema import utcnow
from src.shenlun.reflow import load_question, USER_QUESTIONS_DIR


def _read_text_file(path: str) -> str:
    p = Path(path)
    if not p.exists():
        print(f"找不到文件: {path}")
        sys.exit(1)
    return p.read_text(encoding="utf-8", errors="replace")


def _next_question_id() -> str:
    """自动生成 id：user_YYYYMMDD_NN（NN 按当天已入库数递增）。"""
    day = utcnow().strftime("%Y%m%d")
    prefix = f"user_{day}_"
    n = 1
    if USER_QUESTIONS_DIR.exists():
        n = sum(1 for f in USER_QUESTIONS_DIR.glob(f"{prefix}*.json")) + 1
    return f"{prefix}{n:02d}"


def _gather(args) -> dict:
    """收集题目语境 + 标准答案。--from-benchmark 时语境取自官方金标。"""
    ctx = {"question": "", "requirements": "", "material": "", "max_score": 0,
           "standard_answer": "", "question_id": "", "official_gold": None}

    if args.from_benchmark:
        item = load_question(args.from_benchmark)
        if item is None:
            print(f"题库里没有 {args.from_benchmark}")
            sys.exit(1)
        task = item["task"]
        ctx.update(question=task["question"], requirements=task.get("requirements", ""),
                   material=task.get("material", ""), max_score=task.get("max_score", 0))
        ctx["official_gold"] = item.get("gold", {}).get("reference_points")
        print(f"语境取自官方金标：{args.from_benchmark}（满分 {ctx['max_score']}）")
        if ctx["official_gold"]:
            print(f"官方金标点（对照用）：{', '.join(p['point'] for p in ctx['official_gold'])}")

    if not ctx["question"]:
        ctx["question"] = input("题目: ").strip()
        ctx["requirements"] = input("要求（可回车跳过）: ").strip()
        ctx["material"] = input("材料（给定资料，可回车跳过）: ").strip()
        try:
            ctx["max_score"] = int(input("满分: ").strip() or 0)
        except ValueError:
            ctx["max_score"] = 0

    if args.standard:
        ctx["standard_answer"] = _read_text_file(args.standard)
    elif not ctx["question"]:
        # --from-benchmark 时题目语境已有，标答单独问
        ctx["standard_answer"] = input("标准答案（可贴全文；或 ctrl+z 结束多行输入）: ").strip()
    else:
        ctx["standard_answer"] = input("标准答案: ").strip()

    if not ctx["standard_answer"]:
        print("标准答案不能为空")
        sys.exit(1)

    ctx["question_id"] = args.id or _next_question_id()
    return ctx


def _save_user_question(ctx: dict, result) -> None:
    """写 data/user_questions/{id}.json（benchmark 兼容格式，authority=user）。"""
    USER_QUESTIONS_DIR.mkdir(parents=True, exist_ok=True)
    points = [{
        "id": p.id,
        "point": p.point,
        "keywords": p.keywords,
        "score": p.score,
        "approved": p.approved,
        "source": p.source,
    } for p in result.reference_points]
    doc = {
        "id": ctx["question_id"],
        "domain": "shenlun",
        "meta": {
            "province": "用户上传",
            "year": "",
            "paper": "",
            "type": "用户上传",
            "authority": "user",
            "source": "用户上传标准答案，经 LLM 拆解 + 人工审核（decompose_points → annotate_points）",
        },
        "task": {
            "question": ctx["question"],
            "requirements": ctx["requirements"],
            "material": ctx["material"],
            "max_score": ctx["max_score"],
        },
        "gold": {
            "reference_points": points,
            "scoring_note": "用户上传题：采分点经人工审核（全部确认通过）后入库；source 保留 llm_draft/human_approved 溯源。",
        },
    }
    path = USER_QUESTIONS_DIR / f"{ctx['question_id']}.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 已入库: {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="申论题目入库：拆采分点 → 人工审核 → 入库")
    ap.add_argument("--from-benchmark", metavar="ID", help="题目语境取自官方金标（验收对比用）")
    ap.add_argument("--standard", metavar="FILE", help="标准答案从文件读（.txt/.md）")
    ap.add_argument("--id", metavar="SLUG", help="入库 id（默认自动 user_YYYYMMDD_NN）")
    args = ap.parse_args()

    ctx = _gather(args)

    print("\n=== 步骤1 · LLM 拆解采分点 ===")
    result = decompose_points(
        ctx["standard_answer"],
        question=ctx["question"],
        requirements=ctx["requirements"],
        material=ctx["material"],
        max_score=ctx["max_score"],
        question_id=ctx["question_id"],
    )
    print(f"拆出 {len(result.reference_points)} 个采分点：")
    for p in result.reference_points:
        print(f"  [{p.id}] {p.point}  keywords: {'/'.join(p.keywords)}  score: {p.score}")

    print("\n=== 步骤2 · 人工审核闸门 ===")
    result = annotate_points(result, input)

    print("\n=== 步骤3 · 入库 ===")
    if result.all_approved:
        _save_user_question(ctx, result)
    else:
        print(f"整批未全部通过（通过 {result.approved_count}/{len(result.reference_points)}），保持草稿不入库。")
        print("可重新运行本脚本，审核确认所有点后再入库；或换更完整的标准答案重拆。")
        for w in result.warnings:
            print(f"  ⚠ {w}")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\n已取消")
