"""用户画像 —— 从错题本聚合出「人级」弱点地图（主题 × 强弱 × 趋势）。

设计（grill 定稿）：
- 两步：确定性聚合（本模块核心，可测）→ LLM 提炼建议文字（可选，失败降级纯统计版）
- 分层（主题级）：🔴 稳定弱点 = 加权 fail ≥2 或 快忘了（gap≥0.5 且 7 天无复习）
                🟡 关注 = gap≥0.3；✅ 成长 = review_log 显示回升
- source 加权（真实面试栽的更可信）：SELF_REVIEW×1.5 / MOCK_INTERVIEW×1.0 / PUBLIC_JINGYAN×0.5
- 冷启动：无错题 → 空画像（降级为简历+JD 两源出题，不硬凑）
- 存储：data/spaces/{space}/profile.json（随空间隔离，全量重算，天然幂等）
- 回流：面试后答差新题进错题本 → 下次全量重算自动带上，无需单独 merge

用法：
  profile = build_profile("default")          # 聚合 + 落盘
  profile = load_profile("default")           # 读回
  profile.to_prompt_text()                    # 给面试官的画像文本（plan_interview 注入）
  profile.weak_topic_names()                  # 给 decide_next 的薄弱主题名列表
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime

from src.memory import knowledge_store as store
from src.memory.mastery import effective_mastery, _elapsed_days
from src.memory import review_log
from src.cleaner.schema import utcnow, ItemSource, ItemStatus
from src.llm import chat_json
from src.config import space_dir

logger = logging.getLogger(__name__)

# ── 阈值（初值待校准，与 λ=0.05 同待遇）──
STABLE_FAIL_THRESHOLD = 2.0   # 稳定弱点：主题加权 fail ≥ 2
GAP_RED = 0.5                 # 快忘了
GAP_YELLOW = 0.3              # 该看看
NO_REVIEW_DAYS = 7            # 快忘了的判定：gap≥0.5 且 ≥7 天无复习

# source 权重：真实面试栽的 > 模拟面试 > 网上面经（只有题无自评，可信度最低）
SOURCE_WEIGHT = {
    ItemSource.SELF_REVIEW: 1.5,
    ItemSource.MOCK_INTERVIEW: 1.0,
    ItemSource.PUBLIC_JINGYAN: 0.5,
}
DEFAULT_WEIGHT = 1.0


@dataclass
class TopicProfile:
    """一个主题的画像：强弱 + 趋势 + 代表题。"""
    topic: str
    weighted_fail: float        # 加权 fail 次数（真实×1.5）
    raw_fail_count: int         # 原始 fail 题数
    max_gap: float              # 主题内最大遗忘缺口
    avg_gap: float
    trend: str                  # recovering / declining / stable
    tier: str                   # red / yellow
    representatives: list[str] = field(default_factory=list)  # fail 题里 gap 最大的 2 道


@dataclass
class UserProfile:
    """用户画像：弱点地图 + 成长轨迹 + 行为模式 + 建议。"""
    generated_at: str = ""
    weak_topics: list[TopicProfile] = field(default_factory=list)  # red 优先，按权重降序
    growth: list[dict] = field(default_factory=list)               # 复习回升的题
    behaviors: list[str] = field(default_factory=list)             # 跨场行为标签（去重）
    summary: str = ""               # LLM 提炼建议（空 = 纯统计版）

    @property
    def empty(self) -> bool:
        return not self.weak_topics and not self.growth and not self.behaviors

    def weak_topic_names(self, limit: int = 3) -> list[str]:
        """给 decide_next 的薄弱主题名（只传名不传细节，省 token）。"""
        return [t.topic for t in self.weak_topics[:limit]]

    def to_prompt_text(self) -> str:
        """给面试官（plan_interview 注入）的画像文本。空画像返回空串（冷启动降级）。"""
        if self.empty:
            return ""
        lines = ["## 候选人画像（记忆管家基于错题本/review_log/行为标签聚合）", ""]
        if self.weak_topics:
            lines.append("稳定弱点（技术验证章优先覆盖）：")
            for t in self.weak_topics:
                lines.append(
                    f"- [{t.tier.upper()}] {t.topic}：加权 fail {t.weighted_fail} 次"
                    f"（原始 {t.raw_fail_count}），avg gap {t.avg_gap}，趋势 {t.trend}"
                )
                if t.representatives:
                    lines.append(f"  代表题：{t.representatives[0][:40]}")
            lines.append("")
        if self.growth:
            lines.append("成长轨迹（复习回升，可降低优先级）：")
            for g in self.growth:
                lines.append(f"- {g['question'][:40]}（{g['before']} → {g['after']}）")
            lines.append("")
        if self.behaviors:
            lines.append(f"行为模式：{'、'.join(self.behaviors)}")
        if self.summary:
            lines.append("")
            lines.append(f"记忆管家建议：{self.summary}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "UserProfile":
        topics = [TopicProfile(**t) for t in d.get("weak_topics", [])]
        return cls(
            generated_at=d.get("generated_at", ""),
            weak_topics=topics,
            growth=d.get("growth", []),
            behaviors=d.get("behaviors", []),
            summary=d.get("summary", ""),
        )


def _source_weight(item) -> float:
    return SOURCE_WEIGHT.get(item.source, DEFAULT_WEIGHT)


def _trend_of(item, log_by_id: dict[str, list[dict]]) -> str:
    """看该题最后一次复习事件：答对回升 → recovering；答错 → declining；无 → stable。"""
    events = log_by_id.get(item.id, [])
    if not events:
        return "stable"
    last = events[-1]
    action = last.get("action", "")
    if action == "review":
        return "recovering"
    if action == "review_fail":
        return "declining"
    return "stable"


def build_profile(space: str | None = None, *, save: bool = True) -> UserProfile:
    """确定性聚合：读错题本 + review_log → 主题弱点地图 + 成长轨迹 + 行为模式。

    save=True 落盘到 data/spaces/{space}/profile.json。
    """
    space = space or "default"
    items = (
        store.search(status="fail", space=space, top_k=1000)
        + store.search(status="partial", space=space, top_k=1000)
    )
    now = utcnow()

    # review_log 按 item_id 分组
    log_by_id: dict[str, list[dict]] = {}
    for ev in review_log.read():
        log_by_id.setdefault(ev.get("item_id", ""), []).append(ev)

    # ── 题级计算：gap / 加权 fail / 趋势 ──
    topics: dict[str, dict] = {}   # topic → 聚合数据
    growth: list[dict] = []
    behaviors: set[str] = set()
    tier_meta: dict[str, dict] = {}  # topic → {"max_gap":..,"has_red":..,"last_review_days":..}

    for it in items:
        em = effective_mastery(it, now)
        gap = round(1.0 - em, 3)
        days = int(_elapsed_days(it, now))
        topic = it.topic or "未分类"
        trend = _trend_of(it, log_by_id)

        t = topics.setdefault(topic, {
            "weighted_fail": 0.0, "raw_fail_count": 0, "gaps": [], "reps": [],
        })
        if it.status == ItemStatus.FAIL:
            t["weighted_fail"] += _source_weight(it)
            t["raw_fail_count"] += 1
            t["reps"].append((gap, it.question))
        t["gaps"].append(gap)

        # 成长：复习答对回升（recovering）
        if trend == "recovering":
            last = log_by_id[it.id][-1]
            growth.append({
                "question": it.question,
                "before": last.get("before", 0),
                "after": last.get("after", 0),
            })

        # 行为标签跨场聚合
        for tag in (it.behavior_tags or []):
            behaviors.add(tag)

    # ── 主题判层 ──
    weak_topics: list[TopicProfile] = []
    for topic, t in topics.items():
        avg_gap = round(sum(t["gaps"]) / len(t["gaps"]), 3)
        max_gap = max(t["gaps"])
        reps = sorted(t["reps"], key=lambda x: -x[0])[:2]
        # 趋势：主题内 recovering 题占比高 → recovering；有 declining → declining
        trend = "declining" if any(_trend_of(it, log_by_id) == "declining"
                                   for it in items if (it.topic or "未分类") == topic) else (
            "recovering" if growth else "stable")

        # 判层：稳定弱点（加权 fail≥2 或 快忘了）> 关注（gap≥0.3）
        fast_forgetting = max_gap >= GAP_RED and any(
            _elapsed_days(it, now) >= NO_REVIEW_DAYS
            for it in items if (it.topic or "未分类") == topic
        )
        if t["weighted_fail"] >= STABLE_FAIL_THRESHOLD or fast_forgetting:
            tier = "red"
        elif max_gap >= GAP_YELLOW:
            tier = "yellow"
        else:
            tier = "stable"

        if tier in ("red", "yellow"):
            weak_topics.append(TopicProfile(
                topic=topic,
                weighted_fail=round(t["weighted_fail"], 2),
                raw_fail_count=t["raw_fail_count"],
                max_gap=max_gap,
                avg_gap=avg_gap,
                trend=trend,
                tier=tier,
                representatives=[q for _, q in reps],
            ))

    # red 优先，再按加权 fail 降序，再按 gap 降序
    weak_topics.sort(key=lambda t: (0 if t.tier == "red" else 1, -t.weighted_fail, -t.max_gap))
    growth.sort(key=lambda g: -g["after"])

    profile = UserProfile(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        weak_topics=weak_topics,
        growth=growth,
        behaviors=sorted(behaviors),
    )
    if save:
        _save(profile, space)
    return profile


def _save(profile: UserProfile, space: str) -> None:
    path = space_dir() / "profile.json"
    try:
        path.write_text(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        logger.warning("画像落盘失败：%s", e)


# ── LLM 提炼（P1）：基于确定性统计写建议文字。失败降级纯统计版（summary 空）。 ──
_REFINE_PROMPT = (
    "你是 OfferLoop 的记忆管家，基于候选人的弱点统计写一段面试建议。你会收到："
    "弱点主题列表（含加权 fail 次数、avg gap、趋势、代表题）、成长轨迹、行为标签。\n"
    "任务：写一段给「面试官」的 2-3 句建议：指出面试时最该重点验证的主题、怎么问（换角度/深挖/降低难度），"
    "以及行为上值得留意的点。只输出 JSON：{\"summary\": \"建议文字\"}\n"
    "要求：只基于给定统计事实，不要编造未提供的弱点或经历。"
)


def refine_summary(profile: UserProfile) -> str:
    """LLM 提炼画像建议。失败返回 ''（纯统计版降级，不阻塞）。"""
    if profile.empty:
        return ""
    lines = ["弱点主题："]
    for t in profile.weak_topics[:5]:
        lines.append(f"- {t.topic}（加权fail {t.weighted_fail}，avg gap {t.avg_gap}，趋势 {t.trend}）")
    if profile.growth:
        lines.append(f"成长：{len(profile.growth)} 条复习回升")
    if profile.behaviors:
        lines.append(f"行为标签：{'、'.join(profile.behaviors)}")
    try:
        data = chat_json(_REFINE_PROMPT, "\n".join(lines), max_tokens=512)
        return str(data.get("summary", "")).strip()
    except Exception as e:
        logger.warning("画像建议提炼失败，降级纯统计版：%s", e)
        return ""


def load_profile(space: str | None = None) -> UserProfile:
    """读回画像。文件缺失/损坏返回空画像（不抛异常）。"""
    path = space_dir() / "profile.json"
    if not path.exists():
        return UserProfile()
    try:
        return UserProfile.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, TypeError) as e:
        logger.warning("画像读取失败，返回空：%s", e)
        return UserProfile()


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    sp = None
    if "--space" in sys.argv:
        i = sys.argv.index("--space")
        if i + 1 < len(sys.argv):
            sp = sys.argv[i + 1]
    p = build_profile(sp)
    print(f"画像（{sp or 'default'}）：{len(p.weak_topics)} 个弱点主题，{len(p.growth)} 条成长，{len(p.behaviors)} 个行为标签")
    print(p.to_prompt_text())
