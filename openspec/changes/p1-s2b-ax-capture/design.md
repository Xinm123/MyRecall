## Context

P1-S2a 已经把 Host 侧主触发链路切换为事件驱动：`openrecall/client/recorder.py` 中的 `ScreenRecorder.run_capture_loop()` 负责 `capture_trigger` 消费、monitor 刷新、截图、`TriggerEventChannel` 背压计数上报，以及 `PermissionStateMachine` 的权限降级闭环；`openrecall/client/events/base.py`、`openrecall/client/events/macos.py`、`openrecall/client/events/permissions.py` 已经交付了 `idle` / `app_switch` / `manual` / `click`、`device_name` monitor 绑定基础、以及 `granted` / `transient_failure` / `denied_or_revoked` / `recovering` 四态状态机。与此同时，`openrecall/client/spool.py` 与 `openrecall/client/v3_uploader.py` 已经提供 Host spool 与 `/v1/ingest` 上传路径，`openrecall/server/api_v1.py` 与 `openrecall/server/database/frames_store.py` 已经负责 v3 主链路的 ingest 校验、`frames` 写入、queue/status 与 `/v1/health` 可观测性。

当前缺口也很明确：代码库里还没有 `openrecall/client/accessibility/`，`ScreenRecorder` 仍只在截图后构造 `active_app/active_window` 元数据并直接 `spool.enqueue()`，`openrecall/server/api_v1.py` 目前只强制校验 `capture_trigger`，`FramesStore.claim_frame()` 只提取 `timestamp/app_name/window_name/browser_url/focused/device_name/capture_trigger/event_ts`，尚未承担 `accessibility_text` / `content_hash` required-key 契约。这意味着 P1-S2b 不是重新发明一条采集链路，而是要把 AX 遍历、`focused_context` 一致性、Browser URL stale rejection、`content_hash` canonicalization 与 Host dedup 精确插入到现有 v3 主链路中，并把当前单队列 recorder 结构收敛为更接近 screenpipe 的 `TriggerBus(broadcast) -> MonitorWorker[N]` paired-capture 模型，同时保证 S2b 只负责 raw handoff correctness，不越界承担 P1-S3 的 `text_source` 与 OCR fallback 语义。

还存在一个必须在设计中显式收口的现状偏差：`openrecall/client/events/base.py` 的 `TriggerEvent` 当前把 `device_name` 作为事件载荷的一部分，而 `openrecall/client/events/macos.py` 的 click / app_switch 事件源也会在源头直接填入 `device_name`。这与 OQ-040 冻结的“event source 仅发 `capture_trigger`，`device_name` 必须由 monitor worker 在消费 trigger、执行截图时绑定”存在张力，因此本设计必须把“当前实现如何过渡到 frozen rule”写清楚，而不是默认沿用现状。

本设计严格遵循 `docs/v3/spec.md` > `docs/v3/data-model.md` > `docs/v3/open_questions.md` > `docs/v3/acceptance/phase1/p1-s2b.md` > `docs/v3/gate_baseline.md` 的优先级；若引用 screenpipe，对照路径使用 `docs/v3/references/screenpipe-p1-s2b-validation.md` 中已经冻结的审计锚点，例如 `crates/screenpipe-server/src/paired_capture.rs`、`crates/screenpipe-accessibility/src/tree/mod.rs`、`crates/screenpipe-accessibility/src/tree/macos.rs`、`crates/screenpipe-server/src/event_driven_capture.rs`。

## Goals / Non-Goals

**Goals:**

- 在 `ScreenRecorder` 的单次 capture cycle 内引入新的 AX 采集阶段：截图完成后、写入 spool 前，执行 macOS AXUIElement 遍历，产出 `accessibility_text`、`focused_context`、`browser_url` 与 `content_hash`，并保持 `capture_trigger` 与 `device_name` 继续沿用 P1-S2a 的 frozen 语义。
- 在 Host 侧落实 `accessibility_text` / `content_hash` raw handoff 契约：`accessibility_text` required string（允许 `""`，禁止 `null`），`content_hash` required nullable string（允许 `null`，禁止 `""`），空 AX 必须 no-drop 上传，partial AX text 必须按最终上报值计算 `content_hash`。
- 在 `openrecall/client` 与 `openrecall/server` 之间收口 `focused_context = {app_name, window_name, browser_url}`、`device_name`、Browser URL stale rejection 与 permissions 的 ownership boundary，确保 S2b 只处理 capability / frozen metadata / raw handoff correctness，而不引入任何 S3 的 processing-stage meaning。
- 在 Host 侧把 `content_hash` canonicalization、非 `idle` / `manual` 的 dedup、`inter_write_gap_sec` 证据口径、`ax_hash_eligible` 分母语义与 `broken_window` 窗口标记设计成可验证的数据流，供后续测试与收口脚本直接取证。
- 在 `openrecall/server/api_v1.py`、`openrecall/server/database/frames_store.py` 和 `/v1/health` 现有结构上增量扩展 S2b 需要的字段与可观测性，同时保持 v3-only 主链路，明确 legacy `/api/*` 不承载新的 S2b 规则。

