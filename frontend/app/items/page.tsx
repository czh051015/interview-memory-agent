"use client";

import { useCallback, useEffect, useState } from "react";
import { deleteItem, editItem, fetchItems, markItemStatus, searchItems } from "@/lib/api";
import type { ItemStatus, KnowledgeItem } from "@/lib/types";

type Tab = "" | "fail" | "partial" | "unknown" | "pass";

const TABS: Array<{ key: Tab; label: string }> = [
  { key: "", label: "全部" },
  { key: "fail", label: "❌ 错题" },
  { key: "partial", label: "⚠️ 半会" },
  { key: "unknown", label: "📚 知识库" },
  { key: "pass", label: "✅ 已会" },
];

const STATUS_BADGE: Record<string, string> = {
  fail: "bg-red-50 text-red-600 border-red-200",
  partial: "bg-amber-50 text-amber-600 border-amber-200",
  pass: "bg-emerald-50 text-emerald-600 border-emerald-200",
  unknown: "bg-zinc-100 text-zinc-500 border-zinc-200",
};

const STATUS_LABEL: Record<string, string> = {
  fail: "没答上",
  partial: "答一半",
  pass: "答上了",
  unknown: "待标注",
};

// 申论错题条目 badge（docs/实施计划 任务二）：reflow_tier 非空即申论条目（初始 red，wrongbook.py L53）
const SL_TIER_CHIP: Record<string, string> = {
  red: "bg-red-50 text-red-600 border-red-200",
  yellow: "bg-amber-50 text-amber-600 border-amber-200",
  green: "bg-emerald-50 text-emerald-600 border-emerald-200",
};

const MARK_OPTIONS: Array<{ key: "fail" | "partial" | "pass"; label: string }> = [
  { key: "fail", label: "不会" },
  { key: "partial", label: "一半" },
  { key: "pass", label: "会了" },
];

function daysSince(iso: string | null): number | null {
  if (!iso) return null;
  const d = (Date.now() - new Date(iso).getTime()) / 86400000;
  return Math.max(0, Math.floor(d));
}

