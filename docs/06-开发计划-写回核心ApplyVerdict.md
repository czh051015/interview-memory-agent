# 开发计划：写回核心 `apply_verdict` + `feedback` 专用字段

> 关联文档：`05-重构方案-模拟面试模块化.md`（本计划 = 该文档的 **Phase 1 + 决策项 §5 选 A** 的落地细化）
> 决策已定：**方案 A** —— 面试官单题反馈写进**专用 `feedback` 字段**，不复用 `answer`；前后端写回逻辑合一。
> 范围锁定：**仅后端**（含 REST API 层 `app/api/mock.py`，它属服务端不属于浏览器前端）。浏览器 JS 零改动。

---

## 1. 目标

1. 消除 CLI（`scripts/run_mock_interview.py`）与 Web（`app/api/mock.py::mock_complete`）**写回逻辑重复 + 行为分叉**这一真实 bug。
2. 把"一次判定 → 掌握度涨跌 + 新题采集 + review_log + 行为标签合并"抽成**单一共享核心** `src/mock/writeback.py::apply_verdict`。
3. 面试官单题反馈（要点 + 漏答 + 评语）沉淀到**专用 `feedback` 字段**，语义清晰、不污染 `answer`（其定义为"面经自带参考答案"）。
4. **前端契约不变**：`/mock/start|verdict|followup|complete` 端点路径、请求/响应 JSON 字段名与类型全部保持原样 → 浏览器前端零改动。

---

## 2. 已核准的事实（写计划前已读代码确认）

| 事实 | 位置 | 影响 |
|---|---|---|
| `KnowledgeItem` 目前**无 `feedback` 字段** | `src/cleaner/schema.py:33-59` | 需新增 |
| store 用**显式字段列表**（非动态序列化）：`_to_metadata` 写、`_parse_results` 读 | `src/memory/knowledge_store.py:385-406, 467-488` | 加字段须**同步改这两处**，否则不持久化/读不回 |
| 旧数据缺 `feedback` key → `_parse_results` 用 `.get(..., "")` 兜底，**无需迁移脚本** | `knowledge_store.py:457-465` 同模式 | 向后兼容 |
| CLI result 字典字段：`question/source/topic/item/performance/answer/transcript`（**无 points/misses/reason**） | `run_mock_interview.py:835-840` | CLI 需补传 `points/misses/reason` 才能生成 feedback |
| Web `MockResult` **已带** `points/misses/reason` | `app/api/mock.py:82-92` | Web 侧直接可用 |
| CLI 写回三段：`_write_back` → `store_items` → `_log_write_back` | `run_mock_interview.py:977-979` | 由 `apply_verdict` 合一 |
| Web `mock_complete` 内联重写写回（250-256 把 feedback 追加进 `item.answer`） | `app/api/mock.py:225-316` | 改委托 `apply_verdict`，删除内联 |
| CLI actor=`"mock_interview"`，Web actor=`"mock_interview_web"` | `run_mock_interview.py:552` / `mock.py:313` | 统一为 `mock_interview` |
| `_feedback_text(performance, judge)` 拼装反馈文本 | `run_mock_interview.py:503-521` | 复用，仅改落点（→feedback 而非 answer） |
| `_collect_new_item(r)` 新题 `answer=r.get("feedback")` | `run_mock_interview.py:482-500` | 方案 A：改设 `feedback=r.get("feedback")`，`answer` 留空（更干净） |

---

## 3. 接口契约

### 3.1 `KnowledgeItem` 新增字段
```python
# src/cleaner/schema.py（KnowledgeItem 内，约 48 行后）
feedback: str = Field(default="", description="模拟面试面试官反馈（单题：要点+漏答+评语），来源可追溯，不复用 answer")
```

### 3.2 `knowledge_store` 持久化（两处必改）
- `_to_metadata`（约 405 行）：增加 `"feedback": item.feedback  # 不截断，或 [:4000] 防 Chroma metadata 过大`
- `_parse_results`（约 485 行构造处）：增加 `feedback=meta.get("feedback", "")`

> ⚠️ Chroma 对 metadata 单值有大小限制，feedback 文本较长时建议截断（如 4000 字符）。与 `user_note[:200]` 同理但放宽。

