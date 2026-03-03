# MyRecall-v3 API 契约规范（SSOT）

- 版本：v1.0
- 日期：2026-03-03
- 作用：本文件是 v3 对外 HTTP 契约的唯一事实源。
- 关联：[`spec.md`](./spec.md), [`data_model.md`](./data_model.md), [`decisions.md`](./decisions.md), [`gate_baseline.md`](./gate_baseline.md)

## API-000 范围

- 覆盖：`/v1/*` 端点、请求/响应 schema、统一错误、幂等语义。
- 不覆盖：DDL/SQL（见 `data_model.md`）、阶段 Gate（见 `roadmap.md`）。

## API-001 命名空间冻结

- v3 对外契约统一 `/v1/*`。
- `/api/*` 仅用于 v2 历史描述，不属于 v3 默认入口。
- 验收脚本与客户端默认调用路径不得依赖 `/api/*`。

引用：DEC-024A。

## API-002 统一错误响应

所有端点错误统一返回：

```json
{"error": "human readable message", "code": "SNAKE_CASE_CODE", "request_id": "uuid-v4"}
```

错误码清单：

| `code` | HTTP 状态 | 触发场景 |
|---|---:|---|
| `INVALID_PARAMS` | 400 | 参数格式错误或缺失必填项 |
| `NOT_FOUND` | 404 | 资源（帧/文件）不存在 |
| `PAYLOAD_TOO_LARGE` | 413 | 图像超过大小限制 |
| `QUEUE_FULL` | 503 | ingest 队列满 |
| `INTERNAL_ERROR` | 500 | 未预期服务器错误 |
| `ALREADY_EXISTS` | 200 | `capture_id` 重复（幂等命中） |

引用：DEC-020A。

## API-010 CapturePayload 契约（Host -> Edge）

```python
class CapturePayload(BaseModel):
    capture_id: str                    # UUID v7, Host 生成
    timestamp: float                   # UNIX epoch 秒
    app_name: Optional[str] = None
    window_name: Optional[str] = None
    browser_url: Optional[str] = None
    device_name: str = ""
    focused: Optional[bool] = True
    capture_trigger: Optional[str] = None
    accessibility_text: Optional[str] = None
    content_hash: Optional[str] = None
    simhash: Optional[int] = None
```

字段验证：

| 字段 | 类型约束 | 必填 | 规则 |
|---|---|---|---|
| `capture_id` | string | ✅ | UUID v7；重复时返回 `ALREADY_EXISTS` |
| `timestamp` | float | ✅ | 不早于当前 30 天，不晚于当前 60 秒 |
| `device_name` | string | ✅ | 非空，最长 128 |
| `app_name` | string/null | ❌ | 最长 256 |
| `window_name` | string/null | ❌ | 最长 512 |
| `browser_url` | string/null | ❌ | 若非空须合法 URL，最长 2048 |
| `capture_trigger` | string/null | ❌ | P1 枚举：`idle/app_switch/manual/window_focus/click` |
| `content_hash` | string/null | ❌ | `sha256:` + 64 hex |
| `simhash` | int/null | ❌ | 非负 64 位整数 |
| `image_data` | multipart file | ✅ | JPEG/PNG，最大 10MB |

## API-100 `POST /v1/ingest`（单帧幂等上传）

### Request

- `Content-Type: multipart/form-data`
- fields:
  - `capture_id`: UUID v7
  - `metadata`: JSON（`CapturePayload`）
  - `file`: 二进制图像

### Response

- `201 Created`

```json
{"capture_id":"...","frame_id":123,"status":"queued"}
```

- `200 OK`（幂等命中）

```json
{"capture_id":"...","frame_id":123,"status":"already_exists","code":"ALREADY_EXISTS"}
```

- `400/413/503` 按统一错误响应。

### 幂等语义

- 相同 `capture_id`：不得重复入库，不得重复处理。
- `content_hash` 相同但 `capture_id` 不同：仍按新 capture 处理（不跨 `capture_id` 去重）。

引用：DEC-019A。

## API-101 `GET /v1/ingest/queue/status`

### Response 200

```json
{
  "pending": 5,
  "processing": 1,
  "completed": 1023,
  "failed": 2,
  "capacity": 200,
  "oldest_pending_timestamp": "2026-02-26T10:00:00Z"
}
```

字段语义：

- `pending/processing`: 当前队列实时态。
- `completed/failed`: 当前进程生命周期累计值（重启清零）。
- `capacity`: 队列容量上限；`pending >= capacity` 时 ingest 返回 `QUEUE_FULL`。
- `oldest_pending_timestamp`: 最老 pending 项时间戳，空队列时为 `null`。

## API-200 `GET /v1/search`

