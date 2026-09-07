"use client";

// ── 申论错题本 · 工作台第 5 页签（docs/39 §6.1）──
// 数据源 = 与面试域同库的 KnowledgeItem（GET /api/items 已按遗忘 gap 降序 = 快忘了排
// 最前），前端过滤 reflow_tier 非空（schema L55「空 = 非申论条目」，面经条目自动滤掉）。
// 条目 = 每漏点一条（id 稳定 sl_{question_id}_{point_id}，wrongbook.py L40，upsert 覆盖）：
//   question=题干 · topic=漏点名 · answer=我的作答（片段/空答）·
//   material_source=漏点材料锚定（L3）· feedback=【错因】cause_type：cause + 【示范】demo
// 内容全走：① 练习黄行回流 ＋ ② 「录入」页手动录错题（docs/39 拍板：不预置示例）。
// 定位：接收 highlightKey（sl_…，档案行「错题 →」落点）→ 滚动 + ring 3s 高亮。

import { useCallback, useEffect, useRef, useState } from "react";
import { deleteItem, fetchItems } from "@/lib/api";
import type { KnowledgeItem } from "@/lib/types";

const SL_TIER_CHIP: Record<string, string> = {
  red: "bg-red-50 text-red-600 border-red-200",
  yellow: "bg-amber-50 text-amber-600 border-amber-200",
  green: "bg-emerald-50 text-emerald-600 border-emerald-200",
};