**Non-Goals:**

- OCR fallback、`text_source` 最终判定、`accessibility` / `ocr_text` 分表写入语义、`failed` 处理语义（这些都属于 P1-S3，S2b 只输出 raw handoff）
- 引入新的 trigger 类型或回退到固定轮询；`capture_trigger` 仅继续使用 `idle`、`app_switch`、`manual`、`click`
- Windows/Linux AX 采集实现
- 为 legacy `/api/*` 端点追加 S2b 功能语义；兼容路径只做回归，不做证明链路
- 在本阶段承诺新的 UI 页面；S2b 只要求既有 `#mr-health`、`data-state`、timeline 证据口径可承载 permission / capture 可观测性

## Design Closure Summary

本节是 S2b 实现与验收的单一解释入口；后续各 decision / task / spec 如有展开，均必须服从这里的表述，不得另行改写 owner、边界或 proof 语义。

- **Trigger topology**：S2b 统一采用 `TriggerSource -> TriggerBus(broadcast) -> MonitorWorker[N]`。trigger source 只发布 `TriggerIntent`，不拥有最终 monitor truth；每个 `MonitorWorker` 独占一个 monitor binding，并在同一 capture cycle 内完成 screenshot、AX snapshot、URL、hash、dedup 与 outcome 判定。
- **Field owner**：`event_device_hint` 只属于 trigger source/internal routing；`final_device_name` 只属于 capture-time monitor binding，且是唯一允许进入 payload、spool、frames、dedup bucket、acceptance SQL 与 Gate evidence 的 `device_name` truth；`app_name/window_name/browser_url` 只属于同轮 `focused_context` snapshot；`accessibility_text/content_hash` 只属于同轮 AX walker + hash 阶段。允许缺失，不允许由 alias fallback、跨轮 snapshot、uploader 或 server 默认补全后伪装为同轮 truth。
- **Permission boundary**：S2b 的权限状态机只表达 AX capability，不表达 screenshot path 总开关。`transient_failure` 只计入连续失败统计，不改变本轮 paired capture owner；只有 `denied_or_revoked` / `recovering` 才进入 capability-blocked 语义。权限 degraded 时，screenshot 与 heartbeat 必须继续；AX walk、browser URL、content-hash 驱动的 dedup 必须停止并按 capability-blocked 语义输出。任何 screen-recording 或其他 screenshot-path 故障都不得被重命名为 `permission_blocked`。
- **Outcome layering**：`capture_completed`、`ax_empty`、`ax_timeout_partial`、`browser_url_rejected_stale`、`permission_blocked`、`dedup_skipped`、`spool_failed` 属于 Host recorder 的 pre-upload outcome；`schema_rejected` 只属于 uploader / `/v1/ingest` contract failure；S2b outcome 只表达 raw handoff、capability、transport 与 contract 事实，不表达 S3 semantic interpretation。
- **Proof-filter owner**：S2b proof sample 集合只允许由 acceptance/evidence aggregation 层的单一 mechanized filter 生成。Host runtime 与 Edge ingest 负责输出原始信号和可区分分类，但不各自裁定最终 proof truth。alias-only payload、mixed-version observation、`broken_window=true` 窗口、以及仅靠 compatibility fallback 才补齐 canonical keys 的样本，一律不得进入 S2b Gate proof。`p1-s2b-proof-filter.json` 是唯一权威 proof 样本清单，SQL、health snapshot 与 UI evidence 只能在该清单定义的 included/eligible universe 内解释。

## Decisions

### D1：S2b 采用“broadcast trigger + per-monitor paired capture worker”结构，而不是把 AX 采集拆到 uploader 或 server

**选择**：`openrecall/client/recorder.py` 继续作为 Host capture orchestration owner，但不再把所有 monitor capture 串在单个消费循环里。S2b 将其收敛为 `TriggerSource -> TriggerBus(broadcast) -> MonitorWorker[N]`：trigger source 只发布 `TriggerIntent`；每个 `MonitorWorker` 绑定单个 `MonitorDescriptor`，在本 worker 的 capture cycle 中完成“接收 trigger -> 绑定 `final_device_name` -> screenshot -> AX 遍历 -> `focused_context` / `browser_url` / `content_hash` 组装 -> Host dedup -> `spool.enqueue()`”。`openrecall/client/v3_uploader.py` 继续只负责上传已经冻结好的 payload，`openrecall/server/api_v1.py` 只负责 wire contract 校验与持久化。

**理由**：

- 当前 recorder 已掌握 trigger source、monitor registry、权限与 heartbeat，因此最适合作为 TriggerBus/worker 生命周期 owner；而真正的 paired capture truth 必须下沉到 per-monitor worker，才能让 `final_device_name`、dedup bucket 与 `inter_write_gap_sec` 真正按 monitor 分桶，而不是按单循环里的事件 hint 分桶。
- `openrecall/client/spool.py` 当前的 `.jpg + .json` 落盘已经是 Host side truth；在落盘前补齐 `accessibility_text` / `content_hash`，才能让 mixed-version 样本与 `last_write_time` 语义保持可审计。
- `openrecall/server/api_v1.py` 现有职责是校验 `capture_trigger` + claim frame，不适合承担 browser_url stale rejection 或 AX timeout partial-text 聚合，否则会把 Host capability failure 与 Edge persistence 混为一层。

