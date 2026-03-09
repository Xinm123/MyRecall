## ADDED Requirements

### Requirement: 单帧幂等上传端点

Edge SHALL 提供 `POST /v1/ingest` 端点，接收 `multipart/form-data` 请求，包含 `capture_id`（UUID v7，必填）、`metadata`（JSON，CapturePayload 字段）和 `file`（JPEG 二进制，必填）三个 part。

`metadata` 的窗口/应用字段兼容键如下：
- app：`app_name` / `app` / `active_app`
- window：`window_name` / `window` / `active_window`

`metadata.timestamp` 推荐使用 UTC ISO8601；为兼容旧链路，Edge 可接受 Unix 时间戳字符串与 `capture_time` 别名，并在入库前统一标准化为 UTC ISO8601（`Z` 后缀）。

#### Scenario: 新帧上传成功

- **WHEN** Host 发送合法 `POST /v1/ingest` 请求，且 `capture_id` 在 DB 中不存在
- **THEN** Edge 返回 `201 Created`，响应体包含 `{"capture_id": "...", "frame_id": <int>, "status": "queued", "request_id": "<uuid-v4>"}`，且 `frames` 表新增一行（`status='pending'`），snapshot JPEG 持久化到 `${OPENRECALL_SERVER_DATA_DIR}/frames/` 目录

#### Scenario: 幂等重复上传

- **WHEN** Host 发送 `POST /v1/ingest` 请求，且 `capture_id` 已存在于 DB 中
- **THEN** Edge 返回 `200 OK`，响应体包含 `{"capture_id": "...", "frame_id": <int>, "status": "already_exists", "request_id": "<uuid-v4>"}`，`frames` 表无新增行，且响应体不包含错误 `code` 字段

### Requirement: 2xx 成功响应不包含错误 code 字段

Edge 的 `POST /v1/ingest` 在返回 `201` 或 `200` 时，响应体 SHALL NOT 包含 `code` 字段。`request_id` 字段 SHALL 始终存在。

#### Scenario: 201 响应无 code 字段

- **WHEN** 新帧上传成功，Edge 返回 `201 Created`
- **THEN** 响应 JSON 包含 `capture_id`、`frame_id`、`status`、`request_id`，且不包含 `code` 键

#### Scenario: 200 幂等响应无 code 字段

- **WHEN** 重复 `capture_id` 上传，Edge 返回 `200 OK`
- **THEN** 响应 JSON 包含 `capture_id`、`frame_id`、`status`（值为 `already_exists`）、`request_id`，且不包含 `code` 键

### Requirement: 统一错误响应格式

Edge 的 `POST /v1/ingest` 在返回 4xx/5xx 时，SHALL 使用统一错误格式：`{"error": "<人类可读消息>", "code": "<SNAKE_CASE_CODE>", "request_id": "<uuid-v4>"}`。

#### Scenario: 参数缺失或格式错误返回 400

- **WHEN** 请求缺少 `capture_id` 或 `file` 字段，或 `capture_id` 不符合 UUID v7 格式
- **THEN** Edge 返回 `400`，响应体 `code` 为 `INVALID_PARAMS`

#### Scenario: 图片超过大小限制返回 413

- **WHEN** 上传的 `file` 大小超过 10MB
- **THEN** Edge 返回 `413`，响应体 `code` 为 `PAYLOAD_TOO_LARGE`

#### Scenario: 队列满返回 503

- **WHEN** DB 实时 `pending >= capacity` 时收到上传请求
- **THEN** Edge 返回 `503`，响应体 `code` 为 `QUEUE_FULL`，且包含 `retry_after` 字段（整数秒）

#### Scenario: 服务器内部错误返回 500

- **WHEN** Edge 处理请求时发生未预期异常
- **THEN** Edge 返回 `500`，响应体 `code` 为 `INTERNAL_ERROR`

### Requirement: 4xx/5xx 不创建或修改 frames 行

Edge 在返回 `400`、`413`、`503` 时，SHALL NOT 创建或修改任何 `frames` 行。

#### Scenario: 400 不影响 DB

- **WHEN** 请求因参数校验失败返回 `400`
- **THEN** `frames` 表行数与请求前一致，`GET /v1/ingest/queue/status` 计数不变

#### Scenario: 413 不影响 DB

