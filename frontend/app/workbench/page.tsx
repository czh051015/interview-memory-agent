"use client";

import { useState } from "react";
import ArchivePanel from "@/components/workbench/ArchivePanel";
import DashboardPanel from "@/components/workbench/DashboardPanel";
import PracticePanel from "@/components/workbench/PracticePanel";
import RecordPanel from "@/components/workbench/RecordPanel";
import Sidebar, { type Tab } from "@/components/workbench/Sidebar";
import WrongbookPanel from "@/components/workbench/WrongbookPanel";
import type { WeakPointItem } from "@/lib/types";

// docs/39：跨面板跳转一律走 props 回调（先例 DashboardPanel onGoPractice），
// 不引入新路由/query —— SPA state 单一来源
export default function WorkbenchPage() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [hlKey, setHlKey] = useState<string | null>(null); // 错题本定位（档案「错题 →」落点）

  // 档案行「错题 →」→ 切错题本 tab + 定位该弱项条目（sl_{question_id}_{point_id}）
  const goWrongbook = (w: WeakPointItem) => {
    const pid = w.point_key.split(":")[1] ?? "";
    setHlKey(`sl_${w.question_id}_${pid}`);
    setTab("wrongbook");
  };

  return (
    <div className="min-h-screen bg-zinc-50 flex">
      <Sidebar tab={tab} onSelect={setTab} />
      <main className="flex-1 min-w-0">
        {tab === "dashboard" && <DashboardPanel onGoPractice={() => setTab("practice")} />}
        {tab === "practice" && <PracticePanel />}
        {tab === "archive" && <ArchivePanel onGoWrongbook={goWrongbook} />}
        {tab === "record" && <RecordPanel onDone={() => setTab("wrongbook")} />}
        {tab === "wrongbook" && (
          <WrongbookPanel
            highlightKey={hlKey}
            onGoPractice={() => setTab("practice")}
            onGoRecord={() => setTab("record")}
          />
        )}
      </main>
    </div>
  );
}
