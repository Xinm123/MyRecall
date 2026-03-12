## Why

P1-S2a 已完成事件驱动触发与基础健康暴露，但 P1 仍缺少进入 S3 之前必须冻结的 AX 采集能力：macOS AXUIElement 遍历、`accessibility_text` / `content_hash` raw handoff 契约、Browser URL stale rejection、以及 capability failure 与 semantic fallback 的分责边界。P1-S2b 现在需要把这些行为收口到 v3-only 主链路，确保后续处理阶段可以直接消费稳定的原始输入，而不会把权限失效、空 AX、URL 陈旧或 monitor 绑定错误混入 S3 语义。

涉及冻结行为、handoff 契约或 Gate 阈值时，本提案按 `docs/v3/spec.md` > `docs/v3/data-model.md` > `docs/v3/open_questions.md` > `docs/v3/acceptance/phase1/p1-s2b.md` > `docs/v3/gate_baseline.md` 的优先级解释；若出现冲突，以更高优先级文档为准，不在本提案中重写规则。

## What Changes

- **新增 macOS AX 采集主能力**：Host capture 拓扑收敛为 `TriggerSource -> TriggerBus(broadcast) -> MonitorWorker[N]`。在每个 monitor worker 的 capture 周期内执行 screenshot、AXUIElement 遍历与文本提取，遵守 `walk_timeout=500ms`、`max_depth=30`、`max_nodes=5000` 的 S2b 基线，并保持 `capture_trigger` 语义继续使用 `idle`、`app_switch`、`manual`、`click`。
- **冻结 raw handoff 契约**：`POST /v1/ingest` 的 v3 主链路必须上传 `accessibility_text` 与 `content_hash`；其中 `accessibility_text` 为 required string（允许 `""`，禁止 `null`），`content_hash` 为 required nullable string（允许 `null`，禁止 `""`）。空 AX 必须 no-drop 上传，并固定表达为 `accessibility_text=""`、`content_hash=null`；partial AX text 仍按最终上报值计算 hash。S2b 生效后，上述 required-key 规则仅以 `/v1/*` + v3 Host/Edge 主链路为正确性判定口径；若存在 mixed Host/Edge 版本运行，不纳入 S2b Gate 证明样本。
- **冻结上下文一致性规则**：`focused_context = {app_name, window_name, browser_url}` 必须由同一轮 snapshot 一次性产出，允许部分字段为 `None`，但禁止字段级混拼；无法确认同轮一致性时，必须按 Better None than wrong 写 `None`，不得猜测填写。进入 proof sample 的 payload 必须使用 canonical keys `app_name`、`window_name`、`browser_url`、`device_name`；`active_app`、`active_window` 等 alias 仅允许用于 compatibility/migration observation。`device_name` 必须表示本次实际被截取的 monitor；迁移期内部若仍保留事件源预绑定值，则其仅可视为 `event_device_hint`，而 payload、落盘、dedup bucket 与验收统计一律以 `final_device_name` 为准。两者要求 same-cycle coherence，但不得伪装成全局原子快照；一旦出现已确认错误的非空 `window_name` 或 `browser_url`，按 S2b failure 处理。
- **新增 Browser URL stale rejection 能力**：按 screenpipe 风格实现三层 URL 提取与校验链，要求 `browser_url` 只有在与同轮 `focused_context` 交叉校验一致时才可写入；校验失败、陈旧或无法确认时必须写 `null`，遵循 Better None than wrong URL。
- **新增 `content_hash` canonicalization 与 Host dedup 规则**：`content_hash` 仅基于最终上报的 `accessibility_text` 计算；计算前固定执行 Unicode NFC、换行统一为 `\n`、每行去尾部空白、整体 `strip()`；当 `TRIM(COALESCE(accessibility_text, '')) = ''` 时，`content_hash` 必须为 `null`。`ax_hash_eligible = TRIM(COALESCE(accessibility_text, '')) <> ''` 作为 coverage 分母；非 `idle` / `manual` 的重复帧在 Host 侧基于 hash 与最近成功写入 Host 本地 spool 的时间执行 dedup，并把 `inter_write_gap_sec` 作为每 `device_name` 分桶的 Hard Gate 证据口径。跨重启窗口必须标记 `broken_window=true`，但其最终判定由 Gate/evidence 聚合层负责，runtime 仅提供原始 pid 与时间窗信号。
- **冻结 capability failure 边界与权限恢复闭环**：`granted`、`transient_failure`、`denied_or_revoked`、`recovering` 四态继续作为权限状态机口径；连续 2 次失败进入 `denied_or_revoked`，连续 3 次成功恢复到 `granted`，权限轮询周期保持 `10s`，冷却时间保持 `300s`。该状态机只表达 AX capability，不吞并 screenshot path 故障。`transient_failure` 仅用于计数与观测，不单独产出 capability-blocked handoff；只有 `denied_or_revoked` 与 `recovering` 才进入 capability-blocked 路径：截图与 heartbeat 继续，AX walk / URL 提取 / dedup 停止，结果以 `permission_blocked` outcome 与 `accessibility_text=""`、`content_hash=null`、`browser_url=null` 表达；不得被伪装成 OCR fallback 或普通空 AX。`/v1/health` 中 AX capability 与 screenshot-path continuity 必须分开暴露，不得共用同一状态字段。
- **锁定 v3-only 证明链路**：S2b 功能正确性只认 `/v1/*` + v3 runtime/store；legacy `/api/*` 与旧 worker 仅做兼容检查，不承载新的 S2b 语义、字段规则或 Gate 责任。
- **冻结 capture outcome 与 proof sample 过滤**：S2b 结果分类收敛为 `capture_completed`、`ax_empty`、`ax_timeout_partial`、`browser_url_rejected_stale`、`permission_blocked`、`dedup_skipped`、`spool_failed`、`schema_rejected`。其中前七类属于 Host recorder 的 pre-upload outcome，`schema_rejected` 明确属于 uploader / `/v1/ingest` 的 contract-failure classification。阶段收口必须由单一 mechanized proof filter 读取 Host capture attempts、Edge ingest decisions 与窗口/健康快照，并输出权威文件 `artifacts/p1-s2b/p1-s2b-proof-filter.json`。legacy `/api/*`、alias-only payload、mixed-version required-key 缺失、`final_device_name` 不可信、以及 `broken_window=true` 样本都不得进入 S2b Gate proof；`dedup_skipped`、`permission_blocked`、`ax_empty` 属于合法 outcome，不是 proof exclusion reason。
- **补齐阶段交付物**：新增 S2b 的 Gate 校验测试与本机收口脚本。测试范围至少覆盖 `content_hash` coverage、AX timeout、S2b handoff 字段矩阵、focused-context 一致性、`device_name` binding、Browser URL stale rejection、权限恢复状态流转，以及 UI/health 证据导出。

