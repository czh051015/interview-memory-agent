# -*- coding: utf-8 -*-
"""秋招 Copilot —— docx 面经预处理 CLI（jingyan_preprocess 入口封装）。

用法：
  python run_preprocess.py [docx]                       # 解析摘要（默认仓库根目录《面试题.docx》）
  python run_preprocess.py [docx] --seed                # 输出归一化去重后的题目列表（每行一题）
  python run_preprocess.py [docx] --import              # 预处理 + 按面经回填公司/岗位/日期入库
  python run_preprocess.py [docx] --import --limit 10   # 只打印前 10 条

选项：
  --no-dedup   跳过去重（--seed / --import 生效）
  --limit N    打印条数上限（--import 生效，默认 20）

打标+入库复用 src.market.jingyan.import_jingyan（LLM 提 topic + item_meta 回填公司/岗位/日期），
status=unknown、category=knowledge、source=public_jingyan，作为错题本冷启动补给池。
"""

import io
import logging
import sys
from pathlib import Path

from src.market import jingyan as jingyan_mod
from src.market import jingyan_preprocess as preprocess_mod
from src.memory import knowledge_store as store

# 真实终端/stdout 才包装；pytest 环境直接放行（包装会 GC 关闭原 stdout 缓冲，破坏 pytest 捕获）
if hasattr(sys.stdout, "buffer") and "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

EMOJI = {"fail": "❌", "partial": "⚠️", "pass": "✅", "unknown": "❓"}


def _print_usage():
    print(__doc__)


def _flatten_with_meta(records, *, dedup: bool) -> list[tuple[str, dict[str, str]]]:
    """把面经拍平成 (题目, 元信息) 列表；下标即 item_meta 的 key。"""
    pairs: list[tuple[str, dict[str, str]]] = []
    seen: set[str] = set()
    for record in records:
        for question in record.questions:
            normalized = preprocess_mod.normalize_question(question)
            key = preprocess_mod.dedup_key(normalized)
            if dedup and (not key or key in seen):
                continue
            seen.add(key)
            pairs.append(
                (
                    normalized,
                    {
                        "company": record.company,
                        "role": record.role,
                        "date": record.date,
                    },
                )
            )
    return pairs


def _import_and_store(records, *, dedup: bool) -> list:
    """Cleaner 打标 + 入库：import_jingyan（LLM 提 topic + item_meta 回填）→ store_items。"""
    pairs = _flatten_with_meta(records, dedup=dedup)
    if not pairs:
        return []
    text = "\n".join(q for q, _ in pairs)
    item_meta = {i: meta for i, (_, meta) in enumerate(pairs)}
    items = jingyan_mod.import_jingyan(text, item_meta=item_meta)
    store.store_items(items)
    return items


def _print_items(items, limit: int | None = None):
    for item in items[:limit]:
        emoji = EMOJI.get(item.status.value, "❓")
        topic = f" ({item.topic})" if item.topic else ""
        meta = " | ".join(x for x in (item.company, item.role, item.date) if x)
        meta = f" [{meta}]" if meta else ""
        print(f"  {emoji} {item.question}{topic}{meta}")
    if limit and len(items) > limit:
        print(f"  ... 还有 {len(items) - limit} 条")


def cmd_summary(records, path: Path) -> int:
    """打印解析摘要：份数、每份元信息与题数、去重前后总数。"""
    raw = sum(len(r.questions) for r in records)
    unique = len(preprocess_mod.flatten_questions(records))
    print(f"解析 {path.name}: {len(records)} 份面经, 抽题 {raw} 条, 全局去重后 {unique} 条")
    for record in records:
        meta = (
            " | ".join(x for x in (record.company, record.role, record.date) if x) or "(无元信息)"
        )
        print(f"  {record.index:>2}. {meta}  {len(record.questions)} 题")
    return 0


def cmd_seed(records, *, dedup: bool) -> int:
    """输出归一化去重后的题目列表（每行一题）。"""
    for q in preprocess_mod.flatten_questions(records, dedup=dedup):
        print(q)
    return 0


def cmd_import(records, *, dedup: bool, limit: int | None) -> int:
    """预处理结果带公司/岗位/日期入库（source=public_jingyan）。"""
    items = _import_and_store(records, dedup=dedup)
    if not items:
        print("未解析出题目")
        return 1

    print(f"入库 {len(items)} 条（source=public_jingyan，按面经回填公司/岗位/日期）:")
    _print_items(items, limit=limit or 20)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    if args and args[0] in ("-h", "--help"):
        _print_usage()
        return 0

    docx_arg: str | None = None
    do_seed = False
    do_import = False
    dedup = True
    limit: int | None = None

    it = iter(args)
    for arg in it:
        if arg == "--seed":
            do_seed = True
        elif arg == "--import":
            do_import = True
        elif arg == "--no-dedup":
            dedup = False
        elif arg == "--limit":
            try:
                limit = int(next(it))
            except (StopIteration, ValueError):
                print("--limit 需要数字参数")
                return 1
        elif arg.startswith("--limit="):
            try:
                limit = int(arg.split("=", 1)[1])
            except ValueError:
                print("--limit 需要数字参数")
                return 1
        elif arg.startswith("-"):
            print(f"未知参数: {arg}")
            return 1
        else:
            if docx_arg is not None:
                print(f"多余参数: {arg}")
                return 1
            docx_arg = arg

    path = Path(docx_arg) if docx_arg else preprocess_mod.DEFAULT_DOCX
    if not path.exists():
        print(f"文件不存在: {path}")
        return 1

    records = preprocess_mod.preprocess_docx(path, dedup=dedup)
    if do_import:
        return cmd_import(records, dedup=dedup, limit=limit)
    if do_seed:
        return cmd_seed(records, dedup=dedup)
    return cmd_summary(records, path)


if __name__ == "__main__":
    sys.exit(main())
