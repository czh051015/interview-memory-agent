"""用户题入库唯一实现（docs/实施计划 任务一：录入页补落库闭环）。

背景：录题闭环此前只有 CLI（scripts/run_decompose_question.py 里自带的
_next_question_id/_save_user_question），录入页只预览不落库。为防两份实现漂移
（CLI 与页面各写一遍 user_questions 格式），把入库逻辑抽到这里作为唯一实现：
CLI 改 import 本模块（行为不变），录入页确认入库走新端点（本模块同源）。

入库语义（防循环论证，docs/16 §3.4 / schema.py:90 注释）：
  - 页面点「确认入库」= 全部采分点人工通过（等价 CLI annotate_points 全 k）
    → 写库统一补 approved=True, source="human_approved"；
  - doc 结构与 CLI 逐字段一致（meta.authority="user"，task/gold 布局同
    run_decompose_question._save_user_question），供 load_question/推题/门禁全链路复用。

目录常量活引用 reflow.USER_QUESTIONS_DIR（不 from-import 绑定值），测试 monkeypatch
模块属性即隔离真实 data/user_questions/。
"""
from __future__ import annotations

import json

from src.cleaner.schema import utcnow
from src.shenlun import reflow

META_SOURCE_NOTE = (
    "用户上传标准答案，经 LLM 拆解 + 人工审核（decompose_points → annotate_points）"
)


def next_user_question_id() -> str:
    """自动生成 id：user_YYYYMMDD_NN（NN = 当天已入库最大序号 + 1）。

    连续入库（无删文件）时与 CLI 原 count+1 语义等价；文件有洞（手动删过）时
    max+1 保证不覆盖已有题目（原 count+1 会撞回已有序号覆盖旧题，此处修正）。
    """
    day = utcnow().strftime("%Y%m%d")
    prefix = f"user_{day}_"
    n = 1
    if reflow.USER_QUESTIONS_DIR.exists():
        nums = []
        for f in reflow.USER_QUESTIONS_DIR.glob(f"{prefix}*.json"):
            try:
                nums.append(int(f.stem[len(prefix):]))
            except ValueError:
                continue  # 非数字尾缀文件不参与计数
        if nums:
            n = max(nums) + 1
    return f"{prefix}{n:02d}"


def save_user_question(
    *,
    question_id: str,
    question: str,
    requirements: str = "",
    material: str = "",
    max_score: int = 20,
    points: list[dict],
) -> str:
    """写 data/user_questions/{question_id}.json（benchmark 兼容格式，authority=user）。

    points 每项 {id, point, keywords, score, point_type}——写库时统一补
    approved=True / source="human_approved"（页面确认/CLI 全 k 通过 = 等价人审）。

    Returns: 写入的路径（str，供调用方展示）。
    """
    reference_points = []
    for p in points:
        reference_points.append({
            "id": str(p.get("id") or ""),
            "point": str(p.get("point") or ""),
            "keywords": [str(k) for k in (p.get("keywords") or [])],
            "score": int(p.get("score") or 0),
            "point_type": str(p.get("point_type") or ""),
            # 页面「确认入库」/ CLI 全通过 = 全部点人工通过（防循环论证：LLM 拆的点不
            # 经人审不得成为可信金标，schema.py:90 注释）
            "approved": True,
            "source": "human_approved",
        })
    doc = {
        "id": question_id,
        "domain": "shenlun",
        "meta": {
            "province": "用户上传",
            "year": "",
            "paper": "",
            "type": "用户上传",
            "authority": "user",
            "source": META_SOURCE_NOTE,
        },
        "task": {
            "question": question,
            "requirements": requirements,
            "material": material,
            "max_score": max_score,
        },
        "gold": {
            "reference_points": reference_points,
            "scoring_note": (
                "用户上传题：采分点经人工审核（全部确认通过）后入库；"
                "source 保留 llm_draft/human_approved 溯源。"
            ),
        },
    }
    d = reflow.USER_QUESTIONS_DIR
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{question_id}.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)
