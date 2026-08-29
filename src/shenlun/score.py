"""评分传感器 —— 把 benchmark 的 hit/miss 逻辑做成可复用引擎层。

domain 无关：输入「采分点列表 + 作答文本」，输出「命中/漏掉哪些点」。
换壳时不需要改这里，只需换 reference_points 的来源（benchmark/data 或产品题库）。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Point:
    id: str
    point: str
    keywords: list[str]
    score: int = 1
    type: str = ""   # 采分角度（问题/原因/影响/对策/意义/危害/其他），docs/13 §5.1


@dataclass
class ScoreResult:
    """一次作答的评分结果：只报 hit/miss，不报精确分数。"""
    hit_points: list[Point] = field(default_factory=list)
    miss_points: list[Point] = field(default_factory=list)

    @property
    def hit_ratio(self) -> float:
        total = len(self.hit_points) + len(self.miss_points)
        return len(self.hit_points) / total if total else 0.0

    @property
    def hit_ids(self) -> list[str]:
        return [p.id for p in self.hit_points]

    @property
    def miss_ids(self) -> list[str]:
        return [p.id for p in self.miss_points]


def score_answer(answer: str, points: list[Point]) -> ScoreResult:
    """纯关键词匹配（A 模式）：任一关键词出现在作答中即命中该点。

    这是「漏点识别」传感器 —— 不需要精确分，只需要可靠地指出漏了哪个点。
    """
    result = ScoreResult()
    for p in points:
        if any(kw in answer for kw in p.keywords):
            result.hit_points.append(p)
        else:
            result.miss_points.append(p)
    return result


def from_benchmark(reference_points: list[dict]) -> list[Point]:
    """把 benchmark JSON 的 reference_points 转成引擎 Point。"""
    return [
        Point(
            id=p["id"],
            point=p["point"],
            keywords=p["keywords"],
            score=int(p.get("score", 1)),
            type=p.get("point_type", ""),
        )
        for p in reference_points
    ]
