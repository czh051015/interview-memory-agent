"use client";

import { useState, type ReactNode } from "react";
import { addWrongbook, getExplain, getGuidance, parsePractice, scorePractice } from "@/lib/api";
import type {
  ExplainResult,
  GuidanceResult,
  InlineGold,
  ParseTrace,
  PracticeSubmit,
} from "@/lib/types";

// ── 示例题（河南 2025 市级，benchmark/data/henan_2025_city_1.json）──
// 点「载入示例题」即填充四个输入区，可立即试跑评分 + 材料锚定。
const SAMPLE: InlineGold = {
  qtype: "归纳概括",
  question: "请根据“给定资料1”，梳理概括A区与B县在推动同城化发展中的举措和成效。",
  material:
    "清晨，A 区居民小陈准备烧饭，打开水龙头，清冽的自来水哗哗流出。这股来自 13 公里外 B 县最大饮用水源保护地三合水库的清泉，让 A 区 3 个街道的 16 万人“解了渴”。同饮一库水，得益于两地的同城化发展。A 区和 B 县地域相连且同属 C 市，主城区相距不到 20 公里，A 区人口众多、商贸发达，B 县人文和生态资源丰富。2018 年，在市政府主导下，两地签署战略合作协议，全力推动同城化发展，推进了 80 余项合作。B 县中医院的骨科远近闻名，这两年，从 A 区到 B 县来看骨伤的患者明显增多了。A 区商贸业发达，经常能看到成群结队的 B 县年轻人到 A 区逛街、消费。而 B 县的农家乐也很受A 区居民欢迎，去年前往 B 县乡村游的 A 区游客占总量的 50%。“这几年两地开通了城际公交，实现了高速公路免费互通，两地的互联互通还在进一步加速，未来将新建、提升改造 3条道路。”A 区交通运输局相关负责人介绍。2020 年 4 月，两地组织部门签署了人才协同发展战略合作框架协议，建立年轻干部互派挂职机制。现挂职 A 区文旅局副局长的 B 县青阳街道办马副主任在漫步 A 区文创街区时，想到青阳特色美食街，突然冒出一个想法，“两地各有优势，何不强强联手？”想到就干，他与同事合作，促成 A 区与 B 县召开文旅共建联席会议，积极推动两地开展“美食文创街区”旅游营销活动，协同打造县域消费目的地。“这几年，A 区高速发展对 B 县的辐射带动正在逐步增强，两地产业互补性、协调性还在加深。”B 县孙县长表示，“2024 年，B 县制造业投资增长超过 50%，增速位列全市第一。在 A 区新兴产业带动下，一批与其紧密关联的新能源项目相继落地 B 县，不仅完善了产业结构，也带动了装备制造、光伏光电、电子信息等新兴产业投资。”走进毗邻 A 区的 B 县黄龙工业园区，一栋栋现代化新厂房映入眼帘。近几年，该园区共落地企业 218 家，其中企业法人为 A 区籍的有 86 家。A 区某面膜生产企业负责人表示，2020年看准两地同城合作机遇，她在 B 县投资建起了新工厂。在市场需求带动下，A 区和 B 县之间已经形成了面膜上下游供应链企业紧密合作的生态圈。近期，两地的物流公司正积极谋划，在黄龙工业园区开展综合货运枢纽共建等项目。“我们在黄龙工业园建有物流仓库，在此集货后，可通过 A 区中欧班列、水运发往全世界。”A 区某物流公司负责人说，在 B 县建仓成本低、发货效率高。B 县某商业小区因地理位置优越、价格适中，项目一开盘就吸引了 500 余户 A 区市民前来投资置业。“在 A 区赚钱，在 B 县生活。”在 A 区做服装生意的小江选择将家安在 B 县，生活成本低、舒适度高，一家人在一起，幸福甜蜜。今年，B 县人社部门帮助推广 A 区的“找零工”App，将 A 区实时响应的零工招聘信息推送到 B 县用户手中，已帮助 1000 余名 B 县籍务工人员在 A 区找到了打短工的机会。B 县人社局就业科负责人说，家住 B 县城乡接合部的邹先生，忙时在家务农，闲时出门打工。这几年 A 区对零工需求很多，打包的、配货的、装运的，有时一干就是十天半个月，增加了不少收入。据统计，2019-2024 年 A 区 GDP 增幅达 31%，增幅高出 B 县约 11 个百分点。但在 A 区的带动下，B 县二三产业协同驱动的经济增长方式逐渐形成，多项经济指标增速在 C 市 9 个区县中名列前茅，显示出强劲的发展势头。虽然 2024 年 A 区 GDP 增速仍然高于 B 县，但两地增幅的差距，已由去年的 1.6 个百分点缩小到了 1.1 个百分点，目前“1+1>2”的区域发展格局初步形成。",
  points: [
    { id: "c1", point: "设施互通", keywords: ["城际公交", "高速免费", "道路", "互通"], score: 1, point_type: "对策" },
    { id: "c2", point: "产业协同", keywords: ["新兴产业", "新能源", "物流枢纽", "供应链"], score: 1, point_type: "对策" },
    { id: "c3", point: "服务共享", keywords: ["医疗", "文旅", "营销活动"], score: 1, point_type: "对策" },
    { id: "c4", point: "人才共育", keywords: ["干部互派", "人才协同", "挂职"], score: 1, point_type: "对策" },
    { id: "c5", point: "民生联动", keywords: ["灵活就业", "置业", "零工"], score: 1, point_type: "对策" },
    { id: "c6", point: "经济共进", keywords: ["GDP增长", "制造业投资", "差距缩小"], score: 1, point_type: "影响" },
    { id: "c7", point: "产业升级", keywords: ["二三产业", "产业结构"], score: 1, point_type: "影响" },
    { id: "c8", point: "民生提质", keywords: ["就医", "消费", "就业", "幸福感"], score: 1, point_type: "影响" },
    { id: "c9", point: "格局初成", keywords: ["1+1>2", "协同效应"], score: 1, point_type: "影响" },
  ],
};