### Query Parameters

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `q` | string | `""` | 全文检索，空值返回全部 |
| `content_type` | string | `"all"` | `ocr/accessibility/all` |
| `limit` | uint32 | `20` | 最大 100 |
| `offset` | uint32 | `0` | 分页偏移（P1 为加载更多） |
| `start_time` | ISO8601 | null | 时间起点 |
| `end_time` | ISO8601 | null | 时间终点 |
| `app_name` | string | null | 应用名过滤 |
| `window_name` | string | null | 窗口名过滤 |
| `browser_url` | string | null | URL 过滤（FTS token 序列匹配） |
| `focused` | bool | null | 焦点过滤 |
| `min_length` | uint | null | OCR 文本最小长度（仅 OCR 路径） |
| `max_length` | uint | null | OCR 文本最大长度（仅 OCR 路径） |
| `include_frames` | bool | `false` | P1 预留，默认不返回 base64 |

### Response 200

```json
{
  "data": [
    {
      "type": "OCR",
      "content": {
        "frame_id": 123,
        "text": "提取的 OCR 文字",
        "timestamp": "2026-02-26T10:00:00Z",
        "file_path": "/data/screenshots/abc.png",
        "frame_url": "/v1/frames/123",
        "app_name": "Safari",
        "window_name": "GitHub - main",
        "browser_url": "https://github.com",
        "focused": true,
        "device_name": "MacBook-Pro",
        "tags": []
      }
    },
    {
      "type": "UI",
      "content": {
        "id": 456,
        "text": "AX 提取的 UI 文本",
        "timestamp": "2026-02-26T10:00:01Z",
        "file_path": "/data/screenshots/def.png",
        "frame_url": "/v1/frames/789",
        "app_name": "VS Code",
        "window_name": "spec.md — MyRecall",
        "browser_url": null,
        "focused": true,
        "device_name": "MacBook-Pro",
        "tags": []
      }
    }
  ],
  "pagination": {
    "limit": 20,
    "offset": 0,
    "total": 142
  }
}
```

约束：

- `content_type=ocr` 仅返回 `type=OCR`。
- `content_type=accessibility` 仅返回 `type=UI`。
- `content_type=all` 返回混合结果并按 `timestamp DESC` 合并分页。
- `type=UI` 的 `content.id` 是 `accessibility.id`（不是 `frame_id`）。

搜索路径与 SQL 细节见 `data_model.md`（DB-001）。

引用：DEC-003A, DEC-020A, DEC-022C, DEC-025A。

## API-300 `GET /v1/frames/:frame_id`

- 成功：`Content-Type: image/jpeg`，返回图像二进制。
- 失败：`404 NOT_FOUND`。

## API-301 `GET /v1/frames/:frame_id/metadata`

### Response 200

```json
{
  "frame_id": 123,
  "timestamp": "2026-02-26T10:00:00Z",
  "app_name": "Safari",
  "window_name": "GitHub - main",
  "browser_url": "https://github.com",
  "focused": true,
  "device_name": "MacBook-Pro",
  "ocr_text": "提取的文字",
  "file_path": "/data/screenshots/abc.png",
  "capture_trigger": "app_switch",
  "content_hash": "sha256:abcdef...",
  "status": "completed"
}
```

约束：

- `status` 只允许：`pending/processing/completed/failed`。
- `capture_trigger` 的枚举与 `CapturePayload` 一致。

## API-400 `GET /v1/health`

### Response 200

```json
{
  "status": "ok",
  "last_frame_timestamp": "2026-02-26T10:00:00Z",
  "frame_status": "ok",
  "message": "",
  "queue": {
    "pending": 0,
    "processing": 0,
    "failed": 0
  }
}
```

约束：

- `status`: `ok/degraded/error`
- `frame_status`: `ok/stale/error`

## API-500 `POST /v1/chat`（P1 契约）

- Request：`{message, session_id, images?}`
- Response：SSE 透传 Pi 原生事件，不做 OpenAI format 翻译。
- 事件类型：`message_update`, `tool_execution_*`, `agent_start/end`, `response` 等。
- 引用要求：回答必须输出可解析 deep link（`myrecall://frame/{frame_id}` 或 `myrecall://timeline?timestamp=ISO8601`）。

引用：DEC-002A, DEC-013A。

## API-900 兼容与演进

- P1 保持单帧幂等上传为主路径。
- P2+ 可新增 `session/chunk/commit/checkpoint` 分片接口，不破坏 P1 契约。
- P2+ 若引入 keyset cursor，可废弃 `offset` 分页。

## API-999 禁止重复项

- `spec.md` 与 `roadmap.md` 禁止复制完整 API schema。
- 验收文档只允许引用 API-ID，不得重新定义契约。
