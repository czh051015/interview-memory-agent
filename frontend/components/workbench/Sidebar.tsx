"use client";

export type Tab = "dashboard" | "practice" | "archive" | "record";

const TABS: Array<{ key: Tab; label: string; icon: string }> = [
  { key: "dashboard", label: "工作台", icon: "▦" },
  { key: "practice", label: "练习", icon: "✍" },
  { key: "archive", label: "档案", icon: "🗂" },
  { key: "record", label: "录入", icon: "＋" },
];

export default function Sidebar({
  tab,
  onSelect,
}: {
  tab: Tab;
  onSelect: (t: Tab) => void;
}) {
  return (
    <aside className="w-44 shrink-0 border-r border-zinc-200 bg-white flex flex-col">
      <div className="px-4 py-4 border-b border-zinc-100">
        <a href="/" className="flex items-center gap-2">
          <span className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center text-white text-xs font-bold">
            申
          </span>
          <div>
            <h1 className="text-sm font-semibold text-zinc-900 leading-tight">申论陪练</h1>
            <p className="text-[10px] text-zinc-400">练一道，忘不了的采分点</p>
          </div>
        </a>
      </div>

      <nav className="flex-1 py-2 space-y-0.5">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => onSelect(t.key)}
            className={`w-full flex items-center gap-2.5 px-4 py-2.5 text-sm transition-colors ${
              tab === t.key
                ? "bg-indigo-50 text-indigo-700 font-medium border-r-2 border-indigo-600"
                : "text-zinc-600 hover:bg-zinc-50"
            }`}
          >
            <span className="text-xs">{t.icon}</span>
            {t.label}
          </button>
        ))}
      </nav>

      <div className="px-4 py-3 border-t border-zinc-100 text-[11px]">
        <a href="/dashboard" className="text-zinc-400 hover:text-indigo-600 transition-colors">
          面试错题本 →
        </a>
      </div>
    </aside>
  );
}
