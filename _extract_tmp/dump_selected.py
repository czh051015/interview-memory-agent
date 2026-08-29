import json, os
P='D:/AIWorkspace/OfferLoop/offerloop/_extract_tmp/papers'
allq=json.load(open('D:/AIWorkspace/OfferLoop/offerloop/_extract_tmp/all.json',encoding='utf-8'))

selected = {
 '归纳概括': [(2023,'B',1),(2024,'A',1),(2024,'B',1),(2024,'C',1),(2025,'A',1),(2017,'A',3),(2023,'A',1),(2021,'C',1)],
 '综合分析': [(2023,'A',2),(2023,'B',2),(2023,'B',4),(2017,'A',2),(2017,'B',2),(2017,'C',1),(2018,'B',1),(2018,'C',3)],
 '提出对策': [(2023,'B',3),(2025,'A',2),(2017,'C',2),(2021,'C',0),(2022,'C',0)],
 '贯彻执行': [(2023,'A',3),(2017,'B',1),(2025,'A',3),(2024,'B',3),(2024,'C',3),(2024,'C',4),(2019,'C',0)],
}
# index all.json by (year,vol,idx)
idx_map={(q['year'],q['vol'],q['idx']):q for q in allq}

out=[]
for t, lst in selected.items():
    out.append(f'\n########## {t} ##########')
    for (y,v,i) in lst:
        if i>0:
            q=idx_map.get((y,v,i))
            if not q:
                out.append(f'  [{y}{v}#{i}] NOT IN all.json'); continue
            out.append(f'\n--- {t} | {y}{v}#{i} ---')
            out.append('PROMPT: '+q['prompt'])
            out.append('ANSWER: '+q['answer'])
        else:
            # dump all questions of this paper from per-paper json
            rec=json.load(open(os.path.join(P,f'{y}_{v}.json'),encoding='utf-8'))
            out.append(f'\n=== {t} | RAW PAPER {y}{v} (all questions) ===')
            out.append(f'MATERIAL_LEN={len(rec.get("material",""))}')
            for q in rec['questions']:
                out.append(f'\n--- {y}{v}#{q["idx"]} [{q["type_hint"]}] ---')
                out.append('PROMPT: '+q['prompt'])
                out.append('ANSWER: '+q['answer'])
out.append('\n=== END ===')
open('D:/AIWorkspace/OfferLoop/offerloop/_extract_tmp/selected.txt','w',encoding='utf-8').write('\n'.join(out))
print('written selected.txt lines=', len(out))