**trigger topology（锁定）**：

- `TriggerSource`：产生 `TriggerIntent{capture_trigger, event_ts, event_device_hint?, trigger_metadata}`，不拥有最终 monitor truth。
- `TriggerBus`：broadcast fan-out，不因某个 monitor 慢而阻塞其它 monitor；容量与 lag 观测由 Host 统一暴露。
- `MonitorWorker[N]`：单 monitor owner，消费同一份 `TriggerIntent`，决定是否对本 monitor 执行 paired capture；只有它可以写出 `final_device_name`。
- `Uploader`：只转发 worker 已冻结的 payload。

**capture cycle（锁定）**：`capture_trigger` 到达 -> TriggerBus fan-out -> monitor worker 绑定 `final_device_name` -> screenshot -> 单轮 AX snapshot 产出 `focused_context` -> Browser URL 提取 / stale rejection -> `accessibility_text` canonicalization -> `content_hash` 计算 -> Host dedup 判定 -> `spool.enqueue()` -> `v3_uploader.py` 上传 -> `api_v1.py` 校验并持久化 raw handoff。

**screenpipe 对照**：`crates/screenpipe-server/src/paired_capture.rs` — `aligned`。MyRecall 的实现位置在 Python Host，但依旧遵循“单次事件触发内同时完成 screenshot + AX tree walk”的 paired capture 原则。

### D2：新增 `openrecall/client/accessibility/` 包，按“walker / browser_url / hash / coordinator”拆分，而不是把 AX 逻辑塞回 `events/` 或 `recorder.py`

**选择**：新增以下模块：

- `openrecall/client/accessibility/macos.py`：AXUIElement walker、text extraction、snapshot 结构
- `openrecall/client/accessibility/browser_url.py`：Tier 1/2/3 URL 提取与 stale rejection
- `openrecall/client/accessibility/hash.py`：canonicalization + SHA256 `content_hash`
- `openrecall/client/accessibility/types.py`：AX snapshot / focused-context dataclass
- `openrecall/client/accessibility/service.py`：给 `ScreenRecorder` 调用的高层入口，串联 walker、URL、hash 和 empty-AX 语义

**理由**：

- `openrecall/client/events/` 已经专注 trigger / permission / monitor 事件基础设施；把 AX 树遍历放进去会让“何时触发”与“触发后采什么”两个问题再次耦合。
- `recorder.py` 当前已接近 orchestration 层；若继续把 AX 细节塞进去，会把 timeout、标题匹配、canonicalization 和 metrics 混成大块条件分支，既不利于 TDD，也不利于后续 P2 平台扩展。
- 按 service 边界设计后，可以让 `service.py` 对 `ScreenRecorder` 暴露单个“给我 screenshot + current trigger metadata，我返回 raw handoff bundle”的接口，保持 call site 简洁。

**screenpipe 对照**：

- `crates/screenpipe-accessibility/src/tree/mod.rs` / `crates/screenpipe-accessibility/src/tree/macos.rs` — `aligned`，MyRecall 同样把 AX tree walk 与 URL 提取视为独立子模块。
- 以独立 `service.py` 包装 Python 模块边界 — `no comparable pattern`，这是为了贴合当前 Python codebase 组织方式。

### D3：`focused_context` 必须由 AX snapshot 一次性产出；`active_app` / `active_window` 只保留为回退观测字段，不再作为最终 S2b frozen metadata 来源

**选择**：`ScreenRecorder._snapshot_active_context()` 当前基于 `get_active_app_name()` 与 `get_active_window_title_for_app()` 生成的 `active_app/active_window`，在 S2b 中不再直接映射为最终 `app_name/window_name`。最终上报给 `/v1/ingest` 的 `focused_context` 由新的 AX snapshot 一次性产出；若 AX 无法确认 `window_name` 或 `browser_url`，就写 `None`，而不是回退拼接当前 helper 的结果。

**理由**：

- `docs/v3/open_questions.md` OQ-040 已冻结“`app_name/window_name/browser_url` 必须来自同一轮 focused-context snapshot，一次性产出，禁止字段级混拼”。沿用现有 `active_app/active_window` helper 直写，会把不同来源混进最终 handoff。
- 现有 helper 仍有价值：可以作为日志、诊断和 fallback evidence，帮助判断 AX snapshot 是否异常，但不能越权成为最终 frozen metadata。
- `device_name` 仍继续来自 `MonitorRegistry` / screenshot monitor，这符合 same-cycle coherence 但不要求与 `focused_context` 同源；但与当前 `TriggerEvent` 直接携带 `device_name` 的实现相比，S2b 需要把该字段从“event-source 决策”收敛为“monitor worker 绑定结果”。

**screenpipe 对照**：`crates/screenpipe-server/src/paired_capture.rs` + `crates/screenpipe-server/src/event_driven_capture.rs` — `aligned`。screenpipe 也把 capture context 作为一轮 bundle 处理，不做字段级事后混拼。

