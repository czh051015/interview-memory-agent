import type {
  ChatResponse,
  DashboardData,
  DecomposeResult,
  KnowledgeItem,
  MockCompleteResponse,
  MockFollowupResponse,
  MockStartResponse,
  MockVerdictResponse,
  ProfileResponse,
  RecordResponse,
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