interface Round {
  no: number;
  answer: string;
  submit: PracticeSubmit;
}

interface PointDetail {
  open: boolean;
  loadingG: boolean;
  loadingE: boolean;
  guidance?: GuidanceResult;
  explain?: ExplainResult;
  added?: boolean;
}

export default function PracticePanel() {
  const [questionStr, setQuestionStr] = useState("");
  const [materialStr, setMaterialStr] = useState("");
  const [pointsStr, setPointsStr] = useState("");
  const [answerStr, setAnswerStr] = useState("");

  const [gold, setGold] = useState<InlineGold | null>(null); // 最近一次评分用的题面（供示证/错题本复用）
  const [rounds, setRounds] = useState<Round[]>([]);
  const [detail, setDetail] = useState<Record<string, PointDetail>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  // 文字模式（docs/24 §5.2）：标准答案框贴纯文字 → 评分时先自动解析；trace 仅 dev 可见
  const [textMode, setTextMode] = useState(false);
  const [parseTrace, setParseTrace] = useState<ParseTrace | null>(null);

  const current = rounds.length ? rounds[rounds.length - 1] : null;
  const currentAnswer = current ? current.answer : answerStr;
  const showResult = rounds.length > 0;
  // 开发者开关：?dev=1 或 localStorage shenlun_dev=1 → 标准答案框下展开「解析 trace」
  const dev =
    typeof window !== "undefined" &&
    (new URLSearchParams(window.location.search).get("dev") === "1" ||
      localStorage.getItem("shenlun_dev") === "1");

  function loadSample() {
    setQuestionStr(SAMPLE.question);
    setMaterialStr(SAMPLE.material);
    setPointsStr(JSON.stringify(SAMPLE.points, null, 2));
    setAnswerStr("");
    setError("");
    setTextMode(false);
    setParseTrace(null);
  }

  async function resolveGold(): Promise<InlineGold | null> {
    const s = pointsStr.trim();
    if (!s) {
      setError("请先粘贴标准答案（文字或 JSON）");
      return null;
    }
    // JSON（采分点数组）→ 走原逻辑，不解析；纯文字 → LLM 自动拆成采分点再评分
    try {
      const parsed: unknown = JSON.parse(s);
      if (Array.isArray(parsed)) {
        setTextMode(false);
        setParseTrace(null);
        return { qtype: "归纳概括", question: questionStr, material: materialStr, points: parsed as InlineGold["points"] };
      }
      // 能解析但不是数组（不会是采分点 JSON）→ 按文字处理
    } catch {
      // 解析失败 → 文字模式
    }
    setTextMode(true);
    const r = await parsePractice({ question: questionStr, material: materialStr }, s);
    setParseTrace(r.trace);
    if (r.warnings.length) showToast(`解析提示：${r.warnings.join("；")}`);
    if (!r.points.length) {
      setError("解析未拆出采分点，可切回 JSON 模式手填");
      return null;
    }
    return {
      qtype: "归纳概括",
      question: questionStr,
      material: materialStr,
      points: r.points.map((p) => ({
        id: p.id, point: p.point, keywords: p.keywords, score: p.score, point_type: p.point_type,
      })),
    };
  }

  async function score(answer: string) {
    if (!answer.trim()) return;
    setBusy(true);
    setError("");
    try {
      const g = await resolveGold(); // JSON → 直接；纯文字 → 先 parsePractice（busy 覆盖全程）
      if (!g) return;
      const submit = await scorePractice(g, answer.trim());
      setGold(g);
      setRounds((prev) => [...prev, { no: prev.length, answer: answer.trim(), submit }]);
      // 自动展开「推 1 个最该补」的示证
      if (submit.leading) {
        await ensureGuidance(submit.leading.point_id, answer.trim(), g);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "评分失败");
    } finally {
      setBusy(false);
    }
  }

  async function ensureGuidance(pointId: string, answer: string, g: InlineGold) {
    setDetail((d) => ({ ...d, [pointId]: { ...(d[pointId] || { open: false, loadingG: false, loadingE: false }), open: true, loadingG: true } }));
    try {
      const r = await getGuidance(g, answer, pointId);
      setDetail((d) => ({ ...d, [pointId]: { ...(d[pointId] || { open: false, loadingG: false, loadingE: false }), guidance: r, loadingG: false, open: true } }));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "示证加载失败");
      setDetail((d) => ({ ...d, [pointId]: { ...(d[pointId] || { open: false, loadingG: false, loadingE: false }), loadingG: false } }));
    }
  }

  async function ensureExplain(pointId: string, answer: string, g: InlineGold) {
    const cur = detail[pointId] || { open: false, loadingG: false, loadingE: false };
    if (cur.explain) return;
    setDetail((d) => ({ ...d, [pointId]: { ...(d[pointId] || { open: false, loadingG: false, loadingE: false }), loadingE: true } }));
    try {
      const r = await getExplain(g, answer, pointId);
      setDetail((d) => ({ ...d, [pointId]: { ...(d[pointId] || { open: false, loadingG: false, loadingE: false }), explain: r, loadingE: false } }));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "讲解加载失败");
      setDetail((d) => ({ ...d, [pointId]: { ...(d[pointId] || { open: false, loadingG: false, loadingE: false }), loadingE: false } }));
    }
  }

  async function addToWrongbook(pointId: string) {
    if (!gold) return;
    const cur = detail[pointId] || { open: false, loadingG: false, loadingE: false };
    let g = cur.guidance;
    if (!g) {
      // 没展开过示证就点错题本：先补一次示证，保证 demo/cause 有值
      try {
        g = await getGuidance(gold, currentAnswer, pointId);
        setDetail((d) => ({ ...d, [pointId]: { ...(d[pointId] || { open: false, loadingG: false, loadingE: false }), guidance: g } }));
      } catch {
        g = undefined;
      }
    }
    try {
      const r = await addWrongbook(gold, currentAnswer, pointId, g?.demo ?? "", g?.cause_type ?? "", g?.cause ?? "");
      setDetail((d) => ({ ...d, [pointId]: { ...(d[pointId] || { open: false, loadingG: false, loadingE: false }), added: true } }));
      showToast(`已加入错题本：${r.point}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "入库失败");
    }
  }

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(""), 2500);
  }

  function togglePoint(pointId: string) {
    if (!gold) return;
    const cur = detail[pointId];
    if (cur?.open) {
      setDetail((d) => ({ ...d, [pointId]: { ...(d[pointId] || { open: false, loadingG: false, loadingE: false }), open: false } }));
    } else {
      void ensureGuidance(pointId, currentAnswer, gold);
    }
  }

  async function expandAll() {
    if (!gold || !current) return;
    await Promise.all(
      current.submit.misses.map((m) => ensureGuidance(m.id, currentAnswer, gold)),
    );
  }

  return (
    <div className="p-5 flex flex-col h-full min-h-[640px]">
      {/* 状态条 */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-base font-semibold text-zinc-900">申论练习 · 单题示证</h2>
          <p className="text-[11px] text-zinc-500">上传题面 → 评分（全透明）→ 点漏点看示证 → 改完再评（自学闭环）</p>
        </div>
        <button
          onClick={loadSample}
          className="px-3 py-1.5 rounded-lg border border-zinc-200 bg-white text-zinc-600 text-xs font-medium hover:bg-zinc-50 transition-colors"
        >
          载入示例题
        </button>
      </div>

      {error && (
        <div className="mb-3 rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-600">{error}</div>
      )}
      {toast && (
        <div className="mb-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm text-emerald-700">{toast}</div>
      )}

      <div className="flex-1 space-y-4 overflow-y-auto pr-1">
        {/* ── 输入区 ── */}
        <div className="grid gap-3">
          <Field label="题干">
            <textarea value={questionStr} onChange={(e) => setQuestionStr(e.target.value)} rows={2} placeholder="粘贴题干…"
              className={ta} />
          </Field>
          <Field label="给定材料">
            <textarea value={materialStr} onChange={(e) => setMaterialStr(e.target.value)} rows={5} placeholder="粘贴给定材料全文（材料锚定/matched_text 依赖它）"
              className={ta} />
          </Field>
          <Field label="标准答案（文字或 JSON）">
            <textarea value={pointsStr} onChange={(e) => setPointsStr(e.target.value)} rows={8}
              placeholder='粘贴标准答案全文（自动解析为采分点），或直接贴 JSON 数组：[{"id":"c1","point":"...","keywords":["..."],"score":1,"point_type":"对策"}]'
              className={`${ta} font-mono text-[11px]`} />
            {textMode && (
              <p className="text-[10px] text-indigo-500 mt-1">已识别为文字模式：点「评分」时自动解析为采分点（JSON 粘贴则原样使用）</p>
            )}
          </Field>

          {/* 解析 trace（开发者可见，docs/24 §5.3）：?dev=1 或 localStorage shenlun_dev=1 */}
          {dev && parseTrace && (
            <details className="rounded-xl border border-amber-200 bg-amber-50/60 px-3 py-2">
              <summary className="text-[11px] text-amber-700 font-medium cursor-pointer select-none">
                解析 trace（dev）· 拆出 {parseTrace.points.length} 个点
              </summary>
              <div className="mt-2 space-y-2">
                <div>
                  <p className="text-[10px] text-zinc-400 mb-1">原始答案全文</p>
                  <pre className="whitespace-pre-wrap rounded-lg bg-white border border-amber-100 px-2.5 py-2 text-[11px] text-zinc-700 max-h-40 overflow-y-auto">{parseTrace.standard_answer}</pre>
                </div>
                <div>
                  <p className="text-[10px] text-zinc-400 mb-1">拆出的采分点（source_snippet = 原文片段，核验拆点质量）</p>
                  <div className="overflow-x-auto rounded-lg bg-white border border-amber-100">
                    <table className="w-full text-[11px]">
                      <thead>
                        <tr className="text-left text-zinc-400 border-b border-zinc-100">
                          <th className="px-2 py-1.5 font-normal">id</th>
                          <th className="px-2 py-1.5 font-normal">点</th>
                          <th className="px-2 py-1.5 font-normal">关键词</th>
                          <th className="px-2 py-1.5 font-normal">分</th>
                          <th className="px-2 py-1.5 font-normal">角度</th>
                          <th className="px-2 py-1.5 font-normal">原文片段</th>
                        </tr>
                      </thead>
                      <tbody>
                        {parseTrace.points.map((p) => (
                          <tr key={p.id} className="border-b border-zinc-50 align-top">
                            <td className="px-2 py-1.5 text-zinc-400">{p.id}</td>
                            <td className="px-2 py-1.5 text-zinc-800 font-medium">{p.point}</td>
                            <td className="px-2 py-1.5 text-zinc-600">{p.keywords.join("、")}</td>
                            <td className="px-2 py-1.5 text-zinc-600">{p.score}</td>
                            <td className="px-2 py-1.5 text-zinc-600">{p.point_type}</td>
                            <td className="px-2 py-1.5 text-zinc-500">{p.source_snippet || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
                {parseTrace.warnings.length > 0 && (
                  <div>
                    <p className="text-[10px] text-zinc-400 mb-1">warnings</p>
                    <ul className="text-[11px] text-amber-600 space-y-0.5">
                      {parseTrace.warnings.map((w, i) => (
                        <li key={i}>⚠ {w}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </details>
          )}
          <Field label={`作答${current ? `（第 ${current.no + 1} 轮，可改后重新评分）` : ""}`}>
            <textarea value={answerStr} onChange={(e) => setAnswerStr(e.target.value)} rows={4} placeholder="在此作答…"
              className={ta} />
          </Field>
          <div className="flex justify-end">
            <button
              onClick={() => score(answerStr)}
              disabled={busy || !answerStr.trim()}
              className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
            >
              {busy ? "评分中…" : showResult ? "重新评分（再改一版）" : "评分"}
            </button>
          </div>
        </div>

        {/* ── 评分结果 ── */}
        {current && (
          <div className="rounded-xl border border-zinc-200 bg-white shadow-sm overflow-hidden">
            <div className="px-4 py-3 flex items-center justify-between border-b border-zinc-100">
              <p className="text-sm font-semibold text-zinc-900">第 {current.no + 1} 轮评分</p>
              <div className="flex items-center gap-2">
                {current.submit.misses.length > 0 && (
                  <button onClick={expandAll}
                    className="text-[11px] px-2.5 py-1 rounded-full border border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50 transition-colors">
                    展开全部示证
                  </button>
                )}
                <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${current.submit.passed ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-600"}`}>
                  {current.submit.passed ? `✓ 达标 ${Math.round(current.submit.hit_ratio * 100)}%` : `✗ ${Math.round(current.submit.hit_ratio * 100)}%`}
                </span>
              </div>
            </div>

            <div className="px-4 py-3 space-y-3">
              {/* 命中 */}
              <div>
                <p className="text-[11px] text-zinc-400 mb-1">命中（{current.submit.hits.length}）</p>
                <div className="flex flex-wrap gap-1.5">
                  {current.submit.hits.length === 0 && <span className="text-xs text-zinc-300">无</span>}
                  {current.submit.hits.map((h) => (
                    <span key={h.id} title={h.matched_text ?? ""}
                      className="text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-full px-2 py-0.5">
                      {h.point}
                    </span>
                  ))}
                </div>
              </div>

              {/* 轮次 delta */}
              {current.no > 0 && rounds.length >= 2 && (
                <DeltaLine prev={rounds[current.no - 1].submit} cur={current.submit} />
              )}

              {/* 漏点 + 材料锚定 */}
              <div>
                <p className="text-[11px] text-zinc-500 mb-1.5">未命中采分点（{current.submit.misses.length}）— 点任意红 chip 看该点示证，或点右上「展开全部示证」</p>
                <div className="flex flex-wrap gap-1.5">
                  {current.submit.misses.length === 0 && <span className="text-xs text-zinc-300">无（全中！）</span>}
                  {current.submit.misses.map((m) => {
                    const d = detail[m.id];
                    return (
                      <button key={m.id} onClick={() => togglePoint(m.id)}
                        className={`text-xs rounded-full px-2 py-0.5 border transition-colors ${d?.open ? "bg-red-100 border-red-300 text-red-700" : "bg-red-50 border-red-200 text-red-600 hover:bg-red-100"}`}>
                        {m.point}{d?.added ? " ✓" : ""}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* 推 1 个最该补（自动展开）*/}
              {current.submit.leading && <LeadingCard gold={gold!} answer={currentAnswer} leading={current.submit.leading} detail={detail[current.submit.leading.point_id]} ensureExplain={ensureExplain} addToWrongbook={addToWrongbook} />}

              {/* 各漏点展开卡 */}
              {current.submit.misses.filter((m) => detail[m.id]?.open && m.id !== current.submit.leading?.point_id).map((m) => (
                <PointCard key={m.id} gold={gold!} answer={currentAnswer} miss={m} d={detail[m.id]!} ensureExplain={ensureExplain} addToWrongbook={addToWrongbook} />
              ))}
            </div>
          </div>
        )}

        {/* ── 历史轮次（透明轨迹）── */}
        {rounds.length > 1 && (
          <details className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5">
            <summary className="text-xs text-zinc-500 cursor-pointer">评分过程（{rounds.length} 轮轨迹，全透明）</summary>
            <div className="mt-2 space-y-1.5">
              {rounds.map((r) => (
                <div key={r.no} className="text-[11px] text-zinc-500">
                  <span className="font-medium text-zinc-700">第 {r.no + 1} 轮</span> · 命中 {r.submit.hits.length}/{r.submit.hits.length + r.submit.misses.length}（{Math.round(r.submit.hit_ratio * 100)}%）
                  <span className="text-zinc-400"> · {r.submit.hits.map((h) => h.point).join("、") || "—"}</span>
                </div>
              ))}
            </div>
          </details>
        )}
      </div>
    </div>
  );
}

const ta = "w-full rounded-xl border border-zinc-200 bg-white px-3.5 py-2.5 text-sm text-zinc-800 outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-400 placeholder:text-zinc-300";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="text-[11px] text-zinc-400 mb-1">{label}</p>
      {children}
    </div>
  );
}

