"""run_viz.py —— 生成单文件 HTML 可视化报告（给面试官看）。

画什么（核心 = 动态遗忘分层的外显）：
  1. 分层概览（🔴快忘了 / 🟡该看看 / ✅刚看过 各多少道）—— 证明「提醒是实时算的，不是写死清单」
  2. 每道真错题的 gap 条形图 —— 具体是哪几道、按遗忘程度排序
  3. 理论遗忘曲线（mastery × e^(-λt)，λ=0.05）—— 说明「为什么这样衰减」

只画不调：λ/boost/权重保持默认，图上只标注取值理由（「多久会忘」没标准答案，调不出最优）。

用法：python run_viz.py   →  生成 data/viz/report.html（单文件，内嵌 ECharts，离线可开）
"""
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from src.memory import knowledge_store as store
from src.memory.mastery import effective_mastery, _elapsed_days, decay, LAMBDA, REVIEW_BOOST
from src.cleaner.schema import utcnow, ItemCategory
from src.config import DATA_DIR

VIZ_DIR = DATA_DIR / "viz"
OUT = VIZ_DIR / "report.html"


# ── 数据提取 ──
def collect() -> dict:
    now = utcnow()
    items = store.search(status="fail", top_k=1000) + store.search(status="partial", top_k=1000)
    # 信息性问题（自我介绍/薪酬期望/哪里人）不算「错题」，过滤掉（ISSUES F2 既定结论）
    items = [it for it in items if it.category != ItemCategory.INFO]

    rows = []
    for it in items:
        em = effective_mastery(it, now)
        gap = 1.0 - em
        if gap >= 0.5:
            tier, tier_label, color = "red", "🔴 快忘了", "#e5484d"
        elif gap >= 0.2:
            tier, tier_label, color = "yellow", "🟡 该看看", "#f5a623"
        else:
            tier, tier_label, color = "green", "✅ 刚看过", "#30a46c"
        rows.append({
            "question": it.question,
            "status": it.status.value,
            "mastery": round(em, 3),
            "gap": round(gap, 3),
            "tier": tier,
            "tier_label": tier_label,
            "color": color,
            "days": int(_elapsed_days(it, now)),
        })
    rows.sort(key=lambda r: -r["gap"])

    stats = store.get_stats()
    counts = {"red": 0, "yellow": 0, "green": 0}
    for r in rows:
        counts[r["tier"]] += 1

    # 理论遗忘曲线：mastery = e^(-λt)，t = 0..30 天
    curve = [{"t": t, "mastery": round(decay(1.0, t), 3)} for t in range(0, 31)]

    # 检索 eval 结果（如已跑过 eval/retrieval_eval.py）
    eval_path = DATA_DIR.parent / "eval" / "retrieval_eval_results.json"
    eval_data = None
    if eval_path.exists():
        try:
            eval_data = json.loads(eval_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            eval_data = None

    return {
        "total": stats["total"],
        "weak_count": len(items),
        "counts": counts,
        "rows": rows,
        "curve": curve,
        "lambda": LAMBDA,
        "boost": REVIEW_BOOST,
        "by_status": stats["by_status"],
        "by_source": stats["by_source"],
        "eval": eval_data,
    }


# ── HTML 模板 ──
_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OfferLoop · 动态遗忘可视化</title>
<style>
  :root { --ink:#1a1a1a; --sub:#666; --line:#e5e5e5; --bg:#ffffff; --card:#fafafa; }
  * { box-sizing: border-box; }
  body { margin:0; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
         color:var(--ink); background:var(--bg); line-height:1.6; }
  .wrap { max-width:960px; margin:0 auto; padding:40px 32px 80px; }
  h1 { font-size:26px; margin:0 0 4px; }
  .tagline { color:var(--sub); margin:0 0 28px; font-size:15px; }
  .metrics { display:flex; gap:16px; flex-wrap:wrap; margin-bottom:32px; }
  .metric { flex:1; min-width:150px; background:var(--card); border:1px solid var(--line);
            border-radius:12px; padding:16px 18px; }
  .metric .num { font-size:32px; font-weight:700; }
  .metric .lbl { color:var(--sub); font-size:13px; margin-top:2px; }
  .metric.red .num { color:#e5484d; } .metric.yellow .num { color:#f5a623; }
  .metric.green .num { color:#30a46c; } .metric.dark .num { color:var(--ink); }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px;
          padding:20px 20px 12px; margin-bottom:28px; }
  .card h2 { font-size:17px; margin:0 0 4px; }
  .why { color:var(--sub); font-size:13px; margin:0 0 8px; }
  .chart { width:100%; }
  .foot { color:var(--sub); font-size:12px; text-align:center; margin-top:8px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>OfferLoop · 系统报告</h1>
  <p class="tagline">上：动态遗忘——系统「实时按遗忘状态」算出来的提醒分层（核心价值）。下：检索质量——唯一有 ground truth 的部分，用标注集实测（硬数字）。</p>

  <div class="metrics">
    <div class="metric dark"><div class="num" id="m-total">0</div><div class="lbl">错题本总题数</div></div>
    <div class="metric dark"><div class="num" id="m-weak">0</div><div class="lbl">真错题（fail/partial）</div></div>
    <div class="metric red"><div class="num" id="m-red">0</div><div class="lbl">🔴 快忘了（优先提醒）</div></div>
    <div class="metric yellow"><div class="num" id="m-yellow">0</div><div class="lbl">🟡 该看看</div></div>
    <div class="metric green"><div class="num" id="m-green">0</div><div class="lbl">✅ 最近刚看过</div></div>
  </div>

  <div class="card">
    <h2>① 提醒分层概览</h2>
    <p class="why">提醒不是写死清单，是实时按遗忘状态算的：gap = 1 − 掌握度，掌握度 = 上次复习值 × e^(−λt)。越久没复习、gap 越大，越该提醒。</p>
    <div id="chart-tier" class="chart" style="height:260px"></div>
  </div>

  <div class="card">
    <h2>② 每道真错题的遗忘程度（按 gap 降序）</h2>
    <p class="why">顶部红色 = 面试前最该看的题。复习答对 ×1.5 回升、答错封顶 0.5，所以「复习成果会回流」——练过的题会从这里沉下去。</p>
    <div id="chart-gap" class="chart" style="height:720px"></div>
  </div>

  <div class="card">
    <h2>③ 理论遗忘曲线（λ=0.05）</h2>
    <p class="why">为什么取 0.05：艾宾浩斯遗忘曲线的经验值。这些参数保持默认、不调优——因为「你多久会忘一道面试题」没有标准答案，调不出「最优」，只能选合理值并讲清为什么。</p>
    <div id="chart-curve" class="chart" style="height:320px"></div>
  </div>

  <div class="card">
    <h2>④ 检索 Recall@k（20 条标注查询 · 经人工校对）</h2>
    <p class="why">Recall@5≈70%、Recall@10≈76%、噪音≈0：能召回大部分相关题、几乎不召回无关题。Recall@1 偏低说明本地 768 维嵌入的排序精度有限——所以系统不赌单一检索，而是 rank 双因子（相关 0.5 + 遗忘重要性 0.5）排序，检索只是其中一个信号。</p>
    <div id="chart-recall" class="chart" style="height:300px"></div>
  </div>

  <div class="card">
    <h2>⑤ 检索 Precision-Recall 曲线（阈值扫描）</h2>
    <p class="why">阈值越低召回越全、精度越低。系统默认 0.45，是在「召回够用」和「不误召回无关题」之间取的平衡点——这个值是从这条曲线上「调出来」的，是能测的，跟遗忘参数「调不出来」形成对照。</p>
    <div id="chart-pr" class="chart" style="height:300px"></div>
  </div>

  <p class="foot">OfferLoop · 记忆层纯函数可复现，本报告由 run_viz.py 从错题本实时快照生成</p>
</div>

<script>__ECHARTS__</script>
<script>
var DATA = __DATA__;

document.getElementById('m-total').textContent = DATA.total;
document.getElementById('m-weak').textContent = DATA.weak_count;
document.getElementById('m-red').textContent = DATA.counts.red;
document.getElementById('m-yellow').textContent = DATA.counts.yellow;
document.getElementById('m-green').textContent = DATA.counts.green;

// ① 分层概览
echarts.init(document.getElementById('chart-tier')).setOption({
  grid:{left:60,right:30,top:20,bottom:30},
  xAxis:{type:'value', name:'题数'},
  yAxis:{type:'category', data:['🔴 快忘了','🟡 该看看','✅ 刚看过']},
  series:[{type:'bar', barWidth:28, label:{show:true,position:'right'},
    data:[
      {value:DATA.counts.red, itemStyle:{color:'#e5484d'}},
      {value:DATA.counts.yellow, itemStyle:{color:'#f5a623'}},
      {value:DATA.counts.green, itemStyle:{color:'#30a46c'}},
    ]}]
});

// ② gap 条形图
var rows = DATA.rows;
var cats = rows.map(function(r){ return r.question.length>22 ? r.question.slice(0,22)+'…' : r.question; });
var bars = rows.map(function(r){ return {value:r.gap, itemStyle:{color:r.color}}; });
echarts.init(document.getElementById('chart-gap')).setOption({
  grid:{left:10,right:50,top:10,bottom:40},
  tooltip:{trigger:'axis', axisPointer:{type:'shadow'},
    formatter:function(p){ var r=rows[p[0].dataIndex]; return r.question+'<br/>掌握度 '+r.mastery+' · gap '+r.gap+' · '+r.days+'天没复习'; }},
  xAxis:{type:'value', max:1, name:'gap（遗忘程度）'},
  yAxis:{type:'category', data:cats, axisLabel:{fontSize:10}},
  dataZoom:[{type:'slider', yAxisIndex:0, start:0, end: Math.max(20, Math.min(100, 400/rows.length))}],
  series:[{type:'bar', data:bars, barWidth:'60%'}]
});

// ③ 理论遗忘曲线
var curve = DATA.curve;
echarts.init(document.getElementById('chart-curve')).setOption({
  grid:{left:50,right:30,top:30,bottom:40},
  tooltip:{trigger:'axis', formatter:function(p){return p[0].dataIndex+'天 → 掌握度 '+p[0].value;}},
  xAxis:{type:'category', name:'距上次复习（天）', data:curve.map(function(c){return c.t;})},
  yAxis:{type:'value', min:0, max:1, name:'掌握度'},
  series:[{type:'line', smooth:true, showSymbol:false, lineStyle:{width:3,color:'#4f46e5'},
    areaStyle:{color:'rgba(79,70,229,0.08)'}, data:curve.map(function(c){return c.mastery;})}]
});

// ④ 检索 Recall@k / ⑤ PR 曲线（只有跑过 eval 才有数据）
if (DATA.eval && DATA.eval.recall_at_k) {
  var rk = DATA.eval.recall_at_k;
  echarts.init(document.getElementById('chart-recall')).setOption({
    grid:{left:50,right:50,top:30,bottom:40},
    tooltip:{trigger:'axis'},
    legend:{data:['Recall@k','Precision@k'], top:0},
    xAxis:{type:'category', name:'k', data:rk.map(function(r){return r.k;})},
    yAxis:{type:'value', min:0, max:1},
    series:[
      {name:'Recall@k', type:'line', smooth:true, lineStyle:{width:3,color:'#4f46e5'},
       data:rk.map(function(r){return r.recall_at_k;})},
      {name:'Precision@k', type:'line', smooth:true, lineStyle:{width:2,color:'#30a46c',type:'dashed'},
       data:rk.map(function(r){return r.precision_at_k;})},
    ]
  });

  var pr = DATA.eval.pr_curve;
  echarts.init(document.getElementById('chart-pr')).setOption({
    grid:{left:50,right:50,top:30,bottom:40},
    tooltip:{trigger:'axis', formatter:function(p){var i=p[0].dataIndex; return '阈值 '+pr[i].threshold+'<br/>Precision '+pr[i].precision+' · Recall '+pr[i].recall;}},
    xAxis:{type:'value', min:0, max:1, name:'Recall'},
    yAxis:{type:'value', min:0, max:1, name:'Precision'},
    series:[{type:'line', smooth:true, lineStyle:{width:3,color:'#e5484d'},
      data:pr.map(function(r){return [r.recall, r.precision];}),
      label:{show:true, formatter:function(p){return pr[p.dataIndex].threshold;}}}]
  });
} else {
  var tip = document.createElement('p');
  tip.className = 'why';
  tip.textContent = '（未跑检索 eval：先执行 python eval/retrieval_eval.py 生成数字，再重跑本脚本）';
  document.getElementById('chart-recall').appendChild(tip);
  document.getElementById('chart-pr').innerHTML = '';
}
</script>
</body>
</html>
"""


def render(data: dict, echarts_js: str) -> str:
    return (_HTML
            .replace("__ECHARTS__", echarts_js)
            .replace("__DATA__", json.dumps(data, ensure_ascii=False)))


def main():
    data = collect()
    if data["weak_count"] == 0:
        print("没有 fail/partial 错题，先跑 run_interview.py / annotate_jingyan.py 标错题。")
        return

    echarts_path = VIZ_DIR / "echarts.min.js"
    if not echarts_path.exists():
        print("缺少 echarts.min.js，请先下载到 data/viz/echarts.min.js")
        return

    html = render(data, echarts_path.read_text(encoding="utf-8"))
    OUT.write_text(html, encoding="utf-8")

    print(f"错题本 {data['total']} 题，真错题 {data['weak_count']} 道")
    print(f"分层：🔴 {data['counts']['red']} · 🟡 {data['counts']['yellow']} · ✅ {data['counts']['green']}")
    print(f"已生成：{OUT}")


if __name__ == "__main__":
    main()
