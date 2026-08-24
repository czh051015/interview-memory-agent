"""秋招 Copilot v1 —— 面经消化 Agent。
用法：
  python run_interview.py              # 读取 data/seed/interview.txt，追加到错题本
  python run_interview.py --fresh       # 先清空旧数据再拆解
  python run_interview.py --space 试玩   # 写入指定空间（默认 default）
  python run_interview.py 你的面经...   # 命令行直接贴复盘
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sys, logging
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

from pathlib import Path
from src.cleaner.decompose import decompose
from src.cleaner.schema import ItemStatus
from src.memory import knowledge_store as store
import src.config as _cfg  # noqa: E402

# --space 参数（在导入前设置，保证 store 读当前空间）
if "--space" in sys.argv:
    _i = sys.argv.index("--space")
    if _i + 1 < len(sys.argv):
        _cfg.SPACE = sys.argv[_i + 1]
    del sys.argv[_i:_i + 2]

args = [a for a in sys.argv[1:] if a != "--fresh"]
fresh_mode = "--fresh" in sys.argv

if fresh_mode:
    store.clear()
    print("(已清空旧数据)")

print("=" * 60)
print("秋招 Copilot v1 —— 面经消化 Agent")

if args:
    text = " ".join(args)
    print(f"输入: 命令行 ({len(text)} 字)")
elif Path("data/seed/interview.txt").exists():
    text = Path("data/seed/interview.txt").read_text(encoding="utf-8")
    print(f"输入: data/seed/interview.txt ({len(text)} 字)")
else:
    print("用法: python run_interview.py [--fresh] [面经文本]")
    print("或: 创建 data/seed/interview.txt 写入面经")
    sys.exit(0)

print("正在拆解...")
print("=" * 60)

result = decompose(text)

# ── 写入当前空间：拆解出的题统一打上 space 标签（否则会落 default）──
for it in result.items:
    if it.space != _cfg.SPACE:
        it.space = _cfg.SPACE

# ── ISSUES E1: unknown 条目交互补标（仅交互终端，管道场景跳过防卡死）──
items = result.items
if result.unknown_count > 0:
    if sys.stdin.isatty():
        from src.cleaner.annotate import annotate_unknown
        items = annotate_unknown(result.items, prompt_fn=input)
    else:
        logging.warning("有 %d 条 status=unknown，非交互环境跳过补标", result.unknown_count)

print(f"\n公司: {result.company or '(未识别)'}")
print(f"岗位: {result.role or '(未识别)'}")
print(f"轮次: {result.round or '(未识别)'}")
print(f"日期: {result.date or '(未识别)'}")
print(f"\n拆出 {result.total_count} 道题:")
print()

fail_count = 0
partial_count = 0
pass_count = 0

for item in items:
    cat_tag = " [ℹ️信息]" if item.category == "info" else ""
    emoji = {"fail": "❌", "partial": "⚠️", "pass": "✅", "unknown": "❓"}.get(item.status.value, "❓")
    print(f"  {emoji} [{item.status.value.upper()}]{cat_tag} {item.question}")
    if item.user_note:
        print(f"     备注: {item.user_note}")
    if item.topic:
        print(f"     主题: {item.topic}")
    print()

    # ISSUES F2: info 类不计入错题统计
    if item.category == "info":
        continue
    if item.status == ItemStatus.FAIL:
        fail_count += 1
    elif item.status == ItemStatus.PARTIAL:
        partial_count += 1
    elif item.status == ItemStatus.PASS:
        pass_count += 1

# ── 入库 ──
print("=" * 60)
before_count = store.get_stats(space=_cfg.SPACE)["total"]
count = store.store_items(items)
print(f"本次入库: {count} 条")

# ── 统计 ──
stats = store.get_stats(space=_cfg.SPACE)
print()
print("=" * 60)
print("📊 本次拆解:")
print(f"  ❌ 不会:  {fail_count} 题")
print(f"  ⚠️ 半会:  {partial_count} 题")
print(f"  ✅ 已过:  {pass_count} 题")
print(f"  ❓ 未知:  {sum(1 for it in items if it.status == ItemStatus.UNKNOWN)} 题")
print(f"  合计:    {result.total_count} 题")

if before_count > 0:
    print(f"\n📊 累计（含历史）: {stats['total']} 题")
    print(f"  ❌ fail: {stats['by_status']['fail']} | ⚠️ partial: {stats['by_status']['partial']} | ✅ pass: {stats['by_status']['pass']}")

if stats["hot_topics"]:
    print(f"\n  🔥 累计薄弱主题 TOP5:")
    for t in stats["hot_topics"]:
        print(f"     {t['topic']} ({t['count']} 题)")

remaining_unknown = sum(1 for it in items if it.status == ItemStatus.UNKNOWN)
if remaining_unknown > 0:
    print(f"\n⚠️ 本次有 {remaining_unknown} 条 status=unknown，建议手动标注")

# ── 错题列表 ──
knowledge_items = [it for it in items if it.status in (ItemStatus.FAIL, ItemStatus.PARTIAL) and it.category != "info"]
if knowledge_items:
    print()
    print("=" * 60)
    print("📖 需要复习的题目:")
    for item in knowledge_items:
        print(f"  [{item.status.value.upper()}] {item.question}")

    # ── 检索演示 ──
    print()
    print("=" * 60)
    print("🔍 错题本检索:")
    all_fails = store.search(status="fail")
    print(f"  fail 总数: {len(all_fails)} 题")
    for item in all_fails[:5]:
        print(f"  ❌ {item.question} ({item.topic})")

    if len(all_fails) > 5:
        print(f"  ... 还有 {len(all_fails) - 5} 题")

    all_partials = store.search(status="partial")
    if all_partials:
        print(f"\n  partial 总数: {len(all_partials)} 题")
        for item in all_partials[:3]:
            print(f"  ⚠️ {item.question} ({item.topic})")
