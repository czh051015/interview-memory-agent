"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  completeMockInterview,
  fetchProfile,
  getMockFollowup,
  getMockVerdict,
  startMockInterview,
  uploadJd,
  uploadResume,
} from "@/lib/api";
import type {
  DocStatus,
  MockQuestion,
  MockVerdictResponse,
  ProfileResponse,
} from "@/lib/types";

type Phase = "loading" | "setup" | "question" | "judging" | "verdict" | "report";

type Verdict = "pass" | "partial" | "fail";

interface AnsweredQuestion {
  q: MockQuestion;
  answer: string;
  verdict: Verdict;
  judge: MockVerdictResponse;
}

const VERDICT_LABEL: Record<Verdict, string> = {
  pass: "答对了 ✅",
  partial: "一半 ⚠️",
  fail: "没答上 ❌",
};

const VERDICT_DESC: Record<Verdict, string> = {
  pass: "要点基本覆盖，下次面试能直接过",
  partial: "答了主干漏了细节，值得再看一遍",
  fail: "核心没答到，面试前必须再看",
};

const VERDICT_BADGE: Record<Verdict, string> = {
  pass: "+掌握度",
  partial: "保持",
  fail: "-掌握度",
};

const STATUS_PILL: Record<string, string> = {
  fail: "❌ fail",
  partial: "⚠️ partial",
  pass: "✅ pass",
};

const SOURCE_BADGE: Record<string, { label: string; cls: string }> = {
  weak: { label: "错题", cls: "text-red-600 bg-red-50 border-red-100" },
  resume: { label: "简历深挖", cls: "text-blue-600 bg-blue-50 border-blue-100" },
  jd: { label: "JD 能力", cls: "text-violet-600 bg-violet-50 border-violet-100" },
  behavior: { label: "行为面", cls: "text-emerald-600 bg-emerald-50 border-emerald-100" },
  motivation: { label: "动机面", cls: "text-amber-600 bg-amber-50 border-amber-100" },
  generic: { label: "通用", cls: "text-zinc-500 bg-zinc-100 border-zinc-200" },
};

function SourceBadge({ source }: { source: string }) {
  const s = SOURCE_BADGE[source] ?? SOURCE_BADGE.generic;
  return (
    <span className={`text-[10px] rounded-full px-2 py-0.5 border ${s.cls}`}>
      {s.label}
    </span>
  );
}

// ── 章节序列（按出现顺序去重）+ 每章状态 ──
// status: done（已答完） / active（正在答） / todo（未开始）
function buildSections(
  questions: MockQuestion[],
  idx: number,
): { name: string; status: "done" | "active" | "todo" }[] {
  const names: string[] = [];
  for (const q of questions) {
    const s = q.section || "其他";
    if (!names.includes(s)) names.push(s);
  }
  return names.map((name, i) => {
    // 当前章节 = 当前题所在章节；之前章节全部 done
    const cur = questions[idx]?.section || "其他";
    if (name === cur) return { name, status: "active" };
    // 章节顺序在前的已完成（按索引判断）
    const curSectionFirstIdx = questions.findIndex((q) => (q.section || "其他") === cur);
    const thisSectionFirstIdx = questions.findIndex((q) => (q.section || "其他") === name);
    return { name, status: thisSectionFirstIdx < curSectionFirstIdx ? "done" : "todo" };
  });
}

