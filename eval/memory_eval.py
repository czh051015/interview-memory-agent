"""memory 档评测 —— 验证受控记忆闭环的生命周期行为（docs/17 机制的固定回归）。

背景：现有 4 套件（score/decompose/demo/medium）全在测评分侧，回流→档案→毕业→
隔离→提醒这条记忆闭环没有评测。本套件用多轮练习序列（临时库，每场景独立）驱动
reflow/profile 真实代码路径，断言生命周期行为，产出达标型数字。

口径（2026-09-08 冻结，先定后跑，跑完不调参重跑）：
  10 场景 × 22 检查项，全部确定性 0 LLM token，真实参数（不 patch MAX_ATTEMPTS）：
    S1  毕业正路径      连续命中 3 + 间隔 ≥7 天 → 候选 → 毕业考命中 → graduated 且退出提醒池
    S2  连击不足不毕业  连续命中 2 → 非候选，毕业考命中也不毕业
    S3  间隔不足不毕业  连续命中 3 但间隔 1 天 → 间隔验证拦截（非候选）
    S4  毕业考失败归零  候选 + 毕业考 miss → 不毕业且 consecutive_hits 归零
    S5  隔离防死锁      30 轮全漏（真实 MAX_ATTEMPTS）→ stuck 且退出提醒池
    S6  隔离复活        stuck 点再练 → 回 active + events 记 revive
    S7  遗忘衰减排序    同漏 1 次，8 天未练排在前（紧急度 = 弱点权重 × 遗忘程度）
    S8  提醒池过滤      graduated/stuck 不进池、pinned 进池、完整档案保留（只出池不删档）
    S9  疑似溯源（红线）suspect 点按 miss 入库（B1 判据统一）且 events 必留 suspect 行
    S10 内联零通道（红线）非库内 qid 走 practice/complete → 404，weak_points 零写入

summary 顶层字段（供 run_evals extract_summary 扁平化）：
    memory_pass_rate   达标率 = passed/total（↑，HEADLINE 接入项）
    inline_reflow_leak 内联回流泄漏（↓，红线须 0：泄漏=complete 非 404 或 weak_points 有写入）
    suspect_untraced   疑似入库缺溯源行数（↓，红线须 0）
    llm_calls          恒 0（纯确定性）

用法：
  python eval/memory_eval.py            # 跑全部场景，json 落 eval/results/baseline/
  python eval/memory_eval.py --out x.json
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, ROOT := os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

from src.shenlun import profile, reflow
from src.shenlun.reflow import (
    ACTION_GRADUATION_CHECK,
    ACTION_REVIVE,
    GRADUATE_SPACING_DAYS,
    MAX_ATTEMPTS,
    graduate_hits,
    reflow_answer,
)

# 单题 3 采分点（与 tests/test_shenlun_memory.py 同款，关键词互不重叠，便于逐点控制 hit/miss）
QID = "jiangsu_2023_a_1"
QTYPE = "归纳概括"
REFS = [
    {"id": "c1", "point": "六尺巷·化解纠纷", "keywords": ["六尺巷"], "score": 3},
    {"id": "c2", "point": "河长制·治水", "keywords": ["河长"], "score": 3},
    {"id": "c3", "point": "生态理念·象群", "keywords": ["象群"], "score": 4},
]
KEY = f"{QID}:c1"  # 主角点（各场景统一操作 c1，c2/c3 当对照）


class Scenario:
    """一个场景 = 临时库 + 多轮作答 + 若干命名检查项。检查失败只记录不中断。"""

    def __init__(self, sid: str, desc: str):
        self.sid, self.desc = sid, desc
        self.tmp = tempfile.TemporaryDirectory(prefix=f"memory_eval_{sid}_")
        self.db_path = Path(self.tmp.name) / "eval.db"
        self._old_reflow_db, self._old_profile_db = reflow.DB_PATH, profile.DB_PATH
        reflow.DB_PATH = self.db_path
        profile.DB_PATH = self.db_path
        self.checks: list[dict] = []

    def close(self):
        reflow.DB_PATH, profile.DB_PATH = self._old_reflow_db, self._old_profile_db
        self.tmp.cleanup()

    def answer(self, text: str, *, action: str = "answered", verdicts: list[dict] | None = None):
        return reflow_answer(QID, QTYPE, text, REFS, action=action, verdicts=verdicts)

    def backdate(self, key: str, days: float):
        """把某点的 last_hit_at/last_practiced_at 拨到 N 天前（模拟间隔，不 sleep）。"""
        past = (datetime.utcnow() - timedelta(days=days)).isoformat()
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute(
                "UPDATE weak_points SET last_hit_at=?, last_practiced_at=? WHERE point_key=?",
                (past, past, key),
            )
            conn.commit()
        finally:
            conn.close()

    def row(self, key: str) -> dict | None:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            r = conn.execute("SELECT * FROM weak_points WHERE point_key=?", (key,)).fetchone()
            return dict(r) if r else None
        finally:
            conn.close()

    def event_actions(self) -> list[str]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            return [r["action"] for r in conn.execute("SELECT action FROM events").fetchall()]
        finally:
            conn.close()

    def pool_keys(self) -> set[str]:
        return {wp.point_key for wp in profile.read_weak_points()}

    def check(self, name: str, ok: bool, detail: str = ""):
        self.checks.append({"name": name, "ok": bool(ok), "detail": detail})

    def candidates(self) -> set[str]:
        return {wp.point_key for wp in profile.graduation_candidates()}


# ── S1-S4：毕业闭环 ─────────────────────────────────────────────────
def s1_graduate_full_path() -> Scenario:
    sc = Scenario("S1", "毕业正路径：连击3+间隔8天 → 候选 → 毕业考命中 → graduated 退出提醒池")
    for _ in range(3):
        sc.answer("六尺巷")  # c1 hit，c2/c3 miss
    sc.backdate(KEY, GRADUATE_SPACING_DAYS + 1)
    cand = sc.candidates()
    sc.check("毕业候选成立", KEY in cand, f"candidates={sorted(cand)}")
    r = sc.answer("六尺巷", action=ACTION_GRADUATION_CHECK)  # 毕业考：c1 命中
    done = graduate_hits(QID, r.result.hit_ids, cand)
    sc.check("毕业考命中即毕业", done == ["c1"], f"graduated={done}")
    row = sc.row(KEY)
    sc.check("毕业点退出提醒池", KEY not in sc.pool_keys() and row["state"] == "graduated",
             f"state={row['state']}")
    return sc


def s2_graduate_consec_short() -> Scenario:
    sc = Scenario("S2", "连击不足：命中 2 次（<3）→ 非候选，毕业考命中也不毕业")
    for _ in range(2):
        sc.answer("六尺巷")
    sc.backdate(KEY, GRADUATE_SPACING_DAYS + 1)
    cand = sc.candidates()
    sc.check("连击不足非候选", KEY not in cand, f"consecutive_hits={sc.row(KEY)['consecutive_hits']}")
    r = sc.answer("六尺巷", action=ACTION_GRADUATION_CHECK)
    done = graduate_hits(QID, r.result.hit_ids, cand)
    sc.check("未候选不毕业", done == [] and sc.row(KEY)["state"] == "active", f"graduated={done}")
    return sc


def s3_graduate_spacing_short() -> Scenario:
    sc = Scenario("S3", "间隔不足：连击 3 但距 last_hit 仅 1 天（<7）→ 间隔验证拦截")
    for _ in range(3):
        sc.answer("六尺巷")
    sc.backdate(KEY, 1.0)
    cand = sc.candidates()
    sc.check("间隔不足非候选", KEY not in cand, f"candidates={sorted(cand)}")
    return sc


def s4_graduate_exam_miss() -> Scenario:
    sc = Scenario("S4", "毕业考失败：候选点毕业考 miss → 不毕业且连续命中归零")
    for _ in range(3):
        sc.answer("六尺巷")
    sc.backdate(KEY, GRADUATE_SPACING_DAYS + 1)
    cand = sc.candidates()
    r = sc.answer("河长 象群", action=ACTION_GRADUATION_CHECK)  # 毕业考不含 c1 → miss
    done = graduate_hits(QID, r.result.hit_ids, cand)
    row = sc.row(KEY)
    sc.check("考砸不毕业", KEY not in done and row["state"] == "active", f"state={row['state']}")
    sc.check("连击归零重来", row["consecutive_hits"] == 0, f"consecutive_hits={row['consecutive_hits']}")
    return sc


# ── S5-S6：隔离与复活 ───────────────────────────────────────────────
def s5_stuck_deadlock() -> Scenario:
    sc = Scenario("S5", f"隔离防死锁：{MAX_ATTEMPTS} 轮全漏（真实参数）→ stuck 退出提醒池")
    for _ in range(MAX_ATTEMPTS):
        sc.answer("空白作答，不含任何关键词")
    row = sc.row(KEY)
    sc.check("长期不补转隔离", row["state"] == "stuck", f"attempts={row['miss_count'] + row['hit_count']}")
    sc.check("隔离点退出提醒池", KEY not in sc.pool_keys(), "")
    return sc


def s6_stuck_revive() -> Scenario:
    sc = Scenario("S6", "隔离复活：stuck 点再练 → 回 active + events 记 revive")
    for _ in range(MAX_ATTEMPTS):
        sc.answer("空白作答，不含任何关键词")
    pre = sc.row(KEY)["state"]
    sc.answer("六尺巷")  # c1 命中 → 复活
    row = sc.row(KEY)
    sc.check("隔离前状态为 stuck", pre == "stuck", f"pre={pre}")
    sc.check("再练复活回 active", row["state"] == "active", f"state={row['state']}")
    sc.check("events 留 revive 行", ACTION_REVIVE in sc.event_actions(), "")
    return sc


# ── S7-S8：提醒池与排序 ─────────────────────────────────────────────
def s7_urgency_forgetting() -> Scenario:
    sc = Scenario("S7", "遗忘衰减排序：同漏 1 次，8 天未练排在前（紧急度=弱点权重×遗忘程度）")
    sc.answer("六尺巷")  # c2/c3 各漏 1 次
    c2, c3 = f"{QID}:c2", f"{QID}:c3"
    sc.backdate(c2, 8.0)  # c2 拨到 8 天前，c3 保持刚练
    pts = {wp.point_key: wp for wp in profile.read_weak_points()}
    sc.check("更久未练排更前", pts[c2].urgency > pts[c3].urgency,
             f"urgency c2={pts[c2].urgency} c3={pts[c3].urgency}")
    keys = [wp.point_key for wp in profile.read_weak_points()]
    sc.check("排序单调生效", keys.index(c2) < keys.index(c3), f"order={keys}")
    return sc


def s8_pool_filter_archive() -> Scenario:
    sc = Scenario("S8", "提醒池过滤：graduated/stuck 不进池、pinned 进池、档案完整保留")
    sc.answer("六尺巷 河长 象群")  # 3 点全建档
    conn = sqlite3.connect(str(sc.db_path))
    conn.execute(f"UPDATE weak_points SET state='graduated' WHERE point_key='{QID}:c1'")
    conn.execute(f"UPDATE weak_points SET state='stuck' WHERE point_key='{QID}:c2'")
    conn.execute(f"UPDATE weak_points SET state='pinned' WHERE point_key='{QID}:c3'")
    conn.commit()
    conn.close()
    pool = sc.pool_keys()
    sc.check("毕业/隔离不进提醒池", f"{QID}:c1" not in pool and f"{QID}:c2" not in pool, f"pool={sorted(pool)}")
    sc.check("钉住点留在提醒池", f"{QID}:c3" in pool, "")
    all_keys = {wp.point_key for wp in profile.read_all_weak_points()}
    sc.check("档案只出池不删档", all_keys == {f"{QID}:c1", f"{QID}:c2", f"{QID}:c3"}, f"archive={sorted(all_keys)}")
    return sc


# ── S9-S10：红线 ────────────────────────────────────────────────────
def s9_suspect_trace() -> Scenario:
    sc = Scenario("S9", "疑似溯源红线：suspect 按 miss 入库（B1 判据统一）且 events 必留 suspect 行")
    sc.answer("六尺巷 河长 象群", verdicts=[
        {"point_id": "c1", "status": "hit", "evidence": "六尺巷", "matched_by": "kw"},
        {"point_id": "c2", "status": "miss"},
        {"point_id": "c3", "status": "suspect", "reason": "疑似漏答（LLM 软标注，无证据字段）"},
    ])
    row = sc.row(f"{QID}:c3")
    sc.check("疑似点按 miss 入库", row["miss_count"] == 1, f"miss_count={row['miss_count']}")
    sc.check("events 留 suspect 溯源行", "suspect" in sc.event_actions(),
             f"actions={sc.event_actions()}")
    return sc


def s10_inline_no_reflow() -> Scenario:
    sc = Scenario("S10", "内联零通道红线：非库内 qid 走 practice/complete → 404 且 weak_points 零写入")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.shenlun import router

    client = TestClient(FastAPI())
    client.app.include_router(router, prefix="/api")
    resp = client.post("/api/shenlun/practice/complete", json={
        "question_id": "inline_memory_eval_not_in_store",
        "rounds": [{"round_no": 0, "answer": "任意作答", "hit_ratio": 0.0}],
    })
    # 404 路径下 reflow 从未执行，先按 _SCHEMA 建表再数行数（Windows 下连接必须关干净）
    conn = reflow._conn()
    try:
        n = conn.execute("SELECT count(*) FROM weak_points").fetchone()[0]
    finally:
        conn.close()
    sc.check("内联 complete 被拒（404）", resp.status_code == 404, f"http={resp.status_code}")
    sc.check("内联零写入 weak_points", n == 0, f"rows={n}")
    return sc


SCENARIOS = [
    s1_graduate_full_path, s2_graduate_consec_short, s3_graduate_spacing_short,
    s4_graduate_exam_miss, s5_stuck_deadlock, s6_stuck_revive,
    s7_urgency_forgetting, s8_pool_filter_archive, s9_suspect_trace, s10_inline_no_reflow,
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out",
                    default=os.path.join(ROOT, "eval", "results", "baseline", "memory_eval_results.json"),
                    help="结果 json 路径（run_evals 从 eval/results/baseline/ 拷贝归档）")
    args = ap.parse_args()

    rows, all_checks = [], []
    for fn in SCENARIOS:
        sc = fn()
        try:
            passed = sum(1 for c in sc.checks if c["ok"])
            rows.append({"sid": sc.sid, "desc": sc.desc, "checks": sc.checks,
                         "passed": passed, "total": len(sc.checks)})
            all_checks.extend(sc.checks)
        finally:
            sc.close()

    total, passed_n = len(all_checks), sum(1 for c in all_checks if c["ok"])
    s10 = next(r for r in rows if r["sid"] == "S10")
    s9 = next(r for r in rows if r["sid"] == "S9")
    summary = {
        "scenario_count": len(rows),
        "checks_total": total,
        "checks_passed": passed_n,
        "memory_pass_rate": round(passed_n / total, 4) if total else None,  # HEADLINE ↑
        "inline_reflow_leak": 0 if all(c["ok"] for c in s10["checks"]) else 1,  # 红线 ↓ 须 0
        "suspect_untraced": sum(1 for c in s9["checks"] if not c["ok"]),        # 红线 ↓ 须 0
        "llm_calls": 0,
    }

    out = args.out
    parent = os.path.dirname(out)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "rows": rows}, f, ensure_ascii=False, indent=2)

    print("=" * 78)
    print(f"{'场景':<6}{'检查':<8}{'描述'}")
    print("-" * 78)
    for r in rows:
        mark = "✅" if r["passed"] == r["total"] else "❌"
        print(f"{r['sid']:<6}{r['passed']}/{r['total']:<6}{mark} {r['desc']}")
        for c in r["checks"]:
            if not c["ok"]:
                print(f"       └ FAIL {c['name']}: {c['detail']}")
    print("-" * 78)
    print(f"\n达标率：{passed_n}/{total} = {summary['memory_pass_rate']:.0%}；"
          f"红线：内联泄漏 {summary['inline_reflow_leak']}，疑似缺溯源 {summary['suspect_untraced']}；"
          f"llm_calls=0")
    print(f"已归档：{out}")


if __name__ == "__main__":
    main()