## Non-goals

- S2b 只冻结 raw handoff correctness，不在本阶段定义 OCR fallback、`text_source` 最终归因或其他 S3 semantic interpretation
- OCR fallback、`text_source` 最终判定、`accessibility` / `ocr_text` 分表写入与失败语义（属于 P1-S3）
- 新的触发类型或事件监听扩展（typing_pause、scroll_stop、window_focus；属于 P2 或已在 P1-S2a 冻结）
- Windows/Linux AX 采集实现（属于 P2）
- Search / Chat / embeddings / elements 表等后续能力
- 为 legacy `/api/*` 回补新的 S2b 行为定义
- 额外的新页面或大规模 UI 重做；S2b 只要求既有健康与时间线证据可验证

## Capabilities

### New Capabilities
- `ax-raw-handoff`: AX 遍历、文本提取、empty-AX no-drop 上传与 `accessibility_text` / `content_hash` handoff 契约
- `focused-context-binding`: `focused_context` 与 `device_name` 的 same-cycle 绑定、一致性校验与不确定时写 `None`
- `browser-url-stale-rejection`: Browser URL 三层提取、title cross-check 与 stale rejection
- `content-hash-dedup`: `content_hash` canonicalization、`ax_hash_eligible` coverage 口径与 Host dedup / `inter_write_gap_sec` 规则
- `permission-recovery`: Accessibility 权限检测、`granted` / `transient_failure` / `denied_or_revoked` / `recovering` 状态流转与恢复闭环
- `v3-only-ax-mainline`: `/v1/*` + v3 runtime/store 主链路约束，以及 legacy `/api/*` 兼容隔离

### Modified Capabilities

无（`openspec/specs/` 当前为空，本提案仅新增 capability specs）

## Impact

- **Client 代码**：主要影响 `openrecall/client/accessibility/`、capture manager、`TriggerBus` / `MonitorWorker` 拓扑与上传前 dedup 路径；需要把 AX 遍历、`focused_context` 组装、`final_device_name` 绑定、URL 校验和权限恢复串成同一 worker capture 周期。
- **Server / API**：主要影响 `/v1/ingest` 的 CapturePayload 校验与 `/v1/health` 的 capability 降级证明链；`/v1/health` 负责 `ok` / `degraded` 与 permission evidence 的可观测性，`unreachable` 仅属于 UI/网络层观测，不作为 `/v1/health` 返回语义；`#mr-health` 与相关 `data-state` 必须能反映上述边界，而不是把权限故障吞掉。
- **数据与证据**：`frames` 中 `accessibility_text`、`content_hash`、`browser_url`、`device_name` 的写入口径被冻结；Gate 证据需要输出 `ax_hash_eligible`、`inter_write_gap_sec`、Browser URL 分类计数、capture outcome 分类，以及 `broken_window` / proof-sample 过滤结果。
- **测试与验收**：需要新增 `tests/test_p1_s2b_content_hash.py`、`tests/test_p1_s2b_ax_timeout.py`，并补齐 handoff/context/url/permission/device binding 相关测试；在阶段收口时交付 `scripts/acceptance/p1_s2b_local.sh` 与对应 evidence 文件。
- **依赖与运行环境**：保持 Python/macOS 实现路线，依赖 pyobjc / macapptree；Arc AppleScript 路径仍为 conditional evidence / timeboxed sub-scope，不影响 required browser mainline（Chrome/Safari/Edge）。