### 3.3 共享核心签名
```python
# src/mock/writeback.py
def apply_verdict(
    results: list[dict],
    behaviors: list[str],
    space: str = "default",
) -> tuple[int, int]:
    """统一写回核心（替代 CLI _write_back+_log_write_back+store，及 Web mock_complete 内联）。

    results 元素（归一化后）字段：
      question: str
      source: str            # weak 写回错题；其余来源答差→自动采集
      topic: str
      performance: str      # pass|partial|fail
      points: list[str]     # 期望要点（生成 feedback 用）
      misses: list[str]     # 漏答点
      reason: str           # 评语
      item: KnowledgeItem | None   # weak 题的原题快照；新题为 None
      space: str

    行为：
      1. weak 且 item 有值 → record_result（mastery 涨跌 + 合并 behaviors 行为标签）
         并写 item.feedback = _feedback_text(performance, {points,misses,reason})；**不改 answer**
      2. 非 weak 且 performance∈{fail,partial} → _collect_new_item（feedback 字段填 judge 文本，answer 留空）
      3. 一次性 store_items(updated + new)（"失败不半写"）
      4. 对每个 weak updated 写 review_log（actor="mock_interview"）
    返回 (updated_count, new_count)
    """
```

### 3.4 CLI 侧适配
- `interview_one` / `main` 组装 result 字典时，**补传 `points/misses/reason`**（来自 `judge` 结果），字段名对齐 Web，便于共用 `_feedback_text`。
- `main()` 写回段（977-979）改为：
  ```python
  updated, new = apply_verdict(results, behaviors, space=_cfg.SPACE)
  ```
  删除原 `_write_back` / `_log_write_back` / `store_items` 三行调用（逻辑已内聚进 `apply_verdict`）。
- 保留 `_write_back` 作为**薄壳**（返回 `(updated, new)` 列表、不落库），供 `test_mock_interview.py` 现有用例兼容；其体内调用 `_build_writeback_items`（纯函数，被 `apply_verdict` 复用）。`_log_write_back` 删除（逻辑移入 `apply_verdict`）。

### 3.5 Web 侧适配（`app/api/mock.py`）
- `mock_complete`（225-316）删除 238-316 内联写回，改为：
  ```python
  norm = [{
      "question": r.question, "source": r.source, "topic": r.topic,
      "performance": r.verdict, "points": r.points, "misses": r.misses,
      "reason": r.reason, "item": get_by_id(r.question_id), "space": req.space,
  } for r in req.results]
  updated, new = apply_verdict(norm, behaviors, req.space)
  return MockCompleteResponse(updated=updated, new=new, behaviors=behaviors)
  ```
- 删除 `from scripts.run_mock_interview import _feedback_text, _collect_new_item` 等写回相关 import（保留出题/判卷 import）。
- `MockResult` / `MockCompleteRequest` / `MockCompleteResponse` **结构不动**（前端契约不变）。
- `summarize_behaviors` 仍在 `mock_complete` 调用（它在写回前、用于生成 behaviors），保留。

---

## 4. 实施任务清单（建议提交顺序）

| # | 任务 | 文件 | 风险 |
|---|---|---|---|
| T1 | `KnowledgeItem` 增 `feedback` 字段 | `src/cleaner/schema.py` | 低 |
| T2 | store `_to_metadata` + `_parse_results` 加 feedback | `src/memory/knowledge_store.py` | 低（向后兼容） |
| T3 | 新建 `src/mock/__init__.py` + `writeback.py`（`apply_verdict` + `_build_writeback_items`） | 新文件 | 中（核心逻辑） |
| T4 | CLI：result 字典补 `points/misses/reason`；`_collect_new_item` 改设 `feedback`；`_write_back` 转薄壳；`main` 改调 `apply_verdict` | `scripts/run_mock_interview.py` | 中 |
| T5 | Web：`mock_complete` 改委托 `apply_verdict`，删内联 + 多余 import | `app/api/mock.py` | 中 |
| T6 | 补 `tests/test_mock_writeback.py`（锁死：weak 写 feedback 不改 answer / 新题采集 feedback / actor 统一 / 行为标签合并 / 幂等） | 新文件 | 低 |
| T7 | 跑测试验证前端契约 | pytest | — |

> 注：本计划**不拆包**（Phase 2 的 `src/mock/plan|runtime|judge|report` 拆分不在本次范围）；`scripts/run_mock_interview.py` 与 `app/api/mock.py` 继续 import 关系，仅把写回复用逻辑迁到 `src/mock/writeback.py`。

---

