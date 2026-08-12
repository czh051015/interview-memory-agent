"""Streamlit 审批界面 (US-13) —— 批处理模式，不阻塞管道。"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import streamlit as st

from src.config import RUN_DIR
from src.models import (
    Alert,
    ApprovalRecord,
    HypothesisStatus,
    Priority,
)

logger = logging.getLogger(__name__)

# 审批数据持久化文件
APPROVAL_FILE = RUN_DIR / "approvals.json"


def load_approvals() -> dict[str, ApprovalRecord]:
    """从文件加载审批记录。"""
    if not APPROVAL_FILE.exists():
        return {}
    try:
        data = json.loads(APPROVAL_FILE.read_text(encoding="utf-8"))
        return {
            k: ApprovalRecord(**v) for k, v in data.items()
        }
    except Exception as e:
        logger.warning("Failed to load approvals: %s", e)
        return {}


def save_approvals(approvals: dict[str, ApprovalRecord]) -> None:
    """持久化审批记录。"""
    APPROVAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {k: v.model_dump() for k, v in approvals.items()}
    APPROVAL_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def merge_alerts_to_pending(
    alerts: list[Alert],
    existing_approvals: dict[str, ApprovalRecord],
) -> dict[str, ApprovalRecord]:
    """将新告警合并到待审队列——已审批的不覆盖。"""
    for alert in alerts:
        key = alert.cluster_id
        if key not in existing_approvals:
            existing_approvals[key] = ApprovalRecord(
                alert_id=key,
                status=HypothesisStatus.PENDING,
            )
    return existing_approvals


def get_pending_alerts(alerts: list[Alert], approvals: dict[str, ApprovalRecord]) -> list[Alert]:
    """获取待审告警列表（用于审批 UI）。"""
    pending_ids = {
        k for k, v in approvals.items()
        if v.status == HypothesisStatus.PENDING
    }
    return [a for a in alerts if a.cluster_id in pending_ids]


def get_pending_count(approvals: dict[str, ApprovalRecord]) -> int:
    """获取待审数量。"""
    return sum(1 for v in approvals.values() if v.status == HypothesisStatus.PENDING)


# ── Streamlit UI ──

def run_approval_ui(
    alerts: list[Alert],
    evaluations: Optional[list] = None,
) -> dict[str, ApprovalRecord]:
    """启动 Streamlit 审批界面。

    在管道中调用此函数时，它会启动 Streamlit server。
    也可以作为独立 app 运行：`streamlit run src/approval/app.py`
    """
    st.set_page_config(page_title="OfferLoop · 审批", page_icon="✅")

    st.title("📋 OfferLoop · 信号审批")
    st.caption("批处理模式 —— 每周集中审批，不阻塞管道运行")

    # 加载现有审批记录
    approvals = load_approvals()
    approvals = merge_alerts_to_pending(alerts, approvals)

    # 统计
    col1, col2, col3, col4 = st.columns(4)
    total = len(alerts)
    approved = sum(1 for v in approvals.values() if v.status == HypothesisStatus.APPROVED)
    rejected = sum(1 for v in approvals.values() if v.status == HypothesisStatus.REJECTED)
    pending = sum(1 for v in approvals.values() if v.status == HypothesisStatus.PENDING)

    col1.metric("总信号", total)
    col2.metric("✅ 已通过", approved)
    col3.metric("❌ 已驳回", rejected)
    col4.metric("⏳ 待审", pending)

    st.divider()

    # 待审列表
    pending_alerts = [a for a in alerts if approvals.get(a.cluster_id, ApprovalRecord(
        alert_id=a.cluster_id)).status == HypothesisStatus.PENDING]

    if not pending_alerts:
        st.success("🎉 没有待审批的信号！管道可以继续运行。")
        save_approvals(approvals)
        return approvals

    st.subheader(f"待审批信号（{len(pending_alerts)} 条）")

    for alert in pending_alerts:
        with st.expander(
            f"{'⚡' if alert.suggested_priority == Priority.P0 else '🔶' if alert.suggested_priority == Priority.P1 else '🔹'} "
            f"[{alert.suggested_priority.value}] {alert.label}",
            expanded=alert.suggested_priority == Priority.P0,
        ):
            st.markdown(f"**描述**: {alert.description}")
            st.markdown(f"**证据数**: {len(alert.evidence_ids)} 条")
            st.markdown(f"**证据ID**: {', '.join(alert.evidence_ids[:10])}")

            # 审批操作
            col_action, col_priority, col_reason = st.columns([1, 1, 2])

            with col_action:
                action = st.radio(
                    "操作",
                    ["⏳ 待审", "✅ 通过", "❌ 驳回", "🔄 复活（如已驳回）"],
                    key=f"action_{alert.cluster_id}",
                    horizontal=True,
                )

            with col_priority:
                new_priority = st.selectbox(
                    "优先级",
                    ["P0", "P1", "P2"],
                    index=["P0", "P1", "P2"].index(alert.suggested_priority.value),
                    key=f"priority_{alert.cluster_id}",
                )

            with col_reason:
                reason = st.text_input(
                    "理由",
                    placeholder="（可选）记录驳回/修改原因",
                    key=f"reason_{alert.cluster_id}",
                )

            if st.button("提交", key=f"submit_{alert.cluster_id}"):
                record = approvals.get(alert.cluster_id, ApprovalRecord(alert_id=alert.cluster_id))

                if "通过" in action:
                    record.status = HypothesisStatus.APPROVED
                    record.approved_priority = Priority(new_priority)
                    record.approved_by = "hw"
                    record.approved_at = datetime.utcnow()
                    record.reason = reason or "审批通过"
                elif "驳回" in action:
                    record.status = HypothesisStatus.REJECTED
                    record.approved_by = "hw"
                    record.approved_at = datetime.utcnow()
                    record.reason = reason or "驳回，证据不足"
                elif "复活" in action:
                    record.status = HypothesisStatus.PENDING
                    record.reason = reason or "复活重新待审"
                else:
                    record.status = HypothesisStatus.PENDING

                approvals[alert.cluster_id] = record
                save_approvals(approvals)
                st.rerun()

    st.divider()

    # 已审批列表（可复活）
    st.subheader("已审批记录")
    approved_records = [v for v in approvals.values() if v.status != HypothesisStatus.PENDING]
    if approved_records:
        for record in approved_records:
            st.text(
                f"{'✅' if record.status == HypothesisStatus.APPROVED else '❌'} "
                f"[{record.alert_id}] {record.reason} "
                f"({record.approved_at.strftime('%m/%d %H:%M') if record.approved_at else 'N/A'})"
            )
    else:
        st.text("暂无审批记录")

    save_approvals(approvals)
    return approvals


# ── 命令行入口 ──
if __name__ == "__main__":
    # 独立运行审批 UI
    # 需要先有 alerts 数据
    alerts_file = RUN_DIR / "latest_alerts.json"
    if alerts_file.exists():
        alerts_data = json.loads(alerts_file.read_text())
        alerts = [Alert(**a) for a in alerts_data]
    else:
        st.warning("暂无告警数据，请先运行管道生成告警")
        alerts = []

    run_approval_ui(alerts)
