export interface ChatResponse {
  reply: string;
  intent: string;
  cards: unknown[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

// ── 记错题（与后端 src/cleaner/schema.py 对齐）──
export type ItemStatus = "fail" | "partial" | "pass" | "unknown";
export type ItemCategory = "knowledge" | "info";
export type ItemSource = "self_review" | "public_jingyan" | "mock_interview";

export interface KnowledgeItem {
  id: string;
  question: string;
  answer: string;
  question_type: string;
  topic: string;
  category: ItemCategory;
  company: string;
  role: string;
  round: string;
  date: string;
  space: string;
  status: ItemStatus;
  history: Array<{ time: string; from: string | null; to: string; reason: string; actor: string }>;
  user_note: string;
  mastery_score: number;
  last_reviewed_at: string | null;
  review_count: number;
  source: ItemSource;
  behavior_tags: string[];
  created_at: string;
  similarity?: number; // 语义检索命中相似度（cosine，检索接口返回）
}

export interface DecomposeResult {
  company: string;
  role: string;
  round: string;
  date: string;
  items: KnowledgeItem[];
  raw_text: string;
  unknown_count: number;
  total_count: number;
  suspected_fail: boolean;
}

export interface RecordResponse {
  stored: number;
  space: string;
}

// ── 模拟面试（与后端 app/api/mock.py 对齐）──
export interface MockQuestion {
  id: string;
  question: string;
  topic: string;
  status: ItemStatus;
  mastery_score: number;
  gap: number | null; // 1 - effective_mastery，越大越该复习（错题来源有值，现场新题 null）
  section: string; // 章节名：自我介绍/项目深挖/技术验证/行为面/动机面
  source: string; // generic/resume/jd/weak/behavior/motivation
  item_id: string | null;
}

export interface MockStartResponse {
  questions: MockQuestion[];
  focus_topics: string[]; // 画像薄弱主题（setup 页展示"本场重点验证"）
}

export interface MockVerdictResponse {
  points: string[]; // 应该答到的要点
  misses: string[]; // 你漏掉的/差距
  suggested: "pass" | "partial" | "fail";
  reason: string;
}

export interface MockFollowupResponse {
  need_followup: boolean;
  followup_question: string;
  reason: string;
  performance: "pass" | "partial" | "fail";
}

export interface MockResult {
  question_id: string;
  question: string;
  verdict: "pass" | "partial" | "fail";
  answer: string;
  source: string;
  topic: string;
  points?: string[]; // LLM 判定要点（写回 answer 作答案对照）
  misses?: string[];
  reason?: string;
}

export interface MockCompleteResponse {
  updated: number;
  new: number;
  behaviors: string[];
}

// ── 简历资料（模拟面试「简历深挖」数据源）──
export interface DocStatus {
  provided: boolean;
  filename: string | null; // 来源文件名（meta 侧车）
  updated_at: string | null;
  chars: number;
  summary: string; // 正文前 60 字，防错展示用
}

export interface ProfileResponse {
  resume: DocStatus;
  jd: DocStatus;
}

// ── Dashboard ──
export interface RemindEntry {
  id: string;
  question: string;
  topic: string;
  days: number;
  gap: number;
}

export interface CurvePoint {
  bucket: string;
  count: number;
  avg_mastery: number | null;
}

export interface DashboardData {
  space: string;
  spaces: string[];
  stats: {
    total: number;
    by_status: { fail: number; partial: number; pass: number; unknown: number };
    hot_topics: Array<[string, number]>;
  };
  remind: {
    red: RemindEntry[];
    yellow: RemindEntry[];
    green: number;
  };
  curve: CurvePoint[];
  recent: Array<{
    time: string;
    item_id: string;
    question: string;
    before: number;
    after: number;
    action: string;
    actor: string;
  }>;
}