## 5. 行为裁决（方案 A 的唯一行为变更，需用户知情）

| 项 | 旧（分叉） | 新（统一，方案 A） |
|---|---|---|
| weak 题 feedback 落点 | CLI 不写；Web 写进 `answer` | **统一写 `feedback` 字段，`answer` 保持原题值不动** |
| 新题（答差）feedback | CLI `answer` 空；Web `answer`=judge | **统一写 `feedback`=`judge`，`answer` 留空**（更干净） |
| review_log actor | CLI `mock_interview` / Web `mock_interview_web` | **统一 `mock_interview`** |
| 行为标签合并 | CLI 在 record_result 内；Web 循环外单独合并 | **统一在 `apply_verdict` 内对 weak 题合并** |

> 这是本次重构**唯一的行为变更**：浏览器用户会看到"面试官反馈"现在在 `feedback` 字段而非混在 `answer` 里；由于 `feedback` 不进任何 Pydantic 响应模型，**前端 JSON 完全无感**。

---

## 6. 测试策略

**新增 `tests/test_mock_writeback.py`（核心，锁死共享逻辑）：**
- `test_weak_fail_writes_feedback_not_answer`：weak fail → `item.feedback` 含"漏掉的"、`item.answer` 不变。
- `test_weak_pass_no_feedback_noise`：weak pass → feedback 为空或仅要点，mastery 涨。
- `test_new_item_collected_with_feedback`：非 weak + fail → 进 `new`，`feedback`=judge，`answer`=""。
- `test_behavior_tags_merged`：behaviors 合并进 weak 题 `behavior_tags`。
- `test_review_log_actor_unified`：review_log 记 `actor="mock_interview"`。
- `test_idempotent_rerun`：同结果二次调用，`review_count` / mastery 不重复涨（依赖 store upsert 幂等）。

**回归（验证前端契约未破，无需开浏览器）：**
- `pytest tests/test_mock_api.py` —— 直接打 4 个端点，等于前端契约代理测试。
- `pytest tests/test_mock_interview.py tests/test_mock_interview_recover.py` —— CLI 生命周期 + 断点恢复。
- `pytest tests/test_decompose.py tests/test_pipeline.py` —— 确认 cleaner 改动无回归（本计划不动 cleaner，但防误伤）。

---

## 7. 风险与回滚

| 风险 | 缓解 |
|---|---|
| store 显式字段易漏改 → feedback 持久化失效 | T2 两处同改 + T6 测试覆盖读写往返 |
| CLI result 漏传 points/misses/reason → feedback 空 | T4 在 `interview_one` 组装处加字段 + 单测断言 |
| `apply_verdict` 内 store 失败 → 部分写入 | 沿用原"一次性 store_items(updated+new)"原子 upsert；失败不写 review_log（与原 `_log_write_back` 调用顺序一致） |
| 旧数据无 feedback key | `.get("feedback","")` 兜底，无需迁移 |
| 误改前端 JSON | 不改任何 Pydantic 模型字段名/类型；`test_mock_api.py` 全绿即证明 |

**回滚**：`apply_verdict` 为纯新增模块 + 两处小改（schema/store）；一旦异常，`git revert` 对应提交即可，无数据迁移需回滚。

---

## 8. 验收标准

- [ ] `KnowledgeItem.feedback` 存在且经 store 往返不丢。
- [ ] CLI 跑一场面试，`grep` 落库 item：`feedback` 有内容、`answer` 未被 feedback 污染。
- [ ] Web `/mock/complete` 写入结果与 CLI 行为一致（同 actor、同 feedback 落点）。
- [ ] `test_mock_writeback.py` 全过；`test_mock_api.py` + `test_mock_interview*` 全过。
- [ ] 浏览器前端未改动任何文件，契约不变。

---

## 9. 后续（不在本次范围）

- **Phase 2**：把 `scripts/run_mock_interview.py`（1032 行）按生命周期拆成 `src/mock/{plan,runtime,judge,report,cli}.py` + `prompts.py`，`scripts` 留薄壳兼容 `test_mock_*` import。
- **Phase 3**：迁移 `eval/mock_interview_eval.py`、三个 test 的 import、`offerloop.py:29`、文档引用到 `src.mock`，删壳。
- **独立优化**：是否把 `MockQuestion`/`_to_question` 的 Web 专属展示逻辑也下沉（当前留在 `app/api/mock.py` 不动）。
