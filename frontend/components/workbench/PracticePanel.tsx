"use client";

// ── 申论练习 · 单题双模式（docs/38：门禁 gate / 示证 align）──
// 产品哲学：审过的题（gold.question_id 在库且采分点全量一致，D41）才允许系统"说三道四"
// —— 门禁三色判定（绿·关键词 / 绿·AI复核 / 黄·漏答 / 蓝·疑似）+ 建议区三块；
// 没审过的内联题（无 question_id）只做差异配对 —— 示证档 AI 只摆证据不判（docs/37）。
// 布局：整页两栏（≥1280px 分栏，窄屏退化单列）；左栏 = 材料 + 作答；右栏 = 题面配置
// （评分前）/ 逐点清单 + 建议卡（评分后）。
// 门禁（docs/38 §4.3 建议区）：① 为什么标（随评分响应，0 token）② 标准答案原文
// （D46 兜底）③ 改进建议 gap/how/rewrite（点开懒加载 1 次 LLM，措辞候选带"供参考"）。
// 黄行（miss）琥珀应抄句高亮沿用（docs/36 老缺口 anchor 全量下发后同源）。
// 示证（docs/37 §7 对照视图）：◎ 有对应 / ~ 语义弱对应 / ○ 未见对应（候选），
// 措辞遵守 docs/37 §2.3 禁止词表（漏答/命中/没写上/建议你补…一律不出现在本档文案）；
// 无三色、无疑似、无建议生成。题面/作答改动 → 清空轮次（docs/33 D11）。

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { addWrongbook, getGuidance, parsePractice, scorePractice } from "@/lib/api";
import type {
  AlignResult,
  GateResult,
  GuidanceResult,
  InlineGold,
  ParseTrace,
  PointVerdict,
  PracticeSubmit,
} from "@/lib/types";

// ── 示例题（河南 2025 市级，benchmark/data/henan_2025_city_1.json）──
// 点「载入示例题」即填充输入区并可立即评分。question_id 声明该题在题库 → 门禁模式；
// 演示「示证模式」：改动题干/材料/标准答案任一内容后重新评分（qid 自动清除）即可对比。
// standard_answer_text（docs/实施计划 任务三）：载入后标准答案框显示这份文字版
// （解决"界面是 JSON"），评分仍走 samplePoints 库题快照捷径（不经文字解析——LLM 拆点
// 有漂移，拆出的点 ≠ 库题 9 点 → D41 400 → 门禁演示必丢）；用户改动文字/题面才清
// trustQid 落回真实文字解析 → 示证对照。文字草稿基于库题 9 点、关键词语义一致。
const SAMPLE: InlineGold & { standard_answer_text: string } = {
  question_id: "henan_2025_city_1", // docs/38 §6：库题声明 → 门禁（D41 校验通过才 trusted）
  qtype: "归纳概括",
  question: "请根据“给定资料1”，梳理概括A区与B县在推动同城化发展中的举措和成效。",
  material:
    "清晨，A 区居民小陈准备烧饭，打开水龙头，清冽的自来水哗哗流出。这股来自 13 公里外 B 县最大饮用水源保护地三合水库的清泉，让 A 区 3 个街道的 16 万人“解了渴”。同饮一库水，得益于两地的同城化发展。A 区和 B 县地域相连且同属 C 市，主城区相距不到 20 公里，A 区人口众多、商贸发达，B 县人文和生态资源丰富。2018 年，在市政府主导下，两地签署战略合作协议，全力推动同城化发展，推进了 80 余项合作。B 县中医院的骨科远近闻名，这两年，从 A 区到 B 县来看骨伤的患者明显增多了。A 区商贸业发达，经常能看到成群结队的 B 县年轻人到 A 区逛街、消费。而 B 县的农家乐也很受A 区居民欢迎，去年前往 B 县乡村游的 A 区游客占总量的 50%。“这几年两地开通了城际公交，实现了高速公路免费互通，两地的互联互通还在进一步加速，未来将新建、提升改造 3条道路。”A 区交通运输局相关负责人介绍。2020 年 4 月，两地组织部门签署了人才协同发展战略合作框架协议，建立年轻干部互派挂职机制。现挂职 A 区文旅局副局长的 B 县青阳街道办马副主任在漫步 A 区文创街区时，想到青阳特色美食街，突然冒出一个想法，“两地各有优势，何不强强联手？”想到就干，他与同事合作，促成 A 区与 B 县召开文旅共建联席会议，积极推动两地开展“美食文创街区”旅游营销活动，协同打造县域消费目的地。“这几年，A 区高速发展对 B 县的辐射带动正在逐步增强，两地产业互补性、协调性还在加深。”B 县孙县长表示，“2024 年，B 县制造业投资增长超过 50%，增速位列全市第一。在 A 区新兴产业带动下，一批与其紧密关联的新能源项目相继落地 B 县，不仅完善了产业结构，也带动了装备制造、光伏光电、电子信息等新兴产业投资。”走进毗邻 A 区的 B 县黄龙工业园区，一栋栋现代化新厂房映入眼帘。近几年，该园区共落地企业 218 家，其中企业法人为 A 区籍的有 86 家。A 区某面膜生产企业负责人表示，2020年看准两地同城合作机遇，她在 B 县投资建起了新工厂。在市场需求带动下，A 区和 B 县之间已经形成了面膜上下游供应链企业紧密合作的生态圈。近期，两地的物流公司正积极谋划，在黄龙工业园区开展综合货运枢纽共建等项目。“我们在黄龙工业园建有物流仓库，在此集货后，可通过 A 区中欧班列、水运发往全世界。”A 区某物流公司负责人说，在 B 县建仓成本低、发货效率高。B 县某商业小区因地理位置优越、价格适中，项目一开盘就吸引了 500 余户 A 区市民前来投资置业。“在 A 区赚钱，在 B 县生活。”在 A 区做服装生意的小江选择将家安在 B 县，生活成本低、舒适度高，一家人在一起，幸福甜蜜。今年，B 县人社部门帮助推广 A 区的“找零工”App，将 A 区实时响应的零工招聘信息推送到 B 县用户手中，已帮助 1000 余名 B 县籍务工人员在 A 区找到了打短工的机会。B 县人社局就业科负责人说，家住 B 县城乡接合部的邹先生，忙时在家务农，闲时出门打工。这几年 A 区对零工需求很多，打包的、配货的、装运的，有时一干就是十天半个月，增加了不少收入。据统计，2019-2024 年 A 区 GDP 增幅达 31%，增幅高出 B 县约 11 个百分点。但在 A 区的带动下，B 县二三产业协同驱动的经济增长方式逐渐形成，多项经济指标增速在 C 市 9 个区县中名列前茅，显示出强劲的发展势头。虽然 2024 年 A 区 GDP 增速仍然高于 B 县，但两地增幅的差距，已由去年的 1.6 个百分点缩小到了 1.1 个百分点，目前“1+1>2”的区域发展格局初步形成。",
  points: [
    { id: "c1", point: "设施互通", keywords: ["城际公交", "高速免费", "道路", "互通"], score: 1, point_type: "对策" },
    { id: "c2", point: "产业协同", keywords: ["新兴产业", "新能源", "物流枢纽", "供应链"], score: 1, point_type: "对策" },
    { id: "c3", point: "服务共享", keywords: ["医疗", "文旅", "营销活动"], score: 1, point_type: "对策" },
    { id: "c4", point: "人才共育", keywords: ["干部互派", "人才协同", "挂职"], score: 1, point_type: "对策" },
    { id: "c5", point: "民生联动", keywords: ["灵活就业", "置业", "零工"], score: 1, point_type: "对策" },
    { id: "c6", point: "经济共进", keywords: ["GDP增长", "制造业投资", "差距缩小"], score: 1, point_type: "影响" },
    { id: "c7", point: "产业升级", keywords: ["二三产业", "产业结构"], score: 1, point_type: "影响" },
    { id: "c8", point: "民生提质", keywords: ["就医", "消费", "就业", "幸福感"], score: 1, point_type: "影响" },
    { id: "c9", point: "格局初成", keywords: ["1+1>2", "协同效应"], score: 1, point_type: "影响" },
  ],
  // 文字版标准答案（docs/实施计划 §四.1 草稿，载入后显示在标准答案框；关键词与库题一致）
  standard_answer_text:
    "举措方面：一是设施互通。两地开通城际公交，实现高速公路免费互通，并规划新建、提升改造 3 条道路。二是产业协同。在 A 区新兴产业带动下，一批新能源项目相继落地 B 县，双方共建综合货运枢纽，形成面膜上下游供应链生态圈。三是服务共享。推动医疗、文旅等资源互通，联合开展美食文创街区等旅游营销活动。四是人才共育。签署人才协同发展战略合作框架协议，建立年轻干部互派挂职机制。五是民生联动。推广“找零工”App 促进灵活就业，吸引 A 区市民赴 B 县置业。成效方面：一是经济共进。A 区 GDP 增幅达 31%，B 县制造业投资增速位列全市第一，两地增速差距由 1.6 个百分点缩小到 1.1 个百分点。二是产业升级。B 县二三产业协同驱动的经济增长方式逐渐形成。三是民生提质。两地群众就医、消费、就业更加便利，获得感、幸福感增强。四是格局初成。“1+1>2”的区域发展格局初步形成。",
  // 预置演示作答（重构 v2，2026-09-02）：中等偏下考生。设计原则——
  // 规则可证的删净点（漏答）必须完全删净相关表述；其余点部分命中进灰带走 LLM
  // 放行绿或疑似蓝（接受漂移：实际落位以实测校准为准，见 docs/38 §8.3 偏差汇报）。
  answer:
    "A区与B县地域相连、同属C市，在市政府主导下签署战略合作协议，全力推动同城化发展。举措方面：一是设施互通，两地开通城际公交，实现高速公路免费互通，并规划新建、提升改造3条道路。二是产业协同，在A区新兴产业带动下，一批新能源项目相继落地B县，双方共建综合货运枢纽，形成面膜上下游供应链生态圈。三是服务共享，推动医疗、文旅等资源互通共享，方便群众跨区使用。四是民生保障，促进两地群众就业增收。成效方面：一是经济共进，A区GDP增幅达31%，B县制造业投资增速位列全市第一，两地增速差距由1.6个百分点缩小到1.1个百分点。二是产业升级，两地积极培育数字经济、人工智能等新兴产业动能。三是民生提质，不断增强两地群众的获得感、幸福感、安全感。",
};