export default function ItemsPage() {
  const [tab, setTab] = useState<Tab>("fail");
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [markingId, setMarkingId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState({ question: "", topic: "", answer: "" });
  const [saving, setSaving] = useState(false);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<KnowledgeItem[] | null>(null);
  // ── 档案页跳转定位（?item=sl_…）：定位是叠加逻辑，无参数时行为与原来完全一致 ──
  const [locateId, setLocateId] = useState<string | null>(null); // 待定位条目 id
  const [locateMiss, setLocateMiss] = useState(false); // 全量拉完仍无 → 顶部提示
  const [highlightId, setHighlightId] = useState<string | null>(null); // 定位成功 ring 3s

  const space = () => localStorage.getItem("offerloop.space") || "default";

  const load = useCallback(async (t: Tab) => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchItems({ status: t, space: space(), limit: 300 });
      setItems(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  async function handleSearch() {
    const q = query.trim();
    if (!q || searching) return;
    setSearching(true);
    setError("");
    try {
      setSearchResults(await searchItems(q, space()));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "检索失败");
    } finally {
      setSearching(false);
    }
  }

  useEffect(() => {
    load(tab);
  }, [tab, load]);

  // 档案页「错题 →」带 ?item=sl_{question_id}_{point_id} 进入：读一次并消费
  // （useSearchParams 会触发 Next Suspense 要求，此处按 docs 直接读 location.search）。
  // 定位需全量拉取（条目可能被标过 pass/partial，fail tab 下找不到）→ 切 tab ""。
  useEffect(() => {
    if (typeof window === "undefined") return;
    const item = new URLSearchParams(window.location.search).get("item");
    if (!item) return;
    setLocateId(item);
    setTab("");
    setLocateMiss(false);
    window.history.replaceState(null, "", window.location.pathname); // 消费即清，防刷新/返回重复定位
  }, []);

  // 列表就绪后定位：找到 → scrollIntoView + ring 3s + 展开 answer 折叠区；无 → 提示未入错题本
  useEffect(() => {
    if (!locateId || loading || tab !== "") return;
    const el = document.querySelector(`[data-item-id="${CSS.escape(locateId)}"]`);
    if (el instanceof HTMLElement) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.querySelector("details")?.setAttribute("open", "");
      setHighlightId(locateId);
      window.setTimeout(() => setHighlightId((h) => (h === locateId ? null : h)), 3000);
    } else {
      setLocateMiss(true); // 全量已拉仍无 → 该弱项尚未入错题本（空态提示）
    }
    setLocateId(null); // 只定位一次，后续 items 刷新不再触发
  }, [locateId, loading, tab, items]);

  async function handleMark(it: KnowledgeItem, status: "fail" | "partial" | "pass") {
    if (markingId) return;
    setMarkingId(it.id);
    try {
      const updated = await markItemStatus(it.id, status);
      setItems((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "标注失败");
    } finally {
      setMarkingId(null);
    }
  }

  function startEdit(it: KnowledgeItem) {
    setEditingId(it.id);
    setDraft({ question: it.question, topic: it.topic, answer: it.answer });
  }

  async function handleSaveEdit(it: KnowledgeItem) {
    if (!draft.question.trim() || saving) return;
    setSaving(true);
    setError("");
    try {
      const updated = await editItem(
        it.id,
        { question: draft.question.trim(), topic: draft.topic.trim(), answer: draft.answer.trim() },
        space(),
      );
      setItems((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
      setEditingId(null);
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(it: KnowledgeItem) {
    if (!window.confirm(`确定删除这道题？\n\n${it.question.slice(0, 50)}`)) return;
    try {
      await deleteItem(it.id, space());
      setItems((prev) => prev.filter((x) => x.id !== it.id));
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "删除失败");
    }
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
            <h1 className="text-sm font-semibold text-zinc-900">错题本</h1>
            <p className="text-[11px] text-zinc-500">列表按遗忘程度排序，点按钮直接标注</p>
          </div>
        </div>

        {/* 搜索 */}
        <div className="px-5 pt-4">
          <div className="flex gap-2">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder="语义检索：如「RAG 相关的题」"
              className="flex-1 rounded-lg border border-zinc-300 bg-zinc-50 px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:bg-white focus:ring-1 focus:ring-indigo-500/20 transition-all"
            />
            <button
              onClick={handleSearch}
              disabled={!query.trim() || searching}
              className="shrink-0 px-4 rounded-lg bg-indigo-600 text-white text-xs font-medium hover:bg-indigo-700 disabled:opacity-40 transition-all"
            >
              {searching ? "检索中…" : "检索"}
            </button>
            {searchResults !== null ? (
              <button
                onClick={() => {
                  setSearchResults(null);
                  setQuery("");
                }}
                className="shrink-0 px-3 rounded-lg border border-zinc-300 text-xs text-zinc-500 hover:bg-zinc-50 transition-colors"
              >
                清除
              </button>
            ) : null}
          </div>
          {searchResults !== null ? (
            <p className="text-[11px] text-zinc-400 mt-1.5">
              检索「{query}」：{searchResults.length} 条命中（按语义相似度）
            </p>
          ) : null}
        </div>

        {/* Tabs */}
        <div className="px-5 pt-4 flex gap-1.5 flex-wrap">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                tab === t.key
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* 档案跳来但错题本里没有该漏点条目 */}
        {locateMiss && (
          <div className="mx-5 mt-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-xs text-amber-700 leading-relaxed">
            该弱项尚未入错题本（漏答点加入错题本后才会出现）——回「档案」从练习入口再答一次，漏点时会提示加入。
          </div>
        )}

        {/* List */}
        <div className="px-5 py-4 space-y-2.5">
          {loading ? (
            <p className="text-xs text-zinc-400 text-center py-10">加载中…</p>
          ) : error ? (
            <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
              {error}
            </div>
          ) : (searchResults ?? items).length === 0 ? (
            <div className="text-center py-12 space-y-3">
              <p className="text-sm text-zinc-500">
                {searchResults !== null
                  ? "没有检索到相关题目"
                  : tab === "fail"
                    ? "错题本是空的——先去记几道题"
                    : "这个分类下还没有题"}
              </p>
              <a
                href="/record"
                className="inline-block h-10 px-5 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-all"
              >
                ＋ 去记错题
              </a>
            </div>
          ) : (
            (searchResults ?? items).map((it) => (
              <div
                key={it.id}
                data-item-id={it.id}
                className={`rounded-xl border bg-white p-3.5 space-y-2.5 shadow-sm transition-shadow ${
                  highlightId === it.id
                    ? "border-indigo-400 ring-2 ring-indigo-300/70"
                    : "border-zinc-200"
                }`}
              >
                <div className="flex items-start gap-2">
                  {editingId === it.id ? (
                    <input
                      value={draft.question}
                      onChange={(e) => setDraft((d) => ({ ...d, question: e.target.value }))}
                      className="flex-1 rounded-lg border border-indigo-300 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/20"
                      placeholder="题目"
                      autoFocus
                    />
                  ) : (
                    <p className="flex-1 text-sm font-medium text-zinc-900 leading-snug">
                      {it.question}
                    </p>
                  )}
                  <span
                    className={`shrink-0 text-[10px] px-2 py-0.5 rounded-full border ${
                      STATUS_BADGE[it.status] ?? STATUS_BADGE.unknown
                    }`}
                  >
                    {STATUS_LABEL[it.status] ?? it.status}
                  </span>
                  {it.reflow_tier ? (
                    <span
                      className={`shrink-0 text-[10px] px-2 py-0.5 rounded-full border ${
                        SL_TIER_CHIP[it.reflow_tier] ?? "bg-zinc-100 text-zinc-500 border-zinc-200"
                      }`}
                      title="申论漏点条目（错题本红/黄/绿档位，docs/22 §3.6）"
                    >
                      申论 · {it.reflow_tier}
                    </span>
                  ) : null}
                </div>

                {editingId === it.id ? (
                  <div className="space-y-2 rounded-lg border border-indigo-200 bg-indigo-50/40 p-2.5">
                    <label className="block">
                      <span className="text-[10px] text-zinc-400 block mb-0.5">主题</span>
                      <input
                        value={draft.topic}
                        onChange={(e) => setDraft((d) => ({ ...d, topic: e.target.value }))}
                        className="w-full rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-xs outline-none focus:border-indigo-500"
                        placeholder="如 RAG / Agent"
                      />
                    </label>
                    <label className="block">
                      <span className="text-[10px] text-zinc-400 block mb-0.5">
                        {it.reflow_tier ? "作答片段（漏答现场原话，可改）" : "参考答案 / 面试官反馈（可改）"}
                      </span>
                      <textarea
                        value={draft.answer}
                        onChange={(e) => setDraft((d) => ({ ...d, answer: e.target.value }))}
                        rows={4}
                        className="w-full rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-xs leading-relaxed outline-none focus:border-indigo-500"
                        placeholder="留空表示没有"
                      />
                    </label>
                    <div className="flex gap-2">
                      <button
                        onClick={() => setEditingId(null)}
                        disabled={saving}
                        className="h-8 px-3 rounded-lg border border-zinc-300 text-xs text-zinc-600 hover:bg-zinc-50 disabled:opacity-40"
                      >
                        取消
                      </button>
                      <button
                        onClick={() => handleSaveEdit(it)}
                        disabled={!draft.question.trim() || saving}
                        className="h-8 flex-1 rounded-lg bg-indigo-600 text-white text-xs font-medium hover:bg-indigo-700 disabled:opacity-40"
                      >
                        {saving ? "保存中…" : "保存"}
                      </button>
                    </div>
                  </div>
                ) : null}

                <div className="flex flex-wrap items-center gap-1.5">
                  {it.topic ? (
                    <span className="text-[10px] text-indigo-600 bg-indigo-50 border border-indigo-100 rounded-full px-2 py-0.5">
                      {it.topic}
                    </span>
                  ) : null}
                  {it.company ? (
                    <span className="text-[10px] text-zinc-500 bg-zinc-100 rounded-full px-2 py-0.5">
                      {it.company}
                    </span>
                  ) : null}
                  {it.round ? (
                    <span className="text-[10px] text-zinc-400 rounded-full px-2 py-0.5">
                      {it.round}
                    </span>
                  ) : null}
                  <span className="text-[10px] text-zinc-400 rounded-full px-2 py-0.5">
                    掌握度 {Math.round(it.mastery_score * 100)}%
                  </span>
                  {it.similarity !== undefined && it.similarity > 0 ? (
                    <span className="text-[10px] text-blue-600 bg-blue-50 border border-blue-100 rounded-full px-2 py-0.5">
                      sim {it.similarity.toFixed(2)}
                    </span>
                  ) : null}
                  {daysSince(it.last_reviewed_at) !== null && it.status !== "pass" ? (
                    <span
                      className={`text-[10px] rounded-full px-2 py-0.5 ${
                        daysSince(it.last_reviewed_at)! >= 7
                          ? "text-red-500 bg-red-50"
                          : "text-zinc-400"
                      }`}
                    >
                      {daysSince(it.last_reviewed_at)! >= 7
                        ? `${daysSince(it.last_reviewed_at)} 天没复习`
                        : "最近复习过"}
                    </span>
                  ) : null}
                </div>

                {it.user_note ? (
                  <p className="text-xs text-zinc-500 leading-relaxed bg-zinc-50 rounded-lg px-2.5 py-1.5">
                    {it.user_note}
                  </p>
                ) : null}

                {it.answer ? (
                  <details className="group rounded-lg border border-indigo-100 bg-indigo-50/40">
                    <summary className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] text-indigo-600 cursor-pointer select-none list-none">
                      {it.reflow_tier ? "你的作答（漏答现场原话）" : "参考答案 / 面试官反馈"}
                      <span className="ml-auto text-[10px] text-zinc-400 group-open:hidden">展开</span>
                      <span className="ml-auto text-[10px] text-zinc-400 hidden group-open:inline">收起</span>
                    </summary>
                    <div className="px-2.5 pb-2.5 text-xs text-zinc-600 leading-relaxed whitespace-pre-wrap">
                      {it.answer}
                    </div>
                  </details>
                ) : null}

                {/* 申论漏点条目增强（docs/实施计划 任务二）：漏点出处锚定 + 错因与示范——
                    否则跳过来的是"看不懂的面试条目"；topic 已自动显示漏点名 */}
                {it.reflow_tier && (it.material_source || it.feedback) ? (
                  <div className="space-y-1.5">
                    {it.material_source ? (
                      <p className="text-xs text-zinc-500 leading-relaxed bg-zinc-50 rounded-lg px-2.5 py-1.5">
                        <span className="text-zinc-400 mr-1">📎 漏点出处</span>
                        {it.material_source}
                      </p>
                    ) : null}
                    {it.feedback ? (
                      <p className="text-xs text-zinc-600 leading-relaxed bg-amber-50/70 border border-amber-100 rounded-lg px-2.5 py-1.5 whitespace-pre-wrap">
                        {it.feedback}
                      </p>
                    ) : null}
                  </div>
                ) : null}

                {/* 标注三态 + 编辑/删除 */}
                <div className="flex gap-1.5">
                  {MARK_OPTIONS.map((m) => {
                    const active = it.status === m.key;
                    return (
                      <button
                        key={m.key}
                        onClick={() => handleMark(it, m.key)}
                        disabled={markingId === it.id || editingId === it.id}
                        className={`flex-1 h-8 rounded-lg text-xs font-medium border transition-all disabled:opacity-50 ${
                          active
                            ? m.key === "fail"
                              ? "bg-red-500 border-red-500 text-white"
                              : m.key === "partial"
                                ? "bg-amber-500 border-amber-500 text-white"
                                : "bg-emerald-500 border-emerald-500 text-white"
                            : "border-zinc-200 text-zinc-500 hover:bg-zinc-50"
                        }`}
                      >
                        {markingId === it.id ? "…" : m.label}
                      </button>
                    );
                  })}
                  {editingId !== it.id ? (
                    <>
                      <button
                        onClick={() => startEdit(it)}
                        className="shrink-0 h-8 px-2.5 rounded-lg border border-zinc-200 text-[11px] text-zinc-500 hover:bg-zinc-50 transition-colors"
                      >
                        编辑
                      </button>
                      <button
                        onClick={() => handleDelete(it)}
                        className="shrink-0 h-8 px-2.5 rounded-lg border border-zinc-200 text-[11px] text-red-500 hover:bg-red-50 transition-colors"
                      >
                        删除
                      </button>
                    </>
                  ) : null}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