function DeltaLine({ prev, cur }: { prev: PracticeSubmit; cur: PracticeSubmit }) {
  const prevHit = new Set(prev.hits.map((h) => h.id));
  const newHit = cur.hits.filter((h) => !prevHit.has(h.id));
  if (newHit.length === 0) return null;
  return (
    <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-2 text-xs text-emerald-700">
      🎉 本轮新命中：{newHit.map((h) => h.point).join("、")}
    </div>
  );
}

function LeadingCard({ gold, answer, leading, detail, ensureExplain, addToWrongbook }: {
  gold: InlineGold; answer: string; leading: PracticeSubmit["leading"]; detail?: PointDetail;
  ensureExplain: (id: string, a: string, g: InlineGold) => void;
  addToWrongbook: (id: string) => void;
}) {
  if (!leading) return null;
  return (
    <div className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2.5">
      <p className="text-[11px] font-semibold text-amber-700 mb-1">🎯 最该补的漏点：{leading.point}（{leading.score} 分）</p>
      <PointBody gold={gold} answer={answer} pointId={leading.point_id} d={detail} ensureExplain={ensureExplain} addToWrongbook={addToWrongbook} />
    </div>
  );
}

function PointCard({ gold, answer, miss, d, ensureExplain, addToWrongbook }: {
  gold: InlineGold; answer: string; miss: PracticeSubmit["misses"][number]; d: PointDetail;
  ensureExplain: (id: string, a: string, g: InlineGold) => void;
  addToWrongbook: (id: string) => void;
}) {
  return (
    <div className="rounded-lg border border-zinc-200 px-3 py-2.5">
      <p className="text-[11px] font-semibold text-zinc-700 mb-1">❌ {miss.point}（{miss.score} 分）</p>
      <PointBody gold={gold} answer={answer} pointId={miss.id} d={d} ensureExplain={ensureExplain} addToWrongbook={addToWrongbook} />
    </div>
  );
}

