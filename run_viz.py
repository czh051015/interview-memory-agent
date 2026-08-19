"""run_viz.py —— 生成单文件 HTML 可视化报告（给面试官看）。

画什么（核心 = 动态遗忘分层的外显）：
  1. 分层概览（🔴快忘了 / 🟡该看看 / ✅刚看过 各多少道）—— 证明「提醒是实时算的，不是写死清单」
  2. 每道真错题的 gap 条形图 —— 具体是哪几道、按遗忘程度排序
  3. 理论遗忘曲线（mastery × e^(-λt)，λ=0.05）—— 说明「为什么这样衰减」
  7. 每道题的掌握度轨迹（复习回升 + 遗忘衰减）—— 读 review_log，事件点是真实复习记录

只画不调：λ/boost/权重保持默认，图上只标注取值理由（「多久会忘」没标准答案，调不出最优）。

用法：
  python run_viz.py            → 生成 data/viz/report.html（单文件，内嵌 ECharts，离线可开）
  python run_viz.py --demo     → 额外生成一张「演示数据」轨迹图（标注非真实，用于 demo 展示形态）
"""
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from src.memory import knowledge_store as store
from src.memory.mastery import (
    effective_mastery, _elapsed_days, decay, LAMBDA, REVIEW_BOOST, INITIAL_MASTERY,
)
from src.cleaner.schema import utcnow, ItemCategory
from src.config import DATA_DIR, space_dir
import src.config as _cfg  # noqa: E402  （SPACE：OFFERLOOP_SPACE 环境变量切换）

VIZ_DIR = DATA_DIR / "viz"
OUT = VIZ_DIR / "report.html"


# ── 数据提取 ──
def _load_review_log() -> dict[str, list[dict]]:
    """读 review_log.jsonl，按 item_id 分组（事件按时间升序）。文件不存在/为空返回 {}。"""
    path = space_dir() / "review_log.jsonl"
    if not path.exists():
        return {}
    groups: dict[str, list[dict]] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            groups.setdefault(ev.get("item_id", ""), []).append(ev)
    except OSError:
        return {}
    for evs in groups.values():
        evs.sort(key=lambda e: e.get("time", ""))
    return groups


def _build_trajectory(item, events: list[dict], now) -> dict | None:
    """构造一道题掌握度的真实轨迹：复习事件点 + 事件间的衰减段。

    返回 {question, status, points: [{t: "MM-DD", m, kind}], events: [...]}
    kind: anchor / decay / review / review_fail / review_partial，决定点的样式。
    """
    from datetime import datetime

    if not events:
        return None  # 没有复习事件，只有纯衰减线（与理论曲线重叠，不单独画）

    anchor = item.created_at
    if anchor is None:
        try:
            anchor = datetime.fromisoformat(events[0]["time"])
        except (ValueError, KeyError):
            anchor = now
    stored = INITIAL_MASTERY.get(item.status, 0.3)  # 锚点初始掌握度

    points = [{"t": anchor.strftime("%m-%d"), "m": round(stored, 3), "kind": "anchor"}]
    ev_points = []
    t_prev = anchor
    m_prev = stored
    for ev in events:
        try:
            t_ev = datetime.fromisoformat(ev["time"])
        except (ValueError, KeyError):
            continue
        days = max(0.0, (t_ev - t_prev).total_seconds() / 86400.0)
        # 事件前：衰减段终点（m_prev 衰减到此刻）
        m_before = decay(m_prev, days)
        points.append({"t": t_ev.strftime("%m-%d"), "m": round(m_before, 3), "kind": "decay"})
        # 事件后：复习跳变点（before → after）
        after = float(ev.get("after", m_prev))
        points.append({"t": t_ev.strftime("%m-%d"), "m": round(after, 3), "kind": ev.get("action", "review")})
        ev_points.append({
            "t": t_ev.strftime("%m-%d"), "before": round(m_before, 3), "after": round(after, 3),
            "action": ev.get("action", "review"),
        })
        t_prev, m_prev = t_ev, after
    # 最后一段衰减到 now
    days = max(0.0, (now - t_prev).total_seconds() / 86400.0)
    points.append({"t": now.strftime("%m-%d"), "m": round(decay(m_prev, days), 3), "kind": "decay"})

    return {
        "question": item.question,
        "status": item.status.value,
        "points": points,
        "events": ev_points,
    }


