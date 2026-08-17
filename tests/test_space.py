"""空间隔离测试：collection 名 + 文件目录按 space 分。"""

import src.config as config
from src.memory import knowledge_store


def test_collection_name_default():
    """default 空间沿用 v1 collection 名，向后兼容存量数据。"""
    old = config.SPACE
    try:
        config.SPACE = "default"
        assert knowledge_store._collection_name() == "knowledge_items_v1"
    finally:
        config.SPACE = old


def test_collection_name_per_space(monkeypatch):
    """非 default 空间独立 collection。"""
    monkeypatch.setattr(config, "SPACE", "秋招")
    assert knowledge_store._collection_name() == "knowledge_items_秋招"


def test_space_dir_per_space(tmp_path, monkeypatch):
    """文件目录按 space 分目录，且自动创建。"""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "SPACE", "试玩")
    d = config.space_dir()
    assert d == tmp_path / "spaces" / "试玩"
    assert d.exists()
