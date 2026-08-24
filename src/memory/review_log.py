"""复习日志 —— 记录每次 mastery 变化事件，为「演变动态」可视化攒时间序列。

设计约定（与系统「衰减读时算」一致）：
- 日志只记「复习事件点」(time, before, after)，不记衰减。
- 两次复习之间的衰减，画图时用 mastery_score + 时间 现算 e^(-λt) 即可。
- 只 append；读取用 read()（dashboard/memory_keeper/profile/run_viz 共用）。
- 日志失败不阻断主流程（写库/复习不能因为日志崩掉）。
"""
from __future__ import annotations

import json

from src.config import space_dir
from src.cleaner.schema import utcnow


def _log_path():
    return space_dir() / "review_log.jsonl"


def append(*, item_id: str, question: str, before: float, after: float,
           action: str, actor: str, time=None) -> None:
    """追加一条复习事件。before/after 是 mastery_score（存储值，非衰减值）。

    action: review / review_fail / review_partial
    actor:  review / mock_interview
    """
    entry = {
        "time": (time or utcnow()).isoformat(),
        "item_id": item_id,
        "question": question[:120],
        "before": round(float(before), 4),
        "after": round(float(after), 4),
        "action": action,
        "actor": actor,
    }
    try:
        with open(_log_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read(limit: int | None = None) -> list[dict]:
    """读 review_log 尾部 limit 条（limit=None 读全部）。坏行跳过，文件不存在返回 []。"""
    path = _log_path()
    if not path.exists():
        return []
    entries: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in (lines[-limit:] if limit else lines):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries
