"use client";

import { useCallback, useEffect, useState } from "react";
import { getDiagnose, getRemind, getWeakpoints } from "@/lib/api";
import type { DiagnoseData, RemindData, WeakPointItem } from "@/lib/types";

const TIER_BADGE: Record<string, string> = {
  red: "🔴 稳定弱点",
  yellow: "🟡 需关注",
  green: "🟢 巩固中",
};

export default function DashboardPanel({ onGoPractice }: { onGoPractice: () => void }) {
  const [remind, setRemind] = useState<RemindData | null>(null);
  const [diagnose, setDiagnose] = useState<DiagnoseData | null>(null);
  const [top, setTop] = useState<WeakPointItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [r, d, w] = await Promise.all([getRemind(), getDiagnose(), getWeakpoints()]);
      setRemind(r);
      setDiagnose(d);
      setTop(w.items.slice(0, 5));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <p className="text-xs text-zinc-400 text-center py-10">加载中…</p>;
  if (error)
    return <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">{error}</div>;

  const hasData = (remind?.to_practice.length ?? 0) > 0 || (remind?.graduation_candidates.length ?? 0) > 0;

  return (
    <div className="p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-zinc-900">今日工作台</h2>
          <p className="text-[11px] text-zinc-500">按薄弱档案推荐——漏得多的先练</p>
        </div>
        <button
          onClick={onGoPractice}
          className="px-3.5 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors"
        >
          开始练习 →
        </button>
      </div>

      {!hasData && (
        <div className="rounded-xl border border-indigo-100 bg-indigo-50/60 px-4 py-3 text-sm text-indigo-700">
          档案还是空的——去「练习」tab 做第一道题，作答即入库，第二天就有「今日提醒」了。
        </div>
      )}

      {/* 今日提醒卡 */}
      {remind && hasData && (
        <div className="rounded-xl border border-zinc-200 bg-white shadow-sm overflow-hidden">
          <p className="px-4 py-2.5 text-sm font-semibold text-zinc-900 border-b border-zinc-100">
            今日提醒
          </p>
          <div className="divide-y divide-zinc-100">
            {remind.graduation_candidates.map((g) => (
              <div key={g.point} className="px-4 py-2.5 flex items-center gap-2">
                <span className="text-[10px] shrink-0 text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-2 py-0.5">
                  🎓 毕业考
                </span>
                <p className="flex-1 text-sm text-zinc-800">
                  {g.point}
                  <span className="text-[10px] text-zinc-400 ml-1.5">[{g.qtype}]</span>
                </p>
                <span className="shrink-0 text-[10px] text-zinc-400">{g.days} 天未验证</span>
              </div>
            ))}
            {remind.to_practice.map((r) => (
              <div key={r.point} className="px-4 py-2.5 flex items-center gap-2">
                <span className="text-[10px] shrink-0 text-red-700 bg-red-50 border border-red-200 rounded-full px-2 py-0.5">
                  🔴 该练
                </span>
                <p className="flex-1 text-sm text-zinc-800">
                  {r.point}
                  <span className="text-[10px] text-zinc-400 ml-1.5">[{r.qtype}]</span>
                </p>
                <span className="shrink-0 text-[10px] text-zinc-400">
                  {r.days <= 0 ? "今天" : `${r.days} 天前`} 练过
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 角度诊断 */}
      {diagnose && Object.keys(diagnose.by_angle).length > 0 && (
        <div className="rounded-xl border border-zinc-200 bg-white shadow-sm p-4">
          <p className="text-sm font-semibold text-zinc-900 mb-1">角度诊断</p>
          <p className="text-[11px] text-zinc-400 mb-3">总漏哪类角度（跨题型聚合，L2 诊断）</p>
          <div className="space-y-2">
            {Object.entries(diagnose.by_angle)
              .sort(([, a], [, b]) => b.miss_sum - a.miss_sum)
              .slice(0, 6)
              .map(([angle, s]) => {
                const max = Math.max(1, ...Object.values(diagnose.by_angle).map((x) => x.miss_sum));
                return (
                  <div key={angle} className="flex items-center gap-2">
                    <span className="w-16 shrink-0 text-[11px] text-zinc-600 text-right">{angle}</span>
                    <div className="flex-1 h-2 rounded-full bg-zinc-100 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-indigo-500"
                        style={{ width: `${(s.miss_sum / max) * 100}%` }}
                      />
                    </div>
                    <span className="w-8 shrink-0 text-[10px] text-zinc-400">
                      {s.miss_sum}漏
                      {s.red > 0 ? ` · ${s.red}红` : ""}
                    </span>
                  </div>
                );
              })}
          </div>
        </div>
      )}

      {/* 薄弱点 Top */}
      {top.length > 0 && (
        <div className="rounded-xl border border-zinc-200 bg-white shadow-sm overflow-hidden">
          <p className="px-4 py-2.5 text-sm font-semibold text-zinc-900 border-b border-zinc-100">
            薄弱点 Top
          </p>
          <div className="divide-y divide-zinc-100">
            {top.map((w) => (
              <div key={w.point_key} className="px-4 py-2.5 flex items-center gap-2">
                <p className="flex-1 text-sm text-zinc-800">
                  {w.label}
                  <span className="text-[10px] text-zinc-400 ml-1.5">
                    [{w.qtype}
                    {w.point_type ? ` · ${w.point_type}` : ""}]
                  </span>
                </p>
                <span className="text-[10px] text-zinc-400 shrink-0">
                  漏 {w.miss_count} / 练 {w.miss_count + w.hit_count}
                </span>
                <span className="text-[10px] shrink-0">{TIER_BADGE[w.tier] || w.tier}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
