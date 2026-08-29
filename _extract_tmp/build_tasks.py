# -*- coding: utf-8 -*-
"""卷级素材导出：把每卷完整素材（材料+全部题干+全部参考答案原文）整块交给标注 AI，
由 AI 自行按语义把答案对应到题干，规避自动配对的错位问题。
选定 8 卷（2023-2025 为主 + 2019B/2022B 补对策与应用文），覆盖四大题型且均衡。
"""
import json, os, glob, re

P = '_extract_tmp/papers'
OUT = '_extract_tmp/papers_out'
TODO = '_extract_tmp/benchmark_todo.md'
os.makedirs(OUT, exist_ok=True)

# 选定卷（年份_卷，对应 papers/{y}_{vol}.json）
VOL_LIST = ['2023_A', '2023_B', '2023_C', '2024_B', '2024_C', '2025_A', '2022_B', '2019_B']

ESSAY_HINT = re.compile(r'写一篇|800字|1000字|议论文|总论点|以.{0,12}为题|围绕.{0,20}主题|作为文章')

def main():
    vol_records = {}
    for v in VOL_LIST:
        fp = os.path.join(P, f'{v}.json')
        if not os.path.exists(fp):
            print('MISSING', v)
            continue
        vol_records[v] = json.load(open(fp, encoding='utf-8'))

    lines = []
    lines.append('# 申论 Benchmark 采分点标注任务清单（卷级分发）\n')
    lines.append('## 任务目标\n')
    lines.append('把下面 %d 套江苏申论卷，逐题标出「采分点 + 关键词」JSON，补进 benchmark。\n' % len(vol_records))
    lines.append('当前已有 14 道（河南 11 + 江苏 3）。本批补 **约 25 道**（8 卷 × 非大作文题），重点补上「提出对策」与「应用文」两类缺口。\n')
    lines.append('\n## 给标注 AI 的统一指令（复制给每个 AI，每 AI 处理一卷）\n')
    lines.append('```\n')
    lines.append('你是申论阅卷专家。我会给你一套卷的「完整给定材料 + 全部题干 + 全部参考答案原文」。请：\n')
    lines.append('1. 先按"问题一/二/三/四"把题干与参考答案一一对应（答案区是连续编号，请按语义把答案归到正确题干）。\n')
    lines.append('2. 大作文题（要求写 800/1000 字文章、给总论点）跳过，不标。\n')
    lines.append('3. 其余每题输出一个独立 JSON 文件，schema 如下（id 用 {年份}{卷}_{题号}，如 2023B_3）：\n')
    lines.append('{\n  "id": "2023B_3",\n')
    lines.append('  "meta": {"province":"江苏","year":2023,"type":"提出对策","vol":"B类","max_score":25},\n')
    lines.append('  "task": "题干原文",\n  "material": "本题相关给定材料原文（从整卷材料里截取对应部分即可）",\n')
    lines.append('  "gold": {"reference_points": [\n')
    lines.append('    {"id":"p1","point":"一个采分点的完整表述","keywords":["命中该点所需的关键词1","同义表述2"],"score":2},\n')
    lines.append('    {"id":"p2", ...}\n  ]},\n')
    lines.append('  "samples": {\n')
    lines.append('    "good": {"text":"把参考答案充实改写成的、能命中全部采分点的一篇作答","ratio":1.0},\n')
    lines.append('    "bad":  {"text":"故意写偏的、只沾边不答点的跑题作答（专供验证 no_fool）","ratio":0.1}\n  }\n}\n')
    lines.append('}\n')
    lines.append('标注规则：\n')
    lines.append('1. 一个采分点 = 参考答案自然断成的一条（①②③或段落），point 用完整话写。\n')
    lines.append('2. keywords 给 2-4 个：别用大词（"发展/加强/完善"单独不算命中，需配语境）；覆盖同义（"政务公开"与"信息公开"都放）；抓具体动作/对象。\n')
    lines.append('3. score 自行估算每点分值（总和≈max_score）。\n')
    lines.append('4. good 作答要能命中 reference_points 里绝大多数点；bad 作答要明显跑题、几乎命中不了点。\n')
    lines.append('5. 应用文题：把"格式分"（标题/称呼/落款）和"内容分"分开成不同采分点。\n')
    lines.append('6. material 只需截取本题对应的给定资料，不必整卷照搬。\n')
    lines.append('```\n')
    lines.append('\n## 待处理卷清单（%d 卷）\n' % len(vol_records))
    lines.append('| 卷 | 年份/类 | 素材文件 | 预计可标题型（大作文跳过） |')
    lines.append('|---|---------|----------|---------------------------|')

    summary = {
        '2023_A': '归纳概括 / 综合分析 / 应用文',
        '2023_B': '归纳概括 / 综合分析 / 提出对策',
        '2023_C': '提出对策 / 应用文 / 综合分析',
        '2024_B': '归纳概括 / 综合分析 / 应用文',
        '2024_C': '归纳概括 / 提出对策 / 应用文',
        '2025_A': '归纳概括 / 提出对策 / 综合分析',
        '2022_B': '归纳概括 / 综合分析 / 提出对策 / 应用文（无大作文，4题全标）',
        '2019_B': '综合分析 / 归纳概括 / 应用文',
    }

    for v in VOL_LIST:
        rec = vol_records.get(v)
        if not rec:
            continue
        y, vol = rec['year'], rec['vol']
        # 导出卷级素材
        out_txt = []
        out_txt.append(f'# 申论卷素材 {v}（{y}年 {vol}类）\n')
        out_txt.append(f'## 完整给定材料\n{rec.get("material","")}\n')
        # 块1：全部题干（按题号）
        out_txt.append('## 全部题干（按题号列出，大作文已标跳过）\n')
        for q in rec.get('questions', []):
            prompt = q.get('prompt', '').strip()
            is_essay = bool(ESSAY_HINT.search(prompt))
            tag = '【大作文-跳过】' if is_essay else ''
            out_txt.append(f'### 题{q["idx"]} {tag}\n{prompt}\n')
        # 块2：全部参考答案原文（不预配对，AI 自行按语义对应）
        out_txt.append('## 全部参考答案原文（连续编号，请按语义把每条答案归到上面的正确题干；大作文答案跳过不标）\n')
        out_txt.append(rec.get('answers_block', ''))
        open(os.path.join(OUT, f'paper_{v}.txt'), 'w', encoding='utf-8').write('\n'.join(out_txt))
        lines.append(f'| {v} | {y}/{vol} | papers_out/paper_{v}.txt | {summary.get(v,"")} |')

    open(TODO, 'w', encoding='utf-8').write('\n'.join(lines))
    print('已导出', len(vol_records), '卷素材 ->', OUT)
    print('任务清单 ->', TODO)

if __name__ == '__main__':
    main()
