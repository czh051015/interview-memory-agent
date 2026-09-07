import type {
  ChatResponse,
  DashboardData,
  DecomposeResult,
  DiagnoseData,
  ExplainResult,
  GuidanceResult,
  InlineGold,
  KnowledgeItem,
  MockCompleteResponse,
  MockFollowupResponse,
  MockStartResponse,
  MockVerdictResponse,
  ParseResult,
  PracticeSubmit,
  ProfileResponse,
  RecordResponse,
  RemindData,
  WeakpointsData,
  WrongbookResult,
} from "./types";

// 相对路径：next.config.ts 的 rewrites 会把 /api/* 代理到 FastAPI（8000）
export async function sendMessage(message: string, space = "default"): Promise<ChatResponse> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, space }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

export async function decompose(rawText: string): Promise<DecomposeResult> {
  const res = await fetch("/api/decompose", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ raw_text: rawText }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "拆解失败" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

export async function recordItems(
  items: KnowledgeItem[],
  space = "default",
): Promise<RecordResponse> {
  const res = await fetch("/api/record", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items, space }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "入库失败" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

// ── 模拟面试 ──
async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export function startMockInterview(n = 5, space = "default"): Promise<MockStartResponse> {
  return post<MockStartResponse>("/api/mock/start", { n, space });
}

export function getMockVerdict(question: string, answer: string): Promise<MockVerdictResponse> {
  return post<MockVerdictResponse>("/api/mock/verdict", { question, answer });
}

export function getMockFollowup(
  question: string,
  points: string[],
  answer: string,
  roundNum: number,
): Promise<MockFollowupResponse> {
  return post<MockFollowupResponse>("/api/mock/followup", {
    question,
    points,
    answer,
    round_num: roundNum,
  });
}

export function completeMockInterview(
  results: Array<{
    question_id: string;
    question: string;
    verdict: "pass" | "partial" | "fail";
    answer: string;
    source?: string;
    topic?: string;
    points?: string[];
    misses?: string[];
    reason?: string;
  }>,
  space = "default",
): Promise<MockCompleteResponse> {
  return post<MockCompleteResponse>("/api/mock/complete", { results, space });
}

// ── 错题本 ──
export async function fetchItems(params: {
  status?: string;
  space?: string;
  category?: string;
  source?: string;
  limit?: number;
} = {}): Promise<KnowledgeItem[]> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") qs.set(k, String(v));
  }
  const res = await fetch(`/api/items?${qs.toString()}`, { cache: "no-store" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function searchItems(q: string, space = "default", limit = 20): Promise<KnowledgeItem[]> {
  const qs = new URLSearchParams({ q, space, limit: String(limit) });
  const res = await fetch(`/api/search?${qs.toString()}`, { cache: "no-store" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "检索失败" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function markItemStatus(
  itemId: string,
  status: "fail" | "partial" | "pass",
  reason = "",
): Promise<KnowledgeItem> {
  return post<KnowledgeItem>(`/api/items/${itemId}/status`, { status, reason });
}

export async function editItem(
  itemId: string,
  patch: { question?: string; topic?: string; answer?: string },
  space = "default",
): Promise<KnowledgeItem> {
  return post<KnowledgeItem>(`/api/items/${itemId}`, { ...patch, space });
}

export async function deleteItem(
  itemId: string,
  space = "default",
): Promise<{ ok: boolean; deleted: boolean }> {
  const res = await fetch(`/api/items/${itemId}?space=${encodeURIComponent(space)}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "删除失败" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Dashboard ──
export async function fetchDashboard(space = "default"): Promise<DashboardData> {
  const res = await fetch(`/api/dashboard?space=${encodeURIComponent(space)}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── 简历资料（模拟面试「简历深挖」数据源，per-space）──
export async function fetchProfile(space = "default"): Promise<ProfileResponse> {
  const res = await fetch(`/api/profile?space=${encodeURIComponent(space)}`, { cache: "no-store" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function uploadResume(
  file: File,
  space = "default",
): Promise<{ kind: string; filename: string; pages: number; chars: number }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`/api/profile/resume?space=${encodeURIComponent(space)}`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "上传失败" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function uploadJd(
  file: File,
  space = "default",
): Promise<{ kind: string; filename: string; pages: number; chars: number }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`/api/profile/jd?space=${encodeURIComponent(space)}`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "上传失败" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── 申论工作台（docs/20 Step B，照抄 post/get 模式）──
async function get<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── 申论单题上传 · 双模式评分（docs/38 §6：gold 带 question_id → 门禁，缺省 → 示证）──
// 前端无状态：每次调用自带 gold（内联采分点+材料），后端 _resolve 优先用 gold。

// 文字版标准答案 → 采分点（docs/24 §5.1）：纯文字才走此接口（LLM 拆解），
// JSON 模式不调用。返回的 points 拼 InlineGold 后走原 scorePractice 评分链路。
export function parsePractice(
  ctx: { question: string; material: string },
  standard_answer: string,
): Promise<ParseResult> {
  return post<ParseResult>("/api/shenlun/practice/parse", {
    standard_answer,
    question: ctx.question,
    material: ctx.material,
    max_score: 0,
  });
}

export function scorePractice(gold: InlineGold, answer: string): Promise<PracticeSubmit> {
  return post<PracticeSubmit>("/api/shenlun/practice/submit", { gold, answer });
}

export function getGuidance(
  gold: InlineGold,
  answer: string,
  point_id: string,
): Promise<GuidanceResult> {
  return post<GuidanceResult>("/api/shenlun/practice/guidance", { gold, answer, point_id });
}

export function getExplain(
  gold: InlineGold,
  answer: string,
  point_id: string,
): Promise<ExplainResult> {
  return post<ExplainResult>("/api/shenlun/practice/explain", { gold, answer, point_id });
}

// 错题本快照（docs/22 §3.6）：cause_type/cause 回传用户看到的徽章口径句
// （黄行 = 漏答：原因即 verdict.reason，由前端按 status 映射，无 AI demo 依赖）
export function addWrongbook(
  gold: InlineGold,
  answer: string,
  point_id: string,
  cause_type: string,
  cause: string,
): Promise<WrongbookResult> {
  return post<WrongbookResult>("/api/shenlun/wrongbook", {
    gold,
    answer,
    point_id,
    answer_snippet: "",
    demo: "",
    cause_type,
    cause,
  });
}

export function getRemind(): Promise<RemindData> {
  return get<RemindData>("/api/shenlun/remind");
}

export function getWeakpoints(state?: string): Promise<WeakpointsData> {
  const qs = state ? `?state=${encodeURIComponent(state)}` : "";
  return get<WeakpointsData>(`/api/shenlun/weakpoints${qs}`);
}

export function getDiagnose(): Promise<DiagnoseData> {
  return get<DiagnoseData>("/api/diagnose");
}
