"""江苏申论真题抽取器 v3：题干与答案按'问题N/第N题'强锚点对齐，杜绝顺序错位。"""
import pdfplumber, glob, os, re, json

SRC = 'D:/hw/Documents/江苏公务员考试真题——申论05-25'
OUT = 'D:/AIWorkspace/OfferLoop/offerloop/_extract_tmp/papers'
os.makedirs(OUT, exist_ok=True)

CN = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}

def extract_text(path):
    try:
        with pdfplumber.open(path) as pdf:
            return '\n'.join((pg.extract_text() or '') for pg in pdf.pages)
    except Exception as e:
        return f'__ERR__ {e}'

def first_ans(txt):
    # 只认整词"参考答案/参考答案及解析/答案要点/评分说明"，避免材料里"答案："误命中
    poss = []
    for kw in ['参考答案及解析', '参考答案', '答案要点', '评分说明']:
        i = txt.find(kw)
        if i >= 0:
            poss.append(i)
    # 过滤掉出现在前半段（极可能是材料正文误含）的命中
    poss = [i for i in poss if i >= len(txt) * 0.4]
    return min(poss) if poss else -1

def qstart(txt, fa):
    cands = [m.start() for m in re.finditer(r'作答要求|答题要求', txt) if m.start() < fa]
    if cands:
        return max(cands)
    # fallback：题干区第一个"问题N/第N题"锚点
    cands2 = [m.start() for m in re.finditer(r'问题[一二三四五六七八]|第[一二三四五六七八]题', txt) if m.start() < fa]
    return min(cands2) if cands2 else -1

def cn2int(ch):
    return CN.get(ch)

def split_numbered(text, strong=True):
    """按题号锚点把文本切成 {题号数字: 段}。strong 用 问题N/第N题/题目N；weak 用 (一)/1. 兜底。"""
    if strong:
        pat = re.compile(r'问题[一二三四五六七八]|第[一二三四五六七八]题|题目[一二三四五六七八]')
    else:
        pat = re.compile(r'[一二三四五六七八][、．。]|[（(][一二三四五六七八][)）]|\([一二三四五六七八]\)|([1-9]|1[0-2])[.．、]')
    d = {}
    pos = []
    for m in pat.finditer(text):
        g = m.group()
        if strong:
            num = cn2int(g[-1])
        else:
            inner = re.search(r'[一二三四五六七八]', g)
            num = cn2int(inner.group()) if inner else int(g[0])
        pos.append((m.start(), num))
    for (s, num), (s2, _) in zip(pos, pos[1:] + [(len(text), None)]):
        seg = text[s:s2].strip()
        if seg:
            d.setdefault(num, seg)  # 同号取首个
    return d

def clean_header(line):
    return re.sub(r'^\s*(?:[一二三四五六七八]、|\(?[一二三四五六七八]\)?|(?:[1-9]|1[0-2])[.．、])\s*', '', line).strip()

def looks_like_prompt(text):
    return bool(re.search(r'给定资料|请|谈谈|概括|归纳|认识|理解|看法|评析|建议|对策|写一份|拟写|公开信|倡议书|发言稿|提纲|如何|启示|含义', text))

def classify(prompt):
    p = prompt
    if re.search(r'写一份|拟写|草拟|撰写|导言|讲话稿|发言稿|公开信|倡议书|建议书|提纲|简报|短评|编者按|调查问卷|宣传稿|宣讲稿|讲解稿|回应|报道|通稿|写一.*?(信|稿|书|报|提纲)', p):
        return '应用文'
    if re.search(r'对策|建议|措施|解决.*问题|怎么办|如何.*[解措]|思路|提出', p):
        return '提出对策'
    if re.search(r'理解|认识|看法|评析|评论|谈谈|含义|启示|必要性|比较|评价', p):
        return '综合分析'
    if re.search(r'概括|归纳|梳理|概述|列出|提炼|简述', p):
        return '归纳概括'
    if re.search(r'贯彻落实|实施方案|工作要点|计划|安排|流程', p):
        return '贯彻执行'
    return '?'

def parse_year_vol(name):
    m = re.search(r'(20\d{2})', name)
    y = int(m.group(1)) if m else 0
    vol = 'A'
    if 'B类' in name or '（B' in name or '(B' in name or 'B卷' in name:
        vol = 'B'
    elif 'C类' in name or '（C' in name or '(C' in name or 'C卷' in name:
        vol = 'C'
    return y, vol

def main():
    files = sorted(glob.glob(SRC + '/*.pdf'))
    all_q = []
    for f in files:
        name = os.path.basename(f)
        m = re.search(r'(20\d{2})', name)
        if not m:
            continue
        y = int(m.group(1))
        if not (2015 <= y <= 2025):
            continue
        if '联考' in name:
            continue
        y, vol = parse_year_vol(name)
        txt = extract_text(f)
        if txt.startswith('__ERR__'):
            print('ERR', name, txt)
            continue
        fa = first_ans(txt)
        qs = qstart(txt, fa) if fa > 0 else -1
        if fa < 0 or qs < 0:
            print(f'{y}_{vol}: CANNOT_LOCATE fa={fa} qs={qs}')
            continue
        material = txt[:qs].strip()
        qblock = txt[qs:fa]
        ablock = txt[fa:]
        qdict = split_numbered(qblock, True) or split_numbered(qblock, False)
        adict = split_numbered(ablock, True) or split_numbered(ablock, False)
        paired = []
        for num in sorted(qdict):
            qclean = clean_header(qdict[num])
            qclean = re.sub(r'^作答要求\s*', '', qclean).strip()
            if len(qclean) < 8 or not looks_like_prompt(qclean):
                continue
            ans = adict.get(num, '')
            paired.append({'idx': num, 'type_hint': classify(qclean), 'prompt': qclean, 'answer': ans})
        rec = {'year': y, 'vol': vol, 'name': name, 'material': material,
               'answers_block': ablock, 'questions': paired}
        json.dump(rec, open(os.path.join(OUT, f'{y}_{vol}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        for q in paired:
            all_q.append({'year': y, 'vol': vol, 'idx': q['idx'], 'type_hint': q['type_hint'],
                         'prompt': q['prompt'], 'answer': q['answer']})
        print(f'{y}_{vol}: material={len(material)} q={len(qdict)} a={len(adict)} paired={len(paired)}')
    json.dump(all_q, open('D:/AIWorkspace/OfferLoop/offerloop/_extract_tmp/all.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('TOTAL:', len(all_q))

if __name__ == '__main__':
    main()
