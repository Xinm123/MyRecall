## Implementation Tasks

## TDD Execution Rule

- [ ] T0.0 在进入任何生产代码任务前遵守统一 TDD 闸门：对应切片的测试必须先写出并被单独执行到失败（RED），随后才允许进入最小实现（GREEN）与收敛重构；未经历 RED 的实现视为未开始

### 0. Preflight audits and contract lock-in

- [ ] 0.1 审计当前 `openrecall/client/events/base.py`、`trigger_route`、`recorder` 等路径对 `TriggerEvent.device_name` 的使用点，明确哪些仍属 `event_device_hint`，哪些会成为 `final_device_name`，并将该审计结果作为 S2b device-binding 改造前置输入
- [ ] 0.2 审计当前 PermissionStateMachine 是否已满足 `2 fail / 3 success / 300s cooldown / 10s poll` 约束，若现状不一致，先收口为 S2b 约束再进入 paired-capture 改造
- [ ] 0.3 审计当前 `/v1/ingest` 对旧 Host payload、alias-only payload、mixed-version 样本的处理路径，确认 proof sample 与 migration observation 的现状边界
- [ ] 0.4 审计当前 `ScreenRecorder.run_capture_loop()`、trigger channel 与 monitor 刷新路径，明确哪些逻辑要提升为 `TriggerBus(broadcast)` owner，哪些逻辑要下沉到 `MonitorWorker[N]`，避免沿用单循环 recorder 心智进入 S2b 实现

### 1. Slice A - `/v1/ingest` contract first

- [ ] 1.1 RED：扩展 `tests/test_p1_s2a_server_contracts.py`、`tests/test_p1_s1_ingest.py` 或等价服务端测试，先覆盖 `/v1/ingest` 的 S2b required keys、canonical keys、`schema_rejected`、mixed-version exclusion、proof-sample exclusion 与 `frames_store` 字段提取，并确认新断言先失败
- [ ] 1.2 GREEN：修改 `openrecall/client/v3_uploader.py`，确保 `POST /v1/ingest` 的 multipart metadata 始终携带 required keys `accessibility_text`、`content_hash`、`device_name`、`capture_trigger`，并只上传 canonical keys 而非 alias truth
- [ ] 1.3 GREEN：修改 `openrecall/server/api_v1.py`，对 `POST /v1/ingest` 强制校验 `accessibility_text` 为 required string（允许 `""`，禁止 `null`）与 `content_hash` 为 required nullable string（允许 `null`，禁止 `""`）
- [ ] 1.4 GREEN：修改 `openrecall/server/api_v1.py`，确保 `device_name` 仅接受 `final_device_name` 语义，并把仅靠 `active_app` / `active_window` alias 补全上下文的样本视为 migration observation，而不是 proof truth
- [ ] 1.5 GREEN：修改 `openrecall/server/database/frames_store.py`，补齐 `accessibility_text`、`content_hash`、`browser_url`、`device_name` 与 canonical key 提取 / 统一落盘逻辑；不得把 `outcome` 引入 `frames` 持久化语义
- [ ] 1.6 GREEN：修改 `openrecall/server/api_v1.py` 与 `frames_store.py`，让 `schema_rejected`、mixed-version observation 与成功 handoff 样本拥有可区分的计数 / 日志 / 证据口径，并确保 `schema_rejected` 属于 ingest contract failure 而非 recorder pre-upload outcome
- [ ] 1.7 VERIFY：运行 Slice A 相关测试并保持通过，确认客户端后续切片从一开始就对齐最终 `/v1/ingest` 语义

### 2. Slice B - content hash and canonicalization

- [ ] 2.1 RED：新增 `tests/test_p1_s2b_content_hash.py`，覆盖 canonicalization、`content_hash=null`、`sha256:` 格式、`ax_hash_eligible` 分母与 dedup 条件矩阵，并显式覆盖 NFC、换行统一、逐行去尾空白与整体 `strip()` 边界；确认测试先失败
- [ ] 2.2 GREEN：新增 `openrecall/client/accessibility/__init__.py`、`types.py`，定义 S2b raw handoff / `focused_context` / Browser URL 结果 / AX outcome 所需的数据结构，明确 `event_device_hint` 与 `final_device_name` 的语义边界
- [ ] 2.3 GREEN：新增 `openrecall/client/accessibility/hash.py`，实现 `accessibility_text` canonicalization（Unicode NFC、换行统一为 `\n`、逐行去尾部空白、整体 `strip()`）与 `content_hash` 生成逻辑
- [ ] 2.4 VERIFY：运行 `tests/test_p1_s2b_content_hash.py` 与受影响服务端契约测试，确认 hash 规则在 Host / ingest 两侧一致