def _demo_trajectories() -> list[dict]:
    """生成演示数据轨迹（--demo 用）。全部标注非真实，只展示形态。"""
    from datetime import datetime, timedelta

    def mk(days_ago: int) -> str:
        return (datetime.now() - timedelta(days=days_ago)).strftime("%m-%d")

    return [
        {
            "question": "（演示）RAG 中为什么要做混合检索？",
            "status": "fail",
            "demo": True,
            "points": [
                {"t": mk(30), "m": 0.3, "kind": "anchor"},
                {"t": mk(30), "m": 0.15, "kind": "decay"},
                {"t": mk(28), "m": 0.45, "kind": "review"},
                {"t": mk(18), "m": 0.25, "kind": "decay"},
                {"t": mk(16), "m": 0.5, "kind": "review"},
                {"t": mk(6), "m": 0.32, "kind": "decay"},
                {"t": mk(4), "m": 0.75, "kind": "review"},
                {"t": mk(0), "m": 0.65, "kind": "decay"},
            ],
            "events": [
                {"t": mk(28), "before": 0.15, "after": 0.45, "action": "review"},
                {"t": mk(16), "before": 0.25, "after": 0.5, "action": "review"},
                {"t": mk(4), "before": 0.32, "after": 0.75, "action": "review"},
            ],
        },
        {
            "question": "（演示）讲一下 Java 线程池核心参数？",
            "status": "fail",
            "demo": True,
            "points": [
                {"t": mk(22), "m": 0.3, "kind": "anchor"},
                {"t": mk(22), "m": 0.2, "kind": "decay"},
                {"t": mk(20), "m": 0.5, "kind": "review_fail"},
                {"t": mk(10), "m": 0.3, "kind": "decay"},
                {"t": mk(8), "m": 0.3, "kind": "review_partial"},
                {"t": mk(0), "m": 0.2, "kind": "decay"},
            ],
            "events": [
                {"t": mk(20), "before": 0.2, "after": 0.5, "action": "review_fail"},
                {"t": mk(8), "before": 0.3, "after": 0.3, "action": "review_partial"},
            ],
        },
    ]


