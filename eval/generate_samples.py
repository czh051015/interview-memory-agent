"""生成 L3 判别样本（1c）：对 questions.json 每道题生成参考答案 + 4 类判别答案。

输入：eval/samples/questions.json（人工定题）
输出：eval/samples/answers.json（LLM 生成初稿，用户校准 good/confident 后回填）

为什么这样设计：
- 参考答案（expected_points）与 4 类答案由 LLM 生成，用户只校准 good 与 confident 两类
  （断言依赖它们：good 必须明显好、confident 必须明显错但流畅）。
- mediocre/bad 由 LLM 生成即可——断言只要求它们"明显更差"。

用法：
  python eval/generate_samples.py            # 全量生成
  python eval/generate_samples.py --resume   # 只补生成缺失的题（断点续跑）
"""
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.llm import chat_json

EVAL_DIR = Path(__file__).resolve().parent
SAMPLES = EVAL_DIR / "samples"
QUESTIONS = SAMPLES / "questions.json"
OUT = SAMPLES / "answers.json"

_RESUME = (EVAL_DIR.parent / "data" / "resume.md").read_text(encoding="utf-8")[:6000]
_JD = (EVAL_DIR.parent / "data" / "jd.md").read_text(encoding="utf-8")

_ANSWER_PROMPT = (
    "你是面试题样本生成器，为一个候选人生成一份评估样本。你会收到：面试题、候选人的简历片段（用于贴合真实背景作答）、"
    "岗位 JD。请输出 JSON：\n"
    '{"expected_points": ["参考答案要点1", ...], '
    '"answers": {"good": "优质回答", "mediocre": "中等回答", "bad": "很差回答", "confident": "自信但答错的回答"}}\n'
    "要求：\n"
    "1. expected_points：3-5 条，这道题应该答到的关键点，一句话一条；\n"
    "2. good：覆盖全部要点、有细节有取舍、贴合候选人真实项目经历，像面试现场答得好；\n"
    "3. mediocre：覆盖一半左右要点、含糊、缺细节，像答到一半卡住；\n"
    "4. bad：明显不会或跑题，只有一两句；\n"
    "5. confident：篇幅与 good 相当、语气自信流畅，但核心事实上明显答错（如张冠李戴、概念颠倒）——用于测阅卷人能否识破自信错答。\n"
    "四类答案都要像真实面试口述，不要用列表编号句式。"
)


def build_prompt(q: dict) -> str:
    return (
        f"## 面试题\n{q['question']}\n\n"
        f"## 来源\nsource={q['source']} topic={q['topic']}\n\n"
        f"## 候选人简历（片段）\n{_RESUME}\n\n"
        f"## 岗位 JD\n{_JD}"
    )


def main() -> int:
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    existing = {}
    if OUT.exists():
        existing = {it["id"]: it for it in json.loads(OUT.read_text(encoding="utf-8")).get("items", [])}

    resume_only = "--resume" in sys.argv
    items = []
    for q in questions:
        qid = q["id"]
        if qid in existing and existing[qid].get("answers"):
            items.append(existing[qid])
            print(f"[skip] {qid} 已有答案")
            continue
        if resume_only:
            items.append(existing.get(qid, {**q, "expected_points": [], "answers": {}}))
            continue
        print(f"[gen ] {qid} {q['question'][:30]}...")
        try:
            data = chat_json(_ANSWER_PROMPT, build_prompt(q), max_tokens=2048, temperature=0.7)
        except Exception as e:
            print(f"  !! 生成失败：{e}")
            data = {}
        item = {
            "id": qid,
            "question": q["question"],
            "source": q["source"],
            "topic": q["topic"],
            "expected_points": [str(p) for p in data.get("expected_points", [])],
            "answers": {
                "good": data.get("answers", {}).get("good", ""),
                "mediocre": data.get("answers", {}).get("mediocre", ""),
                "bad": data.get("answers", {}).get("bad", ""),
                "confident": data.get("answers", {}).get("confident", ""),
            },
            "calibration": {"good": "pending", "confident": "pending"},
        }
        items.append(item)

    out = {"meta": {"generated": "2026-08-19", "count": len(items)}, "items": items}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    done = sum(1 for it in items if it["answers"].get("good"))
    print(f"\n完成：{done}/{len(questions)} 题已生成 → {OUT}")
    print("下一步：你打开 answers.json，只校准每题的 good 与 confident（约 20 条）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