### 3. Slice C - AX walker, raw handoff, and partial-timeout semantics

- [ ] 3.1 RED：新增 `tests/test_p1_s2b_ax_timeout.py`，覆盖 `walk_timeout=500ms`、partial-text 保留、`ax_timeout_partial` 与 `ax_empty` 区分，并确认测试先失败
- [ ] 3.2 GREEN：新增 `openrecall/client/accessibility/macos.py`，实现 macOS AXUIElement walker、`walk_timeout=500ms`、`element_timeout=200ms`、`max_nodes=5000`、`max_depth=30` 约束与 partial-text 收集
- [ ] 3.3 GREEN：新增 `openrecall/client/accessibility/service.py`，把 walker、Browser URL、hash 与 pre-upload outcome 分类串成单个 paired-capture service 入口，输出 `accessibility_text`、`content_hash`、`focused_context`、`browser_url` 与 pre-upload outcome（不在此层承担 `schema_rejected`）
- [ ] 3.4 GREEN：为新的 accessibility service / recorder 路径补齐可注入 test seams：clock、AX walker 结果、Browser URL tier 返回、permission state、monitor binding、spool 结果与 ingest rejection 观测点，确保后续 TDD 与 acceptance 场景可稳定复现
- [ ] 3.5 VERIFY：运行 `tests/test_p1_s2b_ax_timeout.py`，确认 AX timeout / partial handoff 行为已经由测试锁定

### 4. Slice D - focused_context and device binding

- [ ] 4.1 RED：新增 `tests/test_p1_s2b_focused_context.py`，覆盖 one-shot `focused_context`、不确定字段写 `None`、禁止字段级混拼，并确认测试先失败
- [ ] 4.2 RED：新增 `tests/test_p1_s2b_device_binding.py`，覆盖 `event_device_hint` 与 `final_device_name` 冲突、proof truth 只认 capture-time binding、per-device dedup bucket 语义，并确认测试先失败
- [ ] 4.2a RED：新增或扩展 trigger/worker 相关测试，覆盖 `TriggerBus(broadcast)` 在单个 `MonitorWorker` 变慢时仍不会阻塞其它 worker fan-out，并确认测试先失败
- [ ] 4.3 GREEN：修改 `openrecall/client/recorder.py` 与相关 trigger channel/monitor 管理路径，将 Host capture orchestration 收敛为 `TriggerSource -> TriggerBus(broadcast) -> MonitorWorker[N]`，把单 monitor paired capture owner 下沉到 worker，而不是继续沿用单循环串行 capture 作为最终语义
- [ ] 4.4 GREEN：在 `MonitorWorker` capture 路径中接入新的 accessibility service，替换当前仅写 `active_app` / `active_window` 的 metadata 构造路径
- [ ] 4.5 GREEN：将事件源携带的 `device_name` 明确降格为 `event_device_hint`，并在实际 screenshot monitor 选定后生成唯一对外 truth 的 `final_device_name`；迁移期保留两者的诊断对照，但 payload / proof / dedup / 统计一律只认 `final_device_name`
- [ ] 4.6 GREEN：把最终 payload / spool metadata 中的 `app_name`、`window_name`、`browser_url` 改为来自同轮 `focused_context` snapshot，禁止再用 `active_app` / `active_window` 作为 S2b proof truth；不确定时写 `None`，确认错误的非空值进入 mismatch/failure 统计
- [ ] 4.7 GREEN：显式禁止字段级混拼：`app_name`、`window_name`、`browser_url` 只能同时来自单轮 snapshot
- [ ] 4.8 VERIFY：运行 `tests/test_p1_s2b_focused_context.py`、`tests/test_p1_s2b_device_binding.py` 与相关服务端契约测试，确认 same-cycle bundle、TriggerBus/MonitorWorker owner 与 final-device truth 已锁定

### 5. Slice E - permission recovery and health mirroring

