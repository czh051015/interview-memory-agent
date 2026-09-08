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
  feedback: string; // 模拟面试反馈（面试域）/ 申论错题条目：【错因】+【示范】拼接（docs/22 §3.6）
  // ── 申论错题条目扩展字段（docs/22 §3.6：每漏点一条 sl_{question_id}_{point_id}；后端已序列化，非申论条目留空）──
  question_id: string; // 申论题目 id（如 henan_2025_city_1）
  point_id: string; // 申论采分点 id（如 c1）
  material_source: string; // 漏点材料锚定原话（「材料第1段：'…'」）
  demo_text: string; // 申论示范表述（L2，feedback 已含【示范】摘要，此字段留源）
  reflow_tier: string; // red/yellow/green（初始 red）；空 = 非申论条目
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

// ── 申论工作台（与后端 app/api/shenlun.py 对齐）docs/42 单模式：恒 gate 三色判定 + 采分点来源分层 ──
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
  source_snippet?: string; // 标准答案原句摘录（文字版自动解析带出，JSON 手填可省略）
}
export interface InlineGold {
  points: InlinePoint[];
  material: string;
  question: string;
  qtype: string;
  question_id?: string; // docs/42 L1：声明来自题库 → 校验在库 + points 全量一致即金标
  points_source?: "manual" | "llm_parse"; // docs/42 M2 分层信号：manual=手填(L2，缺省) / llm_parse=LLM 拆解(L3)
  answer?: string; // 预置演示作答（「载入示例题」直接可评，构造多状态分布）
}

// ── 评分响应（docs/38 §6 PointVerdict + docs/42 tier）：判定三色 + 规则证据全量下发 ──
export type VerdictStatus = "hit" | "miss" | "suspect";
export interface PointVerdict {
  point_id: string;
  point_name: string;
  mode: "gate";
  status: VerdictStatus;
  matched_by: "kw" | "llm"; // 规则绿 vs LLM 放行绿 / 疑似（透明可查）
  terms: { matched: string[]; missing: string[] }; // 规则证据，逐字可复核
  evidence: string; // 作答原句（规则定位）；黄行空串（§8.1）
  anchor: string | null; // 「材料第X段：'…'」三色都下发（docs/36 老缺口修复）
  official: string; // source_snippet ?? 材料锚句原文（D46 兜底）
  suspect: { label: string; reason: string } | null; // 仅 status=suspect 非空
  reason: string; // 为什么标（规则文案或 LLM reason，D47 ①）
}
// 采分点来源分层（docs/42 §4.0）：判定三色对 L1/L2/L3 同权，分层只决定展示标记与回流资格
// （L1 库题金标 / L2 用户手填 / L3 LLM 拆解「参考 · 未复核」，漏点均走错题本，P-A=②）
export type PointsTier = "L1" | "L2" | "L3";
export interface GateResult {
  mode: "gate";
  tier: PointsTier; // docs/42：来源分层（submit 响应新增）
  verdicts: PointVerdict[]; // 顺序 = 采分点顺序
  warnings: string[]; // 灰带 LLM 不可用等降级说明（不阻断）
}

// ── 示证响应（docs/37 §6 配对契约，SCORE_FORCE=align 测试/回归锁定才返回，生产退役）──
export interface AlignOfficial {
  id: string;
  point: string;
  keywords: string[];
  official_sentence: string | null; // source_snippet（拆点/录入链路才有）
  material_ref: string | null; // 出处附注「材料第X段：'…'」，可空
}
export interface AlignChunk {
  id: number;
  text: string;
}
export interface AlignItem {
  point_id: string;
  chunk_id: number;
  method: "kw" | "semantic";
  kws_hit?: string[]; // kw 行带（共现词 = 证据）
  similarity?: number; // semantic 行带
}
export interface AlignGap {
  point_id: string;
  max_similarity: number | null; // 语义可用才有值（展示数字，非判定）
}
export interface AlignOrphan {
  chunk_id: number;
  max_similarity: number | null;
}
export interface AlignMeta {
  engine: string;
  semantic_used: boolean;
  warnings: string[];
}
export interface AlignResult {
  mode: "align";
  official_points: AlignOfficial[];
  answer_chunks: AlignChunk[];
  alignments: AlignItem[];
  gaps: AlignGap[];
  orphans: AlignOrphan[];
  meta: AlignMeta;
}

export type PracticeSubmit = GateResult | AlignResult; // 判别联合：先看 mode

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
  points_source?: "llm_parse"; // docs/42 M2：LLM 拆解产物 → 拼 InlineGold 时原样回传
  warnings: string[];
  trace: ParseTrace; // 默认不下发解析细节；?dev=1 时前端展示
}

// 建议区③改进建议（docs/42 P-D=①）：点开某点懒加载，L1/L2/L3 全放开；
// gap/how/rewrite 是候选措辞（前端展示带「（供参考，以官方答案为准）」），LLM 失败置空不阻断。
// ①②（为什么标 / 标准答案原文）随评分响应回放（0 token），本接口只补 ③。
export interface GuidanceResult {
  point_id: string;
  point: string;
  official: string; // 与 verdict.official 同源（② 回放已在评分响应，不回传重复消费）
  gap: string; // 差距在哪
  how: string; // 怎么补（结合②官方写法与材料出处）
  rewrite: string; // 示范句（漏答给全新示范，沾边给改写）
  caveat: string; // docs/42：L3 带「基于未复核采分点」措辞，L1/L2 为空串
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