const NUMS = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩", "⑪", "⑫", "⑬", "⑭", "⑮", "⑯", "⑰", "⑱", "⑲", "⑳"];

interface Round {
  no: number;
  answer: string;
  submit: PracticeSubmit;
}

interface PointDetail {
  loadingG?: boolean;
  guidance?: GuidanceResult;
  added?: boolean;
}

// ── 双模式判别（响应 = mode 判别联合，docs/38 §6 / 37 §6）────────────
function isGate(s: PracticeSubmit | null): s is GateResult {
  return !!s && s.mode === "gate";
}
function isAlign(s: PracticeSubmit | null): s is AlignResult {
  return !!s && s.mode === "align";
}

// ── 门禁徽章（docs/38 §5 四态：绿·关键词 / 绿·语义 / 黄·漏答 / 蓝·疑似）──
type VerdictFamily = "hit" | "miss" | "suspect";
interface VerdictBadge {
  label: string;
  cls: string; // pill 浅底深字（三族语义色沿用 D33）
  family: VerdictFamily;
}
function badgeOfVerdict(v: PointVerdict): VerdictBadge {
  if (v.status === "hit") {
    return v.matched_by === "kw"
      ? { label: "✅ 命中", cls: "bg-emerald-100 text-emerald-800 border-emerald-300", family: "hit" }
      : { label: "✅ 命中 · AI复核", cls: "bg-emerald-50 text-emerald-600 border-emerald-200", family: "hit" };
  }
  if (v.status === "miss") {
    return { label: "漏答", cls: "bg-amber-100 text-amber-800 border-amber-300", family: "miss" };
  }
  return { label: "疑似 · 供参考", cls: "bg-blue-50 text-blue-700 border-blue-200", family: "suspect" };
}

// ── 锚点定位（纯前端，docs/33 §3.2）────────────────────────────────
const ANCHOR_RE = /材料第(\d+)段：'([^']*)'/;

/** 定位后端锚「材料第X段：'…'」→ {start,end,para}（全材料下标）；定位失败 → null。
 *  引用句被截断（尾部 …）时逐字符放松重试；必须 indexOf 命中，绝不猜测（docs/33 §7-2）。 */
function locateAnchor(material: string, materialSource: string | null) {
  if (!material || !materialSource) return null;
  const m = ANCHOR_RE.exec(materialSource);
  if (!m) return null;
  const paraHint = Number(m[1]);
  const quoteRaw = m[2];
  // 截断句（后端 quote 超 60 字以 … 截断）→ 先整句试，再逐字符放松尾部重试
  for (let cut = 0; cut <= 3 && quoteRaw.length - cut > 0; cut++) {
    const quote = cut === 0 ? quoteRaw : quoteRaw.slice(0, quoteRaw.length - cut);
    if (quote.endsWith("…")) continue;
    const at = material.indexOf(quote);
    if (at >= 0) {
      const para = material.slice(0, at).split("\n").length;
      return { start: at, end: at + quote.length, para };
    }
    // 段号提示辅助（全局搜不到才用段内搜；两处都失败 → null）
    if (paraHint > 0) {
      const paras = material.split("\n");
      if (paraHint <= paras.length) {
        let base = 0;
        for (let i = 0; i < paraHint - 1; i++) base += paras[i].length + 1;
        const rel = paras[paraHint - 1].indexOf(quote);
        if (rel >= 0) return { start: base + rel, end: base + rel + quote.length, para: paraHint };
      }
    }
  }
  return null;
}

interface AnchorLoc {
  start: number;
  end: number;
  para: number;
}

// 高亮共用一张锚点表（编号只给可定位的黄行，按列表顺序 ①②③…）
interface AnchorTable {
  byPoint: Map<string, AnchorLoc>;
  nums: Map<string, string>;
}