- [ ] 5.1 RED：新增 `tests/test_p1_s2b_permission_recovery.py`，覆盖 `granted` / `transient_failure` / `denied_or_revoked` / `recovering`、`permission_blocked` outcome、截图主链路继续与 `/v1/health` 降级，并验证 2-fail / 3-success 计数收敛语义；确认测试先失败
- [ ] 5.1a RED：在 `tests/test_p1_s2b_permission_recovery.py` 或等价测试中补充负向边界：非 AX 的 screenshot-path failure / screen-recording failure 不得被重分类为 `permission_blocked` 或 `ax_empty`；确认断言先失败
- [ ] 5.2 GREEN：修改 `openrecall/client/events/permissions.py` 或 `openrecall/client/recorder.py` 调用关系，将现有四态 FSM 明确限定为 AX capability gate，而不是 screenshot 主链路总开关
- [ ] 5.3 GREEN：修改 `openrecall/client/recorder.py`，让 `transient_failure` 仅作为计数与观测态，不单独产出 `permission_blocked`；只有 `denied_or_revoked`、`recovering` 在 S2b 中继续 screenshot 与 heartbeat、同时跳过 AX walk / Browser URL / dedup，并产出 `permission_blocked` raw handoff
- [ ] 5.4 GREEN：修改 `openrecall/server/api_v1.py`、`openrecall/server/config_runtime.py` 或相关 heartbeat 镜像逻辑，确保 `/v1/health` 持续暴露 `capture_permission_status`/reason/timestamp，并新增独立的 `screen_capture_status` / `screen_capture_reason` 以表达 screenshot-path continuity
- [ ] 5.5 GREEN：修改 `openrecall/server/templates/layout.html` 与相关 UI 读路径，确保 `#mr-health` / `data-state` 能区分 permission degraded、screenshot-path continuity 与 `unreachable`，且不把权限异常误报为网络不可达
- [ ] 5.6 VERIFY：运行 `tests/test_p1_s2b_permission_recovery.py` 并手动确认 `/v1/health` / `#mr-health` 读路径未回退到旧语义，且 `transient_failure` 不会被错误计为 `permission_blocked`

### 6. Slice F - Browser URL extraction and stale rejection

- [ ] 6.1 RED：新增 `tests/test_p1_s2b_browser_url.py`，覆盖三层提取链、Arc title mismatch stale reject、required browser success / reject / failed / skipped 分类，并确认测试先失败
- [ ] 6.2 GREEN：新增 `openrecall/client/accessibility/browser_url.py`，封装 Tier 1 AXDocument、Tier 2 Arc AppleScript、Tier 3 浅层 AXTextField walk 的统一返回接口与 stale rejection 原因分类
- [ ] 6.3 GREEN：在 `openrecall/client/accessibility/browser_url.py` 中落实 Browser URL 四类 evidence：`browser_url_success`、`browser_url_rejected_stale`、`browser_url_failed_all_tiers`、`browser_url_skipped`；Chrome / Safari / Edge 为 required evidence，Arc 仅作 conditional evidence
- [ ] 6.4 GREEN：修改 `openrecall/client/accessibility/service.py`，将 Browser URL 写入权与 `focused_context` one-shot bundle 一起判定，确保“不确定即 `None`”成为统一出口
- [ ] 6.5 GREEN：为 Arc AppleScript 路径补齐 title cross-check 与 stale rejection 分支，并把 Arc 样本单独保留为 conditional evidence，不污染 required browser success 分母
- [ ] 6.6 VERIFY：运行 `tests/test_p1_s2b_browser_url.py`，确认 Browser URL 行为已由测试锁定而非依赖人工推断

### 7. Slice G - recorder outcomes, dedup, and spool evidence