function PointBody({ gold, answer, pointId, d, ensureExplain, addToWrongbook }: {
  gold: InlineGold; answer: string; pointId: string; d?: PointDetail;
  ensureExplain: (id: string, a: string, g: InlineGold) => void;
  addToWrongbook: (id: string) => void;
}) {
  if (!d) return null;
  return (
    <div className="space-y-2">
      {d.loadingG && <p className="text-xs text-zinc-400">示证加载中…</p>}
      {d.guidance && (
        <div className="text-xs text-zinc-700 space-y-1.5">
          {d.guidance.material_source && (
            <p><span className="text-zinc-400">📄 L3 材料原话：</span>{d.guidance.material_source}</p>
          )}
          {d.guidance.demo && (
            <p><span className="text-indigo-500">✍️ L2 示范表述：</span>{d.guidance.demo}</p>
          )}
          {d.guidance.cause_type && (
            <p><span className="text-rose-500">🧠 L4 错因：</span>{d.guidance.cause_type}{d.guidance.cause ? ` — ${d.guidance.cause}` : ""}</p>
          )}
          {d.guidance.fix && (
            <p><span className="text-emerald-600">🛠️ L4 改法：</span>{d.guidance.fix}</p>
          )}
        </div>
      )}

      {/* 有界追问讲解（不生成完整答案）*/}
      <div className="flex items-center gap-2">
        <button onClick={() => ensureExplain(pointId, answer, gold)} disabled={d.loadingE}
          className="text-[11px] px-2 py-1 rounded-md border border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50 disabled:opacity-50">
          {d.loadingE ? "讲解中…" : d.explain ? "收起讲解" : "追问讲解"}
        </button>
        <button onClick={() => addToWrongbook(pointId)} disabled={d.added}
          className="text-[11px] px-2 py-1 rounded-md bg-zinc-900 text-white hover:bg-zinc-700 disabled:opacity-50">
          {d.added ? "✓ 已入错题本" : "＋ 错题本"}
        </button>
      </div>
      {d.explain && (
        <div className="rounded-md bg-zinc-50 border border-zinc-100 px-3 py-2 text-xs text-zinc-600 space-y-1">
          {d.explain.rephrase && <p><span className="text-zinc-400">换种说法：</span>{d.explain.rephrase}</p>}
          {d.explain.why && <p><span className="text-zinc-400">为什么：</span>{d.explain.why}</p>}
          {d.explain.distinguish && <p><span className="text-zinc-400">辨析：</span>{d.explain.distinguish}</p>}
          <p className="text-[10px] text-amber-500">⚠️ 仅讲解，不替你写完整答案</p>
        </div>
      )}
    </div>
  );
}
