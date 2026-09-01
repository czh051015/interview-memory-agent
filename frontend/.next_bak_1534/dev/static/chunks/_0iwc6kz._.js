(globalThis["TURBOPACK"] || (globalThis["TURBOPACK"] = [])).push([typeof document === "object" ? document.currentScript : undefined,
"[project]/lib/api.ts [app-client] (ecmascript)", ((__turbopack_context__) => {
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
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/app/items/page.tsx [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "default",
    ()=>ItemsPage
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/compiled/react/jsx-dev-runtime.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/compiled/react/index.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/lib/api.ts [app-client] (ecmascript)");
;
var _s = __turbopack_context__.k.signature();
"use client";
;
;
const TABS = [
    {
        key: "",
        label: "全部"
    },
    {
        key: "fail",
        label: "❌ 错题"
    },
    {
        key: "partial",
        label: "⚠️ 半会"
    },
    {
        key: "unknown",
        label: "📚 知识库"
    },
    {
        key: "pass",
        label: "✅ 已会"
    }
];
const STATUS_BADGE = {
    fail: "bg-red-50 text-red-600 border-red-200",
    partial: "bg-amber-50 text-amber-600 border-amber-200",
    pass: "bg-emerald-50 text-emerald-600 border-emerald-200",
    unknown: "bg-zinc-100 text-zinc-500 border-zinc-200"
};
const STATUS_LABEL = {
    fail: "没答上",
    partial: "答一半",
    pass: "答上了",
    unknown: "待标注"
};
const MARK_OPTIONS = [
    {
        key: "fail",
        label: "不会"
    },
    {
        key: "partial",
        label: "一半"
    },
    {
        key: "pass",
        label: "会了"
    }
];
function daysSince(iso) {
    if (!iso) return null;
    const d = (Date.now() - new Date(iso).getTime()) / 86400000;
    return Math.max(0, Math.floor(d));
}
function ItemsPage() {
    _s();
    const [tab, setTab] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])("fail");
    const [items, setItems] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])([]);
    const [loading, setLoading] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])(true);
    const [error, setError] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])("");
    const [markingId, setMarkingId] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])(null);
    const [editingId, setEditingId] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])(null);
    const [draft, setDraft] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])({
        question: "",
        topic: "",
        answer: ""
    });
    const [saving, setSaving] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])(false);
    const [query, setQuery] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])("");
    const [searching, setSearching] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])(false);
    const [searchResults, setSearchResults] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])(null);
    const space = ()=>localStorage.getItem("offerloop.space") || "default";
    const load = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useCallback"])({
        "ItemsPage.useCallback[load]": async (t)=>{
            setLoading(true);
            setError("");
            try {
                const data = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["fetchItems"])({
                    status: t,
                    space: space(),
                    limit: 300
                });
                setItems(data);
            } catch (e) {
                setError(e instanceof Error ? e.message : "加载失败");
            } finally{
                setLoading(false);
            }
        }
    }["ItemsPage.useCallback[load]"], []);
    async function handleSearch() {
        const q = query.trim();
        if (!q || searching) return;
        setSearching(true);
        setError("");
        try {
            setSearchResults(await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["searchItems"])(q, space()));
        } catch (e) {
            setError(e instanceof Error ? e.message : "检索失败");
        } finally{
            setSearching(false);
        }
    }
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useEffect"])({
        "ItemsPage.useEffect": ()=>{
            load(tab);
        }
    }["ItemsPage.useEffect"], [
        tab,
        load
    ]);
    async function handleMark(it, status) {
        if (markingId) return;
        setMarkingId(it.id);
        try {
            const updated = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["markItemStatus"])(it.id, status);
            setItems((prev)=>prev.map((x)=>x.id === updated.id ? updated : x));
        } catch (e) {
            alert(e instanceof Error ? e.message : "标注失败");
        } finally{
            setMarkingId(null);
        }
    }
    function startEdit(it) {
        setEditingId(it.id);
        setDraft({
            question: it.question,
            topic: it.topic,
            answer: it.answer
        });
    }
    async function handleSaveEdit(it) {
        if (!draft.question.trim() || saving) return;
        setSaving(true);
        setError("");
        try {
            const updated = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["editItem"])(it.id, {
                question: draft.question.trim(),
                topic: draft.topic.trim(),
                answer: draft.answer.trim()
            }, space());
            setItems((prev)=>prev.map((x)=>x.id === updated.id ? updated : x));
            setEditingId(null);
        } catch (e) {
            alert(e instanceof Error ? e.message : "保存失败");
        } finally{
            setSaving(false);
        }
    }
    async function handleDelete(it) {
        if (!window.confirm(`确定删除这道题？\n\n${it.question.slice(0, 50)}`)) return;
        try {
            await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["deleteItem"])(it.id, space());
            setItems((prev)=>prev.filter((x)=>x.id !== it.id));
        } catch (e) {
            alert(e instanceof Error ? e.message : "删除失败");
        }
    }
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "min-h-dvh bg-zinc-50/50",
        children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
            className: "max-w-3xl mx-auto w-full bg-white min-h-dvh shadow-sm border-x border-zinc-200",
            children: [
                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                    className: "flex items-center gap-3 px-5 py-3 border-b border-zinc-200 bg-white shrink-0 sticky top-0 z-10",
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("a", {
                            href: "/",
                            className: "w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white text-sm font-bold hover:bg-indigo-700 transition-colors",
                            children: "O"
                        }, void 0, false, {
                            fileName: "[project]/app/items/page.tsx",
                            lineNumber: 141,
                            columnNumber: 11
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("h1", {
                                    className: "text-sm font-semibold text-zinc-900",
                                    children: "错题本"
                                }, void 0, false, {
                                    fileName: "[project]/app/items/page.tsx",
                                    lineNumber: 148,
                                    columnNumber: 13
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                    className: "text-[11px] text-zinc-500",
                                    children: "列表按遗忘程度排序，点按钮直接标注"
                                }, void 0, false, {
                                    fileName: "[project]/app/items/page.tsx",
                                    lineNumber: 149,
                                    columnNumber: 13
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/app/items/page.tsx",
                            lineNumber: 147,
                            columnNumber: 11
                        }, this)
                    ]
                }, void 0, true, {
                    fileName: "[project]/app/items/page.tsx",
                    lineNumber: 140,
                    columnNumber: 9
                }, this),
                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                    className: "px-5 pt-4",
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "flex gap-2",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                    value: query,
                                    onChange: (e)=>setQuery(e.target.value),
                                    onKeyDown: (e)=>e.key === "Enter" && handleSearch(),
                                    placeholder: "语义检索：如「RAG 相关的题」",
                                    className: "flex-1 rounded-lg border border-zinc-300 bg-zinc-50 px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:bg-white focus:ring-1 focus:ring-indigo-500/20 transition-all"
                                }, void 0, false, {
                                    fileName: "[project]/app/items/page.tsx",
                                    lineNumber: 156,
                                    columnNumber: 13
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                    onClick: handleSearch,
                                    disabled: !query.trim() || searching,
                                    className: "shrink-0 px-4 rounded-lg bg-indigo-600 text-white text-xs font-medium hover:bg-indigo-700 disabled:opacity-40 transition-all",
                                    children: searching ? "检索中…" : "检索"
                                }, void 0, false, {
                                    fileName: "[project]/app/items/page.tsx",
                                    lineNumber: 163,
                                    columnNumber: 13
                                }, this),
                                searchResults !== null ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                    onClick: ()=>{
                                        setSearchResults(null);
                                        setQuery("");
                                    },
                                    className: "shrink-0 px-3 rounded-lg border border-zinc-300 text-xs text-zinc-500 hover:bg-zinc-50 transition-colors",
                                    children: "清除"
                                }, void 0, false, {
                                    fileName: "[project]/app/items/page.tsx",
                                    lineNumber: 171,
                                    columnNumber: 15
                                }, this) : null
                            ]
                        }, void 0, true, {
                            fileName: "[project]/app/items/page.tsx",
                            lineNumber: 155,
                            columnNumber: 11
                        }, this),
                        searchResults !== null ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                            className: "text-[11px] text-zinc-400 mt-1.5",
                            children: [
                                "检索「",
                                query,
                                "」：",
                                searchResults.length,
                                " 条命中（按语义相似度）"
                            ]
                        }, void 0, true, {
                            fileName: "[project]/app/items/page.tsx",
                            lineNumber: 183,
                            columnNumber: 13
                        }, this) : null
                    ]
                }, void 0, true, {
                    fileName: "[project]/app/items/page.tsx",
                    lineNumber: 154,
                    columnNumber: 9
                }, this),
                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                    className: "px-5 pt-4 flex gap-1.5 flex-wrap",
                    children: TABS.map((t)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                            onClick: ()=>setTab(t.key),
                            className: `px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${tab === t.key ? "bg-indigo-600 text-white shadow-sm" : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200"}`,
                            children: t.label
                        }, t.key, false, {
                            fileName: "[project]/app/items/page.tsx",
                            lineNumber: 192,
                            columnNumber: 13
                        }, this))
                }, void 0, false, {
                    fileName: "[project]/app/items/page.tsx",
                    lineNumber: 190,
                    columnNumber: 9
                }, this),
                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                    className: "px-5 py-4 space-y-2.5",
                    children: loading ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        className: "text-xs text-zinc-400 text-center py-10",
                        children: "加载中…"
                    }, void 0, false, {
                        fileName: "[project]/app/items/page.tsx",
                        lineNumber: 209,
                        columnNumber: 13
                    }, this) : error ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600",
                        children: error
                    }, void 0, false, {
                        fileName: "[project]/app/items/page.tsx",
                        lineNumber: 211,
                        columnNumber: 13
                    }, this) : (searchResults ?? items).length === 0 ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "text-center py-12 space-y-3",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                className: "text-sm text-zinc-500",
                                children: searchResults !== null ? "没有检索到相关题目" : tab === "fail" ? "错题本是空的——先去记几道题" : "这个分类下还没有题"
                            }, void 0, false, {
                                fileName: "[project]/app/items/page.tsx",
                                lineNumber: 216,
                                columnNumber: 15
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("a", {
                                href: "/record",
                                className: "inline-block h-10 px-5 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-all",
                                children: "＋ 去记错题"
                            }, void 0, false, {
                                fileName: "[project]/app/items/page.tsx",
                                lineNumber: 223,
                                columnNumber: 15
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/items/page.tsx",
                        lineNumber: 215,
                        columnNumber: 13
                    }, this) : (searchResults ?? items).map((it)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                            className: "rounded-xl border border-zinc-200 bg-white p-3.5 space-y-2.5 shadow-sm",
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "flex items-start gap-2",
                                    children: [
                                        editingId === it.id ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                            value: draft.question,
                                            onChange: (e)=>setDraft((d)=>({
                                                        ...d,
                                                        question: e.target.value
                                                    })),
                                            className: "flex-1 rounded-lg border border-indigo-300 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/20",
                                            placeholder: "题目",
                                            autoFocus: true
                                        }, void 0, false, {
                                            fileName: "[project]/app/items/page.tsx",
                                            lineNumber: 238,
                                            columnNumber: 21
                                        }, this) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                            className: "flex-1 text-sm font-medium text-zinc-900 leading-snug",
                                            children: it.question
                                        }, void 0, false, {
                                            fileName: "[project]/app/items/page.tsx",
                                            lineNumber: 246,
                                            columnNumber: 21
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                            className: `shrink-0 text-[10px] px-2 py-0.5 rounded-full border ${STATUS_BADGE[it.status] ?? STATUS_BADGE.unknown}`,
                                            children: STATUS_LABEL[it.status] ?? it.status
                                        }, void 0, false, {
                                            fileName: "[project]/app/items/page.tsx",
                                            lineNumber: 250,
                                            columnNumber: 19
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/app/items/page.tsx",
                                    lineNumber: 236,
                                    columnNumber: 17
                                }, this),
                                editingId === it.id ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "space-y-2 rounded-lg border border-indigo-200 bg-indigo-50/40 p-2.5",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                                            className: "block",
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: "text-[10px] text-zinc-400 block mb-0.5",
                                                    children: "主题"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/items/page.tsx",
                                                    lineNumber: 262,
                                                    columnNumber: 23
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                                    value: draft.topic,
                                                    onChange: (e)=>setDraft((d)=>({
                                                                ...d,
                                                                topic: e.target.value
                                                            })),
                                                    className: "w-full rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-xs outline-none focus:border-indigo-500",
                                                    placeholder: "如 RAG / Agent"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/items/page.tsx",
                                                    lineNumber: 263,
                                                    columnNumber: 23
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/items/page.tsx",
                                            lineNumber: 261,
                                            columnNumber: 21
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                                            className: "block",
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: "text-[10px] text-zinc-400 block mb-0.5",
                                                    children: "参考答案 / 面试官反馈（可改）"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/items/page.tsx",
                                                    lineNumber: 271,
                                                    columnNumber: 23
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("textarea", {
                                                    value: draft.answer,
                                                    onChange: (e)=>setDraft((d)=>({
                                                                ...d,
                                                                answer: e.target.value
                                                            })),
                                                    rows: 4,
                                                    className: "w-full rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-xs leading-relaxed outline-none focus:border-indigo-500",
                                                    placeholder: "留空表示没有"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/items/page.tsx",
                                                    lineNumber: 274,
                                                    columnNumber: 23
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/items/page.tsx",
                                            lineNumber: 270,
                                            columnNumber: 21
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "flex gap-2",
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                    onClick: ()=>setEditingId(null),
                                                    disabled: saving,
                                                    className: "h-8 px-3 rounded-lg border border-zinc-300 text-xs text-zinc-600 hover:bg-zinc-50 disabled:opacity-40",
                                                    children: "取消"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/items/page.tsx",
                                                    lineNumber: 283,
                                                    columnNumber: 23
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                    onClick: ()=>handleSaveEdit(it),
                                                    disabled: !draft.question.trim() || saving,
                                                    className: "h-8 flex-1 rounded-lg bg-indigo-600 text-white text-xs font-medium hover:bg-indigo-700 disabled:opacity-40",
                                                    children: saving ? "保存中…" : "保存"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/items/page.tsx",
                                                    lineNumber: 290,
                                                    columnNumber: 23
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/items/page.tsx",
                                            lineNumber: 282,
                                            columnNumber: 21
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/app/items/page.tsx",
                                    lineNumber: 260,
                                    columnNumber: 19
                                }, this) : null,
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "flex flex-wrap items-center gap-1.5",
                                    children: [
                                        it.topic ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                            className: "text-[10px] text-indigo-600 bg-indigo-50 border border-indigo-100 rounded-full px-2 py-0.5",
                                            children: it.topic
                                        }, void 0, false, {
                                            fileName: "[project]/app/items/page.tsx",
                                            lineNumber: 303,
                                            columnNumber: 21
                                        }, this) : null,
                                        it.company ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                            className: "text-[10px] text-zinc-500 bg-zinc-100 rounded-full px-2 py-0.5",
                                            children: it.company
                                        }, void 0, false, {
                                            fileName: "[project]/app/items/page.tsx",
                                            lineNumber: 308,
                                            columnNumber: 21
                                        }, this) : null,
                                        it.round ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                            className: "text-[10px] text-zinc-400 rounded-full px-2 py-0.5",
                                            children: it.round
                                        }, void 0, false, {
                                            fileName: "[project]/app/items/page.tsx",
                                            lineNumber: 313,
                                            columnNumber: 21
                                        }, this) : null,
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                            className: "text-[10px] text-zinc-400 rounded-full px-2 py-0.5",
                                            children: [
                                                "掌握度 ",
                                                Math.round(it.mastery_score * 100),
                                                "%"
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/items/page.tsx",
                                            lineNumber: 317,
                                            columnNumber: 19
                                        }, this),
                                        it.similarity !== undefined && it.similarity > 0 ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                            className: "text-[10px] text-blue-600 bg-blue-50 border border-blue-100 rounded-full px-2 py-0.5",
                                            children: [
                                                "sim ",
                                                it.similarity.toFixed(2)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/items/page.tsx",
                                            lineNumber: 321,
                                            columnNumber: 21
                                        }, this) : null,
                                        daysSince(it.last_reviewed_at) !== null && it.status !== "pass" ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                            className: `text-[10px] rounded-full px-2 py-0.5 ${daysSince(it.last_reviewed_at) >= 7 ? "text-red-500 bg-red-50" : "text-zinc-400"}`,
                                            children: daysSince(it.last_reviewed_at) >= 7 ? `${daysSince(it.last_reviewed_at)} 天没复习` : "最近复习过"
                                        }, void 0, false, {
                                            fileName: "[project]/app/items/page.tsx",
                                            lineNumber: 326,
                                            columnNumber: 21
                                        }, this) : null
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/app/items/page.tsx",
                                    lineNumber: 301,
                                    columnNumber: 17
                                }, this),
                                it.user_note ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                    className: "text-xs text-zinc-500 leading-relaxed bg-zinc-50 rounded-lg px-2.5 py-1.5",
                                    children: it.user_note
                                }, void 0, false, {
                                    fileName: "[project]/app/items/page.tsx",
                                    lineNumber: 341,
                                    columnNumber: 19
                                }, this) : null,
                                it.answer ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("details", {
                                    className: "group rounded-lg border border-indigo-100 bg-indigo-50/40",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("summary", {
                                            className: "flex items-center gap-1 px-2.5 py-1.5 text-[11px] text-indigo-600 cursor-pointer select-none list-none",
                                            children: [
                                                "参考答案 / 面试官反馈",
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: "ml-auto text-[10px] text-zinc-400 group-open:hidden",
                                                    children: "展开"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/items/page.tsx",
                                                    lineNumber: 350,
                                                    columnNumber: 23
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                                    className: "ml-auto text-[10px] text-zinc-400 hidden group-open:inline",
                                                    children: "收起"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/items/page.tsx",
                                                    lineNumber: 351,
                                                    columnNumber: 23
                                                }, this)
                                            ]
                                        }, void 0, true, {
                                            fileName: "[project]/app/items/page.tsx",
                                            lineNumber: 348,
                                            columnNumber: 21
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                            className: "px-2.5 pb-2.5 text-xs text-zinc-600 leading-relaxed whitespace-pre-wrap",
                                            children: it.answer
                                        }, void 0, false, {
                                            fileName: "[project]/app/items/page.tsx",
                                            lineNumber: 353,
                                            columnNumber: 21
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/app/items/page.tsx",
                                    lineNumber: 347,
                                    columnNumber: 19
                                }, this) : null,
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "flex gap-1.5",
                                    children: [
                                        MARK_OPTIONS.map((m)=>{
                                            const active = it.status === m.key;
                                            return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                onClick: ()=>handleMark(it, m.key),
                                                disabled: markingId === it.id || editingId === it.id,
                                                className: `flex-1 h-8 rounded-lg text-xs font-medium border transition-all disabled:opacity-50 ${active ? m.key === "fail" ? "bg-red-500 border-red-500 text-white" : m.key === "partial" ? "bg-amber-500 border-amber-500 text-white" : "bg-emerald-500 border-emerald-500 text-white" : "border-zinc-200 text-zinc-500 hover:bg-zinc-50"}`,
                                                children: markingId === it.id ? "…" : m.label
                                            }, m.key, false, {
                                                fileName: "[project]/app/items/page.tsx",
                                                lineNumber: 364,
                                                columnNumber: 23
                                            }, this);
                                        }),
                                        editingId !== it.id ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["Fragment"], {
                                            children: [
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                    onClick: ()=>startEdit(it),
                                                    className: "shrink-0 h-8 px-2.5 rounded-lg border border-zinc-200 text-[11px] text-zinc-500 hover:bg-zinc-50 transition-colors",
                                                    children: "编辑"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/items/page.tsx",
                                                    lineNumber: 384,
                                                    columnNumber: 23
                                                }, this),
                                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                                    onClick: ()=>handleDelete(it),
                                                    className: "shrink-0 h-8 px-2.5 rounded-lg border border-zinc-200 text-[11px] text-red-500 hover:bg-red-50 transition-colors",
                                                    children: "删除"
                                                }, void 0, false, {
                                                    fileName: "[project]/app/items/page.tsx",
                                                    lineNumber: 390,
                                                    columnNumber: 23
                                                }, this)
                                            ]
                                        }, void 0, true) : null
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/app/items/page.tsx",
                                    lineNumber: 360,
                                    columnNumber: 17
                                }, this)
                            ]
                        }, it.id, true, {
                            fileName: "[project]/app/items/page.tsx",
                            lineNumber: 232,
                            columnNumber: 15
                        }, this))
                }, void 0, false, {
                    fileName: "[project]/app/items/page.tsx",
                    lineNumber: 207,
                    columnNumber: 9
                }, this)
            ]
        }, void 0, true, {
            fileName: "[project]/app/items/page.tsx",
            lineNumber: 138,
            columnNumber: 7
        }, this)
    }, void 0, false, {
        fileName: "[project]/app/items/page.tsx",
        lineNumber: 137,
        columnNumber: 5
    }, this);
}
_s(ItemsPage, "altR3ke+FzJ7WdNWZIwCg8x7/78=");
_c = ItemsPage;
var _c;
__turbopack_context__.k.register(_c, "ItemsPage");
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/node_modules/next/dist/compiled/react/cjs/react-jsx-dev-runtime.development.js [app-client] (ecmascript)", ((__turbopack_context__, module, exports) => {
"use strict";

