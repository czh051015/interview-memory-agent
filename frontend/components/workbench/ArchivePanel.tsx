"use client";

import { useCallback, useEffect, useState } from "react";
import { getWeakpoints } from "@/lib/api";
import type { WeakPointItem } from "@/lib/types";

const STATE_FILTERS = [
  { key: "", label: "全部" },
  { key: "active", label: "激活" },
  { key: "stuck", label: "卡住" },
  { key: "graduated", label: "毕业" },
  { key: "pinned", label: "置顶" },
];

const TIER_BADGE: Record<string, string> = {
  red: "🔴 稳定弱点",
  yellow: "🟡 需关注",
  green: "🟢 巩固中",
};

export default function ArchivePanel() {
  const [state, setState] = useState("");
  const [items, setItems] = useState<WeakPointItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async (s: string) => {
    setLoading(true);
    setError("");
    try {
      const r = await getWeakpoints(s || undefined);
      setItems(r.items);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(state);
  }, [state, load]);

  return (
    <div className="p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-base font-semibold text-zinc-900">薄弱点档案</h2>
          <p className="text-[11px] text-zinc-500">每次练习回流的 hit/miss 累积——漏得多的先练</p>
        </div>
        <div className="flex gap-1.5">
          {STATE_FILTERS.map((f) => (
            <button
              key={f.key || "all"}
              onClick={() => setState(f.key)}
              className={`px-2.5 py-1 rounded-full text-xs transition-colors ${
                state === f.key
                  ? "bg-indigo-600 text-white"
                  : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="mb-3 rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-600">
          {error}
        </div>
      )}
      {loading && <p className="text-xs text-zinc-400 text-center py-10">加载中…</p>}
      {!loading && items.length === 0 && (
        <div className="rounded-xl border border-zinc-100 bg-white px-4 py-10 text-center text-sm text-zinc-400">
          档案为空——去「练习」tab 做一道题，漏点会自动沉淀到这里。
        </div>
      )}

      {!loading && items.length > 0 && (
        <div className="rounded-xl border border-zinc-200 bg-white shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-100 text-left text-[11px] text-zinc-400">
                <th className="px-4 py-2.5 font-medium">采分点</th>
                <th className="px-3 py-2.5 font-medium">来源题</th>
                <th className="px-3 py-2.5 font-medium">漏/练</th>
                <th className="px-3 py-2.5 font-medium">连中</th>
                <th className="px-3 py-2.5 font-medium">状态</th>
                <th className="px-4 py-2.5 font-medium text-right">紧急度</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-50">
              {items.map((w) => (
                <tr key={w.point_key} className="hover:bg-zinc-50/60 transition-colors">
                  <td className="px-4 py-2.5">
                    <p className="text-zinc-800">{w.label}</p>
                    <p className="text-[10px] text-zinc-400">
                      [{w.qtype}
                      {w.point_type ? ` · ${w.point_type}` : ""}]
                    </p>
                  </td>
                  <td className="px-3 py-2.5 text-[11px] text-zinc-500">{w.question_id}</td>
                  <td className="px-3 py-2.5 text-xs text-zinc-600">
                    漏 {w.miss_count} / {w.miss_count + w.hit_count} 练
                  </td>
                  <td className="px-3 py-2.5 text-xs text-zinc-600">
                    {w.consecutive_hits > 0 ? `${w.consecutive_hits} 次` : "—"}
                  </td>
                  <td className="px-3 py-2.5 text-[11px]">{TIER_BADGE[w.tier] || w.tier}</td>
                  <td className="px-4 py-2.5 text-right text-xs text-zinc-500">
                    {w.urgency > 0 ? `${w.urgency.toFixed(1)}` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