### D3a：`device_name` 从“事件源预绑定”收敛为“per-monitor worker 的 capture-time 绑定”，S2b 允许保留 `TriggerEvent.device_name` 字段但改变其 owner

**选择**：不强行重写 `TriggerEvent` dataclass 形状，但把 `device_name` 明确拆成两层语义：事件源传入的 `device_name` 仅视为 `event_device_hint`；真正写入 spool / payload / dedup state / Gate evidence 的值必须是对应 `MonitorWorker` 在 capture-time 依据自身 monitor binding 确认的 `final_device_name`。若 hint 与 worker monitor 冲突，以 `final_device_name` 为准并记录诊断日志。

**规则**：

- `event_device_hint` 只用于 trigger 路由与内部诊断，不作为 persisted truth。
- `/v1/ingest` payload 中的 `device_name` 一律表示 `final_device_name`。
- `inter_write_gap_sec`、Host dedup bucket、acceptance SQL 与证据导出一律按 `final_device_name` 分桶。

**理由**：

- 这是将现有 S2a 代码平滑过渡到 OQ-040 frozen rule 的最小破坏路径：不必先大改全部 event source API，仍然可以把最终语义 owner 收回到 monitor worker。
- click 事件当前确实依赖坐标匹配 monitor；保留 hint 可以帮助 worker 决定是否优先处理或只做诊断，但 hint 不能再被视为最终事实值。
- 只要最终写入 `frames`、spool metadata、dedup state 的 `device_name` 全部来自 capture-time 绑定，就能满足 S2b required semantics，即使内部过渡期仍保留旧字段。

**screenpipe 对照**：`crates/screenpipe-server/src/event_driven_capture.rs` 的 per-monitor worker binding — `aligned`。保留现有 `TriggerEvent.device_name` 作为内部 hint 属于迁移层面的 `intentional divergence`，不是对外语义。

### D3b：迁移期必须显式区分 `event_device_hint`、`final_device_name` 与 proof truth

**选择**：S2b 迁移期间允许现有事件源、debounce 与 trigger route 继续读取 `TriggerEvent.device_name`，但设计上必须将其解释为 `event_device_hint`。只有 recorder 在 capture-time 确认的 monitor 绑定结果才是 `final_device_name`，并且只有 `final_device_name` 能进入 spool metadata、`/v1/ingest` payload、dedup state、`inter_write_gap_sec` 与 Gate evidence。

**原因**：

- 当前代码已经在事件源、去抖与截图选择中读写 `device_name`；若不写清迁移语义，后续实现极易在内部 hint 与外部 truth 之间混用。
- 该约束允许最小化改动现有 `TriggerEvent` 形状，同时保证外部契约与 proof path 不再依赖事件源预绑定。
- 多屏场景的验收、dedup 分桶与问题诊断都要求“内部可以过渡，外部语义不能混杂”。

**proof rule（锁定）**：凡进入 payload、frames、evidence、acceptance SQL 的 `device_name` 都表示 `final_device_name`；任何 `event_device_hint` 仅允许停留在内部日志或调试字段。

### D3c：字段 owner 以单轮 capture-cycle truth 为唯一准入规则

**锁定规则**：S2b 只允许一个字段 owner 矩阵进入实现与验收：`event_device_hint` 由 trigger source 产生、仅供内部路由/诊断；`final_device_name` 由 capture-time monitor binding 产生、作为唯一 persisted truth；`app_name/window_name/browser_url` 由同轮 `focused_context` snapshot 产生；`accessibility_text/content_hash` 由 AX walker + hash 阶段产生。上述字段允许缺失，但不得由 legacy alias、跨轮 snapshot 或 uploader/server 侧默认补全后伪装为同轮 truth。

**最小验证口径**：任何 proof sample 若其 canonical truth 只能通过 alias fallback、mixed-version 兼容路径或 event hint 反推获得，则该样本只能算 migration observation，不得进入 S2b proof。

### D4：Browser URL 使用三层提取链，Arc stale rejection 为固定规则，结果必须在 Host 侧写成 `browser_url` 或 `None`

**选择**：在 `openrecall/client/accessibility/browser_url.py` 实现三层策略：

- Tier 1：AXDocument（Chrome / Safari / Edge）
- Tier 2：Arc AppleScript + title cross-check
- Tier 3：浅层 AXTextField walk

对所有候选 URL，在写入 payload 前统一做格式校验与 focused-context 一致性校验。只要出现 title mismatch、无法确认同轮一致性、非 `http(s)`、或提取失败，结果都写 `None`。

**理由**：

- `docs/v3/acceptance/phase1/p1-s2b.md` 已把三层 fallback 和 Arc stale rejection 冻结为 required / conditional evidence 的一部分。
- Browser URL stale rejection 是 S2b capability correctness，而不是 S3 processing decision；因此必须在 Host 侧决策并写入 payload，不允许把不确定 URL 交给 Edge 或 Search 层再修正。
- 统一在 Host 侧归一为 `browser_url` 或 `None`，可确保后续 `FramesStore._extract_metadata_fields()` 和 search schema 接收到单一语义，而不是“候选 URL + 置信度”。

