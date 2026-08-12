"""JD 技能关键词提取准确率评估 —— v1.5 验收标准 2 的自动化形态。

对 data/seed/jd/*.txt 真实调用 extract_jd_keywords，
与 data/seed/jd/gold/*.json 的人工黄金集对比。
匹配规则与 cross_validate._topics_match 一致（精确相等或双向包含）。

准确率 = 命中的黄金关键词 / 黄金关键词总数（micro 平均）。
≥ 0.80 → PASS（退出码 0），否则 FAIL（退出码 1）。

用法: python eval/jd_extract_eval.py
"""
import sys, io, json
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.market.jd import extract_jd_keywords
from src.market.cross_validate import _topics_match

JD_DIR = Path(__file__).resolve().parent.parent / "data" / "seed" / "jd"
PASS_THRESHOLD = 0.80


def match_gold(extracted: list[str], gold: list[str]) -> tuple[list[str], list[str]]:
    """返回 (命中的黄金关键词, 未命中的黄金关键词)。"""
    matched, missed = [], []
    for g in gold:
        if any(_topics_match(g, e) for e in extracted):
            matched.append(g)
        else:
            missed.append(g)
    return matched, missed


def main() -> int:
    jd_files = sorted(JD_DIR.glob("*.txt"))
    if not jd_files:
        print(f"没有找到 JD 文件: {JD_DIR}")
        return 1

    total_gold = 0
    total_matched = 0
    print("=" * 60)
    print("JD 关键词提取评估（匹配规则: 精确相等或双向包含）")
    print("=" * 60)

    for jd_file in jd_files:
        gold_path = JD_DIR / "gold" / f"{jd_file.stem}.json"
        if not gold_path.exists():
            print(f"⚠️ 缺少黄金集 {gold_path.name}，跳过 {jd_file.name}")
            continue

        gold = json.loads(gold_path.read_text(encoding="utf-8"))
        jd_text = jd_file.read_text(encoding="utf-8")

        try:
            extracted = extract_jd_keywords(jd_text)
        except ValueError as e:
            print(f"\n❌ {jd_file.name}: 提取失败 → {e}")
            continue

        matched, missed = match_gold(extracted["keywords"], gold["keywords"])
        extra = [k for k in extracted["keywords"] if not any(_topics_match(k, g) for g in gold["keywords"])]
        precision = len(matched) / len(gold["keywords"]) if gold["keywords"] else 0.0

        total_gold += len(gold["keywords"])
        total_matched += len(matched)

        print(f"\n{jd_file.name}")
        print(f"  提取: {extracted['keywords']}")
        print(f"  命中: {matched}")
        print(f"  遗漏: {missed or '(无)'}")
        print(f"  超出: {extra or '(无)'}")
        print(f"  准确率: {len(matched)}/{len(gold['keywords'])} = {precision:.0%}")

    if total_gold == 0:
        print("\n没有可评估的数据")
        return 1

    overall = total_matched / total_gold
    print()
    print("=" * 60)
    print(f"总体准确率: {total_matched}/{total_gold} = {overall:.0%}  (阈值 {PASS_THRESHOLD:.0%})")
    if overall >= PASS_THRESHOLD:
        print("✅ PASS —— 验收标准 2 达成")
        return 0
    print("❌ FAIL —— 低于 80%，需检查 JD_EXTRACT_SYSTEM 提示词")
    return 1


if __name__ == "__main__":
    sys.exit(main())