- **WHEN** 请求因图片过大返回 `413`
- **THEN** `frames` 表行数与请求前一致

#### Scenario: 503 不影响 DB

- **WHEN** 请求因队列满返回 `503`
- **THEN** `frames` 表行数与请求前一致，无新 `pending` 行

### Requirement: capture_id 去重由 DB UNIQUE 约束保障

`frames.capture_id` 列 SHALL 具有 `UNIQUE` 约束。幂等判定 SHALL 依赖 DB 层 `INSERT OR IGNORE`（或等效机制），不依赖应用层缓存。

#### Scenario: DB 层拒绝重复 capture_id

- **WHEN** 两个并发请求携带相同 `capture_id` 同时到达
- **THEN** 仅一个请求创建 `frames` 行并返回 `201`；另一个返回 `200` + `already_exists`；`frames` 表中该 `capture_id` 仅存在一行

### Requirement: JPEG 主链路持久化

`POST /v1/ingest` 接收的图片 SHALL 使用 `image/jpeg` 并以 JPEG 格式持久化到 `${OPENRECALL_SERVER_DATA_DIR}/frames/` 目录，`frames.snapshot_path` 记录该 JPEG 文件的路径。P1-S1 阶段 SHALL NOT 接收 PNG/WebP 等非 JPEG 上传。

#### Scenario: JPEG 文件正常持久化

- **WHEN** 上传 `image/jpeg` 文件并返回 `201`
- **THEN** `frames.snapshot_path` 指向 `${OPENRECALL_SERVER_DATA_DIR}/frames/` 下的 `.jpg` 或 `.jpeg` 文件，该文件可读且为合法 JPEG

#### Scenario: 非 JPEG 上传被拒绝

- **WHEN** 上传 `image/png`、`image/webp` 或其他非 `image/jpeg` 文件
- **THEN** Edge 返回 `400`，响应体 `code` 为 `INVALID_PARAMS`，且不创建或修改任何 `frames` 行

### Requirement: Host spool 与上传语义

Host SHALL 将 capture 写入 `~/MRC/spool/`（`.jpg` + `.json`），使用原子写入（`.tmp` -> `rename`）。Uploader SHALL 向 `POST /v1/ingest` 发送 multipart 请求；收到 `201` 或 `200`（`already_exists`）时删除 spool 项；收到 `503` 时遵守 `retry_after`；网络失败时无限重试（exponential backoff：`1s -> 2s -> 4s -> 8s ...` 上限 `60s`）。

#### Scenario: 上传成功后删除 spool 项

- **WHEN** Uploader 收到 `201 Created` 或 `200 OK`（`already_exists`）
- **THEN** 对应的 spool `.jpg` 和 `.json` 文件被删除

#### Scenario: 503 时遵守 retry_after

- **WHEN** Uploader 收到 `503` + `retry_after=30`
- **THEN** Uploader 在至少 30 秒后才重试该 spool 项，不立即重试

#### Scenario: 网络断连时无限重试

- **WHEN** 网络不通导致请求失败
- **THEN** Uploader 按 exponential backoff 重试（`1s -> 2s -> 4s -> 8s ...` 上限 `60s`），spool 项不删除

#### Scenario: 进程重启后自动续传

- **WHEN** Host 进程重启或断电恢复
- **THEN** spool 目录中残留的 `.jpg` + `.json` 项被自动重新上传

#### Scenario: spool 原子写入

- **WHEN** Host 产生一条新 capture
- **THEN** 先写入 `.tmp` 临时文件，再 `rename` 为 `.jpg`/`.json`，避免中途崩溃产生不完整文件

### Requirement: 503 QUEUE_FULL 一致性

`503 QUEUE_FULL` 的触发条件 SHALL 与 `GET /v1/ingest/queue/status` 返回的 `pending` 和 `capacity` 口径一致：当 DB 实时 `pending >= capacity` 时拒绝入队。不允许使用与 queue/status 不同的计数源。

#### Scenario: pending 达到 capacity 时拒绝

- **WHEN** DB 中 `frames.status='pending'` 的行数 `>= capacity`，此时收到新 `POST /v1/ingest`
- **THEN** Edge 返回 `503` + `QUEUE_FULL`，且同时调用 `GET /v1/ingest/queue/status` 可观测到 `pending >= capacity`