**screenpipe 对照**：`crates/screenpipe-accessibility/src/tree/macos.rs` — `aligned`。Arc stale rejection 与 title matching 是直接对齐；Arc 仍保持 timeboxed optional heuristic sub-scope，属于 MyRecall 在 required-browser evidence 上的 `intentional divergence`（仅证据范围差异，不是运行时规则差异）。

### D5：`content_hash` 在 Host 侧基于最终 `accessibility_text` 计算，empty-AX 直接落为 `null`，并复用同一结果驱动 dedup 与 Gate 证据

**选择**：在 `openrecall/client/accessibility/hash.py` 固定实现 canonicalization：Unicode NFC、换行统一为 `\n`、每行 `rstrip()`、整体 `strip()`。若 canonicalized 文本为空，则返回 `content_hash=None`；否则返回 `sha256:<64hex>`。同一个结果既写入 spool metadata，也驱动 Host dedup 判定。

**理由**：

- `docs/v3/data-model.md` 已冻结 exact canonicalization 规则，且明确 `content_hash` 只基于最终上报的 `accessibility_text`。若在 dedup 用一个 hash、上传用另一个 hash，会直接破坏 `ax_hash_eligible` 和 `inter_write_gap_sec` 的可审计性。
- `openrecall/client/v3_uploader.py` 当前只负责转发 `item.metadata`；因此把 hash 结果先写入 spool JSON，既能保证上传幂等，也能保留 Host side evidence。
- empty-AX 不参与 dedup，但必须 no-drop 上传；因此 hash 模块必须把“空文本”与“无结果”都收敛到 `content_hash=None`，而不是特殊 sentinel。

**screenpipe 对照**：

- `crates/screenpipe-accessibility/src/tree/mod.rs` 的 hash snapshot — `aligned`（都只做 exact text hash）
- Hash 算法从 DefaultHasher(u64) 改为 SHA256(hex) — `intentional divergence`，理由已在 ADR-0013 和 reference validation 中冻结为跨 session 一致性更强

### D5a：capture outcome 必须冻结为有限终态，避免把 AX 空值、权限异常与去重跳过混成同一语义

**选择**：S2b 的 end-to-end evidence 结果限制为有限 outcome：`capture_completed`、`ax_empty`、`ax_timeout_partial`、`browser_url_rejected_stale`、`permission_blocked`、`dedup_skipped`、`spool_failed`、`schema_rejected`。其中 recorder pre-upload outcome 只覆盖前七类，`schema_rejected` 明确由 uploader / `/v1/ingest` 在 wire-contract 校验失败时发出。上述 outcome 只表达 raw handoff / capability / transport / contract 事实，不表达 S3 的语义解释。

**规则**：

- `permission_blocked`：允许截图与 heartbeat 继续，但 `accessibility_text=""`、`content_hash=null`、`browser_url=null`，且不得触发 dedup skip。
- `ax_empty`：表示 AX 成功返回但 canonicalized 文本为空；允许上传，`content_hash=null`。
- `ax_timeout_partial`：表示 AX 超时但拿到了部分文本；若最终文本非空，则照常计算 `content_hash` 并允许 dedup。
- `dedup_skipped`：仅允许发生在 `capture_trigger ∉ {idle, manual}` 且 `content_hash != null` 且同设备 `<30s` 同 hash。
- `spool_failed` 属于 recorder pre-upload outcome；`schema_rejected` 属于 uploader / ingest contract failure。两者都必须独立计数，不得并入 capture failure 或 dedup。

**理由**：

- 该冻结把“有没有截图”“有没有写入 spool”“为什么 hash 为 null”分开，能直接约束日志、指标与 acceptance evidence 的解释口径。
- 这些 outcome 必须进入规范与证据导出，而不应只停留在设计描述层；否则实现者会把 empty-AX、permission-blocked 与 schema reject 用不同日志口径各自实现，导致 Gate 不可比。

### D6：Host dedup 发生在 `spool.enqueue()` 之前，并按 `final_device_name` 维护纯内存 `last_content_hash/last_write_time` 状态，不把 dedup owner 下沉到 Edge

**选择**：在每个 `MonitorWorker` 内新增按 `final_device_name` 分桶的 dedup runtime state（例如 `_dedup_state_by_device`），其输入是 `capture_trigger`、canonicalized `content_hash`、当前 wall clock 与 `final_device_name`。只有当条件全部满足时才跳过 `spool.enqueue()`：非 `idle` / `manual`、`content_hash` 非空、距最近一次成功 spool 写入 `<30s`、hash 与同设备上次相同。若跳过上传，则记录 dedup metrics；若写入 spool 成功，更新 `last_write_time/last_content_hash`。

**理由**：

