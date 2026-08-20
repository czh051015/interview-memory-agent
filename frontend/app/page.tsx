"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchDashboard } from "@/lib/api";
import type { DashboardData, RemindEntry } from "@/lib/types";

const SPACE_KEY = "offerloop.space";

function getSpace(): string {
  if (typeof window === "undefined") return "default";
  return localStorage.getItem(SPACE_KEY) || "default";
}

function setSpace(v: string) {
  localStorage.setItem(SPACE_KEY, v);
}

const STATUS_CARD = [
  { key: "fail", label: "错题", cls: "text-red-600 bg-red-50 border-red-200", emoji: "❌" },
  { key: "partial", label: "半会", cls: "text-amber-600 bg-amber-50 border-amber-200", emoji: "⚠️" },
  { key: "pass", label: "已会", cls: "text-emerald-600 bg-emerald-50 border-emerald-200", emoji: "✅" },
  { key: "unknown", label: "待标注", cls: "text-zinc-500 bg-zinc-50 border-zinc-200", emoji: "📚" },
];

function RemindList({ title, color, entries }: { title: string; color: string; entries: RemindEntry[] }) {
  const [open, setOpen] = useState(true);
  if (!entries.length) return null;
  const shown = open ? entries : entries.slice(0, 5);
  return (
    <div className="rounded-xl border border-zinc-200 bg-white shadow-sm overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-zinc-50 transition-colors"
      >
        <span className={`text-sm font-semibold ${color}`}>
          {title}（{entries.length}）
        </span>
        <span className="text-[10px] text-zinc-400">{open ? "收起 ▲" : "展开 ▼"}</span>
      </button>
      <div className="border-t border-zinc-100 divide-y divide-zinc-100">
        {shown.map((e) => (
          <div key={e.id} className="px-4 py-2.5 flex items-start gap-2">
            <p className="flex-1 text-sm text-zinc-800 leading-snug">{e.question}</p>
            <span className="shrink-0 text-[10px] text-zinc-400 mt-0.5">
              {e.days <= 0 ? "今天" : `${e.days}天前`} · {Math.round(e.gap * 100)}% 缺口
            </span>
          </div>
        ))}
      </div>
      {!open && entries.length > 5 && (
        <button
          onClick={() => setOpen(true)}
          className="w-full text-center text-[11px] text-indigo-600 py-2 hover:bg-indigo-50/50 transition-colors"
        >
          展开全部 {entries.length} 条
        </button>
      )}
    </div>
  );
}

function MasteryCurve({ curve }: { curve: DashboardData["curve"] }) {
  const W = 340, H = 110, PAD = 30, TOP = 12;
  const xs = curve.map((_, i) => PAD + (i * (W - PAD * 2)) / Math.max(curve.length - 1, 1));
  const yOf = (m: number) => H - TOP - m * (H - TOP * 2);
  const points = curve
    .map((c, i) => (c.avg_mastery === null ? null : { x: xs[i], y: yOf(c.avg_mastery), c }))
    .filter((p): p is { x: number; y: number; c: DashboardData["curve"][number] } => p !== null);

  // 折线路径：相邻有值点连线
  const pathParts: string[] = [];
  let prev: { x: number; y: number } | null = null;
  for (const p of points) {
    if (prev && p.x - prev.x > (W - PAD * 2) / 2 + 1) {
      prev = null; // 断点（空桶）
    }
    pathParts.push(`${prev ? "L" : "M"}${p.x},${p.y}`);
    prev = p;
  }

  return (
    <div className="rounded-xl border border-zinc-200 bg-white shadow-sm p-4">
      <div className="flex items-center justify-between mb-2">
        <p className="text-sm font-semibold text-zinc-900">遗忘曲线</p>
        <p className="text-[10px] text-zinc-400">按上次复习/标注间隔 · 平均掌握度</p>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto">
        {/* 网格 + 标签 */}
        {[0.25, 0.5, 0.75, 1.0].map((m) => (
          <g key={m}>
            <line x1={PAD} y1={yOf(m)} x2={W - PAD} y2={yOf(m)} stroke="#f4f4f5" strokeWidth={1} />
            <text x={W - PAD + 6} y={yOf(m) + 3} fontSize={8} fill="#a1a1aa">
              {Math.round(m * 100)}%
            </text>
          </g>
        ))}
        <path d={pathParts.join("")} fill="none" stroke="#4f46e5" strokeWidth={2} strokeLinejoin="round" />
        {points.map((p) => (
          <g key={p.x}>
            <circle cx={p.x} cy={p.y} r={3.5} fill="#4f46e5" />
            <text x={p.x} y={p.y - 7} fontSize={8} textAnchor="middle" fill="#71717a">
              {p.c.count}
            </text>
          </g>
        ))}
        {curve.map((c, i) => (
          <text key={c.bucket} x={xs[i]} y={H - 2} fontSize={8} textAnchor="middle" fill="#a1a1aa">
            {c.bucket}
          </text>
        ))}
      </svg>
      <p className="text-[10px] text-zinc-400 mt-1">点上的数字 = 该间隔的题目数；曲线整体向右下 = 遗忘在发生</p>
    </div>
  );
}

