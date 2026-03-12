## ADDED Requirements

### Requirement: v3-only proof path for S2b correctness
系统 MUST 将 S2b 的功能正确性证明限制在 `/v1/*` + v3 runtime/store 主链路：`Host capture -> spool/uploader -> POST /v1/ingest -> v3 queue/status -> S3 handoff`。所有 S2b capability、字段 requiredness、Gate evidence 与 acceptance 结论 MUST 仅基于该主链路得出。进入 proof sample 的 payload MUST 使用 canonical keys `app_name`、`window_name`、`browser_url`、`device_name`；兼容 alias 仅允许用于迁移观测，不得构成 proof sample 真值。

Acceptance impact: 该要求冻结 S2b 的证明链路边界；tests、runbook、evidence 与人工验收都必须以 `/v1/*` + v3 runtime/store 为唯一正确性口径。

#### Scenario: Accept S2b evidence only from v3 mainline
- **WHEN** 某个样本来自 `/v1/*` 主链路并使用 v3 runtime/store
- **THEN** 系统 MAY 将其纳入 S2b Gate 证明样本

#### Scenario: Exclude alias-only payloads from proof samples
- **WHEN** 某个 `/v1/*` 样本仅依赖 `active_app`、`active_window` 等兼容 alias 才能补全上下文语义
- **THEN** 该样本 MUST 视为 compatibility or migration observation，而不得进入 S2b proof sample 集合

#### Scenario: Exclude non-v3 paths from proof
- **WHEN** 某个样本依赖 legacy `/api/*`、旧 worker 或非 v3 持久化路径
- **THEN** 该样本 MUST NOT 作为 S2b 正确性证明使用

### Requirement: Legacy path remains compatibility-only
legacy `/api/*` 与旧 worker MAY 保留用于兼容回归检查，但 MUST NOT 承载新的 S2b 字段语义、required-key 契约、Browser URL stale rejection、Host dedup owner、或 `device_name` / `focused_context` frozen rules。若实现需要复用旧代码，复用 MUST 通过 adapter 接入 v3 主链路，而不得把 legacy 语义反向带回 `/v1/*`。

Acceptance impact: 该要求冻结 legacy compatibility 的边界；兼容回归通过不代表 S2b 功能通过，相关样本不得混入主 Gate 证据。

#### Scenario: Keep legacy success separate from S2b correctness
- **WHEN** legacy `/api/*` 路径在兼容测试中继续工作
- **THEN** 该结果 MUST 仅作为兼容回归结论，而不能被解释为 S2b v3 主链路已满足要求

### Requirement: Mixed Host/Edge versions are not proof samples
当 Host 与 Edge 版本组合导致 `accessibility_text` / `content_hash` / `device_name` / `browser_url` 契约不完整时，系统 MUST 将该样本视为 mixed-version observation，而不是有效 S2b proof sample。以下任一命中都 MUST 触发 mixed-version or migration exclusion：required key 缺失、canonical key 缺失但 alias 存在、legacy `/api/*` 重定向接入、或 Edge 未执行 S2b required-field 校验。系统 MAY 记录此类样本用于迁移诊断，但 MUST 将其排除在 S2b Gate 统计之外。

Acceptance impact: 该要求冻结 mixed-version 样本排除规则；阶段收口时必须显式区分 proof samples 与 migration observations。

#### Scenario: Exclude mixed-version payloads from Gate statistics
- **WHEN** Host 或 Edge 缺失 S2b 必需字段校验或上传契约，导致 payload 不能完整体现 `accessibility_text` / `content_hash` / `device_name` / `browser_url` 规则
- **THEN** 该样本 MUST 不进入 S2b Gate proof 统计，并应被标记为 mixed-version observation

### Requirement: Proof filtering is mechanized and centrally owned
系统 MUST 通过单一 mechanized proof filter 产出 S2b proof sample 集合，而不是依赖人工说明或分散在多处脚本/代码中的隐式排除逻辑。该 filter 的 owner 与边界以 `design.md` 的 `Design Closure Summary` 为准。该 filter 的权威输出 MUST 为 `artifacts/p1-s2b/p1-s2b-proof-filter.json`。该 filter MUST 至少排除：alias-only payload、mixed-version observation、`broken_window=true` 窗口，以及仅靠 compatibility fallback 才补齐 canonical keys 的样本。

Acceptance impact: 阶段收口必须能导出 proof sample exclusion 结果及其原因计数；没有 mechanized filter 的 evidence 不足以支撑 S2b Gate 结论。

#### Scenario: Emit one authoritative proof filter artifact
- **WHEN** S2b Gate evidence 被汇总
- **THEN** 系统 MUST 产出唯一权威文件 `p1-s2b-proof-filter.json`，并要求 SQL、health snapshot 与 UI evidence 仅在其 included/eligible universe 内解释

### Requirement: Proof filter input and output schema are explicit
系统 MUST 为 mechanized proof filter 冻结最小输入/输出契约。输入 MUST 至少包括：Host `capture_attempts` 信号、Edge `ingest_decisions` 信号、以及窗口/健康快照。输出 `p1-s2b-proof-filter.json` MUST 至少包含 `inputs`、`ruleset_version`、`attempts[]`、`aggregates` 四段；`attempts[]` 每条 MUST 至少记录 `capture_id`、`frame_id?`、`outcome`、`proof_status`、`exclusion_reason?`、`metric_eligibility[]`、`final_device_name?`。

Acceptance impact: 该要求冻结 proof filter 的最小 schema；没有这些字段的汇总结果不足以作为 Gate 审查依据。

#### Scenario: Classify attempts without losing non-frame outcomes
- **WHEN** proof filter 处理一个 `dedup_skipped`、`permission_blocked` 或 `ax_empty` 样本
- **THEN** 系统 MUST 将其保留为合法 outcome，并通过 `proof_status` / `metric_eligibility[]` 控制是否进入具体指标口径，而不得把它们一律降格为 exclusion

### Requirement: Proof exclusion reasons use a frozen taxonomy
系统 MUST 使用冻结的 exclusion-reason taxonomy，而不得在不同脚本或人工收口阶段自由发明排除原因。最小 taxonomy MUST 包含：`mixed_version`、`alias_only_payload`、`missing_canonical_keys`、`final_device_name_missing`、`final_device_name_mismatch`、`broken_window`、`schema_rejected`、`queue_rejected`。

Acceptance impact: 该要求冻结 proof exclusion 的解释口径；阶段审查必须能按上述原因统计，而不是使用临时自由文本。

#### Scenario: Exclude missing final device truth from proof
- **WHEN** 某个样本缺失可信 `final_device_name`，或只能从 event hint 反推 monitor truth
- **THEN** proof filter MUST 将其排除，并使用 `final_device_name_missing` 或 `final_device_name_mismatch` 作为明确原因