- `docs/v3/open_questions.md` OQ-040 与 `docs/v3/data-model.md` 已明确 dedup owner 在 Host upload 前，`last_write_time` 指最近一次成功写入 Host 本地 spool 的时间，不是 Edge ingest 完成时间。
- `openrecall/server/api_v1.py` 的 `capture_id` 幂等和 queue full 拒绝是另一层语义；若把 content dedup 放到 Edge，就会和 `capture_id` 幂等混淆，破坏 v3-only 证明链路。
- 把 dedup runtime state 放在 per-monitor worker 而不是 `SpoolUploader`，能保证同一个 capture cycle 内就决定“是否值得上传”，并天然保持和 `final_device_name` 同 owner，减少无意义图片写盘和网络流量。

**screenpipe 对照**：`crates/screenpipe-server/src/event_driven_capture.rs` — `aligned`。30s floor 与 non-`idle`/`manual` 条件直接对齐；纯内存 per-device 状态且跨重启重置，在 MyRecall 里同样保留，是 `aligned`。

### D7：`/v1/ingest` 与 `FramesStore` 只负责严格 schema 校验与字段落盘，不解释 `text_source`，并把缺失/非法 field 视为 S2b contract failure

**选择**：更新 `openrecall/server/api_v1.py` 的 `ingest()` 校验逻辑：

- `metadata.accessibility_text` key 必须存在，值必须为 string，允许 `""`，禁止 `null`
- `metadata.content_hash` key 必须存在，值必须为 `null` 或 `sha256:<64hex>`，禁止 `""`
- `metadata.device_name`、`capture_trigger` 继续视为 required semantic inputs
- `browser_url` 允许 `null`

同时扩展 `FramesStore._extract_metadata_fields()` 与落盘 schema，使 `frames` 至少能持久化 `accessibility_text`、`content_hash`、`browser_url`、`device_name` 和当前已有 `capture_trigger`。

**理由**：

- Server 是 wire contract gatekeeper；只要 Host 发来的 payload 缺 key、空串或非法格式，就必须在 `/v1/ingest` 以 `400 INVALID_PARAMS` 拒绝，不能默默修复。
- `FramesStore` 已是 metadata extraction 单点；扩展这里而不是在多个 route 重复解析，能保持 DB field mapping 一致。
- 根据 OQ-039，Server 不得引入任何“AX empty => OCR fallback”或“permission denied => 仍按 empty-AX 入库”的解释逻辑；它只接受一个已经被 S2b 冻结好的 raw handoff。

**contract completeness（锁定）**：

- required fields：`accessibility_text`、`content_hash`、`device_name`、`capture_trigger`
- optional fields：`browser_url`、`event_ts`、`app_name`、`window_name`
- `accessibility_text` 缺失或为 `null` -> `400 INVALID_PARAMS`
- `content_hash` 缺失或为 `""` -> `400 INVALID_PARAMS`
- `content_hash=null` 合法，表示 empty-AX / permission-blocked / no-hash outcome
- `device_name` 必须表示 `final_device_name`，不得上传 event hint
- proof sample canonical keys：`app_name`、`window_name`、`browser_url`、`device_name`
- 兼容 alias（如 `active_app`、`active_window`）只允许用于 migration observation 或内部兼容解析，不得构成 S2b proof truth

**screenpipe 对照**：

- `paired_capture.rs` handoff shape — `aligned`
- MyRecall 把 internal `Option` 收紧为 required wire keys — `intentional divergence`，这是 staged S2b->S3 contract 的已冻结差异

### D7a：proof filter 必须有单一 owner，且以机制而不是文字说明生效

**选择**：S2b proof filter 作为独立证据职责存在，必须由 acceptance/evidence aggregation 层统一执行；Host runtime 与 Edge ingest 只负责输出原始信号与可区分分类，不分别各自裁定最终 proof truth。该聚合层的权威输出固定为 `artifacts/p1-s2b/p1-s2b-proof-filter.json`。

**输入（锁定）**：

- Host `capture_attempts.ndjson`：一条 capture attempt 一个 `capture_id`，包含 `trigger`, `event_device_hint?`, `final_device_name?`, `outcome`, `window_id`, `host_schema_version`。
- Edge `ingest_decisions.ndjson`：记录 `capture_id`, `frame_id?`, `decision`, `request_id`, `edge_schema_version`。
- 窗口与健康快照：用于判定 `broken_window`、重启边界与 proof eligibility。

**输出（锁定）**：`p1-s2b-proof-filter.json` 至少包含 `inputs`、`ruleset_version`、`attempts[]`、`aggregates` 四段；`attempts[]` 每条至少包含 `capture_id`, `frame_id?`, `outcome`, `proof_status`, `exclusion_reason?`, `metric_eligibility[]`, `final_device_name?`。

**exclusion taxonomy（锁定）**：`mixed_version`、`alias_only_payload`、`missing_canonical_keys`、`final_device_name_missing`、`final_device_name_mismatch`、`broken_window`、`schema_rejected`、`queue_rejected`。

**最小规则**：alias-only payload、mixed-version 样本、`broken_window=true` 窗口、以及仅靠 compatibility fallback 才补齐 canonical keys 的样本，全部必须被同一个 mechanized filter 排除在 S2b Gate proof 之外。`dedup_skipped`、`permission_blocked`、`ax_empty` 不是排除原因，而是合法 outcome；它们是否进入具体指标分母，只能通过 `metric_eligibility[]` 控制。