- [ ] 7.1 RED：在 `tests/test_p1_s2b_content_hash.py`、`tests/test_p1_s2b_device_binding.py`、`tests/test_p1_s2b_permission_recovery.py` 中补齐 dedup / outcome / evidence 边界断言，覆盖 `<30s`、`=30s`、`>30s`、`idle/manual` 例外、`permission_blocked` 不进 dedup、`schema_rejected` 不属于 recorder outcome；确认断言先失败
- [ ] 7.2 GREEN：修改 `openrecall/client/recorder.py` / `MonitorWorker`，为每个 worker capture cycle 记录有限 pre-upload outcome：`capture_completed`、`ax_empty`、`ax_timeout_partial`、`browser_url_rejected_stale`、`permission_blocked`、`dedup_skipped`、`spool_failed`；`schema_rejected` 改由 uploader / server 证据口径负责
- [ ] 7.3 GREEN：记录完整 `capture_cycle_latency = TriggerBus/worker dequeue -> monitor bind -> screenshot -> AX -> URL -> hash -> dedup -> spool write` 的观测数据，避免只记录 AX walk 时间
- [ ] 7.4 GREEN：在每个 `MonitorWorker` 内新增 per-`final_device_name` 的 `last_content_hash` / `last_write_time` 运行时状态，并把 dedup 判定固定在 `spool.enqueue()` 之前执行
- [ ] 7.5 GREEN：实现“仅当 `capture_trigger ∉ {idle, manual}`、`content_hash != null`、同设备 `<30s` 同 hash 时才 `dedup_skipped`”的 Host dedup 规则
- [ ] 7.6 GREEN：保证 `permission_blocked` 分支不会进入 dedup skip，`transient_failure` 不会单独产出 `permission_blocked`，且 `ax_empty` 与 `ax_timeout_partial` 的 `content_hash` 语义分别符合 specs
- [ ] 7.7 GREEN：修改 `openrecall/client/spool.py`，扩展 spool JSON metadata，使其稳定携带 `accessibility_text`、`content_hash`、`browser_url`、`device_name`、`capture_trigger`、`event_ts`、outcome 与原始证据字段
- [ ] 7.8 GREEN：修改 `openrecall/client/spool.py` 或相关证据导出辅助逻辑，只补齐 dedup / outcome / runtime pid / time-window 原始信号；`window_id`、`restart_events`、`broken_window` 的推导保留在 acceptance aggregation 层，不回灌主链路 truth
- [ ] 7.9 GREEN：复查 `openrecall/server/database/migrations/20260227000001_initial_schema.sql` 与相关 runner/DDL 使用点，确认 S2b 只复用已存在字段，不额外引入超出 specs 的新持久化语义
- [ ] 7.10 VERIFY：重跑本切片相关测试，确认 dedup、pre-upload outcome、spool evidence 与 ingest-side `schema_rejected` 的 owner 已被测试锁死

### 8. Acceptance script and evidence export

- [ ] 8.1 RED：新增或扩展本地脚本测试（如 `tests/test_p1_s2b_local_script.py`），静态校验 `p1_s2b_local.sh` 的帮助输出、证据文件骨架与关键指标字段，并确认测试先失败
- [ ] 8.2 GREEN：新增 `scripts/acceptance/p1_s2b_local.sh`，编排 S2b 单元/集成测试、运行时样本采集、health snapshots、Browser URL 分类统计与 UI proof 导出，并固定生成 `p1-s2b-proof-filter.json`、`p1-s2b-health-snapshots.json`、`p1-s2b-outcomes.json`、`p1-s2b-ui-proof.md`
- [ ] 8.3 GREEN：在 acceptance 导出中补齐 `ax_hash_eligible`、`inter_write_gap_sec`、`browser_url_*` 分类、`capture_cycle_latency`、outcome 计数、`focused_context_mismatch_count`、`host_pid` / `edge_pid` 原始窗口信息，以及 proof filter `attempts[]` / `aggregates` 所需的最小输入信号
- [ ] 8.4 GREEN：在 acceptance 聚合逻辑中基于 runtime 原始信号生成 `window_id`、`restart_events`、`broken_window` 与 proof sample / migration observation 区分；proof filter 必须按 `design.md` 的 `Design Closure Summary` 与 `specs/v3-only-ax-mainline/spec.md` 的 taxonomy 由这一层以统一机制排除 alias-only、mixed-version、`final_device_name` 不可信、`schema_rejected`、`queue_rejected` 与 `broken_window=true` 样本，且不把这些派生字段回写为主链路 truth
- [ ] 8.4a GREEN：确保 proof filter 输出的 `attempts[]` 至少包含 `capture_id`、`frame_id?`、`outcome`、`proof_status`、`exclusion_reason?`、`metric_eligibility[]`、`final_device_name?`，并明确 `dedup_skipped`、`permission_blocked`、`ax_empty` 属于合法 outcome 而非默认 exclusion
- [ ] 8.5 VERIFY：运行本地脚本测试并检查 evidence skeleton 与字段名是否已在自动化层固定

## Acceptance Verification

### 9. Baseline and regression checks

- [ ] 9.1 运行与 S2b 相关的基线测试：`pytest tests/test_p1_s1_ingest.py tests/test_p1_s2a_server_contracts.py tests/test_p1_s2a_device_binding.py -q`
- [ ] 9.2 运行新的 S2b 契约测试：`pytest tests/test_p1_s2b_content_hash.py tests/test_p1_s2b_ax_timeout.py tests/test_p1_s2b_focused_context.py tests/test_p1_s2b_device_binding.py tests/test_p1_s2b_browser_url.py tests/test_p1_s2b_permission_recovery.py -q`；该组测试应随功能演进持续通过，而不是留到实现完成后集中补齐
- [ ] 9.3 启动 Edge（`./run_server.sh --debug`）与 Host（`./run_client.sh --debug`），确认 `/v1/health`、`/v1/ingest/queue/status` 与 `#mr-health` 在 S2b 变更后仍可稳定工作

