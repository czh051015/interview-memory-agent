import json, os
P='D:/AIWorkspace/OfferLoop/offerloop/_extract_tmp/papers'
papers=['2017A','2018C','2021A','2021C','2025B','2019A','2019B','2020A','2020B','2020C','2023C','2025C']
for pv in papers:
    fp=os.path.join(P,f'{pv}.json')
    if not os.path.exists(fp):
        print(f'\n===== {pv} : NO PAPER JSON ====='); continue
    rec=json.load(open(fp,encoding='utf-8'))
    ab=rec.get('answers_block','')
    # trim leading boilerplate before first '参考答案'
    i=ab.find('参考答案')
    seg=ab[i:] if i>=0 else ab
    print(f'\n===== {pv} answers_block (first 2000) =====')
    print(seg[:2000])
print('\n=== END ===')
