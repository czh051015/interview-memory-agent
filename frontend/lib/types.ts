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

// ── 申论工作台（与后端 app/api/shenlun.py + diagnose.py 对齐，docs/20/22）──
export interface PracticeStart {
  question_id: string;
  question: string;
  material: string;
  max_score: number | null;
  type: string;
  recommend_reason: string;
  focus: string;
  action: string; // practice / graduation_check / intervene
}

// ── 单题上传模式：内联采分点 + 材料（解题库依赖，docs/22 §3.5）──
export interface InlinePoint {
  id: string;
  point: string;
  keywords: string[];
  score: number;
  point_type: string;
}
export interface InlineGold {
  points: InlinePoint[];
  material: string;
  question: string;
  qtype: string;
}

export interface PracticeHit {
  id: string;
  point: string;
  score: number;
  point_type: string;
  matched_text: string | null; // 命中片段（L1 标红定位）：kw=含词句，semantic=语义相似句，llm=LLM 引用的作答句
  matched_by?: "kw" | "semantic" | "llm"; // 命中来源（docs/25 语义层 / docs/26 judge 引擎，kw 命中缺省）
  semantic_score?: number | null; // 语义命中相似度（docs/25，kw 命中为 null）
}
export interface PracticeMiss {
  id: string;
  point: string;
  score: number;
  point_type: string;
  material_source: string | null; // 材料锚定句（L3 溯源，「材料第X段：'…'」）
}
export interface PracticeLeading {
  point_id: string;
  point: string;
  score: number;
  material_source: string | null;
}

export interface PracticeSubmit {
  hit_ratio: number;
  passed: boolean;
  hits: PracticeHit[]; // L1 命中
  misses: PracticeMiss[]; // L1 漏点（每点挂材料原话）
  leading: PracticeLeading | null; // 推 1 个最该补的漏点（示证式主动，非逼问）
}

// ── 文字版标准答案自动解析（docs/24 §5.1）：后端 decompose_points 产出 ──
export interface ParsePoint {
  id: string; // p1/p2/…
  point: string;
  keywords: string[];
  score: number;
  point_type: string;
  source_snippet: string; // 该点对应的标准答案原文片段（核验拆点质量用）
}
export interface ParseTrace {
  standard_answer: string; // 原始答案全文
  points: ParsePoint[]; // 拆出的采分点（含 source_snippet）
  warnings: string[];
}
export interface ParseResult {
  points: ParsePoint[];
  warnings: string[];
  trace: ParseTrace; // 默认不下发解析细节；?dev=1 时前端展示
}

// 按需示证（点开某漏点才返回）：L3 材料锚定 + L2 示范 + L4 错因/改法
export interface GuidanceResult {
  point_id: string;
  point: string;
  material_source: string | null;
  demo: string; // L2 示范表述
  cause_type: string; // L4 错因归类：完全没提/写偏/太模糊
  cause: string; // L4 错因说明
  fix: string; // L4 具体改法
}

// 按需讲解（点开某漏点的「追问讲解」按钮）：有界、不生成完整答案（no_full_answer）
export interface ExplainResult {
  point_id: string;
  point: string;
  material_source: string | null;
  rephrase: string; // 换一种更口语/更易懂的说法
  why: string; // 为什么材料这句话能支撑这个点
  distinguish: string; // 与相邻点的辨析
}

export interface WrongbookResult {
  stored: number;
  item_id: string;
  point: string;
}

export interface PracticeRound {
  round_no: number;
  answer: string;
  hit_ids: string[];
  miss_ids: string[];
  hit_ratio: number;
  guided_point_ids: string[];
}

export interface PracticeComplete {
  ok: boolean;
  weak_added: number;
  answer_id: number | null;
}

export interface ShenlunRemindEntry {
  point: string;
  qtype: string;
  days: number;
}

export interface RemindData {
  graduation_candidates: ShenlunRemindEntry[]; // 毕业考候选（≤2）
  to_practice: ShenlunRemindEntry[]; // 该练 topK（≤3，按紧急度）
}

export interface WeakPointItem {
  point_key: string;
  label: string;
  qtype: string;
  point_type: string;
  question_id: string;
  miss_count: number;
  hit_count: number;
  consecutive_hits: number;
  tier: string; // red / yellow / green
  urgency: number;
  state: string; // active / graduated / stuck / pinned
  last_miss_at: string | null;
}

export interface WeakpointsData {
  items: WeakPointItem[];
}

export type AngleStat = { total: number; red: number; miss_sum: number };
export interface DiagnoseData {
  by_type: Record<string, AngleStat>;
  by_angle: Record<string, AngleStat>;
  total_points: number;
}