### 10. Raw handoff and ingest validation

- [ ] 10.1 提交 empty-AX 样本，确认 `accessibility_text=""`、`content_hash=null` 可被 `/v1/ingest` 接受且不被当作 generic failure
- [ ] 10.2 提交缺失 `accessibility_text`、`content_hash`、`device_name` 或非法 `content_hash=""` 的样本，确认 `/v1/ingest` 返回 `400 INVALID_PARAMS`，且 `frames` 行数与 queue 计数不变；该类样本记为 `schema_rejected` 而不是 recorder outcome
- [ ] 10.3 构造 AX timeout 但 partial text 非空的样本，确认其进入 `ax_timeout_partial` 而不是 `ax_empty`，并且 `content_hash` 仍按最终文本生成
- [ ] 10.4 构造仅依赖 `active_app` / `active_window` alias 才能补全上下文的样本，确认其只作为 migration observation，不进入 proof sample 统计

### 11. Context, URL, and dedup validation

- [ ] 11.1 构造 `event_device_hint != final_device_name` 的样本，确认最终 payload、`frames`、dedup bucket 与 `inter_write_gap_sec` 仅按 `final_device_name` 解释
- [ ] 11.2 对 Chrome、Safari、Edge 构造 Browser URL required evidence，确认 success / stale reject / failed-all-tiers 分类可区分，且 required browser success denominator 不混入 Arc
- [ ] 11.3 对 Arc 构造 title mismatch 场景，确认结果记为 `browser_url_rejected_stale` 或 `browser_url_skipped`，最终 `browser_url=None`
- [ ] 11.4 对同一 `final_device_name` 构造 `<30s`、`=30s`、`>30s` 同 hash 的非 `idle` / `manual` 样本，确认仅 `<30s` 发生 `dedup_skipped`；对 `idle` / `manual` 重复样本确认不会被 dedup 丢弃
- [ ] 11.5 导出 `ax_hash_eligible` coverage 与 `inter_write_gap_sec` 样本，确认 `broken_window=true` 的窗口不会进入 Hard Gate proof 集合

### 12. Permission and health verification

- [ ] 12.1 制造 startup denied、mid-run revoked、recovered 三类权限场景，确认状态机按 `granted -> transient_failure -> denied_or_revoked -> recovering -> granted` 收敛
- [ ] 12.2 验证 `transient_failure` 仅作为计数/观测态存在，不单独产出 `permission_blocked`，且不会把 screenshot-path continuity 误标记为降级停摆
- [ ] 12.3 在 `denied_or_revoked` / `recovering` 期间确认 screenshot / heartbeat 仍继续，但 AX walk / Browser URL / dedup 停止，且结果记为 `permission_blocked`
- [ ] 12.4 验证 `/v1/health` 与 `#mr-health`：`capture_permission_status` 与 `screen_capture_status` 可同时表达 AX capability degraded + screenshot continuity，`denied_or_revoked` / `recovering` 显示 `degraded`，`unreachable` 仅在网络/服务不可达时出现，不复用为权限状态

### 13. Final S2b evidence run

- [ ] 13.1 运行 `scripts/acceptance/p1_s2b_local.sh`，确认生成 S2b metrics、health snapshots、UI proof、raw sample 序列、`p1-s2b-proof-filter.json`、`p1-s2b-health-snapshots.json`、`p1-s2b-outcomes.json` 与 Gate 摘要文件
- [ ] 13.2 检查证据包中是否包含 `content_hash` coverage、`ax_hash_eligible`、`inter_write_gap_sec`、`browser_url_*` 分类、`capture_cycle_latency`、outcome 计数、`focused_context_mismatch_count`、`window_id`、`restart_events`、`broken_window`，以及 proof filter 的 `inputs`、`ruleset_version`、`attempts[]`、`aggregates`
- [ ] 13.3 检查 `p1-s2b-proof-filter.json` 中逐 attempt 记录是否具备 frozen schema，且 `dedup_skipped`、`permission_blocked`、`ax_empty` 被保留为合法 outcome，而不是被错误降格为 exclusion
- [ ] 13.4 根据证据包复核 S2b 仅证明 `/v1/*` + v3 runtime/store 主链路正确性，且 legacy `/api/*` 与 mixed-version observation 未混入最终 Gate 结论