export default function PracticePanel() {
  const [questionStr, setQuestionStr] = useState("");
  const [materialStr, setMaterialStr] = useState("");
  const [pointsStr, setPointsStr] = useState("");
  const [answerStr, setAnswerStr] = useState("");
  // docs/38 §6：库题声明（载入示例题自带）；题面任一内容被改动 → 清除（回示证模式）
  const [trustQid, setTrustQid] = useState("");
  // 载入示例题时的库题结构化快照（docs/实施计划 任务三）：trustQid 未被动过 → 评分捷径
  // 直接用它（不经文字解析），文本编辑 → 清 trustQid → 此快照自然失效
  const [samplePoints, setSamplePoints] = useState<InlineGold["points"] | null>(null);

  const [gold, setGold] = useState<InlineGold | null>(null); // 最近一次评分用的题面（示证/错题本/锚定基）
  const [rounds, setRounds] = useState<Round[]>([]);
  const [detail, setDetail] = useState<Record<string, PointDetail>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editOpen, setEditOpen] = useState(false); // 评分态下的「编辑题面」开关
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  // 文字模式（docs/24 §5.2）：标准答案框贴纯文字 → 评分时先自动解析；trace 仅 dev 可见
  const [textMode, setTextMode] = useState(false);
  const [parseTrace, setParseTrace] = useState<ParseTrace | null>(null);
  // D11 快照：最近一次评分所用的题面原文（检测题面改动 → 清轮次，旧锚定失效防护）
  const [lastUsed, setLastUsed] = useState<{ question: string; material: string; points: string } | null>(null);

  const current = rounds.length ? rounds[rounds.length - 1] : null;
  const currentAnswer = current ? current.answer : answerStr;
  const showResult = rounds.length > 0;
  const mode = current ? current.submit.mode : null; // gate | align
  const curSubmit = current?.submit ?? null; // 最新一轮响应（判别联合：先看 mode 再分派）
  // 开发者开关：?dev=1 或 localStorage shenlun_dev=1 → 标准答案框下展开「解析 trace」
  const dev =
    typeof window !== "undefined" &&
    (new URLSearchParams(window.location.search).get("dev") === "1" ||
      localStorage.getItem("shenlun_dev") === "1");

  // ── 锚点表：评分态左栏高亮，纯前端计算，0 网络 ──
  // 只服务门禁黄行（status=miss 且有锚）——漏答点才暗示"该句可抄"（docs/35 D27 精神沿用）；
  // 绿/蓝行（含 AI 复核放行、疑似）不高亮不编号。
  const anchors: AnchorTable = useMemo(() => {
    const byPoint = new Map<string, AnchorLoc>();
    const nums = new Map<string, string>();
    if (gold && isGate(curSubmit)) {
      let n = 0;
      for (const v of curSubmit.verdicts) {
        if (v.status !== "miss") continue;
        const loc = locateAnchor(gold.material, v.anchor);
        if (loc) {
          byPoint.set(v.point_id, loc);
          nums.set(v.point_id, NUMS[n] || `(${n + 1})`);
          n += 1;
        }
      }
    }
    return { byPoint, nums };
  }, [gold, curSubmit]);

  // ── 视图分派（identifier 窄化，TS 判别联合）：门禁清单 / 降级横幅 / 示证渲染 ──
  const gateView = isGate(curSubmit) ? curSubmit : null;
  const alignView = isAlign(curSubmit) ? curSubmit : null;
  const gateWarnings = gateView ? gateView.warnings : [];
  // ── 门禁逐点清单（verdicts 顺序 = 采分点顺序，docs/38 §6）──────────
  const gateVerdicts = useMemo(() => (isGate(curSubmit) ? curSubmit.verdicts : []), [curSubmit]);
  const selVerdict = gateVerdicts.find((v) => v.point_id === selectedId) ?? null;
  const selBadge = selVerdict ? badgeOfVerdict(selVerdict) : null;
  const allHit =
    gateVerdicts.length > 0 && gateVerdicts.every((v) => v.status === "hit");
  const gateSemanticCount = gateVerdicts.filter((v) => v.status === "hit" && v.matched_by === "llm").length;

  function scrollToAnchor(pointId: string) {
    // 选中态渲染完成后定位黄行应抄句（延迟让 React 先画出来）
    requestAnimationFrame(() => {
      document
        .getElementById(`pAnc-${pointId}`)
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  function loadSample() {
    setQuestionStr(SAMPLE.question);
    setMaterialStr(SAMPLE.material);
    // 任务三：显示文字版标准答案（不再是 JSON 摊平）；评分走 samplePoints 库题快照捷径
    setPointsStr(SAMPLE.standard_answer_text);
    setSamplePoints(SAMPLE.points);
    setAnswerStr(SAMPLE.answer ?? "");
    setTrustQid(SAMPLE.question_id ?? "");
    setGold(null);
    setRounds([]);
    setDetail({});
    setSelectedId(null);
    setEditOpen(false);
    setLastUsed(null);
    setError("");
    setTextMode(false);
    setParseTrace(null);
  }

  // 编辑题面：进入编辑态时用 gold 回填输入框（保证所见即所评）
  function openEditor() {
    if (!gold) return;
    setQuestionStr(gold.question);
    setMaterialStr(gold.material);
    setPointsStr(JSON.stringify(gold.points, null, 2));
    setError("");
    setEditOpen(true);
  }

  // D11：题面（题干/材料/标准答案）改动 → 评分轮次作废（旧锚定失效）；作答改动不在此列
  function configChanged(): boolean {
    if (!lastUsed) return true;
    return (
      questionStr !== lastUsed.question ||
      materialStr !== lastUsed.material ||
      pointsStr !== lastUsed.points
    );
  }

  function cancelEdit() {
    // 取消编辑 = 丢弃题面改动（回到评分态视图）；gold 仍在，轮次不丢
    if (gold) {
      setQuestionStr(gold.question);
      setMaterialStr(gold.material);
      setPointsStr(JSON.stringify(gold.points, null, 2));
    }
    setEditOpen(false);
  }

  // docs/38 §6：题面内容被改动 → 库题声明自动清除（内容已不等于库题，D41 会 400）
  const touchConfig = () => setTrustQid("");

  async function resolveGold(): Promise<InlineGold | null> {
    const s = pointsStr.trim();
    if (!s) {
      setError("请先粘贴标准答案（文字或 JSON）");
      return null;
    }
    // ── 库题捷径分支（docs/实施计划 任务三，在一切解析之前）──
    // 库题声明未被改动（trustQid 在）+ 持有载入快照 → 直接提交库题结构化采分点：
    // 门禁题的正确答案本来就来自题库（D41：声明 + 逐点一致才 trusted），不经 LLM 现拆。
    // 若不设此捷径：示例题文字解析拆点必然 ≠ 库题点 → 400 → 门禁演示丢失；
    // 用户改动文字/题面 → touchConfig 已清 trustQid → 落入下方真实文字解析（示证）。
    if (trustQid && samplePoints) {
      setTextMode(false);
      setParseTrace(null);
      return {
        question_id: trustQid,
        qtype: "归纳概括",
        question: questionStr,
        material: materialStr,
        points: samplePoints,
      };
    }
    // JSON（采分点数组）→ 原样用；纯文字 → LLM 自动拆成采分点再评分
    try {
      const parsed: unknown = JSON.parse(s);
      if (Array.isArray(parsed)) {
        setTextMode(false);
        setParseTrace(null);
        return {
          question_id: trustQid || undefined, // 库题声明（无 = 示证）
          qtype: "归纳概括",
          question: questionStr,
          material: materialStr,
          points: parsed as InlineGold["points"],
        };
      }
      // 能解析但不是数组（不会是采分点 JSON）→ 按文字处理
    } catch {
      // 解析失败 → 文字模式
    }
    setTextMode(true);
    const r = await parsePractice({ question: questionStr, material: materialStr }, s);
    setParseTrace(r.trace);
    if (r.warnings.length) showToast(`解析提示：${r.warnings.join("；")}`);
    if (!r.points.length) {
      setError("解析未拆出采分点，可切回 JSON 模式手填");
      return null;
    }
    return {
      question_id: trustQid || undefined, // 文字拆点通常 ≠ 库题 → 后端会 400 防伪并提示
      qtype: "归纳概括",
      question: questionStr,
      material: materialStr,
      points: r.points.map((p) => ({
        id: p.id,
        point: p.point,
        keywords: p.keywords,
        score: p.score,
        point_type: p.point_type,
        source_snippet: p.source_snippet, // 文字模式拆点带官方原句 → 建议卡参考写法
      })),
    };
  }

  async function score() {
    if (!answerStr.trim()) return;
    setBusy(true);
    setError("");
    try {
      const g = await resolveGold(); // JSON → 直接；纯文字 → 先 parsePractice（busy 覆盖全程）
      if (!g) return;
      const changed = configChanged();
      // 题面改动 → D11 清空旧轮次（锚定/示证全失效）；作答改动保留轮次做 delta
      if (changed) setRounds([]);
      // 示证缓存以轮次为作用域：每轮都重置（点集/作答变了，旧 guidance 会误导）
      setDetail({});
      setSelectedId(null);
      const submit = await scorePractice(g, answerStr.trim());
      setGold(g);
      setLastUsed({ question: questionStr, material: materialStr, points: pointsStr });
      setEditOpen(false);
      setRounds((prev) => [...prev, { no: prev.length, answer: answerStr.trim(), submit }]);
      // 门禁：评分后默认选中第一个非绿行（漏答优先）并拉③建议；全绿/示证 → 空态
      if (isGate(submit)) {
        const first = submit.verdicts.find((v) => v.status !== "hit");
        if (first) {
          setSelectedId(first.point_id);
          setDetail((d) => ({ ...d, [first.point_id]: { ...(d[first.point_id] || {}), loadingG: true } }));
          try {
            const r = await getGuidance(g, answerStr.trim(), first.point_id);
            setDetail((d) => ({ ...d, [first.point_id]: { ...(d[first.point_id] || {}), guidance: r, loadingG: false } }));
          } catch (e: unknown) {
            setError(e instanceof Error ? e.message : "示证加载失败");
            setDetail((d) => ({ ...d, [first.point_id]: { ...(d[first.point_id] || {}), loadingG: false } }));
          }
        }
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "评分失败";
      // docs/38 D41：trusted 校验 400（声明与库题不一致/查无）→ 明确提示并清 qid 回示证
      if (trustQid && /不一致|防伪|不存在题库/.test(msg)) {
        setTrustQid("");
        setError(`${msg} —— 已清除库题声明（改动过的题面只能按示证模式对照，不能按门禁判分）`);
      } else {
        setError(msg);
      }
    } finally {
      setBusy(false);
    }
  }

  async function ensureGuidance(pointId: string) {
    if (!gold || !isGate(current?.submit ?? null)) return; // ③仅门禁路由（示证档后端 400）
    const cur = detail[pointId];
    if (cur?.guidance || cur?.loadingG) return; // 已加载/加载中不重复请求
    setDetail((d) => ({ ...d, [pointId]: { ...(d[pointId] || {}), loadingG: true } }));
    try {
      const r = await getGuidance(gold, currentAnswer, pointId);
      setDetail((d) => ({ ...d, [pointId]: { ...(d[pointId] || {}), guidance: r, loadingG: false } }));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "示证加载失败");
      setDetail((d) => ({ ...d, [pointId]: { ...(d[pointId] || {}), loadingG: false } }));
    }
  }

  // 联动：选中变化 → 左栏滚动定位（仅黄行有锚；绿/蓝行不滚动）
  useEffect(() => {
    if (!selectedId) return;
    if (anchors.byPoint.has(selectedId)) scrollToAnchor(selectedId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  function pickPoint(pointId: string) {
    setSelectedId(pointId);
    if (isGate(current?.submit ?? null)) void ensureGuidance(pointId); // 懒加载：选中即拉（详情缓存，回看秒开）
  }

  async function addToWrongbook(pointId: string) {
    if (!gold || !gateView) return;
    const v = gateView.verdicts.find((x) => x.point_id === pointId);
    if (!v || v.status !== "miss") return; // 黄行（漏答）才入错题本（规则可证档；蓝行 AI 判断不硬收）
    try {
      // docs/38 D43：原因 = 随评分返回的规则文案（不再拉 LLM demo）；服务端重算锚定
      const r = await addWrongbook(gold, currentAnswer, pointId, "漏答", v.reason);
      setDetail((d) => ({ ...d, [pointId]: { ...(d[pointId] || {}), added: true } }));
      showToast(`已加入错题本：${r.point}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "入库失败");
    }
  }

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(""), 2500);
  }

  const inEditArea = !showResult || editOpen; // 右栏放题面配置（窄屏顶置）还是评分结果

  return (
    <div className="p-5 flex flex-col min-h-[640px] xl:h-screen">
      {/* ── header（不滚）── */}
      <div className="flex items-center justify-between gap-3 mb-3 shrink-0">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold text-zinc-900 whitespace-nowrap">申论练习 · 单题</h2>
            {current && (
              <ModeTag submit={current.submit} no={current.no} />
            )}
          </div>
          <p className="text-[11px] text-zinc-500 truncate max-w-[60vw]">
            {showResult && gold ? gold.question : questionStr || "题干摘要：粘贴题干 / 载入示例题后可见"}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button onClick={loadSample} disabled={busy}
            className="px-3 py-1.5 rounded-lg border border-zinc-200 bg-white text-zinc-600 text-xs font-medium hover:bg-zinc-50 transition-colors">
            载入示例题
          </button>
          {showResult && (
            <button onClick={editOpen ? cancelEdit : openEditor} disabled={busy}
              className="px-3 py-1.5 rounded-lg border border-zinc-200 bg-white text-zinc-600 text-xs font-medium hover:bg-zinc-50 transition-colors">
              {editOpen ? "取消编辑" : "编辑题面"}
            </button>
          )}
          <button onClick={() => score()} disabled={busy || !answerStr.trim()}
            className="px-4 py-1.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors">
            {busy ? "评分中…" : showResult ? "重新评分" : "评分"}
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-3 shrink-0 rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-600">{error}</div>
      )}
      {toast && (
        <div className="mb-3 shrink-0 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm text-emerald-700">{toast}</div>
      )}
      {gateWarnings.length > 0 && (
        <div className="mb-3 shrink-0 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-700">
          ⚠ {gateWarnings.join("；")}（灰带点已按放行处理，不影响本轮对照）
        </div>
      )}

      {/* ── 两栏：窄屏单列流（题面配置 order-first 顶置，评分态回落 材料→作答→结果 自然序）── */}
      <div className="flex-1 xl:min-h-0 flex flex-col gap-3 xl:flex-row xl:gap-4">
        {/* 左栏：材料 + 作答 */}
        <div className="flex flex-col gap-3 min-w-0 xl:flex-1 xl:min-h-0">
          {showResult && !editOpen && gold ? (
            <MaterialView material={gold.material} anchors={anchors} onPick={pickPoint}
              caption={mode === "align" ? "材料原文（右栏对照的出处附注源）" : undefined} />
          ) : (
            <div className="rounded-xl border border-zinc-200 bg-white shadow-sm flex flex-col xl:flex-1 xl:min-h-0">
              <Field label={`给定材料${editOpen ? "（编辑中，改后重新评分将清空旧轮次）" : ""}`}>
                <textarea value={materialStr} onChange={(e) => { setMaterialStr(e.target.value); touchConfig(); }} rows={editOpen ? 8 : 7}
                  placeholder="粘贴给定材料全文（评分后按漏点高亮应抄句）"
                  className={ta} />
              </Field>
            </div>
          )}

          {/* 示证档：作答切句对照（只摆配对事实，docs/37 §7.1）*/}
          {alignView && <ChunkStrip r={alignView} />}

          {/* 你的作答：常驻左栏（材料下方，评分后保留可改 → 重评出新 delta 轮）*/}
          <div className="rounded-xl border border-zinc-200 bg-white shadow-sm shrink-0">
            <Field label={current ? `你的作答（第 ${current.no + 1} 轮 · 可改后重新评分对比）` : "你的作答"}>
              <textarea value={answerStr} onChange={(e) => setAnswerStr(e.target.value)} rows={5}
                placeholder="边看材料边写…"
                className={ta} />
            </Field>
            {!showResult && (
              <div className="px-4 pb-3 flex justify-end">
                <button onClick={() => score()} disabled={busy || !answerStr.trim()}
                  className="xl:hidden px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors">
                  {busy ? "评分中…" : "评分"}
                </button>
              </div>
            )}
          </div>
        </div>

        {/* 右栏：题面配置（评分前/编辑中）/ 逐点清单+建议卡（评分后）*/}
        <div className={`flex flex-col gap-3 min-w-0 xl:w-[42%] xl:min-h-0 xl:overflow-y-auto ${inEditArea ? "order-first xl:order-none" : ""}`}>
          {inEditArea ? (
            <div className="rounded-xl border border-zinc-200 bg-white shadow-sm p-4 space-y-3 shrink-0">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-zinc-900">题面配置</p>
                {showResult && (
                  <span className="text-[11px] text-amber-600">改动题干/材料/标准答案 → 重新评分将清空旧轮次（docs/33 D11）</span>
                )}
              </div>
              {/* 模式声明（docs/38 §6）：库题声明 → 门禁；缺省 → 示证 */}
              <div className={`rounded-lg px-3 py-2 text-[11px] leading-relaxed ${trustQid ? "bg-indigo-50 text-indigo-700 border border-indigo-100" : "bg-zinc-50 text-zinc-500 border border-zinc-100"}`}>
                {trustQid ? (
                  <>门禁模式：库题 <b>{trustQid}</b>（载入示例题自带声明，采分点须与库题全量一致才放行）。
                    改动题干/材料/标准答案任一内容会清除声明 → 回到示证模式。</>
                ) : (
                  <>示证模式（未声明库题）：只标注作答与采分点的文本差异，不判好坏、不给建议。
                    想体验门禁三色 → 点「载入示例题」。</>
                )}
              </div>
              <Field label="题干">
                <textarea value={questionStr} onChange={(e) => { setQuestionStr(e.target.value); touchConfig(); }} rows={2} placeholder="粘贴题干…"
                  className={ta} />
              </Field>
              <Field label="标准答案（文字或 JSON）">
                <textarea value={pointsStr} onChange={(e) => { setPointsStr(e.target.value); touchConfig(); }} rows={10}
                  placeholder='粘贴标准答案全文（自动解析为采分点），或直接贴 JSON 数组：[{"id":"c1","point":"...","keywords":["..."],"score":1,"point_type":"对策"}]'
                  // 任务三：文字版不用等宽字体；仅内容为 JSON 数组（手填采分点）时保留 mono
                  className={`${ta} ${pointsStr.trim().startsWith("[") ? "font-mono text-[11px]" : ""}`} />
                {textMode ? (
                  <p className="text-[10px] text-indigo-500 mt-1">已识别为文字模式：点「评分」时自动解析为采分点（JSON 粘贴则原样使用）</p>
                ) : trustQid && samplePoints ? (
                  <p className="text-[10px] text-indigo-500 mt-1">库题文字版：评分直接用题库采分点走门禁（不经解析）；改动文字后会自动转为解析 · 示证对照</p>
                ) : null}
              </Field>

              {/* 解析 trace（开发者可见，docs/24 §5.3）：?dev=1 或 localStorage shenlun_dev=1 */}
              {dev && parseTrace && (
                <details className="rounded-xl border border-amber-200 bg-amber-50/60 px-3 py-2">
                  <summary className="text-[11px] text-amber-700 font-medium cursor-pointer select-none">
                    解析 trace（dev）· 拆出 {parseTrace.points.length} 个点
                  </summary>
                  <div className="mt-2 space-y-2">
                    <div>
                      <p className="text-[10px] text-zinc-400 mb-1">原始答案全文</p>
                      <pre className="whitespace-pre-wrap rounded-lg bg-white border border-amber-100 px-2.5 py-2 text-[11px] text-zinc-700 max-h-40 overflow-y-auto">{parseTrace.standard_answer}</pre>
                    </div>
                    <div>
                      <p className="text-[10px] text-zinc-400 mb-1">拆出的采分点（source_snippet = 原文片段，核验拆点质量）</p>
                      <div className="overflow-x-auto rounded-lg bg-white border border-amber-100">
                        <table className="w-full text-[11px]">
                          <thead>
                            <tr className="text-left text-zinc-400 border-b border-zinc-100">
                              <th className="px-2 py-1.5 font-normal">id</th>
                              <th className="px-2 py-1.5 font-normal">点</th>
                              <th className="px-2 py-1.5 font-normal">关键词</th>
                              <th className="px-2 py-1.5 font-normal">分</th>
                              <th className="px-2 py-1.5 font-normal">角度</th>
                              <th className="px-2 py-1.5 font-normal">原文片段</th>
                            </tr>
                          </thead>
                          <tbody>
                            {parseTrace.points.map((p) => (
                              <tr key={p.id} className="border-b border-zinc-50 align-top">
                                <td className="px-2 py-1.5 text-zinc-400">{p.id}</td>
                                <td className="px-2 py-1.5 text-zinc-800 font-medium">{p.point}</td>
                                <td className="px-2 py-1.5 text-zinc-600">{p.keywords.join("、")}</td>
                                <td className="px-2 py-1.5 text-zinc-600">{p.score}</td>
                                <td className="px-2 py-1.5 text-zinc-600">{p.point_type}</td>
                                <td className="px-2 py-1.5 text-zinc-500">{p.source_snippet || "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                    {parseTrace.warnings.length > 0 && (
                      <div>
                        <p className="text-[10px] text-zinc-400 mb-1">warnings</p>
                        <ul className="text-[11px] text-amber-600 space-y-0.5">
                          {parseTrace.warnings.map((w, i) => (
                            <li key={i}>⚠ {w}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </details>
              )}
              {!showResult && (
                <div className="flex justify-end">
                  <button onClick={() => score()} disabled={busy || !answerStr.trim()}
                    className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors">
                    {busy ? "评分中…" : "评分"}
                  </button>
                </div>
              )}
            </div>
          ) : gateView ? (
            <>
              {/* ── 门禁：逐点清单 + 建议卡（docs/38 §4.3）── */}
                <VerdictList verdicts={gateVerdicts} detail={detail} anchors={anchors}
                  selectedId={selectedId} onPick={pickPoint} />
                {allHit ? (
                  <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 px-4 py-3 text-sm text-emerald-700">
                    🎉 全部命中：{gateVerdicts.length} 个采分点都写到了，无需补写
                    {gateSemanticCount > 0 && `（其中 ${gateSemanticCount} 个经 AI 复核放行，可在行内悬停查看原因）`}。
                  </div>
                ) : (
                  selVerdict &&
                  selBadge && (
                    <VerdictCard v={selVerdict} badge={selBadge}
                      hasSnippet={!!(gold && gold.points.find((p) => p.id === selVerdict.point_id)?.source_snippet)}
                      d={selectedId ? detail[selectedId] : undefined}
                      onAddWrongbook={addToWrongbook} />
                  )
                )}
                <RoundTrace rounds={rounds} />
              </>
          ) : alignView ? (
            <>
              {/* ── 示证：逐点对照（docs/37 §7，只摆证据不判好坏）── */}
              <AlignRight r={alignView} />
              <RoundTrace rounds={rounds} />
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}

// ── header 模式角标（docs/38 §5：门禁模式 / 示证模式）+ 轮次计数 ──
function ModeTag({ submit, no }: { submit: PracticeSubmit; no: number }) {
  if (submit.mode === "gate") {
    const hit = submit.verdicts.filter((v) => v.status === "hit").length;
    const miss = submit.verdicts.filter((v) => v.status === "miss").length;
    const sus = submit.verdicts.filter((v) => v.status === "suspect").length;
    return (
      <span className="inline-flex items-center gap-1.5 shrink-0">
        <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
          门禁模式 · 审过题
        </span>
        <span className="text-xs font-medium px-2.5 py-0.5 rounded-full bg-zinc-100 text-zinc-600">
          第 {no + 1} 轮 · 绿 {hit} · 黄 {miss} · 蓝 {sus}
        </span>
      </span>
    );
  }
  const pairs = submit.alignments.length;
  return (
    <span className="inline-flex items-center gap-1.5 shrink-0">
      <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-zinc-100 text-zinc-600 border border-zinc-200">
        示证模式 · 仅标注差异
      </span>
      <span className="text-xs font-medium px-2.5 py-0.5 rounded-full bg-zinc-100 text-zinc-500">
        第 {no + 1} 轮 · 有对应 {pairs} 组 · 未见对应 {submit.gaps.length} 点
      </span>
    </span>
  );
}

// ── 左栏材料：段落只读渲染 + 黄行应抄句琥珀高亮（docs/33 §3.2 机制沿用）──
// 只服务门禁黄行（status=miss 且有锚）；示证档无高亮（材料只作对照参考）。
function MaterialView({ material, anchors, onPick, caption }: {
  material: string;
  anchors: AnchorTable;
  onPick: (id: string) => void;
  caption?: string;
}) {
  const paras = useMemo(() => {
    const out: { text: string; start: number }[] = [];
    let base = 0;
    for (const line of material.split("\n")) {
      out.push({ text: line, start: base });
      base += line.length + 1;
    }
    return out;
  }, [material]);

  // 段落 → 片段（plain / hl 琥珀实底应抄句）；编号取 anchors.nums（与右栏行一一对应）
  const paraSegs = useMemo(() => {
    type Mark = { kind: "hl"; s: number; text: string; pointId: string; num: string | null };
    type Seg = { kind: "plain" | "hl"; text: string; pointId: string; num: string | null };

    const marksByPara: Mark[][] = paras.map(() => []);
    for (const [pointId, a] of anchors.byPoint) {
      const pi = a.para - 1;
      if (pi < 0 || pi >= paras.length) continue;
      const s = a.start - paras[pi].start;
      const e = a.end - paras[pi].start;
      if (s < 0 || e > paras[pi].text.length || s >= e) continue; // 防御：越界绝不硬标
      marksByPara[pi].push({ kind: "hl", s, text: paras[pi].text.slice(s, e), pointId, num: anchors.nums.get(pointId) ?? null });
    }

    return paras.map((p, pi) => {
      const segs: Seg[] = [];
      const marks = marksByPara[pi].sort((a, b) => a.s - b.s);
      let cursor = 0;
      for (const mk of marks) {
        if (mk.s < cursor) continue; // 与前段重叠 → 丢弃（防叠印/错位）
        if (mk.s > cursor) segs.push({ kind: "plain", text: p.text.slice(cursor, mk.s), pointId: "", num: null });
        segs.push({ kind: mk.kind, text: mk.text, pointId: mk.pointId, num: mk.num });
        cursor = mk.s + mk.text.length;
      }
      if (cursor < p.text.length) segs.push({ kind: "plain", text: p.text.slice(cursor), pointId: "", num: null });
      return segs.length ? segs : [{ kind: "plain" as const, text: p.text, pointId: "", num: null }];
    });
  }, [paras, anchors]);

  // 点材料应抄句 → 选中该点并把右栏建议卡滚进视野（docs/33 交互保留）
  const pickFromMaterial = (pointId: string) => {
    onPick(pointId);
    requestAnimationFrame(() => {
      document.getElementById("sug-card")?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  };

  return (
    <div className="rounded-xl border border-zinc-200 bg-white shadow-sm flex flex-col min-h-0 xl:flex-1 xl:min-h-0">
      <div className="px-4 py-2.5 flex items-center justify-between border-b border-zinc-100 shrink-0">
        <p className="text-sm font-semibold text-zinc-900">给定材料</p>
        <p className="text-[10px] text-zinc-400">{caption ?? "琥珀 = 漏答点的应抄原句（编号对应右栏行，点击看建议）"}</p>
      </div>
      <div className="px-4 py-3 text-sm leading-7 text-zinc-700 xl:overflow-y-auto xl:flex-1 xl:min-h-0">
        {paras.map((p, i) => (
          <p key={i} className={i > 0 ? "mt-2" : ""}>
            {paraSegs[i].map((seg, j) => {
              if (seg.kind === "hl") {
                return (
                  <span key={j} id={`pAnc-${seg.pointId}`}
                    className="whitespace-pre-wrap rounded-sm bg-[#FAEEDA] cursor-pointer"
                    onClick={() => pickFromMaterial(seg.pointId)}
                    title="应抄原句 · 点击查看该点建议">
                    {seg.num && (
                      <span className="inline-flex items-center justify-center w-4 h-4 mr-0.5 rounded-full bg-[#7c5a2e] text-white text-[9px] leading-none align-middle cursor-pointer select-none"
                        onClick={(e) => { e.stopPropagation(); pickFromMaterial(seg.pointId); }}>
                        {seg.num}
                      </span>
                    )}
                    {seg.text}
                  </span>
                );
              }
              return <span key={j} className="whitespace-pre-wrap">{seg.text}</span>;
            })}
          </p>
        ))}
      </div>
    </div>
  );
}

// ── 左栏作答 · 示证切句展示（docs/37 §7.1）：句末标记 ◎/○/~（中性色，不判好坏）──
// 措辞遵守 docs/37 §2.3 禁止词表——本组件不出现 漏答/命中/没写上 等判定词。
function ChunkStrip({ r }: { r: AlignResult }) {
  const orphans = useMemo(() => new Set(r.orphans.map((o) => o.chunk_id)), [r]);
  // chunk → 配对点（kw 行记共现词，semantic 行记相似度）
  const marks = useMemo(() => {
    const m = new Map<number, Array<{ pointId: string; kw?: string[]; sim?: number }>>();
    for (const a of r.alignments) {
      const list = m.get(a.chunk_id) ?? [];
      if (a.method === "kw") list.push({ pointId: a.point_id, kw: a.kws_hit });
      else list.push({ pointId: a.point_id, sim: a.similarity });
      m.set(a.chunk_id, list);
    }
    return m;
  }, [r]);

  return (
    <div className="rounded-xl border border-zinc-200 bg-white shadow-sm shrink-0">
      <div className="px-4 py-2.5 border-b border-zinc-100 flex items-baseline justify-between gap-2">
        <p className="text-sm font-semibold text-zinc-900">你的作答 · 切句对照</p>
        <p className="text-[10px] text-zinc-400">◎ 有对应 · ~ 语义弱对应 · ○ 无对应候选（点句跳右栏对应点）</p>
      </div>
      <div className="px-4 py-2 max-h-56 xl:max-h-64 overflow-y-auto space-y-1.5">
        {r.answer_chunks.length === 0 && <p className="text-xs text-zinc-400 py-1">（作答过短或为空，无切句）</p>}
        {r.answer_chunks.map((c) => {
          const pts = marks.get(c.id) ?? [];
          const isOrphan = orphans.has(c.id);
          return (
            <div key={c.id} id={`pAns-${c.id}`}
              className="text-xs leading-6 text-zinc-700 border-l-2 border-zinc-100 pl-2.5">
              <span className="text-[10px] text-zinc-400 mr-1.5 select-none">句{c.id}</span>
              <span className="whitespace-pre-wrap">{c.text}</span>
              <span className="block text-[10px] mt-0.5">
                {pts.length === 0 && isOrphan ? (
                  <span className="text-zinc-400">○ 该句与所有要点均无明显对应（候选：是否重要、要不要补由你判断）</span>
                ) : (
                  pts.map((p, i) => (
                    <button key={i} type="button" onClick={() => scrollTo(`pRow-${p.pointId}`)}
                      className="mr-2 text-zinc-500 hover:text-indigo-600 hover:bg-indigo-50 rounded px-1 py-px transition-colors"
                      title="跳右栏对应点">
                      {p.kw
                        ? <>◎ 对应点 {p.pointId} · 共现词：{p.kw.join("、")}</>
                        : <>~ 语义弱对应 · 点 {p.pointId}（相似度 {p.sim !== undefined ? p.sim.toFixed(2) : ""}）</>}
                    </button>
                  ))
                )}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function scrollTo(id: string) {
  const el = document.getElementById(id);
  el?.scrollIntoView({ behavior: "smooth", block: "center" });
}

// ── 右栏 · 门禁逐点清单（docs/38 §4.3 / §5 四态徽章）──────────────
// 顺序 = verdicts 顺序（采分点顺序）；绿行不可点（含 AI 复核放行绿）；黄/蓝行点击展开建议卡。
function VerdictList({ verdicts, detail, anchors, selectedId, onPick }: {
  verdicts: PointVerdict[];
  detail: Record<string, PointDetail>;
  anchors: AnchorTable;
  selectedId: string | null;
  onPick: (id: string) => void;
}) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white shadow-sm shrink-0">
      <div className="px-4 py-2.5 border-b border-zinc-100 flex items-baseline justify-between gap-2">
        <p className="text-sm font-semibold text-zinc-900">采分点对账（{verdicts.length} 个）</p>
        <p className="text-[10px] text-zinc-400 text-right">点黄/蓝行看三块建议 · 编号对应左栏应抄句</p>
      </div>
      {/* 四态图例（docs/38 §5）：确定性分级沿用 D33 语义色 */}
      <div className="px-4 pt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-zinc-400">
        <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-600" />命中（关键词全中，规则）</span>
        <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-400" />命中 · AI复核（灰带放行）</span>
        <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-600" />漏答（规则，应抄句已标）</span>
        <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-600" />疑似（AI 判断，供参考）</span>
      </div>
      <div className="px-2 py-2">
        {verdicts.length === 0 && <p className="px-2 py-1 text-xs text-zinc-400">（本题未拆出采分点）</p>}
        {verdicts.map((v) => {
          const sel = v.point_id === selectedId;
          const badge = badgeOfVerdict(v);
          const clickable = v.status !== "hit";
          const num = anchors.nums.get(v.point_id) ?? null;
          return (
            <button key={v.point_id} type="button" disabled={!clickable} onClick={() => onPick(v.point_id)}
              title={clickable ? undefined : v.reason} // 绿行悬停看为什么（放行绿透明可查）
              className={`w-full text-left rounded-lg px-2.5 py-1.5 border flex items-center gap-2 transition-colors ${
                sel ? "bg-indigo-50/70 border-indigo-200" : "border-transparent hover:bg-zinc-50"
              } ${clickable ? "" : "cursor-default"}`}>
              <span className="shrink-0 w-5 flex justify-center">
                {num && (
                  <span className="inline-flex items-center justify-center h-4 min-w-4 px-0.5 rounded-full bg-[#7c5a2e] text-white text-[10px] font-medium leading-none select-none">
                    {num}
                  </span>
                )}
              </span>
              <span className={`min-w-0 flex-1 truncate text-[13px] ${sel ? "font-medium text-indigo-700" : clickable ? "font-medium text-zinc-800" : "text-zinc-500"}`}>
                {v.point_name}
              </span>
              {detail[v.point_id]?.added && <span className="shrink-0 text-[10px] text-emerald-600">✓ 已入错题本</span>}
              <span className={`shrink-0 text-[10px] font-semibold px-2 py-0.5 rounded-full border ${badge.cls}`}>
                {badge.label}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── 右栏 · 门禁建议卡（docs/38 §4.3 三块：① 为什么标 / ② 原文 / ③ 改进建议）──
// ①② 纯数据回放（评分响应已含，0 token）；③ 点开懒加载 1 次 LLM（候选措辞）。
// 黄行（miss）有错题本按钮（cause = 规则 reason，不拉 LLM demo）；蓝行不给。
function VerdictCard({ v, badge, hasSnippet, d, onAddWrongbook }: {
  v: PointVerdict;
  badge: VerdictBadge;
  hasSnippet: boolean;
  d?: PointDetail;
  onAddWrongbook: (id: string) => void;
}) {
  const g = d?.guidance;
  const loading = !!d?.loadingG && !g;
  const miss = v.status === "miss";

  return (
    <div id="sug-card" className="rounded-xl border border-zinc-200 bg-white shadow-sm shrink-0">
      <div className="px-4 py-2.5 border-b border-zinc-100 flex items-center gap-2">
        <span className={`shrink-0 text-[10px] font-semibold px-2 py-0.5 rounded-full border ${badge.cls}`}>
          {badge.label}
        </span>
        <p className="text-sm font-semibold text-zinc-900 min-w-0 truncate">{v.point_name}</p>
        {d?.added && <span className="shrink-0 text-[10px] text-emerald-600">✓ 已入错题本</span>}
      </div>
      <div className="px-4 py-3 space-y-2 text-xs text-zinc-700">
        {/* ① 为什么标（随评分响应，0 token）：规则文案或 LLM reason（D47 ①）*/}
        <div>
          <p className="text-[11px] font-medium text-zinc-900">① 为什么标</p>
          <p className="text-xs text-zinc-600 mt-0.5">{v.reason}</p>
          {v.status !== "miss" && v.evidence && (
            <p className="text-xs text-zinc-500 mt-1">
              <span className="text-zinc-400">作答原句：</span>
              <span className="whitespace-pre-wrap">「{v.evidence}」</span>
            </p>
          )}
          {v.status !== "hit" && (
            <p className="text-[10px] text-zinc-400 mt-1">
              规则证据：{v.terms.matched.length ? `命中「${v.terms.matched.join("、")}」 · ` : ""}缺失「{v.terms.missing.join("、")}」
            </p>
          )}
        </div>
        {/* ② 标准答案原文（D46 兜底：source_snippet ?? 材料锚句，0 token）*/}
        <div>
          <p className="text-[11px] font-medium text-zinc-900">② 官方写法{hasSnippet ? "" : "（此题答案≈材料句）"}</p>
          {v.official ? (
            <p className="whitespace-pre-wrap text-xs text-zinc-600 mt-0.5">{v.official}</p>
          ) : (
            <p className="text-xs text-zinc-300 mt-0.5">（该点无官方原句，请结合采分点名称与关键词自行组织）</p>
          )}
        </div>
        {/* ③ 改进建议（候选）：点开懒加载 1 次 LLM（docs/38 §4.3 / §7 runtime 收敛）*/}
        <div>
          <p className="text-[11px] font-medium text-zinc-900">③ 改进建议（候选）</p>
          {loading ? (
            <p className="text-xs text-zinc-300 mt-0.5">生成中…</p>
          ) : g ? (
            (g.gap || g.how || g.rewrite) ? (
              <div className="mt-1 space-y-1 text-xs text-zinc-600">
                {g.gap && <p><span className="text-zinc-400">差距：</span>{g.gap}</p>}
                {g.how && <p><span className="text-zinc-400">怎么补：</span>{g.how}</p>}
                {g.rewrite && <p><span className="text-zinc-400">示范改写：</span>{g.rewrite}</p>}
                <p className="text-[10px] text-zinc-300">（供参考，以官方答案为准）</p>
              </div>
            ) : (
              <p className="text-xs text-zinc-300 mt-0.5">（未生成，请对照②官方写法自行组织）</p>
            )
          ) : (
            <p className="text-xs text-zinc-300 mt-0.5">点开时生成…</p>
          )}
        </div>
        {/* 错题本（黄行规则可证才收；蓝行 AI 判断不硬收）*/}
        {miss && (
          <div className="pt-2 border-t border-zinc-100 flex items-center gap-2">
            <button onClick={() => onAddWrongbook(v.point_id)} disabled={d?.added}
              className="text-[11px] px-2 py-1 rounded-md bg-zinc-900 text-white hover:bg-zinc-700 disabled:opacity-50">
              {d?.added ? "✓ 已入错题本" : "＋ 错题本"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── 右栏 · 示证逐点对照（docs/37 §7.3 文案照抄：只陈述可复核的配对事实）──
// 禁止词（37 §2.3）约束：本组件文案不出现 漏答/命中/没写上/答非所问/偏离/套话/宽泛/
// 表述不清/建议你补/你应该写——一律「未见对应句（候选）」+ 共现词 / 相似度数字。
function AlignRight({ r }: { r: AlignResult }) {
  const byPoint = useMemo(() => {
    const m = new Map<string, typeof r.alignments>();
    for (const a of r.alignments) {
      const list = m.get(a.point_id) ?? [];
      list.push(a);
      m.set(a.point_id, list);
    }
    return m;
  }, [r]);
  const gapSim = useMemo(() => new Map(r.gaps.map((g) => [g.point_id, g.max_similarity])), [r]);
  const officialById = useMemo(() => new Map(r.official_points.map((p) => [p.id, p])), [r]);

  return (
    <div className="rounded-xl border border-zinc-200 bg-white shadow-sm shrink-0">
      <div className="px-4 py-2.5 border-b border-zinc-100 flex items-baseline justify-between gap-2">
        <p className="text-sm font-semibold text-zinc-900">采分点对照（{r.official_points.length} 个）</p>
        <p className="text-[10px] text-zinc-400 text-right">只摆证据不判好坏 · 点行跳左栏作答句</p>
      </div>
      <div className="px-4 pt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-zinc-400">
        <span>◎ 有对应（共现词）</span>
        <span>~ 语义弱对应（相似度数字）</span>
        <span>○ 未见对应句（候选）</span>
      </div>
      <div className="px-3 py-2 space-y-1.5">
        {r.official_points.map((p) => {
          const items = byPoint.get(p.id) ?? [];
          const sim = gapSim.get(p.id) ?? null;
          const isGap = items.length === 0;
          return (
            <div key={p.id} id={`pRow-${p.id}`}
              className="rounded-lg px-3 py-2 border border-zinc-100 bg-zinc-50/50">
              <p className="text-[13px] font-medium text-zinc-800">
                {p.id} · {p.point}
                <span className="ml-1.5 text-[10px] text-zinc-400 font-normal">{p.keywords.join("、")}</span>
              </p>
              {/* 官方原句 + 材料出处（§5.4：展示锚，不进配对主链）*/}
              <p className="text-[11px] text-zinc-600 mt-0.5">
                <span className="text-zinc-400">官方原句：</span>
                {p.official_sentence ?? "（未提供官方原句）"}
              </p>
              <p className="text-[11px] text-zinc-600">
                <span className="text-zinc-400">材料出处：</span>
                {p.material_ref ?? "该点无直接材料出处（需自行概括）"}
              </p>
              {/* 配对状态（§7.3 文案照抄）*/}
              <div className="mt-1 space-y-0.5 text-[11px] text-zinc-600">
                {isGap ? (
                  <p>○ 作答中未见包含该点关键词的句子
                    <span className="text-zinc-400">（候选：请自行判断是否重要、要不要补）</span>
                    {sim !== null && sim !== undefined && (
                      <span className="text-zinc-400"> · 语义最近句相似度 {sim.toFixed(2)}</span>
                    )}
                  </p>
                ) : (
                  items.map((a, i) => (
                    <button key={i} type="button" onClick={() => scrollTo(`pAns-${a.chunk_id}`)}
                      className="block text-left hover:text-indigo-600 hover:bg-indigo-50 rounded px-1 py-px transition-colors"
                      title="跳左栏对应作答句">
                      {a.method === "kw" ? (
                        <>◎ 有对应：作答句 {a.chunk_id} 含关键词 {a.kws_hit?.join("、")}</>
                      ) : (
                        <>~ 语义弱对应：作答句 {a.chunk_id} 语义相近（相似度 {a.similarity !== undefined ? a.similarity.toFixed(2) : ""}），无关键词重叠</>
                      )}
                    </button>
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── 轮次轨迹（透明）：门禁数三色 / 示证数配对（文档措辞分域）──────
function RoundTrace({ rounds }: { rounds: Round[] }) {
  const showDelta = rounds.length >= 2 && rounds.some((r) => r.submit.mode === "gate");
  return (
    <div className="space-y-2 shrink-0">
      {showDelta && isGate(rounds[rounds.length - 1].submit) &&
        (() => {
          const prev = rounds[rounds.length - 2].submit;
          const cur = rounds[rounds.length - 1].submit;
          if (!isGate(prev) || !isGate(cur)) return null;
          const was = new Map(prev.verdicts.map((v) => [v.point_id, v.status]));
          const gained = cur.verdicts.filter((v) => v.status === "hit" && was.get(v.point_id) !== "hit");
          if (!gained.length) return null;
          return (
            <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-2 text-xs text-emerald-700">
              🎉 本轮新绿：{gained.map((v) => v.point_name).join("、")}
            </div>
          );
        })()}
      {rounds.length > 1 && (
        <details className="rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-2">
          <summary className="text-xs text-zinc-500 cursor-pointer">评分过程（{rounds.length} 轮轨迹，全透明）</summary>
          <div className="mt-2 space-y-1.5">
            {rounds.map((r) => {
              const s = r.submit; // identifier 判别窄化（TS 联合）
              return (
                <div key={r.no} className="text-[11px] text-zinc-500">
                  <span className="font-medium text-zinc-700">第 {r.no + 1} 轮</span>
                  {s.mode === "gate" ? (
                    <>
                      · 绿 {s.verdicts.filter((v) => v.status === "hit").length}
                      · 黄 {s.verdicts.filter((v) => v.status === "miss").length}
                      · 蓝 {s.verdicts.filter((v) => v.status === "suspect").length}
                    </>
                  ) : (
                    <> · 有对应 {s.alignments.length} 组 · 未见对应 {s.gaps.length} 点 · 无对应句 {s.orphans.length} 句</>
                  )}
                </div>
              );
            })}
          </div>
        </details>
      )}
    </div>
  );
}

const ta = "w-full rounded-xl border border-zinc-200 bg-white px-3.5 py-2.5 text-sm text-zinc-800 outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-400 placeholder:text-zinc-300";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="px-4 pt-3">
      <p className="text-[11px] text-zinc-400 mb-1">{label}</p>
      {children}
    </div>
  );
}