### D8：权限状态继续由 `PermissionStateMachine` 驱动，但 S2b 将其从“截图可用性”提升为“AX capability gate”，并通过 heartbeat / `/v1/health` 持续暴露

**选择**：保留 `openrecall/client/events/permissions.py` 的现有四态 FSM、2 fail / 3 success / 300s cooldown / 10s poll，不新增状态；但在 S2b 中明确把权限状态解释为 AX capability gate，而不是 screenshot gate：`granted` 允许完整 paired capture；`transient_failure` 只保留为计数与观测态，本轮 paired capture 仍按最近一次成功 capability 语义继续，不直接产出 `permission_blocked`；只有 `denied_or_revoked` / `recovering` 才继续截图与 heartbeat、同时停止 AX walk / URL 提取 / dedup 判定，并将结果标记为 `permission_blocked`。`screen_recording` 或其他 screenshot-path 故障不得被本状态机吞并解释。

**状态规则**：

- `granted`：截图、AX、URL、hash、dedup 全部继续。
- `transient_failure`：只推进连续失败计数与观测，不直接改变本轮 paired capture owner；不得单独产出 `permission_blocked`。
- `denied_or_revoked` / `recovering`：截图继续；AX/URL 停止；`accessibility_text=""`、`content_hash=null`、`browser_url=null`；heartbeat 与 `/v1/health` 持续暴露降级状态。
- P1-S2b 不引入“因权限异常而直接丢弃 screenshot”的语义。

**health contract（锁定）**：`/v1/health` 保留 `capture_permission_status` 作为 AX capability state，并新增独立的 `screen_capture_status` / `screen_capture_reason` 用于 screenshot-path continuity 观测；两者不得复用同一状态字段。

**理由**：

- 当前 `ScreenRecorder.run_capture_loop()` 已具备 permission heartbeat 与 health 可观测性，S2b 应复用这条链路，而不是另起一套权限通道。
- 根据 OQ-039，权限异常属于 capability failure，不得被解释成 OCR fallback；同时也不应把 screenshot pipeline 一并停掉，否则会破坏 S2b 的 raw evidence 连续性。
- 该语义把 `empty-AX` 与 `permission_blocked` 分开，避免 Gate 样本被错误稀释。
- 当前 runtime 的现实冲突必须被显式承认：现状 recorder 在 degraded 时会停掉 capture loop 中的采集分支，因此实现不能只改字段解释，必须迁移 loop owner，使 screenshot 继续而 AX 停止，并把 screenshot-path 状态单独暴露。

**screenpipe 对照**：permissions / health handling（参考 validation doc 对 `permissions.rs` 与 paired capture 的总结）— `aligned`。具体四态 FSM 是 MyRecall 当前 codebase 已存在实现，属于对 screenpipe direction 的工程化 `intentional divergence`，但不是新语义。

### D9：阶段设计以 `frames` 为 raw handoff 事实表，不在 S2b 设计中提前引入 S3 的 `accessibility` / `ocr_text` 分表写入

**选择**：S2b 当前 design 只扩展 `/v1/ingest` payload 与 `frames` 原始字段，使 raw `accessibility_text` / `content_hash` / `browser_url` / `device_name` 可追溯；不在本阶段要求 `openrecall/server/worker.py` 或未来 processing pipeline 立刻把数据写入 `accessibility` 表。ADR-0012 与 `docs/v3/data-model.md` 的 Scheme C 仍是 P1-S3 的目标，不是 S2b 的落地义务。

**理由**：

- proposal 已把 `accessibility` / `ocr_text` 分表写入列为 Non-goal；提前把这些写入职责加回 S2b，会直接违反 OQ-039 的 ownership split。
- `FramesStore` 当前已经是 `/v1/*` 主链路的真实写入点；在 S2b 仅扩展 `frames` 可让 acceptance SQL（`ax_hash_eligible`、`content_hash` coverage）直接落在现有表结构上。
- 保持 raw handoff 在 `frames` 中可追溯，也更符合 `docs/v3/acceptance/phase1/p1-s2b.md` 的 Gate SQL 与证据收集方式。

**screenpipe 对照**：paired capture result + downstream processing split — `aligned in principle`；MyRecall 的 staged handoff 是 `intentional divergence`，但 design 必须尊重 staged boundary。

## Risks / Trade-offs

