"""申论示证错题本（docs/22 §3.6）—— 按「每个漏点一条」快照到 KnowledgeItem 库。

真落库路径：KnowledgeItem → knowledge_store.store_items()（Chroma，与面试域错题本同库），
接 app/api/record.py 的 store（docs/22 §3.6 真路径）。
⚠️ app/api/shenlun.py 的 shenlun_record（录入预览）只返回拆解预览不落库，不可用作错题本。

申论条目通过扩展字段（question_id / point_id / material_source / demo_text / reflow_tier）
与 reflow（红黄绿档）与 topK 备考提醒（Next）衔接，实现「哪类题型/采分点反复漏 + 不遗忘」。
"""

from datetime import datetime

from src.cleaner.schema import KnowledgeItem, ItemSource, ItemStatus


def build_wrongbook_item(
    question_item: dict,
    point,
    *,
    material_source: str | None,
    answer_snippet: str = "",
    demo: str = "",
    cause: str = "",
    cause_type: str = "",
) -> KnowledgeItem:
    """把一次示证的单个漏点快照成 KnowledgeItem（每个漏点一条，不是整题一条）。

    字段映射（docs/22 §3.6）：
      question=题干 · answer=用户作答片段（matched_text/空答）· question_type=题型 ·
      topic=漏点名 · feedback=错因(L4)+示范表述(L2) · status=fail · date=当天 ·
      扩展字段：question_id / point_id / material_source（L3 锚定）/ demo_text（L2）/
      reflow_tier（初始红，docs/22 §3.6「初始红」）。
    id 稳定 = sl_{question_id}_{point_id}：反复漏同一点 → upsert 覆盖，不产生重复条目。
    """
    feedback = "；".join(part for part in [
        f"【错因】{cause_type}：{cause}" if (cause_type or cause) else "",
        f"【示范】{demo}" if demo else "",
    ] if part)
    return KnowledgeItem(
        id=f"sl_{question_item['id']}_{point.id}",
        question=str(question_item["task"]["question"]),
        answer=answer_snippet,
        question_type=str(question_item["meta"]["type"]),
        topic=point.point,
        date=datetime.now().strftime("%Y-%m-%d"),  # 「当天」= 本地日期（UTC 晚上会差一天）
        status=ItemStatus.FAIL,
        source=ItemSource.MOCK_INTERVIEW,  # 自动采集的新弱点（复用 mock_interview 采集语义）
        feedback=feedback,
        question_id=str(question_item["id"]),
        point_id=point.id,
        material_source=material_source or "",
        demo_text=demo,
        reflow_tier="red",  # 初始红档：反复漏 + 不遗忘的入口（docs/22 §3.6）
    )