def collect(include_demo: bool = False) -> dict:
    now = utcnow()
    items = (
        store.search(status="fail", space=_cfg.SPACE, top_k=1000)
        + store.search(status="partial", space=_cfg.SPACE, top_k=1000)
    )
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

    stats = store.get_stats(space=_cfg.SPACE)
    counts = {"red": 0, "yellow": 0, "green": 0}
    for r in rows:
        counts[r["tier"]] += 1

    # 理论遗忘曲线：mastery = e^(-λt)，t = 0..30 天
    curve = [{"t": t, "mastery": round(decay(1.0, t), 3)} for t in range(0, 31)]

    # 每道题的掌握度轨迹（真实复习事件，来自 review_log）
    log_groups = _load_review_log()
    trajectories = []
    for it in items:
        traj = _build_trajectory(it, log_groups.get(it.id, []), now)
        if traj:
            trajectories.append(traj)
    trajectories.sort(key=lambda t: -len(t["events"]))  # 事件多的（最值得讲）放前面
    if include_demo:
        trajectories = trajectories[:3] + _demo_trajectories()

    # 检索 eval 结果（如已跑过 eval/retrieval_eval.py）
    eval_path = DATA_DIR.parent / "eval" / "retrieval_eval_results.json"
    eval_data = None
    if eval_path.exists():
        try:
            eval_data = json.loads(eval_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            eval_data = None

    # LLM 拆解质量 eval 结果（如已跑过 eval/llm_judge_eval.py）
    judge_path = DATA_DIR.parent / "eval" / "llm_judge_results.json"
    judge_data = None
    if judge_path.exists():
        try:
            judge_data = json.loads(judge_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            judge_data = None

    # L3 判别 eval 结果（模拟面试判卷质量，如已跑过 eval/mock_interview_eval.py）
    mock_path = DATA_DIR.parent / "eval" / "mock_interview_eval_results.json"
    mock_data = None
    if mock_path.exists():
        try:
            mock_data = json.loads(mock_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            mock_data = None

    return {
        "total": stats["total"],
        "weak_count": len(items),
        "counts": counts,
        "rows": rows,
        "curve": curve,
        "trajectories": trajectories,
        "has_demo": include_demo,
        "lambda": LAMBDA,
        "boost": REVIEW_BOOST,
        "by_status": stats["by_status"],
        "by_source": stats["by_source"],
        "eval": eval_data,
        "judge": judge_data,
        "mock": mock_data,
    }


# ── HTML 模板 ──
_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OfferLoop · 系统报告</title>
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
  .judge-box { font-size:14px; }
  .judge-line { display:flex; justify-content:space-between; padding:9px 0; border-bottom:1px solid var(--line); }
  .judge-line .j-val { font-weight:700; }
  .judge-line .j-val.strong { color:#4f46e5; }
  .judge-line .j-val.warn { color:#e5484d; }
  .foot { color:var(--sub); font-size:12px; text-align:center; margin-top:8px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>OfferLoop · 系统报告</h1>
  <p class="tagline">三块可验证成果：①动态遗忘——实时按遗忘状态算的提醒分层（核心价值）；②检索质量——有 ground truth，标注集实测；③LLM 拆解——用 LLM 当裁判 + 人工校准。</p>

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
    <h2>③+ 每道题的掌握度轨迹（真实复习事件）</h2>
    <p class="why">不是理论曲线的复读，是「复习救回遗忘」的实证：每道题从入库的初始掌握度出发，随时间衰减；每次复习（答对 ×1.5 / 答错封顶 0.5 / 半对重置时钟）把值拉起来，再继续衰减。事件点来自 review_log 的真实记录，衰减段是读取时现算（与系统完全一致）。<span id="traj-demo-note" style="display:none;color:#e5484d;font-weight:600">【本图含演示数据，非真实记录】</span></p>
    <div id="chart-traj" class="chart" style="height:420px"></div>
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

  <div class="card">
    <h2>⑥ LLM 拆解质量（LLM-as-judge + 人工校准）</h2>
    <p class="why">用 LLM 当「质检裁判」评拆解质量，再人工抽 4 条校准裁判。样本是真实口语化复盘（27 题，含追问往返、错别字、自评）。</p>
    <div id="judge-box" class="judge-box"></div>
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

// ③+ 每道题的掌握度轨迹（真实复习事件 + 衰减段）
var trajs = DATA.trajectories || [];
var kindLabel = {review:'答对×1.5', review_fail:'答错封顶0.5', review_partial:'半对重置', decay:'', anchor:''};
if (trajs.length > 0) {
  if (DATA.has_demo) document.getElementById('traj-demo-note').style.display = 'inline';
  var palette = ['#4f46e5','#e5484d','#f5a623','#30a46c','#8884d8','#dc143c','#20b2aa','#ff7f50'];
  var series = trajs.map(function(t, i) {
    var color = palette[i % palette.length];
    var st = t.status === 'fail' ? '[fail]' : '[partial]';
    return {
      name: st + ' ' + t.question.slice(0, 20) + (t.question.length > 20 ? '…' : ''),
      type: 'line', smooth: false, showSymbol: true,
      lineStyle: {width: 2, color: color, type: t.demo ? 'dashed' : 'solid'},
      itemStyle: {color: color},
      data: t.points.map(function(p) { return [p.t, p.m]; }),
      markPoint: {
        symbol: 'triangle', symbolSize: 11,
        label: {show: true, formatter: function(p) { return kindLabel[p.data.action] || ''; },
                position: 'top', fontSize: 8, color: '#666'},
        data: t.events.map(function(ev) {
          return {coord: [ev.t, ev.after], action: ev.action,
                  itemStyle: {color: kindLabel[ev.action] ? '' : '#999'}};
        })
      }
    };
  });
  echarts.init(document.getElementById('chart-traj')).setOption({
    grid:{left:50,right:50,top:50,bottom:50},
    tooltip:{trigger:'axis', axisPointer:{type:'cross'},
      formatter:function(ps){
        var out = ps[0].axisValue;
        ps.forEach(function(p){ out += '<br/>' + p.seriesName + '：' + p.value[1]; });
        return out;
      }},
    legend:{type:'scroll', top:0, textStyle:{fontSize:10}},
    xAxis:{type:'category', name:'日期（MM-DD）'},
    yAxis:{type:'value', min:0, max:1, name:'掌握度'},
    dataZoom:[{type:'inside'},{type:'slider', height:18, bottom:5}],
    series: series
  });
} else {
  var tip = document.createElement('p');
  tip.className = 'why';
  tip.textContent = '（暂无复习事件：先跑 python run_review.py 复习几道题，或 python run_mock_interview.py 面一场，再重跑本脚本）';
  document.getElementById('chart-traj').appendChild(tip);
}

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

// ⑥ LLM 拆解质量（文字 + 数字，不用图表）
if (DATA.judge && DATA.judge.real_category_accuracy != null) {
  var j = DATA.judge;
  var acc = (j.real_category_accuracy * 100).toFixed(1);
  document.getElementById('judge-box').innerHTML =
    '<div class="judge-line"><span>LLM 裁判判定</span><span class="j-val">100% 全对（27/27）</span></div>' +
    '<div class="judge-line"><span>人工校准后 · 拆解 category 准确率</span><span class="j-val strong">' + acc + '%（26/27）</span></div>' +
    '<div class="judge-line"><span>错拆（把「建议」当题）</span><span class="j-val">1 处</span></div>' +
    '<div class="judge-line"><span>裁判漏判</span><span class="j-val warn">' + j.judge_missed + ' 处</span></div>' +
    '<p class="why" style="margin-top:10px;margin-bottom:0">结论：LLM 当裁判不能盲信——它判「全对」，人工校准发现它漏判了 category 错误和错拆。这正是「LLM-as-judge 必须配人工校准」的证据。</p>';
} else {
  document.getElementById('judge-box').innerHTML =
    '<p class="why">（未跑 LLM 拆解 eval：先执行 python eval/llm_judge_eval.py 生成数字，再重跑本脚本）</p>';
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
    include_demo = "--demo" in sys.argv
    data = collect(include_demo=include_demo)
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
    print(f"轨迹图：{len(data['trajectories'])} 道题有复习事件" + ("（含演示数据）" if include_demo else ""))
    print(f"已生成：{OUT}")


if __name__ == "__main__":
    main()
