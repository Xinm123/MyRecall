## ADDED Requirements

### Requirement: 帧图片读取端点

Edge SHALL 提供 `GET /v1/frames/:frame_id` 端点，根据 `frame_id`（`frames.id`）从 DB 查询 `snapshot_path` 并直接 serve 对应的 JPEG 文件，固定返回 `Content-Type: image/jpeg`。不做二次转码。

#### Scenario: 正常读取帧图片

- **WHEN** 请求 `GET /v1/frames/123`，且 `frames` 表中 `id=123` 存在且 `snapshot_path` 指向合法 JPEG 文件
- **THEN** Edge 返回 `200 OK`，`Content-Type: image/jpeg`，响应体为该 JPEG 文件的二进制内容

#### Scenario: 帧不存在返回 404

- **WHEN** 请求 `GET /v1/frames/999`，且 `frames` 表中无 `id=999` 的行
- **THEN** Edge 返回 `404`，响应体为统一错误格式 `{"error": "frame not found", "code": "NOT_FOUND", "request_id": "<uuid-v4>"}`

#### Scenario: snapshot_path 文件丢失

- **WHEN** `frames` 表中 `id=123` 存在但 `snapshot_path` 指向的文件已被删除或不可访问
- **THEN** Edge 返回 `404` 或 `500`，使用统一错误格式，且记录 `error` 级别日志（`IO_ERROR` 仅作为 reason code 使用）；该读路径 SHALL 保持只读，不得修改 `frames.status`，不得导致 queue `failed` 计数增加

### Requirement: 帧读取错误不改变队列状态

`GET /v1/frames/:frame_id` 在任何错误路径（含 snapshot 文件缺失）SHALL 为只读行为：不得调用会修改 `frames` 状态的写操作（如 `mark_failed`），不得改变 `pending/processing/completed/failed` 计数。

#### Scenario: 文件丢失后队列计数不变

- **WHEN** 对同一缺失 `snapshot_path` 的 `frame_id` 连续请求 `GET /v1/frames/:frame_id`
- **THEN** 每次请求均返回错误响应；`GET /v1/ingest/queue/status` 的 `pending/processing/completed/failed` 计数保持不变

### Requirement: 固定 Content-Type 为 image/jpeg

`GET /v1/frames/:frame_id` 的成功响应 SHALL 始终返回 `Content-Type: image/jpeg`，无论原始上传格式。不做内容协商。

#### Scenario: Content-Type 固定验证

- **WHEN** 连续请求多个不同 `frame_id` 的帧
- **THEN** 所有成功响应的 `Content-Type` 头均为 `image/jpeg`

### Requirement: snapshot 落盘目录隔离

v3 帧的 snapshot JPEG SHALL 存储在 `${OPENRECALL_SERVER_DATA_DIR}/frames/` 目录下，不复用现有 `settings.screenshots_path`（`${OPENRECALL_SERVER_DATA_DIR}/screenshots/`）。两个目录允许共存。

#### Scenario: 新帧写入 frames 目录

- **WHEN** 通过 `POST /v1/ingest` 成功上传帧
- **THEN** `frames.snapshot_path` 指向 `${OPENRECALL_SERVER_DATA_DIR}/frames/` 下的文件，而非 `${OPENRECALL_SERVER_DATA_DIR}/screenshots/` 目录