export default function WrongbookPanel({
  highlightKey, // sl_{question_id}_{point_id}（档案「错题 →」）；null = 普通进入
  onGoPractice,
  onGoRecord,
}: {
  highlightKey: string | null;
  onGoPractice: () => void;
  onGoRecord: () => void;
}) {
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [litKey, setLitKey] = useState<string | null>(null); // 定位高亮（3s 消退）
  const litTimer = useRef<number | undefined>(undefined);
  const consumedKey = useRef<string | null>(null); // 定位一次即消费（同 tab 内列表刷新不重复闪）

  const space = () => localStorage.getItem("offerloop.space") || "default";

  // 申论错题条目 = reflow_tier 非空（面经条目该字段空串，自动滤掉）
  const sl = (it: KnowledgeItem) => it.reflow_tier !== "";

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchItems({ space: space(), limit: 200 }); // 后端按遗忘 gap 降序
      setItems(data.filter(sl));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // ── 定位（档案行「错题 →」落点）：数据就绪后滚到该条目并 ring 3s ──
  // 一次定位即消费（consumedKey）：同 tab 内删除/改动导致 items 变化时不重复闪烁；
  // 切走再进（unmount 重挂）ref 重置 → 同一 key 也能再次定位。
  useEffect(() => {
    if (!highlightKey || loading || consumedKey.current === highlightKey) return;
    const el = document.querySelector(`[data-item-key="${CSS.escape(highlightKey)}"]`);
    if (el instanceof HTMLElement) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      setLitKey(highlightKey);
      window.clearTimeout(litTimer.current);
      litTimer.current = window.setTimeout(() => setLitKey(null), 3000);
    }
    consumedKey.current = highlightKey;
  }, [highlightKey, loading, items]);

  async function handleDelete(it: KnowledgeItem) {
    if (deletingId) return;
    if (!window.confirm(`删除这条错题记录？\n\n${it.question.slice(0, 60)}\n漏点：${it.topic}`)) return;
    setDeletingId(it.id);
    try {
      await deleteItem(it.id, space());
      setItems((prev) => prev.filter((x) => x.id !== it.id));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "删除失败");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="p-5 max-w-2xl">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-base font-semibold text-zinc-900">申论错题本</h2>
          <p className="text-[11px] text-zinc-500">
            每漏点一条 · 按遗忘程度排序（漏答点来自练习回流或手动录入）
          </p>
        </div>
      </div>

      {error && (
        <div className="mb-3 rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-600">
          {error}
        </div>
      )}
      {loading && <p className="text-xs text-zinc-400 text-center py-10">加载中…</p>}

      {!loading && !error && items.length === 0 && (
        <div className="rounded-xl border border-zinc-100 bg-white px-4 py-12 text-center space-y-3">
          <p className="text-sm text-zinc-500">
            错题本是空的——漏答的点加入后才会沉淀到这里
          </p>
          <div className="flex justify-center gap-2">
            <button
              onClick={onGoPractice}
              className="h-9 px-4 rounded-lg bg-indigo-600 text-white text-xs font-medium hover:bg-indigo-700 transition-colors"
            >
              ✍ 去练习
            </button>
            <button
              onClick={onGoRecord}
              className="h-9 px-4 rounded-lg border border-zinc-200 text-zinc-600 text-xs font-medium hover:bg-zinc-50 transition-colors"
            >
              ＋ 录错题
            </button>
          </div>
        </div>
      )}

      {!loading && !error && items.length > 0 && (
        <div className="space-y-2.5">
          {items.map((it) => (
            <div
              key={it.id}
              data-item-key={it.id}
              className={`rounded-xl border bg-white p-3.5 space-y-2 shadow-sm transition-shadow ${
                litKey === it.id ? "border-indigo-400 ring-2 ring-indigo-300/70" : "border-zinc-200"
              }`}
            >
              {/* 头部：题干 + 档位/状态 */}
              <div className="flex items-start gap-2">
                <p className="flex-1 text-sm font-medium text-zinc-900 leading-snug">{it.question}</p>
                <span
                  className={`shrink-0 text-[10px] px-2 py-0.5 rounded-full border ${
                    SL_TIER_CHIP[it.reflow_tier] ?? "bg-zinc-100 text-zinc-500 border-zinc-200"
                  }`}
                >
                  申论 · {it.reflow_tier}
                </span>
              </div>

              {/* 漏点 + 出处 */}
              <div className="flex items-start gap-2">
                <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded bg-zinc-100 text-zinc-500 font-mono">
                  {it.point_id}
                </span>
                <div className="min-w-0 space-y-0.5">
                  <p className="text-xs font-medium text-zinc-700">{it.topic}</p>
                  {it.material_source ? (
                    <p className="text-[11px] text-zinc-500 leading-relaxed">
                      <span className="text-zinc-400">漏点出处：</span>
                      {it.material_source}
                    </p>
                  ) : null}
                </div>
              </div>

              {/* 我的作答（漏答现场原话/空答） */}
              {it.answer ? (
                <details className="group rounded-lg border border-zinc-100 bg-zinc-50/60">
                  <summary className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] text-zinc-500 cursor-pointer select-none list-none">
                    我的作答
                    <span className="ml-auto text-[10px] text-zinc-400 group-open:hidden">展开</span>
                    <span className="ml-auto text-[10px] text-zinc-400 hidden group-open:inline">收起</span>
                  </summary>
                  <div className="px-2.5 pb-2.5 text-xs text-zinc-600 leading-relaxed whitespace-pre-wrap">
                    {it.answer}
                  </div>
                </details>
              ) : (
                <p className="text-[11px] text-zinc-300">（无作答记录）</p>
              )}

              {/* 错因 + 示范 */}
              {it.feedback && (
                <p className="text-xs text-zinc-600 leading-relaxed bg-amber-50/70 border border-amber-100 rounded-lg px-2.5 py-1.5 whitespace-pre-wrap">
                  {it.feedback}
                </p>
              )}

              <div className="flex justify-end">
                <button
                  onClick={() => handleDelete(it)}
                  disabled={deletingId === it.id}
                  className="h-7 px-2.5 rounded-lg border border-zinc-200 text-[11px] text-red-500 hover:bg-red-50 disabled:opacity-40 transition-colors"
                >
                  {deletingId === it.id ? "删除中…" : "删除"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