export default function Home() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [space, setSpaceState] = useState<string>(getSpace());
  const [newSpace, setNewSpace] = useState(""); // "新建空间"输入框
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async (sp: string) => {
    setLoading(true);
    setError("");
    try {
      setData(await fetchDashboard(sp));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(space);
  }, [space, load]);

  function handleSpaceChange(v: string) {
    setSpace(v);
    setSpaceState(v);
  }

  const nav = (
    <div className="ml-auto flex items-center gap-2 text-[11px] text-zinc-400">
      <a href="/items" className="px-2.5 py-1 rounded-lg border border-zinc-200 text-zinc-500 hover:bg-zinc-50 hover:text-indigo-600 transition-colors">
        错题本
      </a>
      <a href="/record" className="px-2.5 py-1 rounded-lg border border-zinc-200 text-zinc-500 hover:bg-zinc-50 hover:text-indigo-600 transition-colors">
        ＋ 记错题
      </a>
      <a href="/chat" className="px-2.5 py-1 rounded-lg border border-zinc-200 text-zinc-500 hover:bg-zinc-50 hover:text-indigo-600 transition-colors">
        💬 聊天
      </a>
      <a href="/mock-interview" className="px-2.5 py-1 rounded-lg border border-indigo-200 text-indigo-600 bg-indigo-50/60 hover:bg-indigo-100 transition-colors">
        🎯 模拟面试
      </a>
    </div>
  );

  return (
    <div className="min-h-dvh bg-zinc-50/50">
      <div className="max-w-3xl mx-auto w-full bg-white min-h-dvh shadow-sm border-x border-zinc-200">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-zinc-200 bg-white shrink-0 sticky top-0 z-10">
          <a href="/" className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white text-sm font-bold hover:bg-indigo-700 transition-colors">
            O
          </a>
          <div>
            <h1 className="text-sm font-semibold text-zinc-900">OfferLoop · 面试错题本</h1>
            <p className="text-[11px] text-zinc-500">一眼看懂「我现在还差什么」</p>
          </div>
          <div className="ml-2 flex items-center gap-1">
            <select
              value={space}
              onChange={(e) => {
                if (e.target.value === "__new__") return; // 选中"新建"不动当前空间，交给输入框
                handleSpaceChange(e.target.value);
              }}
              className="text-[11px] rounded-lg border border-zinc-200 bg-white px-2 py-1 text-zinc-600 outline-none focus:border-indigo-500"
              title="切换空间"
            >
              {data?.spaces.map((s) => (
                <option key={s} value={s}>{s === "default" ? "默认空间" : s}</option>
              ))}
              <option value="__new__">＋ 新建空间…</option>
            </select>
            <input
              value={newSpace}
              onChange={(e) => setNewSpace(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && newSpace.trim()) {
                  handleSpaceChange(newSpace.trim());
                  setNewSpace("");
                }
              }}
              placeholder="新空间名"
              className="w-24 text-[11px] rounded-lg border border-zinc-200 bg-white px-2 py-1 text-zinc-600 outline-none focus:border-indigo-500"
              title="输入新空间名后回车"
            />
          </div>
          {nav}
        </div>

        <div className="px-5 py-4 space-y-4">
          {loading ? (
            <p className="text-xs text-zinc-400 text-center py-10">加载中…</p>
          ) : error ? (
            <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">{error}</div>
          ) : data ? (
            <>
              {/* 统计卡 */}
              <div className="grid grid-cols-4 gap-2.5">
                <div className="rounded-xl border border-zinc-200 bg-white p-3 shadow-sm">
                  <p className="text-[10px] text-zinc-400">总数</p>
                  <p className="text-xl font-bold text-zinc-900 mt-0.5">{data.stats.total}</p>
                </div>
                {STATUS_CARD.map((s) => (
                  <div key={s.key} className={`rounded-xl border p-3 shadow-sm ${s.cls}`}>
                    <p className="text-[10px] opacity-70">{s.emoji} {s.label}</p>
                    <p className="text-xl font-bold mt-0.5">{data.stats.by_status[s.key as keyof typeof data.stats.by_status]}</p>
                  </div>
                ))}
              </div>

              {/* 提醒卡 */}
              <RemindList title="🔴 快忘了 · 面试前优先看" color="text-red-600" entries={data.remind.red} />
              <RemindList title="🟡 该看看" color="text-amber-600" entries={data.remind.yellow} />
              {data.remind.green > 0 && (
                <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 px-4 py-2.5 text-xs text-emerald-700">
                  ✅ 掌握得不错（{data.remind.green} 道）——gap 低于阈值，暂时不用看
                </div>
              )}

              {/* 遗忘曲线 */}
              <MasteryCurve curve={data.curve} />

              {/* 热门 topic */}
              {data.stats.hot_topics.length > 0 && (
                <div className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
                  <p className="text-sm font-semibold text-zinc-900 mb-2">高频考点</p>
                  <div className="flex flex-wrap gap-1.5">
                    {data.stats.hot_topics.map(([t, c]) => (
                      <span key={t} className="text-[11px] text-indigo-600 bg-indigo-50 border border-indigo-100 rounded-full px-2.5 py-1">
                        {t} ×{c}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* 最近复习 */}
              {data.recent.length > 0 && (
                <div className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
                  <p className="text-sm font-semibold text-zinc-900 mb-2">最近复习</p>
                  <div className="space-y-1.5">
                    {data.recent.slice(0, 5).map((r, i) => (
                      <div key={i} className="flex items-center gap-2 text-xs">
                        <span className="text-zinc-400 shrink-0">{r.time.slice(5, 16)}</span>
                        <span className="flex-1 text-zinc-700 truncate">{r.question}</span>
                        <span className="text-[10px] text-zinc-400 shrink-0">
                          {Math.round(r.before * 100)}% → {Math.round(r.after * 100)}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
