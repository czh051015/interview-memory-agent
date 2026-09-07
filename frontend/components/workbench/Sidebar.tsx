"use client";

// docs/39：申论错题本 = 第 5 页签（排 dashboard/practice/archive/record 之后）；
// 底部「面试错题本 →」（/dashboard 面经遗留页入口）已删——申论侧错题本不再跨域跳面经页
export type Tab = "dashboard" | "practice" | "archive" | "record" | "wrongbook";

const TABS: Array<{ key: Tab; label: string; icon: string }> = [
  { key: "dashboard", label: "工作台", icon: "▦" },
  { key: "practice", label: "练习", icon: "✍" },
  { key: "archive", label: "档案", icon: "🗂" },
  { key: "record", label: "录入", icon: "＋" },
  { key: "wrongbook", label: "错题本", icon: "❌" },
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
            <h1 className="text-sm font-semibold text-zinc-900 leading-tight">PointLoop 逐点 · 申论陪练</h1>
            <p className="text-[10px] text-zinc-400">逐点对账，练一道忘不了的采分点</p>
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
    </aside>
  );
}