var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$polyfills$2f$process$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = /*#__PURE__*/ __turbopack_context__.i("[project]/node_modules/next/dist/build/polyfills/process.js [app-client] (ecmascript)");
/**
 * @license React
 * react-jsx-dev-runtime.development.js
 *
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */ "use strict";
"production" !== ("TURBOPACK compile-time value", "development") && function() {
    function getComponentNameFromType(type) {
        if (null == type) return null;
        if ("function" === typeof type) return type.$$typeof === REACT_CLIENT_REFERENCE ? null : type.displayName || type.name || null;
        if ("string" === typeof type) return type;
        switch(type){
            case REACT_FRAGMENT_TYPE:
                return "Fragment";
            case REACT_PROFILER_TYPE:
                return "Profiler";
            case REACT_STRICT_MODE_TYPE:
                return "StrictMode";
            case REACT_SUSPENSE_TYPE:
                return "Suspense";
            case REACT_SUSPENSE_LIST_TYPE:
                return "SuspenseList";
            case REACT_ACTIVITY_TYPE:
                return "Activity";
            case REACT_VIEW_TRANSITION_TYPE:
                return "ViewTransition";
        }
        if ("object" === typeof type) switch("number" === typeof type.tag && console.error("Received an unexpected object in getComponentNameFromType(). This is likely a bug in React. Please file an issue."), type.$$typeof){
            case REACT_PORTAL_TYPE:
                return "Portal";
            case REACT_CONTEXT_TYPE:
                return type.displayName || "Context";
            case REACT_CONSUMER_TYPE:
                return (type._context.displayName || "Context") + ".Consumer";
            case REACT_FORWARD_REF_TYPE:
                var innerType = type.render;
                type = type.displayName;
                type || (type = innerType.displayName || innerType.name || "", type = "" !== type ? "ForwardRef(" + type + ")" : "ForwardRef");
                return type;
            case REACT_MEMO_TYPE:
                return innerType = type.displayName || null, null !== innerType ? innerType : getComponentNameFromType(type.type) || "Memo";
            case REACT_LAZY_TYPE:
                innerType = type._payload;
                type = type._init;
                try {
                    return getComponentNameFromType(type(innerType));
                } catch (x) {}
        }
        return null;
    }
    function testStringCoercion(value) {
        return "" + value;
    }
    function checkKeyStringCoercion(value) {
        try {
            testStringCoercion(value);
            var JSCompiler_inline_result = !1;
        } catch (e) {
            JSCompiler_inline_result = !0;
        }
        if (JSCompiler_inline_result) {
            JSCompiler_inline_result = console;
            var JSCompiler_temp_const = JSCompiler_inline_result.error;
            var JSCompiler_inline_result$jscomp$0 = "function" === typeof Symbol && Symbol.toStringTag && value[Symbol.toStringTag] || value.constructor.name || "Object";
            JSCompiler_temp_const.call(JSCompiler_inline_result, "The provided key is an unsupported type %s. This value must be coerced to a string before using it here.", JSCompiler_inline_result$jscomp$0);
            return testStringCoercion(value);
        }
    }
    function getTaskName(type) {
        if (type === REACT_FRAGMENT_TYPE) return "<>";
        if ("object" === typeof type && null !== type && type.$$typeof === REACT_LAZY_TYPE) return "<...>";
        try {
            var name = getComponentNameFromType(type);
            return name ? "<" + name + ">" : "<...>";
        } catch (x) {
            return "<...>";
        }
    }
    function getOwner() {
        var dispatcher = ReactSharedInternals.A;
        return null === dispatcher ? null : dispatcher.getOwner();
    }
    function UnknownOwner() {
        return Error("react-stack-top-frame");
    }
    function hasValidKey(config) {
        if (hasOwnProperty.call(config, "key")) {
            var getter = Object.getOwnPropertyDescriptor(config, "key").get;
            if (getter && getter.isReactWarning) return !1;
        }
        return void 0 !== config.key;
    }
    function defineKeyPropWarningGetter(props, displayName) {
        function warnAboutAccessingKey() {
            specialPropKeyWarningShown || (specialPropKeyWarningShown = !0, console.error("%s: `key` is not a prop. Trying to access it will result in `undefined` being returned. If you need to access the same value within the child component, you should pass it as a different prop. (https://react.dev/link/special-props)", displayName));
        }
        warnAboutAccessingKey.isReactWarning = !0;
        Object.defineProperty(props, "key", {
            get: warnAboutAccessingKey,
            configurable: !0
        });
    }
    function elementRefGetterWithDeprecationWarning() {
        var componentName = getComponentNameFromType(this.type);
        didWarnAboutElementRef[componentName] || (didWarnAboutElementRef[componentName] = !0, console.error("Accessing element.ref was removed in React 19. ref is now a regular prop. It will be removed from the JSX Element type in a future release."));
        componentName = this.props.ref;
        return void 0 !== componentName ? componentName : null;
    }
    function ReactElement(type, key, props, owner, debugStack, debugTask) {
        var refProp = props.ref;
        type = {
            $$typeof: REACT_ELEMENT_TYPE,
            type: type,
            key: key,
            props: props,
            _owner: owner
        };
        null !== (void 0 !== refProp ? refProp : null) ? Object.defineProperty(type, "ref", {
            enumerable: !1,
            get: elementRefGetterWithDeprecationWarning
        }) : Object.defineProperty(type, "ref", {
            enumerable: !1,
            value: null
        });
        type._store = {};
        Object.defineProperty(type._store, "validated", {
            configurable: !1,
            enumerable: !1,
            writable: !0,
            value: 0
        });
        Object.defineProperty(type, "_debugInfo", {
            configurable: !1,
            enumerable: !1,
            writable: !0,
            value: null
        });
        Object.defineProperty(type, "_debugStack", {
            configurable: !1,
            enumerable: !1,
            writable: !0,
            value: debugStack
        });
        Object.defineProperty(type, "_debugTask", {
            configurable: !1,
            enumerable: !1,
            writable: !0,
            value: debugTask
        });
        Object.freeze && (Object.freeze(type.props), Object.freeze(type));
        return type;
    }
    function jsxDEVImpl(type, config, maybeKey, isStaticChildren, debugStack, debugTask) {
        var children = config.children;
        if (void 0 !== children) if (isStaticChildren) if (isArrayImpl(children)) {
            for(isStaticChildren = 0; isStaticChildren < children.length; isStaticChildren++)validateChildKeys(children[isStaticChildren]);
            Object.freeze && Object.freeze(children);
        } else console.error("React.jsx: Static children should always be an array. You are likely explicitly calling React.jsxs or React.jsxDEV. Use the Babel transform instead.");
        else validateChildKeys(children);
        if (hasOwnProperty.call(config, "key")) {
            children = getComponentNameFromType(type);
            var keys = Object.keys(config).filter(function(k) {
                return "key" !== k;
            });
            isStaticChildren = 0 < keys.length ? "{key: someKey, " + keys.join(": ..., ") + ": ...}" : "{key: someKey}";
            didWarnAboutKeySpread[children + isStaticChildren] || (keys = 0 < keys.length ? "{" + keys.join(": ..., ") + ": ...}" : "{}", console.error('A props object containing a "key" prop is being spread into JSX:\n  let props = %s;\n  <%s {...props} />\nReact keys must be passed directly to JSX without using spread:\n  let props = %s;\n  <%s key={someKey} {...props} />', isStaticChildren, children, keys, children), didWarnAboutKeySpread[children + isStaticChildren] = !0);
        }
        children = null;
        void 0 !== maybeKey && (checkKeyStringCoercion(maybeKey), children = "" + maybeKey);
        hasValidKey(config) && (checkKeyStringCoercion(config.key), children = "" + config.key);
        if ("key" in config) {
            maybeKey = {};
            for(var propName in config)"key" !== propName && (maybeKey[propName] = config[propName]);
        } else maybeKey = config;
        children && defineKeyPropWarningGetter(maybeKey, "function" === typeof type ? type.displayName || type.name || "Unknown" : type);
        return ReactElement(type, children, maybeKey, getOwner(), debugStack, debugTask);
    }
    function validateChildKeys(node) {
        isValidElement(node) ? node._store && (node._store.validated = 1) : "object" === typeof node && null !== node && node.$$typeof === REACT_LAZY_TYPE && ("fulfilled" === node._payload.status ? isValidElement(node._payload.value) && node._payload.value._store && (node._payload.value._store.validated = 1) : node._store && (node._store.validated = 1));
    }
    function isValidElement(object) {
        return "object" === typeof object && null !== object && object.$$typeof === REACT_ELEMENT_TYPE;
    }
    var React = __turbopack_context__.r("[project]/node_modules/next/dist/compiled/react/index.js [app-client] (ecmascript)"), REACT_ELEMENT_TYPE = Symbol.for("react.transitional.element"), REACT_PORTAL_TYPE = Symbol.for("react.portal"), REACT_FRAGMENT_TYPE = Symbol.for("react.fragment"), REACT_STRICT_MODE_TYPE = Symbol.for("react.strict_mode"), REACT_PROFILER_TYPE = Symbol.for("react.profiler"), REACT_CONSUMER_TYPE = Symbol.for("react.consumer"), REACT_CONTEXT_TYPE = Symbol.for("react.context"), REACT_FORWARD_REF_TYPE = Symbol.for("react.forward_ref"), REACT_SUSPENSE_TYPE = Symbol.for("react.suspense"), REACT_SUSPENSE_LIST_TYPE = Symbol.for("react.suspense_list"), REACT_MEMO_TYPE = Symbol.for("react.memo"), REACT_LAZY_TYPE = Symbol.for("react.lazy"), REACT_ACTIVITY_TYPE = Symbol.for("react.activity"), REACT_VIEW_TRANSITION_TYPE = Symbol.for("react.view_transition"), REACT_CLIENT_REFERENCE = Symbol.for("react.client.reference"), ReactSharedInternals = React.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE, hasOwnProperty = Object.prototype.hasOwnProperty, isArrayImpl = Array.isArray, createTask = console.createTask ? console.createTask : function() {
        return null;
    };
    React = {
        react_stack_bottom_frame: function(callStackForError) {
            return callStackForError();
        }
    };
    var specialPropKeyWarningShown;
    var didWarnAboutElementRef = {};
    var unknownOwnerDebugStack = React.react_stack_bottom_frame.bind(React, UnknownOwner)();
    var unknownOwnerDebugTask = createTask(getTaskName(UnknownOwner));
    var didWarnAboutKeySpread = {};
    exports.Fragment = REACT_FRAGMENT_TYPE;
    exports.jsxDEV = function(type, config, maybeKey, isStaticChildren) {
        var trackActualOwner = 1e4 > ReactSharedInternals.recentlyCreatedOwnerStacks++;
        if (trackActualOwner) {
            var previousStackTraceLimit = Error.stackTraceLimit;
            Error.stackTraceLimit = 10;
            var debugStackDEV = Error("react-stack-top-frame");
            Error.stackTraceLimit = previousStackTraceLimit;
        } else debugStackDEV = unknownOwnerDebugStack;
        return jsxDEVImpl(type, config, maybeKey, isStaticChildren, debugStackDEV, trackActualOwner ? createTask(getTaskName(type)) : unknownOwnerDebugTask);
    };
}();
}),
"[project]/node_modules/next/dist/compiled/react/jsx-dev-runtime.js [app-client] (ecmascript)", ((__turbopack_context__, module, exports) => {
"use strict";

var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$polyfills$2f$process$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = /*#__PURE__*/ __turbopack_context__.i("[project]/node_modules/next/dist/build/polyfills/process.js [app-client] (ecmascript)");
'use strict';
if ("TURBOPACK compile-time falsy", 0) //TURBOPACK unreachable
;
else {
    module.exports = __turbopack_context__.r("[project]/node_modules/next/dist/compiled/react/cjs/react-jsx-dev-runtime.development.js [app-client] (ecmascript)");
}
}),
]);

//# sourceMappingURL=_0iwc6kz._.js.map