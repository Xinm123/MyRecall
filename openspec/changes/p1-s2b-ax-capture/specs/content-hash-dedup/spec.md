## ADDED Requirements

### Requirement: content_hash canonicalization contract
系统 MUST 仅基于最终上报的 `accessibility_text` 计算 `content_hash`。计算前 MUST 固定执行以下 canonicalization：Unicode NFC、换行统一为 `\n`、每行去尾部空白、整体 `strip()`。当 canonicalized `accessibility_text` 为空字符串时，`content_hash` MUST 为 `null`；当其非空时，`content_hash` MUST 为 `sha256:` 前缀加 64 位十六进制字符串。

Acceptance impact: 该要求冻结 `content_hash` 的可重复计算口径；`test_p1_s2b_content_hash.py`、字段矩阵测试与 coverage SQL 的分子定义必须按本规则执行。

#### Scenario: Produce sha256 hash for non-empty canonicalized text
- **WHEN** 最终 `accessibility_text` 经 canonicalization 后非空
- **THEN** 系统 MUST 生成一个 `sha256:` 前缀的 `content_hash` 并将其写入最终 handoff

#### Scenario: Return null hash for empty canonicalized text
- **WHEN** 最终 `accessibility_text` 经 canonicalization 后为空字符串
- **THEN** 系统 MUST 将 `content_hash` 写为 `null`，且不得写为空字符串或伪 hash 值

### Requirement: ax_hash_eligible denominator
系统 MUST 将 `ax_hash_eligible = TRIM(COALESCE(accessibility_text, '')) <> ''` 作为 `content_hash` coverage 的唯一分母定义。系统 MUST NOT 使用 `text_source`、OCR 成功与否、或其他后续处理阶段字段过滤 S2b coverage 样本。

Acceptance impact: 该要求直接冻结 S2b Gate SQL 分母；coverage 统计、报表与 runbook 必须按 `ax_hash_eligible` 口径执行。

#### Scenario: Count only non-empty raw AX text in coverage denominator
- **WHEN** 某帧的 `accessibility_text` 在 `TRIM(COALESCE(...))` 后非空
- **THEN** 该帧 MUST 进入 `ax_hash_eligible` 分母，并按 `content_hash` 是否非空参与 coverage 统计

#### Scenario: Exclude empty-AX samples from coverage denominator
- **WHEN** 某帧的 `accessibility_text` 为空字符串或仅包含空白
- **THEN** 该帧 MUST NOT 进入 `ax_hash_eligible` 分母，但仍可作为 empty-AX no-drop 样本上传

### Requirement: Host dedup before upload
系统 MUST 在 Host 侧、`spool.enqueue()` 之前基于 `content_hash` 与最近一次成功 spool 写入时间执行 dedup。仅当以下条件同时满足时，系统才允许跳过上传：`capture_trigger` 不属于 `idle` 或 `manual`、`content_hash` 非 `null`、同一 `final_device_name` 上次成功写入距当前小于 30 秒、且 hash 与上次相同。`last_write_time` 的语义 MUST 固定为“最近一次成功写入 Host 本地 spool 的 wall-clock time”。dedup runtime state 默认 MUST 为进程内存态，跨重启不继承。Edge MUST NOT 承担该 dedup 判定职责。

Acceptance impact: 该要求冻结 `inter_write_gap_sec`、dedup hit 与 30 秒 floor 的验证口径；Hard Gate 取证必须以 Host 侧结果为准。

#### Scenario: Skip duplicate non-idle capture within 30 seconds
- **WHEN** 同一 `final_device_name` 的新 capture 与最近一次成功 spool 写入相比，`content_hash` 相同且间隔小于 30 秒，并且 `capture_trigger` 不是 `idle` 或 `manual`
- **THEN** 系统 MUST 跳过该帧的上传路径，并将其记为 dedup skip

#### Scenario: Preserve idle and manual captures despite matching hash
- **WHEN** `capture_trigger` 为 `idle` 或 `manual`，且 `content_hash` 与最近样本相同
- **THEN** 系统 MUST 仍允许该帧继续进入 spool / upload，而不是触发 dedup skip

### Requirement: inter_write_gap_sec and broken_window evidence
系统 MUST 以每个 `device_name` 为分桶导出 `inter_write_gap_sec` 证据，并在 Host 或 Edge 重启打断统计窗口时把受影响窗口标记为 `broken_window=true`。被标记为 `broken_window=true` 的窗口 MAY 用于 observation，但 MUST NOT 作为 S2b Hard Gate 的有效证明样本。S2b MUST 明确区分原始运行时信号与最终证据归属：runtime 至少负责暴露 `host_pid`、`edge_pid` 与时间窗原始样本；Gate script or evidence aggregator 负责产出 `window_id`、`restart_events` 与最终 `broken_window` 判定。

Acceptance impact: 该要求冻结 `inter_write_gap_sec` 的分桶与跨重启排除规则；Gate 报表必须区分有效样本与 `broken_window` 样本。

#### Scenario: Mark restarted windows as broken_window
- **WHEN** Host 或 Edge 在 `inter_write_gap_sec` 统计窗口内发生重启
- **THEN** 系统 MUST 将该窗口标记为 `broken_window=true`，并将其从 Hard Gate 证明样本中排除
