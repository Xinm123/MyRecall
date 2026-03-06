## ADDED Requirements

### Requirement: 健康检查端点

Edge SHALL 提供 `GET /v1/health` 端点，返回对齐 screenpipe `HealthCheckResponse` 子集的健康信息。响应 MUST 包含 `status`、`last_frame_timestamp`、`frame_status`、`message`、`queue` 五个顶层字段。

#### Scenario: 正常健康响应

- **WHEN** 服务正常运行且最近 5 分钟内有帧入库
- **THEN** Edge 返回 `200 OK`，响应体为 `{"status": "ok", "last_frame_timestamp": "<ISO8601>", "frame_status": "ok", "message": "", "queue": {"pending": <int>, "processing": <int>, "failed": <int>}}`

### Requirement: status 字段语义

`status` 字段 SHALL 反映服务整体健康状态：`"ok"` 表示正常；`"degraded"` 表示部分降级；`"error"` 表示严重故障。
P1-S1 口径：`status` MUST 为 `"ok"` 当且仅当 `queue.failed == 0` 且 `frame_status == "ok"`；否则 MUST 为 `"degraded"`。`"error"` 在 P1-S1 阶段为保留值，SHALL NOT 返回。

#### Scenario: 正常状态返回 ok

- **WHEN** 服务运行正常，无 failed 帧，且有新帧入库
- **THEN** `status` 为 `"ok"`

#### Scenario: 有 failed 帧时降级

- **WHEN** `queue.failed > 0`
- **THEN** `status` MUST 为 `"degraded"`

#### Scenario: P1-S1 不返回 error

- **WHEN** P1-S1 阶段请求 `GET /v1/health`
- **THEN** `status` 只能为 `"ok"` 或 `"degraded"`，不得返回 `"error"`

### Requirement: frame_status 字段与 stale 判定

`frame_status` SHALL 反映帧接收状态。当超过 5 分钟无新帧入库时，`frame_status` MUST 为 `"stale"`。正常时为 `"ok"`。
stale 判定基于 Edge 入库时间（`frames.ingested_at`），不基于 capture 时间（`frames.timestamp`）。

#### Scenario: 最近有帧时返回 ok

- **WHEN** 最后一条帧的 `ingested_at` 距当前时间小于 5 分钟
- **THEN** `frame_status` 为 `"ok"`

#### Scenario: 超过 5 分钟无帧时返回 stale

- **WHEN** 最后一条帧的 `ingested_at` 距当前时间大于等于 5 分钟
- **THEN** `frame_status` 为 `"stale"`

#### Scenario: 无任何帧时

- **WHEN** `frames` 表为空（从未收到过帧）
- **THEN** `last_frame_timestamp` 为 `null`，`frame_status` MUST 为 `"stale"`，且 `status` MUST 为 `"degraded"`

### Requirement: queue 子对象

`queue` 子对象 SHALL 包含 `pending`、`processing`、`failed` 三个计数字段，与 `GET /v1/ingest/queue/status` 中对应字段口径一致（实时 DB 查询）。

#### Scenario: queue 计数与 queue/status 一致

- **WHEN** 同时请求 `GET /v1/health` 和 `GET /v1/ingest/queue/status`
- **THEN** 两个响应中 `pending`、`processing`、`failed` 的值一致（允许极小时间窗内的微差异）

### Requirement: last_frame_timestamp 字段

`last_frame_timestamp` SHALL 返回最新一条 `frames` 行的 `timestamp`（UTC ISO8601 格式）。当 `frames` 表为空时返回 `null`。
该字段仅用于回传最近 capture 时间，不用于 `frame_status` 的 stale 判定。

#### Scenario: 有帧时返回最新时间戳

- **WHEN** `frames` 表中有数据
- **THEN** `last_frame_timestamp` 等于 `SELECT MAX(timestamp) FROM frames` 的 ISO8601 表示

#### Scenario: 无帧时返回 null

- **WHEN** `frames` 表为空
- **THEN** `last_frame_timestamp` 为 JSON `null`
