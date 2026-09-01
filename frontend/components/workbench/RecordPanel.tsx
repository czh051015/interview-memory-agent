"use client";

import { useState } from "react";

interface RecordPreview {
  points: Array<{ id: string; point: string; score: number; keywords: string[]; point_type: string }>;
  warnings: string[];
}

// 复用申论域的 post（避免在 api.ts 里为单页面加导出，路径与 API 一致）
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

export default function RecordPanel() {
  const [form, setForm] = useState({
    question: "",
    requirements: "",
    material: "",
    standard_answer: "",
    max_score: 20,
  });
  const [preview, setPreview] = useState<RecordPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  function set<K extends keyof typeof form>(k: K, v: (typeof form)[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function run() {
    if (!form.standard_answer.trim()) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const r = await post<RecordPreview>("/api/shenlun/record", {
        question: form.question,
        requirements: form.requirements,
        material: form.material,
        standard_answer: form.standard_answer,
        max_score: form.max_score,
      });
      setPreview(r);
      setNotice(
        r.points.length > 0
          ? `拆出 ${r.points.length} 个采分点——确认无误后，用 scripts/run_decompose_question.py 正式入库（demo 版仅预览，不落库）。`
          : "没有拆出采分点——检查标准答案是否太短，或稍后重试。",
      );
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "拆解失败");
      setPreview(null);
    } finally {
      setBusy(false);
    }
  }

  const input =
    "w-full rounded-xl border border-zinc-200 bg-white px-3.5 py-2.5 text-sm text-zinc-800 outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-400 placeholder:text-zinc-300";

  return (
    <div className="p-5 max-w-2xl">
      <h2 className="text-base font-semibold text-zinc-900">录入题目</h2>
      <p className="text-[11px] text-zinc-500 mb-4">
        粘贴题目 + 标准答案 → 自动拆采分点预览（人审闸门在 CLI 工具，demo 版不落库）
      </p>

      {error && (
        <div className="mb-3 rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-600">
          {error}
        </div>
      )}

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

        <button
          onClick={run}
          disabled={busy || !form.standard_answer.trim()}
          className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
        >
          {busy ? "拆解中…" : "拆解预览"}
        </button>
      </div>

      {notice && (
        <p className="mt-4 text-xs text-zinc-500 bg-zinc-50 border border-zinc-100 rounded-xl px-4 py-2.5">
          {notice}
        </p>
      )}

      {preview && preview.points.length > 0 && (
        <div className="mt-4 rounded-xl border border-zinc-200 bg-white shadow-sm overflow-hidden">
          <p className="px-4 py-2.5 text-sm font-semibold text-zinc-900 border-b border-zinc-100">
            采分点预览（{preview.points.length} 个，共 {form.max_score} 分）
          </p>
          <div className="divide-y divide-zinc-100">
            {preview.points.map((p) => (
              <div key={p.id} className="px-4 py-2.5">
                <p className="text-sm text-zinc-800">
                  {p.point}
                  <span className="text-[10px] text-zinc-400 ml-1.5">
                    {p.score} 分{p.point_type ? ` · ${p.point_type}` : ""}
                  </span>
                </p>
                {p.keywords.length > 0 && (
                  <p className="text-[11px] text-zinc-400 mt-0.5">关键词：{p.keywords.join("、")}</p>
                )}
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
  );
}
