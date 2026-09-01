"use client";

import { useState } from "react";
import ArchivePanel from "@/components/workbench/ArchivePanel";
import DashboardPanel from "@/components/workbench/DashboardPanel";
import PracticePanel from "@/components/workbench/PracticePanel";
import RecordPanel from "@/components/workbench/RecordPanel";
import Sidebar, { type Tab } from "@/components/workbench/Sidebar";

export default function WorkbenchPage() {
  const [tab, setTab] = useState<Tab>("dashboard");

  return (
    <div className="min-h-screen bg-zinc-50 flex">
      <Sidebar tab={tab} onSelect={setTab} />
      <main className="flex-1 min-w-0">
        {tab === "dashboard" && <DashboardPanel onGoPractice={() => setTab("practice")} />}
        {tab === "practice" && <PracticePanel />}
        {tab === "archive" && <ArchivePanel />}
        {tab === "record" && <RecordPanel />}
      </main>
    </div>
  );
}