// 顶部章节 stepper：当前章节高亮，已完成打勾，未开始置灰
function SectionStepper({ sections }: { sections: { name: string; status: "done" | "active" | "todo" }[] }) {
  const ICONS: Record<string, string> = {
    自我介绍: "👋",
    项目深挖: "🔍",
    技术验证: "⚙️",
    行为面: "🧭",
    动机面: "🎯",
  };
  return (
    <div className="flex items-center gap-1 overflow-x-auto pb-0.5">
      {sections.map((s, i) => {
        const icon = ICONS[s.name] ?? "📂";
        return (
          <div key={s.name} className="flex items-center gap-1 shrink-0">
            {i > 0 ? <span className={`h-px w-3 ${s.status === "todo" ? "bg-zinc-200" : "bg-indigo-400"}`} /> : null}
            <span
              className={`flex items-center gap-1 text-[11px] rounded-full px-2 py-1 border transition-all ${
                s.status === "active"
                  ? "bg-indigo-600 text-white border-indigo-600 shadow-sm font-medium"
                  : s.status === "done"
                    ? "bg-indigo-50 text-indigo-600 border-indigo-100"
                    : "bg-white text-zinc-400 border-zinc-200"
              }`}
            >
              <span>{s.status === "done" ? "✓" : icon}</span>
              {s.name}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export default function MockInterviewPage() {
  const [phase, setPhase] = useState<Phase>("loading");
  const [questions, setQuestions] = useState<MockQuestion[]>([]);
  const [idx, setIdx] = useState(0);
  const [answer, setAnswer] = useState("");
  const [judge, setJudge] = useState<MockVerdictResponse | null>(null);
  const [picked, setPicked] = useState<Verdict>("partial");
  const [results, setResults] = useState<AnsweredQuestion[]>([]);
  const [error, setError] = useState("");
  const [behaviors, setBehaviors] = useState<string[]>([]);
  const [newCount, setNewCount] = useState(0);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [uploading, setUploading] = useState<"resume" | "jd" | null>(null);
  const [uploadMsg, setUploadMsg] = useState("");
  // 追问状态：每题最多追 2 轮（对齐 CLI MAX_FOLLOWUPS）
  const [followQ, setFollowQ] = useState<string | null>(null); // 当前题的追问问题
  const [rounds, setRounds] = useState<number[]>([]); // 每题已追轮数
  const [following, setFollowing] = useState(false);
  const [followMsg, setFollowMsg] = useState(""); // 面试官"不再追问"的提示
  const [focusTopics, setFocusTopics] = useState<string[]>([]); // 画像薄弱主题（setup 页"本场重点"）
  const answerRef = useRef<HTMLTextAreaElement>(null);

  // ── 开始面试：拉错题 ──
  const begin = useCallback(async () => {
    setPhase("loading");
    setError("");
    try {
      const space = localStorage.getItem("offerloop.space") || "default";
      const res = await startMockInterview(5, space);
      setQuestions(res.questions);
      setFocusTopics(res.focus_topics ?? []);
      setPhase(res.questions.length ? "setup" : "setup");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "开始失败");
      setPhase("setup");
    }
  }, []);

  useEffect(() => {
    begin();
  }, [begin]);

  // ── 简历/JD 状态（「简历深挖」章节的数据源，按当前空间）──
  useEffect(() => {
    const space = localStorage.getItem("offerloop.space") || "default";
    fetchProfile(space)
      .then(setProfile)
      .catch(() => setProfile(null));
  }, []);

  async function handleDocUpload(kind: "resume" | "jd", e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // 允许重复选择同一文件
    if (!file || uploading) return;
    setUploading(kind);
    setUploadMsg("");
    setError("");
    try {
      const space = localStorage.getItem("offerloop.space") || "default";
      const res = kind === "resume" ? await uploadResume(file, space) : await uploadJd(file, space);
      setProfile(await fetchProfile(space));
      setUploadMsg(
        `${res.filename}：${res.chars} 字${res.pages ? ` / ${res.pages} 页` : ""}，已更新。下一场模拟面试将用新${
          kind === "resume" ? "简历" : "JD"
        }出题。旧版已备份为 ${kind}.md.bak`,
      );
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "上传失败";
      // 常见运维问题：后端没重启 → 405，翻译成人话
      const friendly =
        /Method Not Allowed|405/.test(msg)
          ? "后端还在跑旧代码——请重启 uvicorn（杀 8000 进程后重新启动），再重试上传"
          : msg;
      setError(friendly);
    } finally {
      setUploading(null);
    }
  }

  // ── 提交回答 → 判卷 ──
  async function submitAnswer() {
    const text = answer.trim();
    if (!text || phase === "judging") return;
    const q = questions[idx];
    setError("");
    setPhase("judging");
    try {
      // 追问轮用追问问题替代原题
      const v = await getMockVerdict(followQ ?? q.question, text);
      setJudge(v);
      setPicked(v.suggested);
      setFollowMsg("");
      setPhase("verdict");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "判卷失败");
      setPhase("question");
    }
  }

  // ── 追问：LLM 判断要不要往下钻，每题最多 2 轮 ──
  async function handleFollowup() {
    const q = questions[idx];
    if (phase !== "verdict" || !judge || following) return;
    setFollowing(true);
    setError("");
    try {
      const res = await getMockFollowup(q.question, judge.points, answer, (rounds[idx] ?? 0) + 1);
      if (res.need_followup && res.followup_question.trim()) {
        setFollowQ(res.followup_question.trim());
        setRounds((prev) => {
          const n = [...prev];
          n[idx] = (n[idx] ?? 0) + 1;
          return n;
        });
        setAnswer("");
        setJudge(null);
        setPhase("question");
        setTimeout(() => answerRef.current?.focus(), 50);
      } else {
        // 面试官认为不用再追
        setFollowMsg(res.reason || "这道题不用再追问了");
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "追问失败");
    } finally {
      setFollowing(false);
    }
  }

  // ── 确认判定 → 下一题 / 报告 ──
  function confirmVerdict() {
    const q = questions[idx];
    const answered: AnsweredQuestion = {
      q,
      answer: answer.trim(),
      verdict: picked,
      judge: judge!,
    };
    const next = [...results, answered];
    setResults(next);
    setAnswer("");
    setJudge(null);
    setFollowQ(null); // 进入下一题前清掉追问状态
    setFollowMsg("");

    if (idx < questions.length - 1) {
      setIdx(idx + 1);
      setPhase("question");
    } else {
      setPhase("report");
      void saveResults(next);
    }
  }

  // ── 报告页写回 ──
  async function saveResults(list: AnsweredQuestion[]) {
    setSaving(true);
    try {
      const res = await completeMockInterview(
        list.map((r) => ({
          question_id: r.q.id,
          question: r.q.question,
          verdict: r.verdict,
          answer: r.answer,
          source: r.q.source || "weak",
          topic: r.q.topic,
          points: r.judge.points,
          misses: r.judge.misses,
          reason: r.judge.reason,
        })),
        localStorage.getItem("offerloop.space") || "default",
      );
      setBehaviors(res.behaviors);
      setNewCount(res.new);
      setSaved(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "写回失败");
    } finally {
      setSaving(false);
    }
  }

  function again() {
    setPhase("loading");
    setQuestions([]);
    setIdx(0);
    setResults([]);
    setError("");
    setBehaviors([]);
    setNewCount(0);
    setSaved(false);
    setFollowQ(null);
    setRounds([]);
    setFollowMsg("");
    begin();
  }

  // ── 渲染 ──
  return (
    <div className="min-h-dvh bg-zinc-50/50">
      <div className="max-w-3xl mx-auto w-full bg-white min-h-dvh shadow-sm border-x border-zinc-200 flex flex-col">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-zinc-200 bg-white shrink-0 sticky top-0 z-10">
          <a
            href="/"
            className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white text-sm font-bold hover:bg-indigo-700 transition-colors"
          >
            O
          </a>
          <div>
            <h1 className="text-sm font-semibold text-zinc-900">模拟面试</h1>
            <p className="text-[11px] text-zinc-500">只考你的错题 · LLM 给对照 · 你拍板</p>
          </div>
          <div className="ml-auto">
            <span className="text-[11px] text-zinc-400 bg-zinc-100 rounded-full px-2.5 py-1">
              v1 单轮
            </span>
          </div>
        </div>

        {/* 进度条 + 章节流转 */}
        {phase === "question" || phase === "judging" || phase === "verdict" ? (
          <div className="px-5 pt-4 space-y-2">
            <div className="h-1.5 rounded-full bg-zinc-100 overflow-hidden">
              <div
                className="h-full bg-indigo-600 transition-all duration-500"
                style={{ width: `${((idx + 0.5) / questions.length) * 100}%` }}
              />
            </div>
            <div className="flex justify-between text-[11px] text-zinc-400">
              <span>第 {idx + 1} / {questions.length} 题</span>
              <span>考的是你栽过的题</span>
            </div>
            <SectionStepper sections={buildSections(questions, idx)} />
          </div>
        ) : null}

        <div className="flex-1 px-5 py-5 space-y-4">
          {/* loading */}
          {phase === "loading" ? (
            <div className="text-center py-20 space-y-3">
              <div className="w-10 h-10 mx-auto rounded-full border-2 border-indigo-600 border-t-transparent animate-spin" />
              <p className="text-sm text-zinc-500">正在根据 简历 + JD + 错题本 生成结构化面试...</p>
            </div>
          ) : null}

          {/* setup：本场面试计划预览（章节分组） */}
          {phase === "setup" ? (
            <div className="space-y-4">
              <div className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
                <p className="text-sm font-semibold text-zinc-900">🎯 本场面试计划</p>
                <p className="text-xs text-zinc-500 mt-1.5 leading-relaxed">
                  出题依据 <b>三源</b>：你的简历（项目深挖）、目标 JD（能力项验证）、
                  错题本（薄弱项优先）。共 {questions.length} 题，分章节进行，
                  每题一答一判，LLM 面试官给<b>参考要点 + 差距</b>，你最终拍板。
                </p>

                {/* 记忆管家：本场重点验证（来自用户画像）——"它记得你"的可见瞬间 */}
                {focusTopics.length > 0 ? (
                  <div className="mt-2.5 rounded-lg border border-violet-200 bg-violet-50/60 px-3 py-2">
                    <p className="text-[11px] text-violet-700 font-medium">
                      🧠 记忆管家记得你：本场将重点验证你的薄弱主题 ——{" "}
                      {focusTopics.map((t) => (
                        <span
                          key={t}
                          className="inline-block text-[11px] bg-white border border-violet-200 text-violet-700 rounded-full px-2 py-0.5 mx-0.5"
                        >
                          {t}
                        </span>
                      ))}
                    </p>
                  </div>
                ) : null}

                {/* 三源状态 + 简历/JD 上传 */}
                <div className="mt-3 rounded-lg border border-zinc-200 bg-zinc-50/60 p-3 space-y-3">
                  <DocRow
                    label="简历"
                    doc={profile?.resume ?? null}
                    uploading={uploading === "resume"}
                    onPick={(e) => handleDocUpload("resume", e)}
                  />
                  <DocRow
                    label="JD"
                    doc={profile?.jd ?? null}
                    uploading={uploading === "jd"}
                    onPick={(e) => handleDocUpload("jd", e)}
                  />
                  {uploadMsg ? (
                    <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700 leading-relaxed">
                      ✓ {uploadMsg}
                    </div>
                  ) : null}
                </div>
              </div>

              {Object.entries(
                questions.reduce<Record<string, typeof questions>>((acc, q) => {
                  const key = q.section || "其他";
                  (acc[key] ||= []).push(q);
                  return acc;
                }, {}),
              ).map(([section, qs]) => (
                <div key={section}>
                  <p className="text-[11px] font-semibold text-zinc-500 mb-1.5 px-0.5">
                    📂 {section} · {qs.length} 题
                  </p>
                  <div className="space-y-2">
                    {qs.map((q, i) => (
                      <div key={q.id || `${section}-${i}`} className="rounded-xl border border-zinc-200 bg-white p-3.5 shadow-sm">
                        <div className="flex items-center gap-1.5 flex-wrap mb-1.5">
                          <SourceBadge source={q.source} />
                          {q.status && q.status in STATUS_PILL ? (
                            <span className="text-[10px] text-red-600 bg-red-50 border border-red-100 rounded-full px-2 py-0.5">
                              {STATUS_PILL[q.status]}
                            </span>
                          ) : null}
                          {q.topic ? (
                            <span className="text-[10px] text-zinc-500 bg-zinc-100 rounded-full px-2 py-0.5">
                              {q.topic}
                            </span>
                          ) : null}
                          {q.gap !== null ? (
                            <span className="text-[10px] text-amber-600 bg-amber-50 border border-amber-100 rounded-full px-2 py-0.5 ml-auto">
                              gap {Math.round(q.gap * 100)}%
                            </span>
                          ) : null}
                        </div>
                        <p className="text-sm font-medium text-zinc-900 leading-snug">{q.question}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ))}

              {error ? (
                <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
                  {error}
                </div>
              ) : null}

              <button
                onClick={() => {
                  setIdx(0);
                  setPhase("question");
                }}
                className="w-full h-12 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-all active:scale-[0.99]"
              >
                开始面试 →
              </button>
            </div>
          ) : null}

          {/* question：出题 + 回答 */}
          {phase === "question" ? (
            <div className="space-y-4">
              <div className="rounded-xl border border-zinc-200 bg-indigo-50/40 p-4">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-7 h-7 rounded-full bg-indigo-100 flex items-center justify-center text-sm">
                    🧑‍💼
                  </div>
                  <span className="text-[11px] text-indigo-500 font-medium">面试官</span>
                </div>
                <p className="text-base font-semibold text-zinc-900 leading-relaxed">
                  {followQ ?? questions[idx]?.question}
                </p>
              </div>

              <div className="flex items-center gap-1.5 flex-wrap">
                {followQ && (rounds[idx] ?? 0) > 0 ? (
                  <span className="text-[10px] text-indigo-600 bg-indigo-50 border border-indigo-100 rounded-full px-2 py-0.5">
                    追问 {(rounds[idx] ?? 0)}/{2} 轮
                  </span>
                ) : null}
                {questions[idx] ? <SourceBadge source={questions[idx].source} /> : null}
                {questions[idx]?.status && questions[idx].status in STATUS_PILL ? (
                  <span className="text-[10px] text-red-600 bg-red-50 border border-red-100 rounded-full px-2 py-0.5">
                    {STATUS_PILL[questions[idx].status]}
                  </span>
                ) : null}
                <span className="text-[10px] text-zinc-500 bg-zinc-100 rounded-full px-2 py-0.5">
                  {questions[idx]?.section || ""} · 考点：{questions[idx]?.topic || "未分类"}
                </span>
              </div>

              <textarea
                ref={answerRef}
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                placeholder="在真实面试中你会怎么回答这道题？打在这里..."
                rows={6}
                className="w-full resize-y rounded-xl border border-zinc-300 bg-zinc-50 px-4 py-3 text-sm leading-relaxed outline-none focus:border-indigo-500 focus:bg-white focus:ring-1 focus:ring-indigo-500/20 transition-all"
              />

              {error ? (
                <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
                  {error}
                </div>
              ) : null}

              <div className="flex gap-3">
                <a
                  href="/"
                  className="h-12 px-5 rounded-xl border border-zinc-300 text-sm text-zinc-600 hover:bg-zinc-50 flex items-center justify-center transition-all"
                >
                  退出
                </a>
                <button
                  onClick={submitAnswer}
                  disabled={!answer.trim()}
                  className="flex-1 h-12 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all active:scale-[0.99]"
                >
                  提交回答 →
                </button>
              </div>
              <p className="text-center text-[11px] text-zinc-400">
                Enter 提交 · Shift+Enter 换行
              </p>
            </div>
          ) : null}

          {/* judging：判卷动画 */}
          {phase === "judging" ? (
            <div className="py-16 space-y-4">
              <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-700 leading-relaxed">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-7 h-7 rounded-full bg-indigo-100 flex items-center justify-center text-sm">
                    🧑‍💼
                  </div>
                  <span className="text-[11px] text-indigo-500 font-medium">面试官</span>
                </div>
                <div className="bg-white rounded-xl border border-zinc-200 px-4 py-3 text-zinc-600 whitespace-pre-wrap">
                  {answer}
                </div>
              </div>
              <div className="text-center space-y-2">
                <div className="flex justify-center gap-1.5">
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className="typing-dot w-2 h-2 bg-zinc-400 rounded-full inline-block"
                      style={{ animationDelay: `${i * 0.2}s` }}
                    />
                  ))}
                </div>
                <p className="text-xs text-zinc-400">
                  LLM 面试官正在生成：期望要点 → 差距分析 → 建议判定
                </p>
              </div>
            </div>
          ) : null}

          {/* verdict：判定卡（灵魂） */}
          {phase === "verdict" && judge ? (
            <div className="space-y-4">
              <div className="rounded-xl border-2 border-indigo-200 bg-white p-4 shadow-sm">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-7 h-7 rounded-full bg-indigo-100 flex items-center justify-center text-sm">
                    🧑‍💼
                  </div>
                  <span className="text-sm font-semibold text-zinc-900">面试官判定</span>
                  <span className="ml-auto text-[10px] text-indigo-600 bg-indigo-50 border border-indigo-100 rounded-full px-2 py-0.5">
                    LLM 建议：{VERDICT_LABEL[judge.suggested]}
                  </span>
                </div>

                {/* 应该答到 */}
                <p className="text-[11px] font-bold text-zinc-400 tracking-wide mt-3 mb-1.5">
                  ✅ 这道题应该答到
                </p>
                <div className="space-y-1.5 mb-3">
                  {judge.points.map((p, i) => (
                    <div key={i} className="flex gap-2 text-sm text-zinc-700">
                      <span className="w-4 h-4 mt-0.5 rounded-full bg-emerald-500 text-white text-[10px] flex items-center justify-center flex-shrink-0">
                        ✓
                      </span>
                      <span className="leading-relaxed">{p}</span>
                    </div>
                  ))}
                </div>

                {/* 差距 */}
                <p className="text-[11px] font-bold text-zinc-400 tracking-wide mt-3 mb-1.5">
                  ✗ 你漏掉的 / 差距
                </p>
                <div className="space-y-1.5 mb-3">
                  {judge.misses.length ? (
                    judge.misses.map((m, i) => (
                      <div key={i} className="flex gap-2 text-sm text-zinc-700">
                        <span className="w-4 h-4 mt-0.5 rounded-full bg-rose-500 text-white text-[10px] flex items-center justify-center flex-shrink-0">
                          ✗
                        </span>
                        <span className="leading-relaxed">{m}</span>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-zinc-400">没有明显遗漏</p>
                  )}
                </div>

                {/* 面试官的话 */}
                {judge.reason ? (
                  <div className="rounded-lg border-l-3 border-l-amber-500 bg-amber-50 px-3.5 py-2.5 text-[13px] text-amber-800 leading-relaxed">
                    <b>面试官的话：</b>{judge.reason}
                  </div>
                ) : null}
              </div>

              {/* 最终判定 */}
              <div className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-sm font-semibold text-zinc-900">🏁 最终判定</p>
                  <p className="text-[10px] text-zinc-400">LLM 建议已预选，你说了算</p>
                </div>
                <div className="space-y-2">
                  {(["pass", "partial", "fail"] as Verdict[]).map((v) => (
                    <button
                      key={v}
                      onClick={() => setPicked(v)}
                      className={`w-full flex items-start gap-3 rounded-xl border-1.5 px-3.5 py-3 text-left transition-all ${
                        picked === v
                          ? "border-indigo-500 bg-indigo-50/70 shadow-sm"
                          : "border-zinc-200 hover:border-indigo-300"
                      }`}
                    >
                      <span
                        className={`w-4 h-4 mt-0.5 rounded-full border-2 flex-shrink-0 flex items-center justify-center transition-all ${
                          picked === v ? "border-indigo-600" : "border-zinc-300"
                        }`}
                      >
                        {picked === v ? (
                          <span className="w-2 h-2 rounded-full bg-indigo-600" />
                        ) : null}
                      </span>
                      <span className="flex-1">
                        <span className="block text-sm font-medium text-zinc-900">
                          {VERDICT_LABEL[v]}
                        </span>
                        <span className="block text-[11px] text-zinc-500 mt-0.5">
                          {VERDICT_DESC[v]}
                        </span>
                      </span>
                      <span className="text-[10px] text-indigo-500 bg-indigo-50 rounded-full px-2 py-0.5 self-center">
                        {VERDICT_BADGE[v]}
                      </span>
                    </button>
                  ))}
                </div>
                <div className="flex gap-3 mt-4">
                  <button
                    onClick={() => {
                      setPhase("question");
                      setJudge(null);
                      answerRef.current?.focus();
                    }}
                    className="h-12 px-5 rounded-xl border border-zinc-300 text-sm text-zinc-600 hover:bg-zinc-50 transition-all"
                  >
                    重答此题
                  </button>
                  {(rounds[idx] ?? 0) < 2 && !followMsg ? (
                    <button
                      onClick={handleFollowup}
                      disabled={following}
                      className="h-12 px-4 rounded-xl border border-indigo-200 text-sm text-indigo-600 hover:bg-indigo-50 disabled:opacity-50 transition-all"
                    >
                      {following ? "面试官思考中…" : `追问（${(rounds[idx] ?? 0) + 1}/2）`}
                    </button>
                  ) : null}
                  <button
                    onClick={confirmVerdict}
                    className="flex-1 h-12 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-all active:scale-[0.99]"
                  >
                    {idx === questions.length - 1 ? "确认，查看报告 🏁" : "确认，下一题 →"}
                  </button>
                </div>
                {followMsg ? (
                  <p className="text-[11px] text-zinc-500 bg-zinc-50 rounded-lg px-3 py-2 mt-2 leading-relaxed">
                    💬 面试官：{followMsg}
                  </p>
                ) : null}
              </div>
            </div>
          ) : null}

          {/* report：本场报告 */}
          {phase === "report" ? (
            <div className="space-y-4">
              {/* 统计 */}
              <div className="grid grid-cols-3 gap-2">
                {(
                  [
                    ["pass", "答对", "text-emerald-600"],
                    ["partial", "一半", "text-amber-600"],
                    ["fail", "没答上", "text-red-600"],
                  ] as const
                ).map(([k, label, color]) => {
                  const n = results.filter((r) => r.verdict === k).length;
                  return (
                    <div key={k} className="rounded-xl border border-zinc-200 bg-white p-4 text-center shadow-sm">
                      <div className={`text-2xl font-bold ${color}`}>{n}</div>
                      <div className="text-[11px] text-zinc-400 mt-0.5">{label}</div>
                    </div>
                  );
                })}
              </div>

              {/* 写回状态 */}
              <div className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-semibold text-zinc-900">💾 写回错题本</p>
                  {saving ? (
                    <span className="text-[11px] text-zinc-400 flex items-center gap-1.5">
                      <span className="w-3 h-3 rounded-full border-2 border-indigo-600 border-t-transparent animate-spin inline-block" />
                      写回中...
                    </span>
                  ) : saved ? (
                    <span className="text-[11px] text-emerald-600 bg-emerald-50 rounded-full px-2 py-0.5">
                      ✅ 已写回 {results.length} 题{newCount > 0 ? ` · 新采集 ${newCount} 道` : ""}
                    </span>
                  ) : (
                    <span className="text-[11px] text-amber-600 bg-amber-50 rounded-full px-2 py-0.5">
                      ⚠️ 写回失败，可重试
                    </span>
                  )}
                </div>
                <p className="text-[11px] text-zinc-500 mt-1.5 leading-relaxed">
                  fail 题下降、partial 保持、pass 上升 —— 下次「面试前提醒」会按新掌握度重新排序。
                </p>
                {behaviors.length ? (
                  <div className="mt-2.5">
                    <p className="text-[11px] text-zinc-400 mb-1">🧠 你的行为特征（整场总结）：</p>
                    <div className="flex flex-wrap gap-1.5">
                      {behaviors.map((b) => (
                        <span key={b} className="text-[11px] text-zinc-600 bg-zinc-100 rounded-full px-2.5 py-0.5">
                          {b}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}
                {error && !saved ? (
                  <button
                    onClick={() => saveResults(results)}
                    disabled={saving}
                    className="mt-3 h-10 px-4 rounded-xl bg-indigo-600 text-white text-sm hover:bg-indigo-700 disabled:opacity-40 transition-all"
                  >
                    重试写回
                  </button>
                ) : null}
              </div>

              {/* 逐题复盘 */}
              <div className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
                <p className="text-sm font-semibold text-zinc-900 mb-3">📋 逐题复盘</p>
                <div className="space-y-3">
                  {results.map((r, i) => (
                    <div key={i} className="rounded-lg border border-zinc-200 p-3">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span
                          className={`text-[10px] rounded-full px-2 py-0.5 font-medium ${
                            r.verdict === "pass"
                              ? "bg-emerald-50 text-emerald-600 border border-emerald-100"
                              : r.verdict === "partial"
                                ? "bg-amber-50 text-amber-600 border border-amber-100"
                                : "bg-red-50 text-red-600 border border-red-100"
                          }`}
                        >
                          {VERDICT_LABEL[r.verdict]}
                        </span>
                        {r.q.topic ? (
                          <span className="text-[10px] text-zinc-500 bg-zinc-100 rounded-full px-2 py-0.5">
                            {r.q.topic}
                          </span>
                        ) : null}
                      </div>
                      <p className="text-[13px] font-medium text-zinc-900 mt-1.5 leading-snug">
                        {r.q.question}
                      </p>
                      <p className="text-[11px] text-zinc-400 mt-1 leading-relaxed">
                        你的回答：{r.answer.slice(0, 80)}{r.answer.length > 80 ? "…" : ""}
                      </p>
                      {r.judge.reason ? (
                        <p className="text-[12px] text-zinc-500 bg-zinc-50 rounded-lg px-2.5 py-1.5 mt-1.5 leading-relaxed">
                          💡 {r.judge.reason}
                        </p>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex gap-3 pb-4">
                <a
                  href="/"
                  className="h-12 flex-1 rounded-xl border border-zinc-300 text-sm text-zinc-600 hover:bg-zinc-50 flex items-center justify-center transition-all"
                >
                  回聊天
                </a>
                <button
                  onClick={again}
                  className="h-12 flex-1 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-all active:scale-[0.99]"
                >
                  再来一场
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

// ── 资料行：简历 / JD 各一行（状态 + 摘要 + 上传按钮）──
function DocRow({
  label,
  doc,
  uploading,
  onPick,
}: {
  label: string;
  doc: DocStatus | null;
  uploading: boolean;
  onPick: (e: React.ChangeEvent<HTMLInputElement>) => void;
}) {
  const missing = label === "简历" ? "简历深挖" : "JD 能力";
  return (
    <div className="flex items-start gap-2">
      <span className="text-[11px] text-zinc-500 w-8 mt-0.5">{label}</span>
      <div className="flex-1 min-w-0">
        {doc?.provided ? (
          <span className="inline-block text-[11px] text-emerald-600 bg-emerald-50 border border-emerald-100 rounded-full px-2 py-0.5">
            ✓ {doc.filename} · {doc.updated_at?.slice(5, 16).replace("T", " ")}
          </span>
        ) : (
          <span className="inline-block text-[11px] text-amber-600 bg-amber-50 border border-amber-100 rounded-full px-2 py-0.5">
            ✕ 未提供 · 面试将跳过{missing}章节
          </span>
        )}
        {doc?.provided && doc.summary ? (
          <p className="text-[11px] text-zinc-400 mt-1 leading-relaxed truncate">{doc.summary}…</p>
        ) : null}
      </div>
      <label className="shrink-0 text-[11px] text-indigo-600 border border-indigo-200 rounded-lg px-2.5 py-1 hover:bg-indigo-50 cursor-pointer transition-colors">
        {uploading ? "上传中…" : "上传"}
        <input
          type="file"
          accept=".pdf,.txt,.md,.markdown,application/pdf,text/plain,text/markdown"
          className="hidden"
          onChange={onPick}
          disabled={uploading}
        />
      </label>
    </div>
  );
}
