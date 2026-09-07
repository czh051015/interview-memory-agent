"use client";

// ── 录入页（docs/39：默认「录错题」，次要「录新题进题库」）──
// mode 1 · 📌 录错题（默认，docs/39 §6.3）：
//   贴题面+标准答案 → LLM 拆点预览 → 填我的作答 → 逐点选「这道题漏了」→ 错因三档
//   快选（标签 → 后端枚举映射，§6.2）→ 每漏点一条循环 POST /shenlun/wrongbook
//   → 「去错题本看」onDone 切第 5 页签。防循环论证（docs/16 语义）：勾选 = 本人确认漏。
// mode 2 · 📚 录新题进题库（原录题闭环，docs/实施计划 任务一）：
//   拆解预览 → 逐点编辑 → 「确认入库」= 全部点人工通过 → POST /shenlun/questions
//   → src/shenlun/question_store.py 唯一实现落库（与 CLI 同源，防两份实现漂移）。
// 注意（wrongbook.py L5 ⚠️）：shenlun_record 只预览不落库——录错题落库走 wrongbook 端点。

import { useState } from "react";

type Mode = "wrongbook" | "question";

// docs/39 §6.2 错因三档快选：前端标签 → 提交枚举（后端 cause_type）
const CAUSE_OPTIONS = [
  { label: "没写上", value: "完全没提" },
  { label: "太宽泛", value: "太模糊" },
  { label: "写偏", value: "写偏" },
];

interface RecordPreview {
  points: Array<{ id: string; point: string; score: number; keywords: string[]; point_type: string }>;
  warnings: string[];
}

