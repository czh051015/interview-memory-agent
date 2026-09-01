module.exports = [
"[project]/lib/api.ts [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "completeMockInterview",
    ()=>completeMockInterview,
    "completePractice",
    ()=>completePractice,
    "decompose",
    ()=>decompose,
    "deleteItem",
    ()=>deleteItem,
    "editItem",
    ()=>editItem,
    "fetchDashboard",
    ()=>fetchDashboard,
    "fetchItems",
    ()=>fetchItems,
    "fetchProfile",
    ()=>fetchProfile,
    "getDiagnose",
    ()=>getDiagnose,
    "getMockFollowup",
    ()=>getMockFollowup,
    "getMockVerdict",
    ()=>getMockVerdict,
    "getRemind",
    ()=>getRemind,
    "getWeakpoints",
    ()=>getWeakpoints,
    "markItemStatus",
    ()=>markItemStatus,
    "recordItems",
    ()=>recordItems,
    "searchItems",
    ()=>searchItems,
    "sendMessage",
    ()=>sendMessage,
    "startMockInterview",
    ()=>startMockInterview,
    "startPractice",
    ()=>startPractice,
    "submitPractice",
    ()=>submitPractice,
    "uploadJd",
    ()=>uploadJd,
    "uploadResume",
    ()=>uploadResume
]);
async function sendMessage(message, space = "default") {
    const res = await fetch("/api/chat", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            message,
            space
        })
    });
    if (!res.ok) {
        const err = await res.json().catch(()=>({
                detail: "请求失败"
            }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
}
async function decompose(rawText) {
    const res = await fetch("/api/decompose", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            raw_text: rawText
        })
    });
    if (!res.ok) {
        const err = await res.json().catch(()=>({
                detail: "拆解失败"
            }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
}
async function recordItems(items, space = "default") {
    const res = await fetch("/api/record", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            items,
            space
        })
    });
    if (!res.ok) {
        const err = await res.json().catch(()=>({
                detail: "入库失败"
            }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
}
// ── 模拟面试 ──
async function post(path, body) {
    const res = await fetch(path, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(body)
    });
    if (!res.ok) {
        const err = await res.json().catch(()=>({
                detail: "请求失败"
            }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
}
function startMockInterview(n = 5, space = "default") {
    return post("/api/mock/start", {
        n,
        space
    });
}
function getMockVerdict(question, answer) {
    return post("/api/mock/verdict", {
        question,
        answer
    });
}
function getMockFollowup(question, points, answer, roundNum) {
    return post("/api/mock/followup", {
        question,
        points,
        answer,
        round_num: roundNum
    });
}
function completeMockInterview(results, space = "default") {
    return post("/api/mock/complete", {
        results,
        space
    });
}
async function fetchItems(params = {}) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)){
        if (v !== undefined && v !== "") qs.set(k, String(v));
    }
    const res = await fetch(`/api/items?${qs.toString()}`, {
        cache: "no-store"
    });
    if (!res.ok) {
        const err = await res.json().catch(()=>({
                detail: "请求失败"
            }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
}
async function searchItems(q, space = "default", limit = 20) {
    const qs = new URLSearchParams({
        q,
        space,
        limit: String(limit)
    });
    const res = await fetch(`/api/search?${qs.toString()}`, {
        cache: "no-store"
    });
    if (!res.ok) {
        const err = await res.json().catch(()=>({
                detail: "检索失败"
            }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
}
async function markItemStatus(itemId, status, reason = "") {
    return post(`/api/items/${itemId}/status`, {
        status,
        reason
    });
}
async function editItem(itemId, patch, space = "default") {
    return post(`/api/items/${itemId}`, {
        ...patch,
        space
    });
}
async function deleteItem(itemId, space = "default") {
    const res = await fetch(`/api/items/${itemId}?space=${encodeURIComponent(space)}`, {
        method: "DELETE"
    });
    if (!res.ok) {
        const err = await res.json().catch(()=>({
                detail: "删除失败"
            }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
}
async function fetchDashboard(space = "default") {
    const res = await fetch(`/api/dashboard?space=${encodeURIComponent(space)}`, {
        cache: "no-store"
    });
    if (!res.ok) {
        const err = await res.json().catch(()=>({
                detail: "请求失败"
            }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
}
async function fetchProfile(space = "default") {
    const res = await fetch(`/api/profile?space=${encodeURIComponent(space)}`, {
        cache: "no-store"
    });
    if (!res.ok) {
        const err = await res.json().catch(()=>({
                detail: "请求失败"
            }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
}
async function uploadResume(file, space = "default") {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`/api/profile/resume?space=${encodeURIComponent(space)}`, {
        method: "POST",
        body: form
    });
    if (!res.ok) {
        const err = await res.json().catch(()=>({
                detail: "上传失败"
            }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
}
async function uploadJd(file, space = "default") {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`/api/profile/jd?space=${encodeURIComponent(space)}`, {
        method: "POST",
        body: form
    });
    if (!res.ok) {
        const err = await res.json().catch(()=>({
                detail: "上传失败"
            }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
}
// ── 申论工作台（docs/20 Step B，照抄 post/get 模式）──
async function get(path) {
    const res = await fetch(path, {
        cache: "no-store"
    });
    if (!res.ok) {
        const err = await res.json().catch(()=>({
                detail: "请求失败"
            }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
}
function startPractice() {
    return post("/api/shenlun/practice/start", {});
}
function submitPractice(questionId, answer, round) {
    return post("/api/shenlun/practice/submit", {
        question_id: questionId,
        answer,
        round
    });
}
function completePractice(questionId, rounds, action = "answered") {
    return post("/api/shenlun/practice/complete", {
        question_id: questionId,
        rounds,
        action
    });
}
function getRemind() {
    return get("/api/shenlun/remind");
}
function getWeakpoints(state) {
    const qs = state ? `?state=${encodeURIComponent(state)}` : "";
    return get(`/api/shenlun/weakpoints${qs}`);
}
function getDiagnose() {
    return get("/api/diagnose");
}
}),
"[project]/app/mock-interview/page.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "default",
    ()=>MockInterviewPage
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/lib/api.ts [app-ssr] (ecmascript)");
"use client";
;
;
;
const VERDICT_LABEL = {
    pass: "答对了 ✅",
    partial: "一半 ⚠️",
    fail: "没答上 ❌"
};
const VERDICT_DESC = {
    pass: "要点基本覆盖，下次面试能直接过",
    partial: "答了主干漏了细节，值得再看一遍",
    fail: "核心没答到，面试前必须再看"
};
const VERDICT_BADGE = {
    pass: "+掌握度",
    partial: "保持",
    fail: "-掌握度"
};
const STATUS_PILL = {
    fail: "❌ fail",
    partial: "⚠️ partial",
    pass: "✅ pass"
};
const SOURCE_BADGE = {
    weak: {
        label: "错题",
        cls: "text-red-600 bg-red-50 border-red-100"
    },
    resume: {
        label: "简历深挖",
        cls: "text-blue-600 bg-blue-50 border-blue-100"
    },
    jd: {
        label: "JD 能力",
        cls: "text-violet-600 bg-violet-50 border-violet-100"
    },
    behavior: {
        label: "行为面",
        cls: "text-emerald-600 bg-emerald-50 border-emerald-100"
    },
    motivation: {
        label: "动机面",
        cls: "text-amber-600 bg-amber-50 border-amber-100"
    },
    generic: {
        label: "通用",
        cls: "text-zinc-500 bg-zinc-100 border-zinc-200"
    }
};
function SourceBadge({ source }) {
    const s = SOURCE_BADGE[source] ?? SOURCE_BADGE.generic;
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
        className: `text-[10px] rounded-full px-2 py-0.5 border ${s.cls}`,
        children: s.label
    }, void 0, false, {
        fileName: "[project]/app/mock-interview/page.tsx",
        lineNumber: 67,
        columnNumber: 5
    }, this);
}
// ── 章节序列（按出现顺序去重）+ 每章状态 ──
// status: done（已答完） / active（正在答） / todo（未开始）
function buildSections(questions, idx) {
    const names = [];
    for (const q of questions){
        const s = q.section || "其他";
        if (!names.includes(s)) names.push(s);
    }
    return names.map((name, i)=>{
        // 当前章节 = 当前题所在章节；之前章节全部 done
        const cur = questions[idx]?.section || "其他";
        if (name === cur) return {
            name,
            status: "active"
        };
        // 章节顺序在前的已完成（按索引判断）
        const curSectionFirstIdx = questions.findIndex((q)=>(q.section || "其他") === cur);
        const thisSectionFirstIdx = questions.findIndex((q)=>(q.section || "其他") === name);
        return {
            name,
            status: thisSectionFirstIdx < curSectionFirstIdx ? "done" : "todo"
        };
    });
}
// 顶部章节 stepper：当前章节高亮，已完成打勾，未开始置灰
function SectionStepper({ sections }) {
    const ICONS = {
        自我介绍: "👋",
        项目深挖: "🔍",
        技术验证: "⚙️",
        行为面: "🧭",
        动机面: "🎯"
    };
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "flex items-center gap-1 overflow-x-auto pb-0.5",
        children: sections.map((s, i)=>{
            const icon = ICONS[s.name] ?? "📂";
            return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "flex items-center gap-1 shrink-0",
                children: [
                    i > 0 ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        className: `h-px w-3 ${s.status === "todo" ? "bg-zinc-200" : "bg-indigo-400"}`
                    }, void 0, false, {
                        fileName: "[project]/app/mock-interview/page.tsx",
                        lineNumber: 110,
                        columnNumber: 22
                    }, this) : null,
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        className: `flex items-center gap-1 text-[11px] rounded-full px-2 py-1 border transition-all ${s.status === "active" ? "bg-indigo-600 text-white border-indigo-600 shadow-sm font-medium" : s.status === "done" ? "bg-indigo-50 text-indigo-600 border-indigo-100" : "bg-white text-zinc-400 border-zinc-200"}`,
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                children: s.status === "done" ? "✓" : icon
                            }, void 0, false, {
                                fileName: "[project]/app/mock-interview/page.tsx",
                                lineNumber: 120,
                                columnNumber: 15
                            }, this),
                            s.name
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/mock-interview/page.tsx",
                        lineNumber: 111,
                        columnNumber: 13
                    }, this)
                ]
            }, s.name, true, {
                fileName: "[project]/app/mock-interview/page.tsx",
                lineNumber: 109,
                columnNumber: 11
            }, this);
        })
    }, void 0, false, {
        fileName: "[project]/app/mock-interview/page.tsx",
        lineNumber: 105,
        columnNumber: 5
    }, this);
}
function MockInterviewPage() {
    const [phase, setPhase] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("loading");
    const [questions, setQuestions] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])([]);
    const [idx, setIdx] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(0);
    const [answer, setAnswer] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    const [judge, setJudge] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(null);
    const [picked, setPicked] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("partial");
    const [results, setResults] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])([]);
    const [error, setError] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    const [behaviors, setBehaviors] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])([]);
    const [newCount, setNewCount] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(0);
    const [saved, setSaved] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(false);
    const [saving, setSaving] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(false);
    const [profile, setProfile] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(null);
    const [uploading, setUploading] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(null);
    const [uploadMsg, setUploadMsg] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    // 追问状态：每题最多追 2 轮（对齐 CLI MAX_FOLLOWUPS）
    const [followQ, setFollowQ] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(null); // 当前题的追问问题
    const [rounds, setRounds] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])([]); // 每题已追轮数
    const [following, setFollowing] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(false);
    const [followMsg, setFollowMsg] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(""); // 面试官"不再追问"的提示
    const [focusTopics, setFocusTopics] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])([]); // 画像薄弱主题（setup 页"本场重点"）
    const answerRef = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRef"])(null);
    // ── 开始面试：拉错题 ──
    const begin = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useCallback"])(async ()=>{
        setPhase("loading");
        setError("");
        try {
            const space = localStorage.getItem("offerloop.space") || "default";
            const res = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["startMockInterview"])(5, space);
            setQuestions(res.questions);
            setFocusTopics(res.focus_topics ?? []);
            setPhase(res.questions.length ? "setup" : "setup");
        } catch (e) {
            setError(e instanceof Error ? e.message : "开始失败");
            setPhase("setup");
        }
    }, []);
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useEffect"])(()=>{
        begin();
    }, [
        begin
    ]);
    // ── 简历/JD 状态（「简历深挖」章节的数据源，按当前空间）──
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useEffect"])(()=>{
        const space = localStorage.getItem("offerloop.space") || "default";
        (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["fetchProfile"])(space).then(setProfile).catch(()=>setProfile(null));
    }, []);
    async function handleDocUpload(kind, e) {
        const file = e.target.files?.[0];
        e.target.value = ""; // 允许重复选择同一文件
        if (!file || uploading) return;
        setUploading(kind);
        setUploadMsg("");
        setError("");
        try {
            const space = localStorage.getItem("offerloop.space") || "default";
            const res = kind === "resume" ? await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["uploadResume"])(file, space) : await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["uploadJd"])(file, space);
            setProfile(await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["fetchProfile"])(space));
            setUploadMsg(`${res.filename}：${res.chars} 字${res.pages ? ` / ${res.pages} 页` : ""}，已更新。下一场模拟面试将用新${kind === "resume" ? "简历" : "JD"}出题。旧版已备份为 ${kind}.md.bak`);
        } catch (err) {
            const msg = err instanceof Error ? err.message : "上传失败";
            // 常见运维问题：后端没重启 → 405，翻译成人话
            const friendly = /Method Not Allowed|405/.test(msg) ? "后端还在跑旧代码——请重启 uvicorn（杀 8000 进程后重新启动），再重试上传" : msg;
            setError(friendly);
        } finally{
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
            const v = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["getMockVerdict"])(followQ ?? q.question, text);
            setJudge(v);
            setPicked(v.suggested);
            setFollowMsg("");
            setPhase("verdict");
        } catch (e) {
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
            const res = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["getMockFollowup"])(q.question, judge.points, answer, (rounds[idx] ?? 0) + 1);
            if (res.need_followup && res.followup_question.trim()) {
                setFollowQ(res.followup_question.trim());
                setRounds((prev)=>{
                    const n = [
                        ...prev
                    ];
                    n[idx] = (n[idx] ?? 0) + 1;
                    return n;
                });
                setAnswer("");
                setJudge(null);
                setPhase("question");
                setTimeout(()=>answerRef.current?.focus(), 50);
            } else {
                // 面试官认为不用再追
                setFollowMsg(res.reason || "这道题不用再追问了");
            }
        } catch (e) {
            setError(e instanceof Error ? e.message : "追问失败");
        } finally{
            setFollowing(false);
        }
    }
    // ── 确认判定 → 下一题 / 报告 ──
    function confirmVerdict() {
        const q = questions[idx];
        const answered = {
            q,
            answer: answer.trim(),
            verdict: picked,
            judge: judge
        };
        const next = [
            ...results,
            answered
        ];
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
    async function saveResults(list) {
        setSaving(true);
        try {
            const res = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["completeMockInterview"])(list.map((r)=>({
                    question_id: r.q.id,
                    question: r.q.question,
                    verdict: r.verdict,
                    answer: r.answer,
                    source: r.q.source || "weak",
                    topic: r.q.topic,
                    points: r.judge.points,
                    misses: r.judge.misses,
                    reason: r.judge.reason
                })), localStorage.getItem("offerloop.space") || "default");
            setBehaviors(res.behaviors);
            setNewCount(res.new);
            setSaved(true);
        } catch (e) {
            setError(e instanceof Error ? e.message : "写回失败");
        } finally{
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
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "min-h-dvh bg-zinc-50/50",
        children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
            className: "max-w-3xl mx-auto w-full bg-white min-h-dvh shadow-sm border-x border-zinc-200 flex flex-col",
            children: [
                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                    className: "flex items-center gap-3 px-5 py-3 border-b border-zinc-200 bg-white shrink-0 sticky top-0 z-10",
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("a", {
                            href: "/",
                            className: "w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white text-sm font-bold hover:bg-indigo-700 transition-colors",
                            children: "O"
                        }, void 0, false, {
                            fileName: "[project]/app/mock-interview/page.tsx",
                            lineNumber: 335,
                            columnNumber: 11
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h1", {
                                    className: "text-sm font-semibold text-zinc-900",
                                    children: "模拟面试"
                                }, void 0, false, {
                                    fileName: "[project]/app/mock-interview/page.tsx",
                                    lineNumber: 342,
                                    columnNumber: 13
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                    className: "text-[11px] text-zinc-500",
                                    children: "只考你的错题 · LLM 给对照 · 你拍板"
                                }, void 0, false, {
                                    fileName: "[project]/app/mock-interview/page.tsx",
                                    lineNumber: 343,
                                    columnNumber: 13
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/app/mock-interview/page.tsx",
                            lineNumber: 341,
                            columnNumber: 11
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "ml-auto",
                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: "text-[11px] text-zinc-400 bg-zinc-100 rounded-full px-2.5 py-1",
                                children: "v1 单轮"
                            }, void 0, false, {
                                fileName: "[project]/app/mock-interview/page.tsx",
                                lineNumber: 346,
                                columnNumber: 13
                            }, this)
                        }, void 0, false, {
                            fileName: "[project]/app/mock-interview/page.tsx",
                            lineNumber: 345,
                            columnNumber: 11
                        }, this)
                    ]
                }, void 0, true, {
                    fileName: "[project]/app/mock-interview/page.tsx",
                    lineNumber: 334,
                    columnNumber: 9
                }, this),
                phase === "question" || phase === "judging" || phase === "verdict" ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                    className: "px-5 pt-4 space-y-2",
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "h-1.5 rounded-full bg-zinc-100 overflow-hidden",
                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "h-full bg-indigo-600 transition-all duration-500",
                                style: {
                                    width: `${(idx + 0.5) / questions.length * 100}%`
                                }
                            }, void 0, false, {
                                fileName: "[project]/app/mock-interview/page.tsx",
                                lineNumber: 356,
                                columnNumber: 15
                            }, this)
                        }, void 0, false, {
                            fileName: "[project]/app/mock-interview/page.tsx",
                            lineNumber: 355,
                            columnNumber: 13
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "flex justify-between text-[11px] text-zinc-400",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                    children: [
                                        "第 ",
                                        idx + 1,
                                        " / ",
                                        questions.length,
                                        " 题"
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/app/mock-interview/page.tsx",
                                    lineNumber: 362,
                                    columnNumber: 15
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                    children: "考的是你栽过的题"
                                }, void 0, false, {
                                    fileName: "[project]/app/mock-interview/page.tsx",
                                    lineNumber: 363,
                                    columnNumber: 15
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/app/mock-interview/page.tsx",
                            lineNumber: 361,
                            columnNumber: 13
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(SectionStepper, {
                            sections: buildSections(questions, idx)
                        }, void 0, false, {
                            fileName: "[project]/app/mock-interview/page.tsx",
                            lineNumber: 365,
                            columnNumber: 13
                        }, this)
                    ]
                }, void 0, true, {
                    fileName: "[project]/app/mock-interview/page.tsx",
                    lineNumber: 354,
                    columnNumber: 11
                }, this) : null,
                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                    className: "flex-1 px-5 py-5 space-y-4",
                    children: [
                        phase === "loading" ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "text-center py-20 space-y-3",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "w-10 h-10 mx-auto rounded-full border-2 border-indigo-600 border-t-transparent animate-spin"
                                }, void 0, false, {
                                    fileName: "[project]/app/mock-interview/page.tsx",
                                    lineNumber: 373,
                                    columnNumber: 15
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                    className: "text-sm text-zinc-500",
                                    children: "正在根据 简历 + JD + 错题本 生成结构化面试..."
                                }, void 0, false, {
                                    fileName: "[project]/app/mock-interview/page.tsx",
                                    lineNumber: 374,
                                    columnNumber: 15
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/app/mock-interview/page.tsx",
                            lineNumber: 372,
                            columnNumber: 13
                        }, this) : null,
                        phase === "setup" ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "space-y-4",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "rounded-xl border border-zinc-200 bg-white p-4 shadow-sm",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                            className: "text-sm font-semibold text-zinc-900",
                                            children: "🎯 本场面试计划"
                                        }, void 0, false, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 382,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                            className: "text-xs text-zinc-500 mt-1.5 leading-relaxed",
                                            children: [
                                                "出题依据 ",
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                                    children: "三源"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 384,
                                                    columnNumber: 24
                                                }, this),
                                                "：你的简历（项目深挖）、目标 JD（能力项验证）、 错题本（薄弱项优先）。共 ",
                                                questions.length,
                                                " 题，分章节进行， 每题一答一判，LLM 面试官给",
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                                    children: "参考要点 + 差距"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 386,
                                                    columnNumber: 34
                                                }, this),
                                                "，你最终拍板。"
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 383,
                                            columnNumber: 17
                                        }, this),
                                        focusTopics.length > 0 ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "mt-2.5 rounded-lg border border-violet-200 bg-violet-50/60 px-3 py-2",
                                            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                className: "text-[11px] text-violet-700 font-medium",
                                                children: [
                                                    "🧠 记忆管家记得你：本场将重点验证你的薄弱主题 ——",
                                                    " ",
                                                    focusTopics.map((t)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                            className: "inline-block text-[11px] bg-white border border-violet-200 text-violet-700 rounded-full px-2 py-0.5 mx-0.5",
                                                            children: t
                                                        }, t, false, {
                                                            fileName: "[project]/app/mock-interview/page.tsx",
                                                            lineNumber: 395,
                                                            columnNumber: 25
                                                        }, this))
                                                ]
                                            }, void 0, true, {
                                                fileName: "[project]/app/mock-interview/page.tsx",
                                                lineNumber: 392,
                                                columnNumber: 21
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 391,
                                            columnNumber: 19
                                        }, this) : null,
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "mt-3 rounded-lg border border-zinc-200 bg-zinc-50/60 p-3 space-y-3",
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(DocRow, {
                                                    label: "简历",
                                                    doc: profile?.resume ?? null,
                                                    uploading: uploading === "resume",
                                                    onPick: (e)=>handleDocUpload("resume", e)
                                                }, void 0, false, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 408,
                                                    columnNumber: 19
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(DocRow, {
                                                    label: "JD",
                                                    doc: profile?.jd ?? null,
                                                    uploading: uploading === "jd",
                                                    onPick: (e)=>handleDocUpload("jd", e)
                                                }, void 0, false, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 414,
                                                    columnNumber: 19
                                                }, this),
                                                uploadMsg ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                    className: "rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700 leading-relaxed",
                                                    children: [
                                                        "✓ ",
                                                        uploadMsg
                                                    ]
                                                }, void 0, true, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 421,
                                                    columnNumber: 21
                                                }, this) : null
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 407,
                                            columnNumber: 17
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/app/mock-interview/page.tsx",
                                    lineNumber: 381,
                                    columnNumber: 15
                                }, this),
                                Object.entries(questions.reduce((acc, q)=>{
                                    const key = q.section || "其他";
                                    (acc[key] ||= []).push(q);
                                    return acc;
                                }, {})).map(([section, qs])=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                        children: [
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                className: "text-[11px] font-semibold text-zinc-500 mb-1.5 px-0.5",
                                                children: [
                                                    "📂 ",
                                                    section,
                                                    " · ",
                                                    qs.length,
                                                    " 题"
                                                ]
                                            }, void 0, true, {
                                                fileName: "[project]/app/mock-interview/page.tsx",
                                                lineNumber: 436,
                                                columnNumber: 19
                                            }, this),
                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                className: "space-y-2",
                                                children: qs.map((q, i)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                        className: "rounded-xl border border-zinc-200 bg-white p-3.5 shadow-sm",
                                                        children: [
                                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                                className: "flex items-center gap-1.5 flex-wrap mb-1.5",
                                                                children: [
                                                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(SourceBadge, {
                                                                        source: q.source
                                                                    }, void 0, false, {
                                                                        fileName: "[project]/app/mock-interview/page.tsx",
                                                                        lineNumber: 443,
                                                                        columnNumber: 27
                                                                    }, this),
                                                                    q.status && q.status in STATUS_PILL ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                                        className: "text-[10px] text-red-600 bg-red-50 border border-red-100 rounded-full px-2 py-0.5",
                                                                        children: STATUS_PILL[q.status]
                                                                    }, void 0, false, {
                                                                        fileName: "[project]/app/mock-interview/page.tsx",
                                                                        lineNumber: 445,
                                                                        columnNumber: 29
                                                                    }, this) : null,
                                                                    q.topic ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                                        className: "text-[10px] text-zinc-500 bg-zinc-100 rounded-full px-2 py-0.5",
                                                                        children: q.topic
                                                                    }, void 0, false, {
                                                                        fileName: "[project]/app/mock-interview/page.tsx",
                                                                        lineNumber: 450,
                                                                        columnNumber: 29
                                                                    }, this) : null,
                                                                    q.gap !== null ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                                        className: "text-[10px] text-amber-600 bg-amber-50 border border-amber-100 rounded-full px-2 py-0.5 ml-auto",
                                                                        children: [
                                                                            "gap ",
                                                                            Math.round(q.gap * 100),
                                                                            "%"
                                                                        ]
                                                                    }, void 0, true, {
                                                                        fileName: "[project]/app/mock-interview/page.tsx",
                                                                        lineNumber: 455,
                                                                        columnNumber: 29
                                                                    }, this) : null
                                                                ]
                                                            }, void 0, true, {
                                                                fileName: "[project]/app/mock-interview/page.tsx",
                                                                lineNumber: 442,
                                                                columnNumber: 25
                                                            }, this),
                                                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                                className: "text-sm font-medium text-zinc-900 leading-snug",
                                                                children: q.question
                                                            }, void 0, false, {
                                                                fileName: "[project]/app/mock-interview/page.tsx",
                                                                lineNumber: 460,
                                                                columnNumber: 25
                                                            }, this)
                                                        ]
                                                    }, q.id || `${section}-${i}`, true, {
                                                        fileName: "[project]/app/mock-interview/page.tsx",
                                                        lineNumber: 441,
                                                        columnNumber: 23
                                                    }, this))
                                            }, void 0, false, {
                                                fileName: "[project]/app/mock-interview/page.tsx",
                                                lineNumber: 439,
                                                columnNumber: 19
                                            }, this)
                                        ]
                                    }, section, true, {
                                        fileName: "[project]/app/mock-interview/page.tsx",
                                        lineNumber: 435,
                                        columnNumber: 17
                                    }, this)),
                                error ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600",
                                    children: error
                                }, void 0, false, {
                                    fileName: "[project]/app/mock-interview/page.tsx",
                                    lineNumber: 468,
                                    columnNumber: 17
                                }, this) : null,
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                    onClick: ()=>{
                                        setIdx(0);
                                        setPhase("question");
                                    },
                                    className: "w-full h-12 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-all active:scale-[0.99]",
                                    children: "开始面试 →"
                                }, void 0, false, {
                                    fileName: "[project]/app/mock-interview/page.tsx",
                                    lineNumber: 473,
                                    columnNumber: 15
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/app/mock-interview/page.tsx",
                            lineNumber: 380,
                            columnNumber: 13
                        }, this) : null,
                        phase === "question" ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "space-y-4",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "rounded-xl border border-zinc-200 bg-indigo-50/40 p-4",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "flex items-center gap-2 mb-2",
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                    className: "w-7 h-7 rounded-full bg-indigo-100 flex items-center justify-center text-sm",
                                                    children: "🧑‍💼"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 490,
                                                    columnNumber: 19
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: "text-[11px] text-indigo-500 font-medium",
                                                    children: "面试官"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 493,
                                                    columnNumber: 19
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 489,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                            className: "text-base font-semibold text-zinc-900 leading-relaxed",
                                            children: followQ ?? questions[idx]?.question
                                        }, void 0, false, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 495,
                                            columnNumber: 17
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/app/mock-interview/page.tsx",
                                    lineNumber: 488,
                                    columnNumber: 15
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "flex items-center gap-1.5 flex-wrap",
                                    children: [
                                        followQ && (rounds[idx] ?? 0) > 0 ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                            className: "text-[10px] text-indigo-600 bg-indigo-50 border border-indigo-100 rounded-full px-2 py-0.5",
                                            children: [
                                                "追问 ",
                                                rounds[idx] ?? 0,
                                                "/",
                                                2,
                                                " 轮"
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 502,
                                            columnNumber: 19
                                        }, this) : null,
                                        questions[idx] ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(SourceBadge, {
                                            source: questions[idx].source
                                        }, void 0, false, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 506,
                                            columnNumber: 35
                                        }, this) : null,
                                        questions[idx]?.status && questions[idx].status in STATUS_PILL ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                            className: "text-[10px] text-red-600 bg-red-50 border border-red-100 rounded-full px-2 py-0.5",
                                            children: STATUS_PILL[questions[idx].status]
                                        }, void 0, false, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 508,
                                            columnNumber: 19
                                        }, this) : null,
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                            className: "text-[10px] text-zinc-500 bg-zinc-100 rounded-full px-2 py-0.5",
                                            children: [
                                                questions[idx]?.section || "",
                                                " · 考点：",
                                                questions[idx]?.topic || "未分类"
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 512,
                                            columnNumber: 17
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/app/mock-interview/page.tsx",
                                    lineNumber: 500,
                                    columnNumber: 15
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("textarea", {
                                    ref: answerRef,
                                    value: answer,
                                    onChange: (e)=>setAnswer(e.target.value),
                                    placeholder: "在真实面试中你会怎么回答这道题？打在这里...",
                                    rows: 6,
                                    className: "w-full resize-y rounded-xl border border-zinc-300 bg-zinc-50 px-4 py-3 text-sm leading-relaxed outline-none focus:border-indigo-500 focus:bg-white focus:ring-1 focus:ring-indigo-500/20 transition-all"
                                }, void 0, false, {
                                    fileName: "[project]/app/mock-interview/page.tsx",
                                    lineNumber: 517,
                                    columnNumber: 15
                                }, this),
                                error ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600",
                                    children: error
                                }, void 0, false, {
                                    fileName: "[project]/app/mock-interview/page.tsx",
                                    lineNumber: 527,
                                    columnNumber: 17
                                }, this) : null,
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "flex gap-3",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("a", {
                                            href: "/",
                                            className: "h-12 px-5 rounded-xl border border-zinc-300 text-sm text-zinc-600 hover:bg-zinc-50 flex items-center justify-center transition-all",
                                            children: "退出"
                                        }, void 0, false, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 533,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                            onClick: submitAnswer,
                                            disabled: !answer.trim(),
                                            className: "flex-1 h-12 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all active:scale-[0.99]",
                                            children: "提交回答 →"
                                        }, void 0, false, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 539,
                                            columnNumber: 17
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/app/mock-interview/page.tsx",
                                    lineNumber: 532,
                                    columnNumber: 15
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                    className: "text-center text-[11px] text-zinc-400",
                                    children: "Enter 提交 · Shift+Enter 换行"
                                }, void 0, false, {
                                    fileName: "[project]/app/mock-interview/page.tsx",
                                    lineNumber: 547,
                                    columnNumber: 15
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/app/mock-interview/page.tsx",
                            lineNumber: 487,
                            columnNumber: 13
                        }, this) : null,
                        phase === "judging" ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "py-16 space-y-4",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-700 leading-relaxed",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "flex items-center gap-2 mb-2",
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                    className: "w-7 h-7 rounded-full bg-indigo-100 flex items-center justify-center text-sm",
                                                    children: "🧑‍💼"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 558,
                                                    columnNumber: 19
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: "text-[11px] text-indigo-500 font-medium",
                                                    children: "面试官"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 561,
                                                    columnNumber: 19
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 557,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "bg-white rounded-xl border border-zinc-200 px-4 py-3 text-zinc-600 whitespace-pre-wrap",
                                            children: answer
                                        }, void 0, false, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 563,
                                            columnNumber: 17
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/app/mock-interview/page.tsx",
                                    lineNumber: 556,
                                    columnNumber: 15
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "text-center space-y-2",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "flex justify-center gap-1.5",
                                            children: [
                                                0,
                                                1,
                                                2
                                            ].map((i)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: "typing-dot w-2 h-2 bg-zinc-400 rounded-full inline-block",
                                                    style: {
                                                        animationDelay: `${i * 0.2}s`
                                                    }
                                                }, i, false, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 570,
                                                    columnNumber: 21
                                                }, this))
                                        }, void 0, false, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 568,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                            className: "text-xs text-zinc-400",
                                            children: "LLM 面试官正在生成：期望要点 → 差距分析 → 建议判定"
                                        }, void 0, false, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 577,
                                            columnNumber: 17
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/app/mock-interview/page.tsx",
                                    lineNumber: 567,
                                    columnNumber: 15
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/app/mock-interview/page.tsx",
                            lineNumber: 555,
                            columnNumber: 13
                        }, this) : null,
                        phase === "verdict" && judge ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "space-y-4",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "rounded-xl border-2 border-indigo-200 bg-white p-4 shadow-sm",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "flex items-center gap-2 mb-2",
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                    className: "w-7 h-7 rounded-full bg-indigo-100 flex items-center justify-center text-sm",
                                                    children: "🧑‍💼"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 589,
                                                    columnNumber: 19
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: "text-sm font-semibold text-zinc-900",
                                                    children: "面试官判定"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 592,
                                                    columnNumber: 19
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: "ml-auto text-[10px] text-indigo-600 bg-indigo-50 border border-indigo-100 rounded-full px-2 py-0.5",
                                                    children: [
                                                        "LLM 建议：",
                                                        VERDICT_LABEL[judge.suggested]
                                                    ]
                                                }, void 0, true, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 593,
                                                    columnNumber: 19
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 588,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                            className: "text-[11px] font-bold text-zinc-400 tracking-wide mt-3 mb-1.5",
                                            children: "✅ 这道题应该答到"
                                        }, void 0, false, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 599,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "space-y-1.5 mb-3",
                                            children: judge.points.map((p, i)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                    className: "flex gap-2 text-sm text-zinc-700",
                                                    children: [
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                            className: "w-4 h-4 mt-0.5 rounded-full bg-emerald-500 text-white text-[10px] flex items-center justify-center flex-shrink-0",
                                                            children: "✓"
                                                        }, void 0, false, {
                                                            fileName: "[project]/app/mock-interview/page.tsx",
                                                            lineNumber: 605,
                                                            columnNumber: 23
                                                        }, this),
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                            className: "leading-relaxed",
                                                            children: p
                                                        }, void 0, false, {
                                                            fileName: "[project]/app/mock-interview/page.tsx",
                                                            lineNumber: 608,
                                                            columnNumber: 23
                                                        }, this)
                                                    ]
                                                }, i, true, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 604,
                                                    columnNumber: 21
                                                }, this))
                                        }, void 0, false, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 602,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                            className: "text-[11px] font-bold text-zinc-400 tracking-wide mt-3 mb-1.5",
                                            children: "✗ 你漏掉的 / 差距"
                                        }, void 0, false, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 614,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "space-y-1.5 mb-3",
                                            children: judge.misses.length ? judge.misses.map((m, i)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                    className: "flex gap-2 text-sm text-zinc-700",
                                                    children: [
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                            className: "w-4 h-4 mt-0.5 rounded-full bg-rose-500 text-white text-[10px] flex items-center justify-center flex-shrink-0",
                                                            children: "✗"
                                                        }, void 0, false, {
                                                            fileName: "[project]/app/mock-interview/page.tsx",
                                                            lineNumber: 621,
                                                            columnNumber: 25
                                                        }, this),
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                            className: "leading-relaxed",
                                                            children: m
                                                        }, void 0, false, {
                                                            fileName: "[project]/app/mock-interview/page.tsx",
                                                            lineNumber: 624,
                                                            columnNumber: 25
                                                        }, this)
                                                    ]
                                                }, i, true, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 620,
                                                    columnNumber: 23
                                                }, this)) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                className: "text-sm text-zinc-400",
                                                children: "没有明显遗漏"
                                            }, void 0, false, {
                                                fileName: "[project]/app/mock-interview/page.tsx",
                                                lineNumber: 628,
                                                columnNumber: 21
                                            }, this)
                                        }, void 0, false, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 617,
                                            columnNumber: 17
                                        }, this),
                                        judge.reason ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "rounded-lg border-l-3 border-l-amber-500 bg-amber-50 px-3.5 py-2.5 text-[13px] text-amber-800 leading-relaxed",
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("b", {
                                                    children: "面试官的话："
                                                }, void 0, false, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 635,
                                                    columnNumber: 21
                                                }, this),
                                                judge.reason
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 634,
                                            columnNumber: 19
                                        }, this) : null
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/app/mock-interview/page.tsx",
                                    lineNumber: 587,
                                    columnNumber: 15
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "rounded-xl border border-zinc-200 bg-white p-4 shadow-sm",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "flex items-center justify-between mb-3",
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                    className: "text-sm font-semibold text-zinc-900",
                                                    children: "🏁 最终判定"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 643,
                                                    columnNumber: 19
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                    className: "text-[10px] text-zinc-400",
                                                    children: "LLM 建议已预选，你说了算"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 644,
                                                    columnNumber: 19
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 642,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "space-y-2",
                                            children: [
                                                "pass",
                                                "partial",
                                                "fail"
                                            ].map((v)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                    onClick: ()=>setPicked(v),
                                                    className: `w-full flex items-start gap-3 rounded-xl border-1.5 px-3.5 py-3 text-left transition-all ${picked === v ? "border-indigo-500 bg-indigo-50/70 shadow-sm" : "border-zinc-200 hover:border-indigo-300"}`,
                                                    children: [
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                            className: `w-4 h-4 mt-0.5 rounded-full border-2 flex-shrink-0 flex items-center justify-center transition-all ${picked === v ? "border-indigo-600" : "border-zinc-300"}`,
                                                            children: picked === v ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                                className: "w-2 h-2 rounded-full bg-indigo-600"
                                                            }, void 0, false, {
                                                                fileName: "[project]/app/mock-interview/page.tsx",
                                                                lineNumber: 663,
                                                                columnNumber: 27
                                                            }, this) : null
                                                        }, void 0, false, {
                                                            fileName: "[project]/app/mock-interview/page.tsx",
                                                            lineNumber: 657,
                                                            columnNumber: 23
                                                        }, this),
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                            className: "flex-1",
                                                            children: [
                                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                                    className: "block text-sm font-medium text-zinc-900",
                                                                    children: VERDICT_LABEL[v]
                                                                }, void 0, false, {
                                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                                    lineNumber: 667,
                                                                    columnNumber: 25
                                                                }, this),
                                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                                    className: "block text-[11px] text-zinc-500 mt-0.5",
                                                                    children: VERDICT_DESC[v]
                                                                }, void 0, false, {
                                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                                    lineNumber: 670,
                                                                    columnNumber: 25
                                                                }, this)
                                                            ]
                                                        }, void 0, true, {
                                                            fileName: "[project]/app/mock-interview/page.tsx",
                                                            lineNumber: 666,
                                                            columnNumber: 23
                                                        }, this),
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                            className: "text-[10px] text-indigo-500 bg-indigo-50 rounded-full px-2 py-0.5 self-center",
                                                            children: VERDICT_BADGE[v]
                                                        }, void 0, false, {
                                                            fileName: "[project]/app/mock-interview/page.tsx",
                                                            lineNumber: 674,
                                                            columnNumber: 23
                                                        }, this)
                                                    ]
                                                }, v, true, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 648,
                                                    columnNumber: 21
                                                }, this))
                                        }, void 0, false, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 646,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "flex gap-3 mt-4",
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                    onClick: ()=>{
                                                        setPhase("question");
                                                        setJudge(null);
                                                        answerRef.current?.focus();
                                                    },
                                                    className: "h-12 px-5 rounded-xl border border-zinc-300 text-sm text-zinc-600 hover:bg-zinc-50 transition-all",
                                                    children: "重答此题"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 681,
                                                    columnNumber: 19
                                                }, this),
                                                (rounds[idx] ?? 0) < 2 && !followMsg ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                    onClick: handleFollowup,
                                                    disabled: following,
                                                    className: "h-12 px-4 rounded-xl border border-indigo-200 text-sm text-indigo-600 hover:bg-indigo-50 disabled:opacity-50 transition-all",
                                                    children: following ? "面试官思考中…" : `追问（${(rounds[idx] ?? 0) + 1}/2）`
                                                }, void 0, false, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 692,
                                                    columnNumber: 21
                                                }, this) : null,
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                    onClick: confirmVerdict,
                                                    className: "flex-1 h-12 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-all active:scale-[0.99]",
                                                    children: idx === questions.length - 1 ? "确认，查看报告 🏁" : "确认，下一题 →"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 700,
                                                    columnNumber: 19
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 680,
                                            columnNumber: 17
                                        }, this),
                                        followMsg ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                            className: "text-[11px] text-zinc-500 bg-zinc-50 rounded-lg px-3 py-2 mt-2 leading-relaxed",
                                            children: [
                                                "💬 面试官：",
                                                followMsg
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 708,
                                            columnNumber: 19
                                        }, this) : null
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/app/mock-interview/page.tsx",
                                    lineNumber: 641,
                                    columnNumber: 15
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/app/mock-interview/page.tsx",
                            lineNumber: 586,
                            columnNumber: 13
                        }, this) : null,
                        phase === "report" ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "space-y-4",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "grid grid-cols-3 gap-2",
                                    children: [
                                        [
                                            "pass",
                                            "答对",
                                            "text-emerald-600"
                                        ],
                                        [
                                            "partial",
                                            "一半",
                                            "text-amber-600"
                                        ],
                                        [
                                            "fail",
                                            "没答上",
                                            "text-red-600"
                                        ]
                                    ].map(([k, label, color])=>{
                                        const n = results.filter((r)=>r.verdict === k).length;
                                        return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "rounded-xl border border-zinc-200 bg-white p-4 text-center shadow-sm",
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                    className: `text-2xl font-bold ${color}`,
                                                    children: n
                                                }, void 0, false, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 731,
                                                    columnNumber: 23
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                    className: "text-[11px] text-zinc-400 mt-0.5",
                                                    children: label
                                                }, void 0, false, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 732,
                                                    columnNumber: 23
                                                }, this)
                                            ]
                                        }, k, true, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 730,
                                            columnNumber: 21
                                        }, this);
                                    })
                                }, void 0, false, {
                                    fileName: "[project]/app/mock-interview/page.tsx",
                                    lineNumber: 720,
                                    columnNumber: 15
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "rounded-xl border border-zinc-200 bg-white p-4 shadow-sm",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "flex items-center gap-2",
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                    className: "text-sm font-semibold text-zinc-900",
                                                    children: "💾 写回错题本"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 741,
                                                    columnNumber: 19
                                                }, this),
                                                saving ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: "text-[11px] text-zinc-400 flex items-center gap-1.5",
                                                    children: [
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                            className: "w-3 h-3 rounded-full border-2 border-indigo-600 border-t-transparent animate-spin inline-block"
                                                        }, void 0, false, {
                                                            fileName: "[project]/app/mock-interview/page.tsx",
                                                            lineNumber: 744,
                                                            columnNumber: 23
                                                        }, this),
                                                        "写回中..."
                                                    ]
                                                }, void 0, true, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 743,
                                                    columnNumber: 21
                                                }, this) : saved ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: "text-[11px] text-emerald-600 bg-emerald-50 rounded-full px-2 py-0.5",
                                                    children: [
                                                        "✅ 已写回 ",
                                                        results.length,
                                                        " 题",
                                                        newCount > 0 ? ` · 新采集 ${newCount} 道` : ""
                                                    ]
                                                }, void 0, true, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 748,
                                                    columnNumber: 21
                                                }, this) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: "text-[11px] text-amber-600 bg-amber-50 rounded-full px-2 py-0.5",
                                                    children: "⚠️ 写回失败，可重试"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 752,
                                                    columnNumber: 21
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 740,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                            className: "text-[11px] text-zinc-500 mt-1.5 leading-relaxed",
                                            children: "fail 题下降、partial 保持、pass 上升 —— 下次「面试前提醒」会按新掌握度重新排序。"
                                        }, void 0, false, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 757,
                                            columnNumber: 17
                                        }, this),
                                        behaviors.length ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "mt-2.5",
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                    className: "text-[11px] text-zinc-400 mb-1",
                                                    children: "🧠 你的行为特征（整场总结）："
                                                }, void 0, false, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 762,
                                                    columnNumber: 21
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                    className: "flex flex-wrap gap-1.5",
                                                    children: behaviors.map((b)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                            className: "text-[11px] text-zinc-600 bg-zinc-100 rounded-full px-2.5 py-0.5",
                                                            children: b
                                                        }, b, false, {
                                                            fileName: "[project]/app/mock-interview/page.tsx",
                                                            lineNumber: 765,
                                                            columnNumber: 25
                                                        }, this))
                                                }, void 0, false, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 763,
                                                    columnNumber: 21
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 761,
                                            columnNumber: 19
                                        }, this) : null,
                                        error && !saved ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                            onClick: ()=>saveResults(results),
                                            disabled: saving,
                                            className: "mt-3 h-10 px-4 rounded-xl bg-indigo-600 text-white text-sm hover:bg-indigo-700 disabled:opacity-40 transition-all",
                                            children: "重试写回"
                                        }, void 0, false, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 773,
                                            columnNumber: 19
                                        }, this) : null
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/app/mock-interview/page.tsx",
                                    lineNumber: 739,
                                    columnNumber: 15
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "rounded-xl border border-zinc-200 bg-white p-4 shadow-sm",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                            className: "text-sm font-semibold text-zinc-900 mb-3",
                                            children: "📋 逐题复盘"
                                        }, void 0, false, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 785,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "space-y-3",
                                            children: results.map((r, i)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                    className: "rounded-lg border border-zinc-200 p-3",
                                                    children: [
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                                            className: "flex items-center gap-1.5 flex-wrap",
                                                            children: [
                                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                                    className: `text-[10px] rounded-full px-2 py-0.5 font-medium ${r.verdict === "pass" ? "bg-emerald-50 text-emerald-600 border border-emerald-100" : r.verdict === "partial" ? "bg-amber-50 text-amber-600 border border-amber-100" : "bg-red-50 text-red-600 border border-red-100"}`,
                                                                    children: VERDICT_LABEL[r.verdict]
                                                                }, void 0, false, {
                                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                                    lineNumber: 790,
                                                                    columnNumber: 25
                                                                }, this),
                                                                r.q.topic ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                                    className: "text-[10px] text-zinc-500 bg-zinc-100 rounded-full px-2 py-0.5",
                                                                    children: r.q.topic
                                                                }, void 0, false, {
                                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                                    lineNumber: 802,
                                                                    columnNumber: 27
                                                                }, this) : null
                                                            ]
                                                        }, void 0, true, {
                                                            fileName: "[project]/app/mock-interview/page.tsx",
                                                            lineNumber: 789,
                                                            columnNumber: 23
                                                        }, this),
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                            className: "text-[13px] font-medium text-zinc-900 mt-1.5 leading-snug",
                                                            children: r.q.question
                                                        }, void 0, false, {
                                                            fileName: "[project]/app/mock-interview/page.tsx",
                                                            lineNumber: 807,
                                                            columnNumber: 23
                                                        }, this),
                                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                            className: "text-[11px] text-zinc-400 mt-1 leading-relaxed",
                                                            children: [
                                                                "你的回答：",
                                                                r.answer.slice(0, 80),
                                                                r.answer.length > 80 ? "…" : ""
                                                            ]
                                                        }, void 0, true, {
                                                            fileName: "[project]/app/mock-interview/page.tsx",
                                                            lineNumber: 810,
                                                            columnNumber: 23
                                                        }, this),
                                                        r.judge.reason ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                                            className: "text-[12px] text-zinc-500 bg-zinc-50 rounded-lg px-2.5 py-1.5 mt-1.5 leading-relaxed",
                                                            children: [
                                                                "💡 ",
                                                                r.judge.reason
                                                            ]
                                                        }, void 0, true, {
                                                            fileName: "[project]/app/mock-interview/page.tsx",
                                                            lineNumber: 814,
                                                            columnNumber: 25
                                                        }, this) : null
                                                    ]
                                                }, i, true, {
                                                    fileName: "[project]/app/mock-interview/page.tsx",
                                                    lineNumber: 788,
                                                    columnNumber: 21
                                                }, this))
                                        }, void 0, false, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 786,
                                            columnNumber: 17
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/app/mock-interview/page.tsx",
                                    lineNumber: 784,
                                    columnNumber: 15
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "flex gap-3 pb-4",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("a", {
                                            href: "/",
                                            className: "h-12 flex-1 rounded-xl border border-zinc-300 text-sm text-zinc-600 hover:bg-zinc-50 flex items-center justify-center transition-all",
                                            children: "回聊天"
                                        }, void 0, false, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 824,
                                            columnNumber: 17
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                            onClick: again,
                                            className: "h-12 flex-1 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-all active:scale-[0.99]",
                                            children: "再来一场"
                                        }, void 0, false, {
                                            fileName: "[project]/app/mock-interview/page.tsx",
                                            lineNumber: 830,
                                            columnNumber: 17
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/app/mock-interview/page.tsx",
                                    lineNumber: 823,
                                    columnNumber: 15
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/app/mock-interview/page.tsx",
                            lineNumber: 718,
                            columnNumber: 13
                        }, this) : null
                    ]
                }, void 0, true, {
                    fileName: "[project]/app/mock-interview/page.tsx",
                    lineNumber: 369,
                    columnNumber: 9
                }, this)
            ]
        }, void 0, true, {
            fileName: "[project]/app/mock-interview/page.tsx",
            lineNumber: 332,
            columnNumber: 7
        }, this)
    }, void 0, false, {
        fileName: "[project]/app/mock-interview/page.tsx",
        lineNumber: 331,
        columnNumber: 5
    }, this);
}
// ── 资料行：简历 / JD 各一行（状态 + 摘要 + 上传按钮）──
function DocRow({ label, doc, uploading, onPick }) {
    const missing = label === "简历" ? "简历深挖" : "JD 能力";
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "flex items-start gap-2",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                className: "text-[11px] text-zinc-500 w-8 mt-0.5",
                children: label
            }, void 0, false, {
                fileName: "[project]/app/mock-interview/page.tsx",
                lineNumber: 860,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "flex-1 min-w-0",
                children: [
                    doc?.provided ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        className: "inline-block text-[11px] text-emerald-600 bg-emerald-50 border border-emerald-100 rounded-full px-2 py-0.5",
                        children: [
                            "✓ ",
                            doc.filename,
                            " · ",
                            doc.updated_at?.slice(5, 16).replace("T", " ")
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/mock-interview/page.tsx",
                        lineNumber: 863,
                        columnNumber: 11
                    }, this) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        className: "inline-block text-[11px] text-amber-600 bg-amber-50 border border-amber-100 rounded-full px-2 py-0.5",
                        children: [
                            "✕ 未提供 · 面试将跳过",
                            missing,
                            "章节"
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/mock-interview/page.tsx",
                        lineNumber: 867,
                        columnNumber: 11
                    }, this),
                    doc?.provided && doc.summary ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        className: "text-[11px] text-zinc-400 mt-1 leading-relaxed truncate",
                        children: [
                            doc.summary,
                            "…"
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/mock-interview/page.tsx",
                        lineNumber: 872,
                        columnNumber: 11
                    }, this) : null
                ]
            }, void 0, true, {
                fileName: "[project]/app/mock-interview/page.tsx",
                lineNumber: 861,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                className: "shrink-0 text-[11px] text-indigo-600 border border-indigo-200 rounded-lg px-2.5 py-1 hover:bg-indigo-50 cursor-pointer transition-colors",
                children: [
                    uploading ? "上传中…" : "上传",
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                        type: "file",
                        accept: ".pdf,.txt,.md,.markdown,application/pdf,text/plain,text/markdown",
                        className: "hidden",
                        onChange: onPick,
                        disabled: uploading
                    }, void 0, false, {
                        fileName: "[project]/app/mock-interview/page.tsx",
                        lineNumber: 877,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/mock-interview/page.tsx",
                lineNumber: 875,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/app/mock-interview/page.tsx",
        lineNumber: 859,
        columnNumber: 5
    }, this);
}
}),
];

//# sourceMappingURL=_0jgpght._.js.map