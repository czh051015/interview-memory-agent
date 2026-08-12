"""错题本检索。"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from src.memory import knowledge_store as store

args = sys.argv[1:]

if args:
    # ── 命令行模式：只做语义搜索 ──
    query = " ".join(args)
    results = store.search(query=query, top_k=5, similarity_threshold=0.45)
    if results:
        for item in results:
            sim = getattr(item, "_similarity", 0)
            emoji = {"fail": "❌", "partial": "⚠️", "pass": "✅", "unknown": "❓"}.get(item.status.value, "❓")
            print(f"{emoji} [{item.status.value}] {item.question}")
            if item.topic:
                print(f"   主题: {item.topic}  sim={sim:.2f}")
    else:
        print("无匹配结果")
else:
    # ── 交互模式 ──
    stats = store.get_stats()
    print(f"共 {stats['total']} 题 | fail: {stats['by_status']['fail']} | partial: {stats['by_status']['partial']}")
    print("搜索> 输入关键词  |  :fail :partial :pass  |  :topic 主题名  |  :q 退出")
    print()

    while True:
        try:
            q = input("搜索> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            continue
        if q in (":q", ":quit", "exit"):
            break
        if q in (":fail", ":partial", ":pass"):
            items = store.search(status=q[1:], top_k=10)
            for item in items:
                print(f"  [{item.status.value}] {item.question}")
            print()
            continue
        if q.startswith(":topic "):
            items = store.search(topic=q[7:].strip(), top_k=10)
            for item in items:
                print(f"  [{item.status.value}] {item.question}")
            print()
            continue
        # 语义搜索
        results = store.search(query=q, top_k=5, similarity_threshold=0.45)
        for item in results:
            sim = getattr(item, "_similarity", 0)
            emoji = {"fail": "❌", "partial": "⚠️", "pass": "✅", "unknown": "❓"}.get(item.status.value, "❓")
            print(f"  {emoji} [{item.status.value}] {item.question}  ({item.topic})  sim={sim:.2f}")
        if not results:
            print("  无匹配")
        print()
