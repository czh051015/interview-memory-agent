import glob, os, json, sys
patt='data/spaces/default/decompose_cache/*.json'
files=sorted(glob.glob(patt), key=os.path.getmtime, reverse=True)
if not files:
    print('NO_FILES')
    sys.exit(0)
print('LATEST_FILE:', files[0])
with open(files[0],'r',encoding='utf-8') as f:
    txt=f.read()
try:
    j=json.loads(txt)
    print('IS_JSON: true')
    print(json.dumps(j, ensure_ascii=False, indent=2)[:2000])
except Exception as e:
    print('IS_JSON: false', e)
    print(txt[:2000])
