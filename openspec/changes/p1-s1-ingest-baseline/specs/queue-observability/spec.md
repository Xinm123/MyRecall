## ADDED Requirements

### Requirement: 队列状态端点实时计数

Edge SHALL 提供 `GET /v1/ingest/queue/status` 端点，返回 JSON 响应，包含 `pending`、`processing`、`completed`、`failed`、`processing_mode`、`capacity`、`oldest_pending_ingested_at` 七个字段。四个计数字段 MUST 与 DB 中 `frames.status` 对应值的实时行数一致。

#### Scenario: 正常返回队列状态

- **WHEN** 客户端请求 `GET /v1/ingest/queue/status`
- **THEN** Edge 返回 `200 OK`，响应体包含 `{"pending": <int>, "processing": <int>, "completed": <int>, "failed": <int>, "processing_mode": "noop", "capacity": <int>, "oldest_pending_ingested_at": <ISO8601|null>}`

#### Scenario: 计数与 DB 实时一致

- **WHEN** 上传 10 条 capture 后立即请求 `GET /v1/ingest/queue/status`
- **THEN** `pending + processing + completed + failed` 的总和等于 `frames` 表总行数，且各计数分别等于 `SELECT COUNT(*) FROM frames WHERE status=<对应状态>` 的结果

### Requirement: 禁止使用进程累计计数器

四个计数字段（`pending`、`processing`、`completed`、`failed`）SHALL 每次请求实时从 DB 查询获得（如 `SELECT COUNT(*) ... WHERE status=...` 或等价 `GROUP BY`）。SHALL NOT 使用"进程启动后累计计数器"替代。

#### Scenario: 进程重启后计数连续

- **WHEN** Edge 进程重启后请求 `GET /v1/ingest/queue/status`
- **THEN** 返回的计数反映 DB 中的实际行数（包含重启前写入的数据），而非从零开始

### Requirement: processing_mode 字段

`GET /v1/ingest/queue/status` 的响应 SHALL 包含 `processing_mode` 字段。P1-S1 阶段该字段 MUST 固定为 `"noop"`。

#### Scenario: P1-S1 返回 noop

- **WHEN** P1-S1 阶段请求 `GET /v1/ingest/queue/status`
- **THEN** 响应体 `processing_mode` 值为字符串 `"noop"`

### Requirement: oldest_pending_ingested_at 语义

`oldest_pending_ingested_at` SHALL 返回最早一条 `status='pending'` 帧的 `frames.ingested_at`（UTC ISO8601 格式）。当 `pending=0` 时，该字段 MUST 返回 `null`。

#### Scenario: 有 pending 帧时返回最早时间戳

- **WHEN** DB 中存在多条 `status='pending'` 的 `frames` 行
- **THEN** `oldest_pending_ingested_at` 等于这些行中 `ingested_at` 最小值的 ISO8601 表示

#### Scenario: 无 pending 帧时返回 null

- **WHEN** DB 中无 `status='pending'` 的 `frames` 行（`pending=0`）
- **THEN** `oldest_pending_ingested_at` 为 JSON `null`（不得返回空字符串、`0` 或当前时间）

### Requirement: capacity 字段

`capacity` SHALL 返回队列最大容量（固定配置值）。该值 MUST 与 `POST /v1/ingest` 判定 `503 QUEUE_FULL` 时使用的阈值一致。

#### Scenario: capacity 与 503 阈值一致

- **WHEN** `capacity` 配置为 200，且 `pending` 达到 200
- **THEN** `GET /v1/ingest/queue/status` 返回 `capacity=200`，且同时 `POST /v1/ingest` 返回 `503 QUEUE_FULL`

### Requirement: processing_mode=noop 启动日志锚点

Edge 在启动完成（HTTP server ready）后，MUST 输出且仅输出一次日志行：`MRV3 processing_mode=noop`。Gate 脚本以该行的字面匹配为准。

#### Scenario: 启动时输出一次锚点

- **WHEN** Edge 以 `processing_mode=noop` 启动并完成 HTTP server 初始化
- **THEN** 启动日志中出现恰好一次 `MRV3 processing_mode=noop`（字面匹配），且不出现 OCR/provider/model preload 的初始化日志

#### Scenario: 运行期间不重复输出

- **WHEN** Edge 持续运行并处理多个请求
- **THEN** `MRV3 processing_mode=noop` 在整个进程生命周期内仅出现一次

### Requirement: noop 模式禁止模型初始化

当 `processing_mode=noop` 时，Edge SHALL NOT 初始化/加载任何 OCR、embedding、vision provider 或模型（包括启动期 preload）。SHALL NOT 写入任何 AI 衍生产物。

#### Scenario: noop 启动不加载模型

- **WHEN** Edge 以 `processing_mode=noop` 启动
- **THEN** 不调用 `preload_ai_models()`，不启动 `ProcessingWorker`，启动日志中无 OCR/provider/model 相关初始化记录

### Requirement: QueueDriver（noop）状态推进

Edge MUST 启动一个后台 QueueDriver，在 `processing_mode=noop` 下异步推进状态：`pending -> completed`。允许实现上经过 `processing` 中间态，但 Gate 脚本不依赖 `processing` 的可观测性。

#### Scenario: 帧从 pending 推进到 completed

- **WHEN** 通过 `POST /v1/ingest` 成功上传一条帧（`status='pending'`）
- **THEN** QueueDriver 在后台将该帧状态推进为 `completed`，`GET /v1/ingest/queue/status` 中 `completed` 计数增加

### Requirement: 失败日志锚点

当任一事件导致 `failed` 计数增加时，Edge MUST 输出结构化日志：`MRV3 frame_failed reason=<REASON> request_id=<uuid-v4> capture_id=<uuid-v7> frame_id=<int_optional>`。`<REASON>` 仅允许枚举：`DB_WRITE_FAILED`、`IO_ERROR`、`STATE_MACHINE_ERROR`。

#### Scenario: DB 写入失败输出日志

- **WHEN** 帧处理过程中因 DB 写入异常导致状态变为 `failed`
- **THEN** 日志中出现 `MRV3 frame_failed reason=DB_WRITE_FAILED request_id=<uuid> capture_id=<uuid> frame_id=<int>`

#### Scenario: IO 错误输出日志

- **WHEN** 帧处理过程中因文件 IO 异常导致状态变为 `failed`
- **THEN** 日志中出现 `MRV3 frame_failed reason=IO_ERROR request_id=<uuid> capture_id=<uuid> frame_id=<int>`

#### Scenario: 禁止 AI 相关失败原因

- **WHEN** `processing_mode=noop` 下有帧进入 `failed` 状态
- **THEN** `reason` 不得为 `AI_INIT_FAILED`、`MODEL_LOAD_FAILED`、`OCR_INIT_FAILED` 或任何 AI/OCR/provider/model 相关原因