// 录新题 mode 的编辑行（keywords 以文本呈现，提交时拆回数组）
interface EditRow {
  key: number;
  id: string;
  point: string;
  keywordsText: string;
  score: number;
  point_type: string;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

const splitKw = (s: string) => s.split(/[,，、;；\s]+/).filter(Boolean);

export default function RecordPanel({ onDone }: { onDone: () => void }) {
  const [mode, setMode] = useState<Mode>("wrongbook"); // docs/39：默认录错题
  const [form, setForm] = useState({
    question: "",
    requirements: "",
    material: "",
    standard_answer: "",
    max_score: 20,
  });
  const [preview, setPreview] = useState<RecordPreview | null>(null); // LLM 拆点产物（两 mode 共用）
  const [rows, setRows] = useState<EditRow[]>([]); // 录新题：可编辑点行
  const [busy, setBusy] = useState(false); // 拆解中
  const [saving, setSaving] = useState(false); // 入库/入错题本中
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  // 录错题流
  const [myAnswer, setMyAnswer] = useState(""); // 我的作答（答题现场原话）
  const [missSel, setMissSel] = useState<Record<string, string>>({}); // point_id → 错因枚举值
  const [doneCount, setDoneCount] = useState(0); // 最近一次成功条数（>0 显示「去错题本看」）

  const missCount = Object.keys(missSel).length;

  function set<K extends keyof typeof form>(k: K, v: (typeof form)[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  function resetAll() {
    setForm({ question: "", requirements: "", material: "", standard_answer: "", max_score: 20 });
    setPreview(null);
    setRows([]);
    setMyAnswer("");
    setMissSel({});
    setDoneCount(0);
  }

  function updateRow(key: number, patch: Partial<EditRow>) {
    setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }

  // 错因三档 = 行状态：选中任意档 = 该点算漏点；再点同档取消
  function toggleCause(pointId: string, value: string) {
    setMissSel((m) => {
      const next = { ...m };
      if (next[pointId] === value) delete next[pointId];
      else next[pointId] = value;
      return next;
    });
  }

  async function run() {
    if (!form.standard_answer.trim()) return;
    setBusy(true);
    setError("");
    setNotice("");
    setDoneCount(0);
    try {
      const r = await post<RecordPreview>("/api/shenlun/record", {
        question: form.question,
        requirements: form.requirements,
        material: form.material,
        standard_answer: form.standard_answer,
        max_score: form.max_score,
      });
      setPreview(r);
      if (mode === "wrongbook") {
        setMissSel({}); // 新一轮拆点 → 勾选清零（点可能已变）
        setRows([]);
        setNotice(
          r.points.length > 0
            ? `拆出 ${r.points.length} 个采分点——对照你的作答，勾出「这道题漏了」的点并标错因。`
            : "没有拆出采分点——检查标准答案是否太短，或稍后重试。",
        );
      } else {
        // 录新题：拆出的点进入可编辑行（关键词回显为顿号分隔文本）
        setRows(
          r.points.map((p) => ({
            key: Math.random(),
            id: p.id,
            point: p.point,
            keywordsText: p.keywords.join("、"),
            score: p.score,
            point_type: p.point_type,
          })),
        );
        setNotice(
          r.points.length > 0
            ? `拆出 ${r.points.length} 个采分点——可直接改分值/关键词、删点/加点，确认后入库（人审即在页面确认）。`
            : "没有拆出采分点——检查标准答案是否太短，或稍后重试。",
        );
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "拆解失败");
      setPreview(null);
      setRows([]);
    } finally {
      setBusy(false);
    }
  }

  // ── mode 1 · 录错题：每漏点一条循环入错题本（docs/39 §6.3）──
  async function submitWrongbook() {
    if (!preview || preview.points.length === 0) {
      setError("请先拆点预览（贴标准答案后点「拆点预览」）");
      return;
    }
    if (!form.question.trim()) {
      setError("题干不能为空（错题条目以题干为主体）");
      return;
    }
    const misses = Object.entries(missSel);
    if (misses.length === 0) {
      setError("还没有勾出漏掉的点——对照拆点结果选出「这道题漏了」的点");
      return;
    }
    // 提交前把拆点产物对齐后端 InlinePoint（gold.points 原样引用，score_answer 服务端锚定）
    const goldPoints = preview.points;
    setSaving(true);
    setError("");
    let stored = 0;
    try {
      for (const [pointId, causeType] of misses) {
        await post<{ stored: number; item_id: string }>("/api/shenlun/wrongbook", {
          gold: {
            question: form.question.trim(), // 必填（_resolve 合成条目题干，§7.2 兜底在此）
            qtype: "手动录入",
            material: form.material,
            points: goldPoints,
          },
          point_id: pointId,
          answer: myAnswer.trim(), // 服务端用它重算材料锚（answer 空 → 无锚，可接受）
          cause_type: causeType, // 标签 → 枚举已在 toggleCause 时映射
          cause: "",
        });
        stored += 1;
      }
      setDoneCount(stored);
      setNotice(`✅ 已加入错题本 ${stored} 条（每漏点一条）——错题本第 5 页签可见`);
      setMyAnswer("");
      setMissSel({});
    } catch (e: unknown) {
      setError(
        e instanceof Error
          ? `已加入 ${stored} 条后中断：${e.message}`
          : `已加入 ${stored} 条后中断`,
      );
    } finally {
      setSaving(false);
    }
  }

  // ── mode 2 · 录新题：点「确认入库」= 全部点人工通过 → 后端补 approved/source（docs/16）──
  async function confirmSave() {
    if (!form.question.trim()) {
      setError("题干不能为空");
      return;
    }
    const points = [];
    for (const r of rows) {
      if (!r.point.trim()) {
        setError(`第 ${r.id} 点名称不能为空`);
        return;
      }
      const kws = splitKw(r.keywordsText);
      if (kws.length === 0) {
        setError(`采分点「${r.point}」未填关键词`);
        return;
      }
      points.push({
        id: r.id,
        point: r.point.trim(),
        keywords: kws,
        score: r.score,
        point_type: r.point_type,
      });
    }
    if (points.length === 0) return;
    setSaving(true);
    setError("");
    try {
      const r = await post<{ question_id: string; stored: number }>("/api/shenlun/questions", {
        question: form.question.trim(),
        requirements: form.requirements.trim(),
        material: form.material,
        max_score: form.max_score,
        points,
      });
      setNotice(`✅ 已入库：${r.question_id}（${r.stored} 个点——可去「练习」tab 推这道题）`);
      resetAll(); // 成功入库清空表单，可继续录下一道
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "入库失败");
    } finally {
      setSaving(false);
    }
  }

  const input =
    "w-full rounded-xl border border-zinc-200 bg-white px-3.5 py-2.5 text-sm text-zinc-800 outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-400 placeholder:text-zinc-300";
  const modeBtn = (m: Mode, icon: string, label: string) => (
    <button
      onClick={() => {
        setMode(m);
        setError("");
        setNotice("");
        // 清预览/勾选（防跨 mode 卡片错位：两 mode 的拆点产物用法不同）
        setPreview(null);
        setRows([]);
        setMissSel({});
        setDoneCount(0);
      }}
      className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
        mode === m
          ? "bg-indigo-600 text-white shadow-sm"
          : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200"
      }`}
    >
      {icon} {label}
      {m === "wrongbook" && <span className="opacity-70">（默认）</span>}
    </button>
  );

  return (
    <div className="p-5 max-w-2xl">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-base font-semibold text-zinc-900">录入</h2>
          <p className="text-[11px] text-zinc-500">
            {mode === "wrongbook"
              ? "录错题：贴题面 + 标准答案 → 拆点 → 勾出漏掉的点 → 进错题本"
              : "录新题进题库：拆解 → 人工确认 → 入库（可被练习推题）"}
          </p>
        </div>
        <div className="flex gap-1.5 shrink-0">
          {modeBtn("wrongbook", "📌", "录错题")}
          {modeBtn("question", "📚", "录新题")}
        </div>
      </div>

      {error && (
        <div className="mb-3 rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-600">
          {error}
        </div>
      )}

      {/* ══ mode 1 · 录错题流（docs/39 §6.3）══ */}
      {mode === "wrongbook" ? (
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-zinc-600 mb-1">题干 *</label>
            <textarea
              value={form.question}
              onChange={(e) => set("question", e.target.value)}
              placeholder="例：根据给定资料，谈谈 H 市政务服务转变的主要做法。"
              rows={2}
              className={input}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-600 mb-1">给定材料（可选）</label>
            <textarea
              value={form.material}
              onChange={(e) => set("material", e.target.value)}
              placeholder="粘贴材料原文（拆点更准；漏点出处锚定需要）"
              rows={3}
              className={input}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-600 mb-1">标准答案 *</label>
            <textarea
              value={form.standard_answer}
              onChange={(e) => set("standard_answer", e.target.value)}
              placeholder="粘贴标准答案/参考要点全文"
              rows={4}
              className={input}
            />
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={run}
              disabled={busy || !form.standard_answer.trim()}
              className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
            >
              {busy ? "拆解中…" : "拆点预览（LLM）"}
            </button>
            {notice && (
              <p className="flex-1 text-xs text-zinc-500 bg-zinc-50 border border-zinc-100 rounded-xl px-3 py-2">
                {notice}
              </p>
            )}
          </div>

          {/* 我的作答（漏点条目的作答对照源；空则无材料锚） */}
          <div>
            <label className="block text-xs font-medium text-zinc-600 mb-1">
              我的作答（这道题我实际写的，漏点据此对照）
            </label>
            <textarea
              value={myAnswer}
              onChange={(e) => setMyAnswer(e.target.value)}
              placeholder="粘贴你当时写的作答全文（可选——漏点错因和锚定用它）"
              rows={4}
              className={input}
            />
          </div>

          {/* 拆点结果 → 漏点勾选 */}
          {preview && preview.points.length > 0 && (
            <div className="rounded-xl border border-zinc-200 bg-white shadow-sm overflow-hidden">
              <div className="px-4 py-2.5 border-b border-zinc-100">
                <p className="text-sm font-semibold text-zinc-900">对照拆点 · 勾出漏掉的</p>
                <p className="text-[10px] text-zinc-400">
                  点错因即算勾选（再点同档取消）；漏掉的点会按「每漏点一条」进错题本
                </p>
              </div>
              <div className="divide-y divide-zinc-50">
                {preview.points.map((p) => {
                  const sel = missSel[p.id];
                  return (
                    <div
                      key={p.id}
                      className={`px-4 py-2.5 ${sel ? "bg-amber-50/60" : ""}`}
                    >
                      <div className="flex items-start gap-2">
                        <span className="shrink-0 mt-1 text-[10px] text-zinc-400 font-mono">
                          {p.id}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm text-zinc-800 leading-snug">
                            {p.point}
                            <span className="ml-1.5 text-[10px] text-zinc-400">
                              {p.score} 分{p.point_type ? ` · ${p.point_type}` : ""}
                            </span>
                          </p>
                          <p className="text-[11px] text-zinc-400 truncate">
                            {p.keywords.join("、")}
                          </p>
                        </div>
                        {sel && <span className="shrink-0 text-[10px] text-amber-600 mt-1">漏了</span>}
                      </div>
                      {/* 错因三档快选（docs/39 §6.2 标签 → 提交枚举映射） */}
                      <div className="mt-1.5 pl-6 flex items-center gap-1.5">
                        <span className="text-[10px] text-zinc-400 shrink-0 w-7">错因</span>
                        {CAUSE_OPTIONS.map((o) => (
                          <button
                            key={o.value}
                            onClick={() => toggleCause(p.id, o.value)}
                            className={`px-2.5 py-1 rounded-full text-[11px] border transition-colors ${
                              sel === o.value
                                ? o.value === "完全没提"
                                  ? "bg-red-500 border-red-500 text-white"
                                  : o.value === "太模糊"
                                    ? "bg-amber-500 border-amber-500 text-white"
                                    : "bg-orange-500 border-orange-500 text-white"
                                : "border-zinc-200 text-zinc-500 hover:bg-zinc-50"
                            }`}
                          >
                            {o.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="px-4 py-3 border-t border-zinc-100 flex items-center gap-2">
                <button
                  onClick={submitWrongbook}
                  disabled={saving || missCount === 0}
                  className="px-4 py-2 rounded-lg bg-zinc-900 text-white text-sm font-medium hover:bg-zinc-700 disabled:opacity-40 transition-colors"
                >
                  {saving ? "加入中…" : `加入错题本（${missCount}）`}
                </button>
                {doneCount > 0 && (
                  <button
                    onClick={onDone}
                    className="px-4 py-2 rounded-lg border border-indigo-200 text-indigo-600 text-sm font-medium hover:bg-indigo-50 transition-colors"
                  >
                    去错题本看 →
                  </button>
                )}
                {preview.warnings.length > 0 && (
                  <div className="flex-1 space-y-0.5">
                    {preview.warnings.map((w, i) => (
                      <p key={i} className="text-[11px] text-amber-600">⚠ {w}</p>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      ) : (
        /* ══ mode 2 · 录新题进题库（原录题闭环，docs/实施计划 任务一）══ */
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-zinc-600 mb-1">题目（题干）*</label>
            <textarea
              value={form.question}
              onChange={(e) => set("question", e.target.value)}
              placeholder="例：根据给定资料，谈谈 H 市政务服务转变的主要做法。"
              rows={2}
              className={input}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-600 mb-1">作答要求</label>
            <input
              value={form.requirements}
              onChange={(e) => set("requirements", e.target.value)}
              placeholder="例：要求：全面准确，条理清晰，不超过 300 字"
              className={input}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-600 mb-1">给定材料</label>
            <textarea
              value={form.material}
              onChange={(e) => set("material", e.target.value)}
              placeholder="粘贴材料原文（最好有，拆点会更准）"
              rows={5}
              className={input}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-600 mb-1">标准答案 *</label>
            <textarea
              value={form.standard_answer}
              onChange={(e) => set("standard_answer", e.target.value)}
              placeholder="粘贴标准答案/参考要点全文"
              rows={4}
              className={input}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-600 mb-1">满分</label>
            <input
              type="number"
              min={1}
              max={100}
              value={form.max_score}
              onChange={(e) => set("max_score", Number(e.target.value) || 20)}
              className={`${input} w-28`}
            />
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={run}
              disabled={busy || !form.standard_answer.trim()}
              className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
            >
              {busy ? "拆解中…" : "拆解预览"}
            </button>
            {notice && (
              <p className="flex-1 text-xs text-zinc-500 bg-zinc-50 border border-zinc-100 rounded-xl px-3 py-2">
                {notice}
              </p>
            )}
          </div>

          {/* 预览 + 逐点编辑（docs/实施计划 任务一）*/}
          {preview && preview.points.length > 0 && (
            <div className="rounded-xl border border-zinc-200 bg-white shadow-sm overflow-hidden">
              <div className="px-4 py-2.5 flex items-center justify-between border-b border-zinc-100">
                <p className="text-sm font-semibold text-zinc-900">
                  采分点编辑（{rows.length} 个，共 {form.max_score} 分）
                </p>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() =>
                      setRows((rs) => [
                        ...rs,
                        { key: Math.random(), id: `p${rs.length + 1}`, point: "", keywordsText: "", score: 1, point_type: "" },
                      ])
                    }
                    disabled={saving}
                    className="h-8 px-3 rounded-lg border border-zinc-200 text-xs text-zinc-600 hover:bg-zinc-50 disabled:opacity-40 transition-colors"
                  >
                    ＋ 添加采分点
                  </button>
                  <button
                    onClick={confirmSave}
                    disabled={saving || rows.length === 0}
                    className="h-8 px-4 rounded-lg bg-indigo-600 text-white text-xs font-medium hover:bg-indigo-700 disabled:opacity-40 transition-colors"
                  >
                    {saving ? "入库中…" : "确认入库"}
                  </button>
                </div>
              </div>

              <div className="divide-y divide-zinc-100">
                {rows.map((r, i) => (
                  <div key={r.key} className="px-4 py-3 space-y-2">
                    <div className="flex items-start gap-2">
                      <span className="w-10 shrink-0 pt-2 text-[10px] text-zinc-400 select-none">
                        {i + 1}. {r.id}
                      </span>
                      <input
                        value={r.point}
                        onChange={(e) => updateRow(r.key, { point: e.target.value })}
                        placeholder="采分点名称（如：设施互通）"
                        className="flex-1 rounded-lg border border-zinc-200 px-2.5 py-1.5 text-sm text-zinc-800 outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-400 placeholder:text-zinc-300"
                      />
                      <input
                        type="number"
                        min={0}
                        value={r.score}
                        onChange={(e) => updateRow(r.key, { score: Number(e.target.value) || 0 })}
                        title="分值"
                        className="w-16 rounded-lg border border-zinc-200 px-2 py-1.5 text-sm text-zinc-800 outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-400"
                      />
                      {r.point_type ? (
                        <span className="pt-2 text-[10px] text-zinc-400 shrink-0">{r.point_type}</span>
                      ) : null}
                      <button
                        onClick={() => {
                          setRows((rs) => rs.filter((x) => x.key !== r.key));
                          setNotice("已删除该点——入库前可随时改回（重新拆解可恢复全部点）");
                        }}
                        disabled={saving}
                        title="删除该点"
                        className="shrink-0 w-7 h-7 rounded-lg border border-zinc-200 text-zinc-400 hover:text-red-500 hover:border-red-200 disabled:opacity-40 transition-colors"
                      >
                        ✕
                      </button>
                    </div>
                    <div className="flex items-center gap-2 pl-12">
                      <span className="shrink-0 text-[10px] text-zinc-400 w-8">关键词</span>
                      <input
                        value={r.keywordsText}
                        onChange={(e) => updateRow(r.key, { keywordsText: e.target.value })}
                        placeholder="逗号/顿号分隔，如：城际公交、互通"
                        className="flex-1 rounded-lg border border-zinc-200 px-2.5 py-1.5 text-xs text-zinc-700 outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-400 placeholder:text-zinc-300"
                      />
                    </div>
                  </div>
                ))}
              </div>

              {preview.warnings.length > 0 && (
                <div className="px-4 py-2.5 bg-amber-50 border-t border-amber-100 text-xs text-amber-700 space-y-0.5">
                  {preview.warnings.map((w, i) => (
                    <p key={i}>⚠ {w}</p>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
