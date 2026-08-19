"""空间隔离测试：单 collection + metadata space 过滤 + 文件目录按 space 分。"""

import src.config as config
from src.memory import knowledge_store


def test_collection_name_always_v1(monkeypatch):
    """所有空间共用 knowledge_items_v1（v2 架构：隔离靠 metadata.space，不靠 collection 名）。

    历史：v1 曾按空间分 collection，中文 space 名（试玩/秋招）在 Chroma 非法会崩。
    """
    for sp in ("default", "秋招", "试玩", "agentops_m1_test"):
        monkeypatch.setattr(config, "SPACE", sp)
        assert knowledge_store._collection_name() == "knowledge_items_v1"


def test_space_dir_per_space(tmp_path, monkeypatch):
    """文件目录按 space 分目录，且自动创建。"""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "SPACE", "试玩")
    d = config.space_dir()
    assert d == tmp_path / "spaces" / "试玩"
    assert d.exists()
