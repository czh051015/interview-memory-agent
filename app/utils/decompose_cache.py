import json
import os
from pathlib import Path
from typing import Dict, Any

from src.config import space_dir


def cache_dir() -> Path:
    d = space_dir() / "decompose_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _trace_path(question_id: str, session_id: str) -> Path:
    q = question_id or "inline"
    filename = f"{q}_{session_id}.json"
    return cache_dir() / filename


def save_trace(trace: Dict[str, Any], question_id: str, session_id: str) -> Path:
    """Atomically save trace JSON and return path."""
    p = _trace_path(question_id, session_id)
    tmp = p.with_suffix(".tmp")
    # write atomically
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(trace, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)
    return p


def load_trace(question_id: str, session_id: str) -> Dict[str, Any] | None:
    p = _trace_path(question_id, session_id)
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
