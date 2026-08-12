"""秋招 Copilot v1.5 —— 市场信号 CLI（网上面经 + JD 交叉验证）。

用法：
  python run_market.py jingyan <file|->           # 导入网上面经（'-' 从 stdin 读，手动粘贴）
  python run_market.py jd <file|目录> [--company 公司名]  # 导入 JD，目录则遍历 *.txt
  python run_market.py prioritize                 # 重算全部 priority + 市场概览 + 复习列表

注意：source 过滤依赖 metadata 里的 source key。存量 v1.0 数据没有该 key，
先跑 prioritize（全量 re-upsert）或 run_interview.py --fresh 补齐。
"""
import sys, io, logging
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

from src.cleaner.schema import ItemStatus, ItemSource, ItemCategory
from src.market import jingyan as jingyan_mod
from src.market import jd as jd_mod
from src.market.cross_validate import build_market_stats, apply_priorities
from src.memory import knowledge_store as store

args = sys.argv[1:]

EMOJI = {"fail": "❌", "partial": "⚠️", "pass": "✅", "unknown": "❓"}


def _print_usage():
    print(__doc__)


def _print_items(items, limit=None):
    for item in items[:limit]:
        emoji = EMOJI.get(item.status.value, "❓")
        topic = f" ({item.topic})" if item.topic else ""
        print(f"  {emoji} {item.question}{topic}  p={item.priority:.1f}")
    if limit and len(items) > limit:
        print(f"  ... 还有 {len(items) - limit} 条")


def cmd_jingyan(path_arg: str) -> int:
    """导入网上面经（只有题目 → status=unknown）。"""
    if path_arg == "-":
        text = sys.stdin.read()
        print("输入: stdin（手动粘贴，Ctrl+Z 结束）")
    else:
        path = Path(path_arg)
        if not path.exists():
            print(f"文件不存在: {path}")
            return 1
        text = path.read_text(encoding="utf-8")
        print(f"输入: {path} ({len(text)} 字)")

    items = jingyan_mod.import_jingyan(text)
    if not items:
        print("未解析出题目（每行一题，空行/# 注释会跳过）")
        return 1

    store.store_items(items)
    print(f"\n入库 {len(items)} 条（source=public_jingyan）:")
    _print_items(items, limit=20)
    print("\n提示: 运行 python run_market.py prioritize 计算交叉验证优先级")
    return 0


def cmd_jd(path_arg: str, company_hint: str = "") -> int:
    """导入 JD（提取技能关键词 → source=jd）。"""
    path = Path(path_arg)
    if not path.exists():
        print(f"路径不存在: {path}")
        return 1

    files = jd_mod.jd_files_from(path)
    if not files:
        print(f"目录下没有 *.txt: {path}")
        return 1

    total = 0
    failed = 0
    for f in files:
        print(f"\n{'=' * 60}\nJD: {f.name}")
        jd_text = f.read_text(encoding="utf-8")
        hint = company_hint or f.stem.split("-")[0]
        try:
            extracted = jd_mod.extract_jd_keywords(jd_text, company_hint=hint)
            items = jd_mod.import_jd(jd_text, company_hint=hint)
        except ValueError as e:
            print(f"  ❌ {e}")
            failed += 1
            continue

        print(f"  公司: {extracted['company'] or '(未识别)'}")
        print(f"  关键词 ({len(extracted['keywords'])}): {'、'.join(extracted['keywords'])}")
        store.store_items(items)
        total += len(items)

    print(f"\n入库 {total} 条（source=jd），失败 {failed} 份")
    if total:
        print("提示: 运行 python run_market.py prioritize 计算交叉验证优先级")
    return 1 if failed else 0


def cmd_prioritize() -> int:
    """全量重算 priority + 市场概览 + 复习列表。"""
    items = store.search(top_k=1000)
    if not items:
        print("知识库为空，先导入面经/JD")
        return 1

    stats = build_market_stats(items)
    adjusted = apply_priorities(items, stats)
    store.store_items(adjusted)  # re-upsert 补齐 source key + 写 priority

    # ── 市场概览 ──
    source_count = {"self_review": 0, "public_jingyan": 0, "jd": 0}
    for item in items:
        source_count[item.source.value] = source_count.get(item.source.value, 0) + 1

    print("=" * 60)
    print("📊 市场概览")
    print(f"  知识库: {len(items)} 条 "
          f"(self_review {source_count['self_review']} | "
          f"public_jingyan {source_count['public_jingyan']} | jd {source_count['jd']})")
    print(f"  题库高频 topic: {sorted(stats['high_freq_topics']) or '(无)'}")
    print(f"  题库低频 topic: {sorted(stats['low_freq_topics']) or '(无)'}")
    print(f"  JD 要求 topic: {sorted(stats['jd_required_topics']) or '(无)'}")

    # ── 复习列表 ──
    review = [
        item for item in adjusted
        if item.source == ItemSource.SELF_REVIEW
        and item.category == ItemCategory.KNOWLEDGE
        and item.status in (ItemStatus.FAIL, ItemStatus.PARTIAL)
    ]
    review.sort(key=lambda x: -x.priority)

    print()
    print("=" * 60)
    print(f"📖 复习列表（{len(review)} 题，按优先级降序）:")
    for item in review:
        emoji = EMOJI.get(item.status.value, "❓")
        boost = " 🔥高频" if item.topic in stats["high_freq_topics"] else ""
        boost += " 💼JD要求" if item.topic in stats["jd_required_topics"] else ""
        print(f"  p={item.priority:.1f} {emoji} [{item.status.value}] {item.question}"
              f" ({item.topic}){boost}")
    return 0


def main() -> int:
    if not args:
        _print_usage()
        return 0

    cmd = args[0]
    rest = args[1:]
    company_hint = ""
    if "--company" in rest:
        idx = rest.index("--company")
        if idx + 1 < len(rest):
            company_hint = rest[idx + 1]
            rest = rest[:idx] + rest[idx + 2:]

    if cmd == "jingyan":
        if not rest:
            print("用法: python run_market.py jingyan <file|->")
            return 1
        return cmd_jingyan(rest[0])
    if cmd == "jd":
        if not rest:
            print("用法: python run_market.py jd <file|目录> [--company 公司名]")
            return 1
        return cmd_jd(rest[0], company_hint)
    if cmd == "prioritize":
        return cmd_prioritize()

    _print_usage()
    return 1


if __name__ == "__main__":
    sys.exit(main())
