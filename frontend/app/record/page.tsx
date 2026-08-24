"use client";

import { useState } from "react";
import { decompose, recordItems } from "@/lib/api";
import type { DecomposeResult, KnowledgeItem } from "@/lib/types";

type Phase = "idle" | "loading" | "preview" | "saving" | "saved";

const CATEGORY_LABEL: Record<string, string> = {
  knowledge: "知识点",
  info: "信息性",
};

export default function RecordPage() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [rawText, setRawText] = useState("");
  const [result, setResult] = useState<DecomposeResult | null>(null);
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [error, setError] = useState("");
  const [storedCount, setStoredCount] = useState(0);

  async function handleDecompose() {
    const text = rawText.trim();
    if (!text || phase === "loading") return;
    setError("");
    setPhase("loading");
    try {
      const res = await decompose(text);
      setResult(res);
      setItems(res.items);
      setPhase("preview");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "拆解失败");
      setPhase("idle");
    }
  }

  // 上传面经文本文件：浏览器 FileReader 读为 UTF-8，拼进输入框，复用拆解链路
  async function handleFilePick(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // 允许重复选择同一文件
    if (!file || phase === "loading") return;
    setError("");
    try {
      const text = await file.text();
      setRawText((prev) => (prev.trim() ? `${prev}\n\n${text}` : text));
    } catch {
      setError("文件读取失败，试试直接粘贴文本");
    }
  }

  function handleRemoveItem(id: string) {
    setItems((prev) => prev.filter((it) => it.id !== id));
  }

  function updateMeta(field: "company" | "role" | "round" | "date", value: string) {
    setResult((prev) => (prev ? { ...prev, [field]: value } : prev));
    setItems((prev) => prev.map((it) => ({ ...it, [field]: value })));
  }

  async function handleSave() {
    if (!items.length || phase === "saving") return;
    setError("");
    setPhase("saving");
    try {
      const space = localStorage.getItem("offerloop.space") || "default";
      const res = await recordItems(items, space);
      setStoredCount(res.stored);
      setPhase("saved");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "入库失败");
      setPhase("preview");
    }
  }

  function handleAgain() {
    setPhase("idle");
    setRawText("");
    setResult(null);
    setItems([]);
    setError("");
  }

  return (
    <div className="min-h-dvh bg-zinc-50/50">
      <div className="max-w-3xl mx-auto w-full bg-white min-h-dvh shadow-sm border-x border-zinc-200">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-zinc-200 bg-white shrink-0 sticky top-0 z-10">
          <a
            href="/"
            className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white text-sm font-bold hover:bg-indigo-700 transition-colors"
          >
            O
          </a>
          <div>
            <h1 className="text-sm font-semibold text-zinc-900">记错题</h1>
            <p className="text-[11px] text-zinc-500">粘贴面经/复盘 → 自动拆解 → 确认入库</p>
          </div>
        </div>

        <div className="px-5 py-5 space-y-5">
          {/* 录入/预览主区 */}
          {phase === "idle" || phase === "loading" ? (
            <div className="space-y-3">
              <textarea
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
                placeholder={`粘贴你的面试复盘或面经原文，例如：\n\n今天面了字节的 AI 应用开发岗。\nQ1: RAG 混合检索怎么做的？我答了向量检索和关键词检索，忘了说 RRF 融合，追问没接住。\nQ2: 自我介绍。过了。`}
                rows={10}
                disabled={phase === "loading"}
                className="w-full resize-y rounded-xl border border-zinc-300 bg-zinc-50 px-4 py-3 text-sm leading-relaxed outline-none focus:border-indigo-500 focus:bg-white focus:ring-1 focus:ring-indigo-500/20 transition-all disabled:opacity-60"
              />
              <button
                onClick={handleDecompose}
                disabled={!rawText.trim() || phase === "loading"}
                className="w-full h-11 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all active:scale-[0.99]"
              >
                {phase === "loading" ? "正在拆解（首次约 10-30 秒）…" : "拆解"}
              </button>

              {/* 或上传面经文本文件：浏览器直接读，填进上方输入框，走同一条拆解链路 */}
              <label className="block text-center text-[11px] text-indigo-600 border border-dashed border-indigo-300 rounded-lg py-2 hover:bg-indigo-50 cursor-pointer transition-colors">
                或上传 .txt / .md 面经文件（不用复制粘贴）
                <input
                  type="file"
                  accept=".txt,.md,text/plain,text/markdown"
                  className="hidden"
                  onChange={handleFilePick}
                  disabled={phase === "loading"}
                />
              </label>

              <p className="text-[11px] text-zinc-400 text-center">
                拆解 = 把一段话切成结构化题目，LLM 理解，可能需要等待
              </p>
            </div>
          ) : null}

          {phase === "preview" || phase === "saving" ? (
            <div className="space-y-4">
              {/* 元信息编辑 */}
              <div className="rounded-xl border border-zinc-200 bg-zinc-50/60 p-4 space-y-3">
                <p className="text-xs font-medium text-zinc-500">面试背景（可改）</p>
                <div className="grid grid-cols-2 gap-3">
                  <MetaInput label="公司" value={result?.company ?? ""} onChange={(v) => updateMeta("company", v)} placeholder="字节" />
                  <MetaInput label="岗位" value={result?.role ?? ""} onChange={(v) => updateMeta("role", v)} placeholder="AI应用开发" />
                  <MetaInput label="轮次" value={result?.round ?? ""} onChange={(v) => updateMeta("round", v)} placeholder="技术一面" />
                  <MetaInput label="日期" value={result?.date ?? ""} onChange={(v) => updateMeta("date", v)} placeholder="2026-08-18" />
                </div>
              </div>

              {/* 条目预览 */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-medium text-zinc-500">
                    拆出 {items.length} 道（可删掉不想要的）
                  </p>
                  {result?.suspected_fail ? (
                    <span className="text-[10px] text-amber-600 bg-amber-50 border border-amber-200 rounded-full px-2 py-0.5">
                      整篇疑似栽过，待你确认后手动标错题
                    </span>
                  ) : null}
                </div>
                <div className="space-y-2.5">
                  {items.map((it) => (
                    <div
                      key={it.id}
                      className="rounded-xl border border-zinc-200 bg-white p-3.5 space-y-2 shadow-sm"
                    >
                      <div className="flex items-start gap-2">
                        <p className="flex-1 text-sm font-medium text-zinc-900 leading-snug">
                          {it.question}
                        </p>
                        <button
                          onClick={() => handleRemoveItem(it.id)}
                          disabled={phase === "saving"}
                          className="shrink-0 text-[11px] text-zinc-400 hover:text-red-500 disabled:opacity-40 transition-colors"
                        >
                          删除
                        </button>
                      </div>
                      <div className="flex flex-wrap items-center gap-1.5">
                        {it.topic ? (
                          <span className="text-[10px] text-indigo-600 bg-indigo-50 border border-indigo-100 rounded-full px-2 py-0.5">
                            {it.topic}
                          </span>
                        ) : null}
                        {it.question_type ? (
                          <span className="text-[10px] text-zinc-500 bg-zinc-100 rounded-full px-2 py-0.5">
                            {it.question_type}
                          </span>
                        ) : null}
                        <span className="text-[10px] text-zinc-400 rounded-full px-2 py-0.5">
                          {CATEGORY_LABEL[it.category] ?? it.category}
                        </span>
                        <span className="text-[10px] text-zinc-400 rounded-full px-2 py-0.5">
                          状态：待标注
                        </span>
                      </div>
                      {it.user_note ? (
                        <p className="text-xs text-zinc-500 leading-relaxed bg-zinc-50 rounded-lg px-2.5 py-1.5">
                          {it.user_note}
                        </p>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>

              {/* 操作 */}
              <div className="flex gap-3">
                <button
                  onClick={() => setPhase("idle")}
                  disabled={phase === "saving"}
                  className="h-11 px-5 rounded-xl border border-zinc-300 text-sm text-zinc-600 hover:bg-zinc-50 disabled:opacity-40 transition-all"
                >
                  返回修改
                </button>
                <button
                  onClick={handleSave}
                  disabled={!items.length || phase === "saving"}
                  className="flex-1 h-11 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all active:scale-[0.99]"
                >
                  {phase === "saving" ? "入库中…" : `确认入库（${items.length} 道）`}
                </button>
              </div>
            </div>
          ) : null}

          {phase === "saved" ? (
            <div className="text-center py-14 space-y-4">
              <div className="w-14 h-14 mx-auto rounded-full bg-emerald-50 border border-emerald-200 flex items-center justify-center text-2xl">
                ✅
              </div>
              <div>
                <p className="text-sm font-semibold text-zinc-900">
                  已入库 {storedCount} 道题
                </p>
                <p className="text-xs text-zinc-500 mt-1">
                  题目已进入你的错题本，可在「看错题」里复查
                </p>
              </div>
              <button
                onClick={handleAgain}
                className="h-11 px-6 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-all active:scale-[0.99]"
              >
                再记一道
              </button>
            </div>
          ) : null}

          {error ? (
            <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
              {error}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function MetaInput({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="block">
      <span className="text-[11px] text-zinc-400 block mb-1">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/20 transition-all"
      />
    </label>
  );
}
