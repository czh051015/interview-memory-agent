"""单条反馈快速测试 —— 把面经文本粘进来，一键跑通全管道。"""
import sys, io, logging
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 打开日志输出，能看到进度
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

from datetime import datetime
from src.pipeline import run_full_pipeline
from pathlib import Path

print("=" * 50)
print("OfferLoop v1.0 - AI求职教练管道")

# 优先读命令行参数，其次读 my_feedback.csv
if len(sys.argv) > 1:
    text = " ".join(sys.argv[1:])
    from src.inbox.webhook import _feedback_buffer
    from src.models import RawFeedback, FeedbackSource
    _feedback_buffer.append(RawFeedback(
        id="raw_cli_001",
        raw_text=text,
        source=FeedbackSource.SELF_REVIEW,
        received_at=datetime.utcnow(),
    ))
    print(f"投放: {text[:80]}...")
    csv_path = None
elif Path("data/seed/my_feedback.csv").exists():
    print("数据: data/seed/my_feedback.csv")
    csv_path = Path("data/seed/my_feedback.csv")
else:
    print("用法: python run_one.py 你的面经内容...")
    print("或: 编辑 data/seed/my_feedback.csv 填入面经")
    sys.exit(0)

import shutil
# 每次运行前清理旧数据，确保是从零开始分析
for d in ["data/chroma", "data/runs"]:
    if Path(d).exists():
        shutil.rmtree(d)
        print(f"已清理: {d}")

print("正在运行管道 (约2分钟, 7个步骤)...")
print("=" * 50)

run = run_full_pipeline(skip_approval=True, csv_path=csv_path)

print()
print("=" * 50)
print("管道完成!")
print(f"  输入: {run.stats().total_feedback} 条")
print(f"  清洗: {run.cleaner_report.get('cleaned', 0)} 条 (去重{run.cleaner_report.get('duplicates', 0)})")
print(f"  聚类: {run.stats().clusters_found} 个主题")
print(f"  告警: {run.stats().alerts_generated} 个信号")
print(f"  耗时: {run.stats().total_duration_s:.1f}s")
print(f"  简报: {run.run_dir / 'briefing.md'}")

if run.briefing and run.briefing.items:
    print()
    print("=" * 50)
    print("简报摘要")
    for item in run.briefing.items:
        print(f"  [{item.priority.value}] {item.hypothesis}")
        print(f"  置信度: {item.confidence} | 证据: {item.evidence_count} 条")

        if item.high_freq_topics:
            print()
            print("  🔥 高频考点:")
            for t in item.high_freq_topics[:10]:
                fu = " ⚠️有追问" if t.has_deep_followup else ""
                cos = ", ".join(t.companies[:3])
                print(f"    - {t.topic} (出现{t.count}次, {cos}{fu})")

        if item.knowledge_gaps:
            print()
            print("  ⚠️ 知识薄弱点:")
            for g in item.knowledge_gaps:
                print(f"    [{g.urgency}] {g.area}")

        if item.study_plan:
            print()
            print("  📖 补课计划:")
            for s in item.study_plan:
                print(f"    {s.priority}. {s.task}")
                if s.resource:
                    print(f"       资源: {s.resource}")

        print()
        print(f"  🎯 {item.recommended_action}")
else:
    print()
    print("注意: 没有生成简报条目 (可能审批未通过或告警不足)")