- **[AX walker 与截图串行执行可能推高 capture latency]** → Mitigation：S2b 不只记录 `AX walk`，还必须记录完整 `capture_cycle_latency = dequeue -> monitor bind -> screenshot -> AX -> URL -> hash -> dedup -> spool write`；Gate 不允许仅用 `AX walk P95 < 500ms` 替代完整链路观测。
- **[现有 `active_app/active_window` helper 与 AX snapshot 并存，容易让实现者偷懒混拼字段]** → Mitigation：在 `accessibility/service.py` 返回明确的 `focused_context` bundle，`recorder.py` 只接受 bundle 或 `None`，不再自行组装最终 `app_name/window_name/browser_url`。
- **[Host dedup 纯内存状态在重启后会重置，容易被误解为数据丢失]** → Mitigation：设计中把 `broken_window`、`last_write_time` 与 per-device runtime state 明确标记为观测语义；跨重启窗口只作为 observation，不作为 Hard Gate 样本。
- **[Browser URL stale rejection 若写得过于激进，会降低 success rate；若写得过于宽松，又会把错误 URL 带入搜索]** → Mitigation：严格采用 Better None than wrong 规则；把 `browser_url_success`、`browser_url_rejected_stale`、`browser_url_failed_all_tiers`、`browser_url_skipped` 作为明确计数器，而不是靠日志猜测。
- **[`api_v1.py` 直接升级 required field 校验后，旧 Host 版本会被新 Edge 拒绝]** → Mitigation：在 design 中把 mixed Host/Edge 明确标记为不纳入 S2b Gate 证明样本；v3-only 主链路是有意约束，不需要为旧版本让步。
- **[设计过早引入 S3 语义会污染 S2b 测试边界]** → Mitigation：所有 decision 都只描述 raw handoff、capability、frozen metadata 与 Gate evidence；凡涉及 OCR fallback、`text_source`、分表写入，都在 Non-goals 与 Open Questions 中显式排除。

## Verification Implications

- S2b 必须为以下场景提供可注入、可重复、可断言的测试 seam：AX timeout、permission 状态切换、`event_device_hint != final_device_name`、Arc stale URL、dedup hit、spool failure、`/v1/ingest` schema reject。
- 上述 test seam 至少需要可注入 owner：clock、AX walker、browser URL resolver、permission source、monitor binding resolver、proof-filter input signals。
- 单元测试至少覆盖 canonicalization -> `content_hash` -> dedup 条件判定；集成测试至少覆盖 `permission_blocked`、`browser_url_rejected_stale`、device rebinding mismatch。
- acceptance evidence 必须能够区分 `ax_empty`、`ax_timeout_partial`、`permission_blocked`、`dedup_skipped`、`spool_failed`、`schema_rejected`，不得只靠笼统的 failed/degraded 日志聚合。
- `broken_window`、`window_id`、`restart_events` 的最终归属必须可追溯：runtime 提供原始 pid/时间窗信号，Gate script or evidence aggregator 负责形成最终窗口判定，避免把聚合责任散落到 Host/Edge 实现中。

## Migration Plan

1. 在 `openrecall/client/accessibility/` 增加新的 AX 包与 service 入口，把 `ScreenRecorder` 现有 capture cycle 从“截图后直接 enqueue”改为“截图 -> AX bundle -> dedup 判定 -> enqueue”。
2. 扩展 `openrecall/client/spool.py` metadata 内容与 `openrecall/client/v3_uploader.py` 上传 payload，使 spool JSON 与 `/v1/ingest` 一致携带 `accessibility_text`、`content_hash`、`browser_url`、`device_name`。
3. 扩展 `openrecall/server/api_v1.py` 的 metadata 校验与 `openrecall/server/database/frames_store.py` 的字段提取 / 落盘 schema，确保 v3 主链路能无损保存 raw handoff 字段。
4. 以 TDD 方式逐步补齐契约测试、AX timeout 测试、focused-context / Browser URL stale / dedup / permission recovery 测试；最后再补 `scripts/acceptance/p1_s2b_local.sh` 收口与 evidence 导出。
5. 若实现过程中发现 S2b 需要新增字段但其语义会改变 Search / processing ownership，则暂停在 S2b 设计层继续扩张，改在后续 `specs/` 与 P1-S3 artifact 中承接，不在本阶段 synthesize 新规则。

## Resolved Implementation Notes

- `frames` DDL 已包含 `accessibility_text`、`content_hash`、`browser_url`、`device_name`（见 `openrecall/server/database/migrations/20260227000001_initial_schema.sql`）。S2b 不需要为这四个字段新增 migration artifact；剩余 server 工作是补齐 `/v1/ingest` 校验与 `FramesStore` 字段提取，落实 frozen wire contract。
- S2b 保持 AX walker 在 Host paired capture cycle 内串行执行，但 paired capture owner 从单循环改为 `TriggerBus + MonitorWorker[N]`。边界控制固定为 `walk_timeout=500ms`、`element_timeout=200ms`、`max_nodes=5000`、`max_depth=30`；实现中必须记录完整 `capture_cycle_latency`，并把广播/worker lag 作为额外观测信号。
- `openrecall/client/spool.py` 继续使用 UTF-8 JSON 与 `ensure_ascii=False`。ASCII literal-match 约束仅适用于文档/日志锚点与字段名，不要求对 `accessibility_text` 做 ASCII 转义；AX 原始 Unicode 文本必须无损保留。
- Screenpipe 参考采用 citation-pack-first 策略。`docs/v3/references/screenpipe-p1-s2b-validation.md` 作为 S2b 的 frozen upstream evidence artifact 可满足大部分情况；必要时可以参考/Users/pyw/old/MyRecall/_ref/screenpipe项目具体内容。
