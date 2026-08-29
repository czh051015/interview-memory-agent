"""能力诊断端点 —— 三层诊断聚合（docs/13 §7 — §8，R1+R2 后端）。

GET /api/diagnose →
{
  "by_type":  {"归纳概括": {"total", "red", "miss_sum"}, ...},  # L1 题型层
  "by_angle": {"对策": {"total", "red", "miss_sum"}, ...},      # L2 角度层（L2 是该诊断的护城河）
  "total_points": N
}

确定性聚合，不调 LLM；数据源 = weak_points 档案（read_all_weak_points）。
"""
from fastapi import APIRouter

from src.shenlun.profile import diagnose

router = APIRouter()


@router.get("/diagnose")
def get_diagnose():
    """当前薄弱点三层诊断（题型 → 角度 → 薄弱点）。"""
    return diagnose()