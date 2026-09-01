"""全局测试兜底：语义匹配阶段 mock 掉（embed_zh → None = 自动降级为纯硬匹配）。

原因：score_answer 默认开启语义阶段（docs/25），真实 embedding 依赖本机 Ollama——
开着会让旧测试变慢、且结果依赖环境（Ollama 在不在、模型在不在），非确定性。
mock 成 None 走的是线上同款降级路径（语义阶段跳过，0 行为差异），旧断言不受影响。
语义层本身的判定逻辑由 tests/test_score_semantic.py 用手造向量单独覆盖。
"""
import pytest

from src.shenlun import score as score_mod


@pytest.fixture(autouse=True)
def _disable_semantic_embed(monkeypatch):
    monkeypatch.setattr(score_mod, "embed_zh", lambda texts: None)
