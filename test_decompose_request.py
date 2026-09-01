import requests
import json

url = 'http://127.0.0.1:8000/api/shenlun/decompose_and_cache'
body = {
    "standard_answer": "水资源短缺，人为因素导致水污染和过度开采。",
    "question": "测试题干",
    "material": "材料第一段：河流被污染。材料第二段：地下水过度开采。",
    "requirements": "",
    "max_score": 20,
    "question_id": "inline",
}

r = requests.post(url, json=body, timeout=30)
print('status', r.status_code)
print(json.dumps(r.json(), ensure_ascii=False, indent=2))

# fetch trace
sess = r.json().get('session_id')
if sess:
    turl = f'http://127.0.0.1:8000/api/shenlun/dev/decompose_trace?question_id=inline&session_id={sess}'
    rt = requests.get(turl)
    print('trace status', rt.status_code)
    print(json.dumps(rt.json(), ensure_ascii=False, indent=2))
