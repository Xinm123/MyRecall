## Implementation Tasks

### 1. 数据模型与迁移基础设施

- [x] 1.1 新增 `openrecall/server/database/migrations/` 目录，创建 `20260227000001_initial_schema.sql`，包含 `schema_migrations` 表与 `docs/v3/data-model.md` §3.0.3 定义的 P1 全量 DDL（`frames/ocr_text/accessibility/frames_fts/ocr_text_fts/accessibility_fts/chat_messages`，含 `capture_id UNIQUE`、`status`、`ingested_at`、索引；SSOT: §3.0.3 + §3.0.7）
- [x] 1.2 新增 `openrecall/server/database/migrations_runner.py`，实现启动时迁移执行逻辑：读取 `schema_migrations` 表、按版本号排序执行未应用的 `.sql` 文件、记录已执行版本（SSOT: `docs/v3/data-model.md` §3.0.7 伪代码）
- [x] 1.3 在 `openrecall/shared/config.py` 中新增 v3 配置项：`db_path` 指向 `${OPENRECALL_SERVER_DATA_DIR}/db/edge.db`（不允许指向 `recall.db`）、`frames_dir` 指向 `${OPENRECALL_SERVER_DATA_DIR}/frames/`、`OPENRECALL_PROCESSING_MODE`（P1-S1 默认 `noop`）、`queue_capacity`（env: `OPENRECALL_QUEUE_CAPACITY`，默认 `200`）
- [x] 1.4 确保 `edge.db` 父目录与 `frames/` 目录在启动时自动创建

### 2. v3 数据存储层

- [x] 2.1 新增 `openrecall/server/database/frames_store.py`，实现 `FramesStore` 类：`insert_frame(capture_id, metadata, snapshot_path) -> (frame_id, is_new)`（INSERT OR IGNORE + 幂等判定）、`get_frame(frame_id) -> Frame | None`、`get_frame_by_capture_id(capture_id) -> Frame | None`
- [x] 2.2 在 `FramesStore` 中实现队列计数方法：`get_queue_counts() -> dict`（实时 `SELECT COUNT(*) ... GROUP BY status`）、`get_oldest_pending_ingested_at() -> str | None`、`get_pending_count() -> int`（用于 503 背压判定）
- [x] 2.3 在 `FramesStore` 中实现状态推进方法：`advance_frame_status(frame_id, from_status, to_status)`、`mark_failed(frame_id, reason, request_id, capture_id)`
- [x] 2.4 在 `FramesStore` 中实现 health 查询方法：`get_last_frame_timestamp() -> str | None`（`SELECT MAX(timestamp) FROM frames`）
- [x] 2.5 在 `FramesStore` 中实现 health 查询方法：`get_last_frame_ingested_at() -> str | None`（`SELECT MAX(ingested_at) FROM frames`）

### 3. v1 Blueprint 与 POST /v1/ingest 端点

- [x] 3.1 新增 `openrecall/server/api_v1.py`，定义 `v1_bp = Blueprint("v1", __name__, url_prefix="/v1")`
- [x] 3.2 在 `openrecall/server/app.py` 中注册 `v1_bp`（`app.register_blueprint(v1_bp)`），不改动现有 `api_bp` 注册
- [x] 3.3 实现 `POST /v1/ingest`：解析 multipart（`capture_id` + `metadata` JSON + `file` 二进制）、校验必填字段与格式（`capture_id` UUID v7、`file` 存在且 MIME 必须为 `image/jpeg`、大小 <= 10MB）、校验失败返回 `400 INVALID_PARAMS` 或 `413 PAYLOAD_TOO_LARGE`
- [x] 3.4 实现 `POST /v1/ingest` 背压检查：`pending >= capacity` 时返回 `503 QUEUE_FULL` + `retry_after`；确保 400/413/503 不创建/修改任何 `frames` 行
- [x] 3.5 实现 `POST /v1/ingest` 成功路径：持久化 JPEG 到 `frames/` 目录、调用 `FramesStore.insert_frame()`、新建返回 `201 Created` + `{"capture_id", "frame_id", "status": "queued", "request_id"}`、幂等返回 `200 OK` + `{"capture_id", "frame_id", "status": "already_exists", "request_id"}`；2xx 响应不包含 `code` 字段
- [x] 3.6 实现统一错误响应辅助函数：`make_error_response(error_msg, code, status_code, request_id=None, **extra)` -> JSON + 对应 HTTP 状态码，自动生成 `request_id`（UUID v4）

### 4. GET /v1/ingest/queue/status 端点

- [ ] 4.1 在 `api_v1.py` 中实现 `GET /v1/ingest/queue/status`：调用 `FramesStore.get_queue_counts()` 返回 `{"pending", "processing", "completed", "failed", "processing_mode": "noop", "capacity", "oldest_pending_ingested_at"}`

### 5. GET /v1/frames/:frame_id 端点

- [ ] 5.1 在 `api_v1.py` 中实现 `GET /v1/frames/<int:frame_id>`：查询 `FramesStore.get_frame(frame_id)`，找到则 `send_file(snapshot_path, mimetype='image/jpeg')`，未找到返回 `404 NOT_FOUND`
- [ ] 5.2 处理 `snapshot_path` 文件不存在的边界情况：记录 `error` 级别日志（`IO_ERROR` 仅作为 reason 枚举值），并返回错误；该 GET 读路径不得调用 `mark_failed()` 或其他写操作，且不得改变 queue `pending/processing/completed/failed` 计数

### 6. GET /v1/health 端点

- [ ] 6.1 在 `api_v1.py` 中实现 `GET /v1/health`：查询 `FramesStore` 获取 `last_frame_timestamp`（`MAX(timestamp)`）、`last_frame_ingested_at`（`MAX(ingested_at)`）与 queue 计数（`pending/processing/failed`）；当 `last_frame_ingested_at == null` 时 `frame_status="stale"`；否则按 `last_frame_ingested_at` 距当前时间是否 >= 5 分钟判定 `stale/ok`；计算 `status`（`failed > 0` 或 `frame_status != "ok"` 则 `degraded`，否则 `ok`），返回完整 `HealthCheckResponse` JSON

### 7. QueueDriver（noop）

- [ ] 7.1 新增 `openrecall/server/queue_driver.py`，实现 `NoopQueueDriver`：后台线程/定时器，轮询 `status='pending'` 的帧并推进为 `completed`（允许经过 `processing` 中间态）
- [ ] 7.2 实现失败处理与日志锚点：当状态推进失败时，调用 `FramesStore.mark_failed()` 并输出 `MRV3 frame_failed reason=<REASON> request_id=<uuid-v4> capture_id=<uuid-v7> frame_id=<int>`，`REASON` 仅限 `DB_WRITE_FAILED` / `IO_ERROR` / `STATE_MACHINE_ERROR`
- [ ] 7.3 在 `openrecall/server/__main__.py` 中集成：当 `processing_mode=noop` 时跳过 `preload_ai_models()` 和 `ProcessingWorker`，启动 `NoopQueueDriver`，且在 HTTP server ready 后输出且仅输出一次 `MRV3 processing_mode=noop`

### 8. Legacy /api/* 301 重定向

- [ ] 8.1 在现有 `openrecall/server/api.py`（legacy Blueprint）中对 4 个 Gate scope 端点新增/覆盖路由：`POST /api/upload` -> 301 `/v1/ingest`、`GET /api/search` -> 301 `/v1/search`、`GET /api/queue/status` -> 301 `/v1/ingest/queue/status`、`GET /api/health` -> 301 `/v1/health`
- [ ] 8.2 每次 301 响应 MUST 包含 `Location` 头，且记录 `[DEPRECATED]` 日志行（格式：`/api/{endpoint} -> /v1/{endpoint}`）

### 9. WebUI #mr-health 健康组件

- [ ] 9.1 在 `openrecall/server/templates/layout.html` 中注入 `#mr-health` 组件：首屏可见，暴露 `data-state="healthy|unreachable|degraded"` 属性
- [ ] 9.2 实现 JS 轮询逻辑：`poll_interval_ms=5000`、`request_timeout_ms=2000`、`unreachable_grace_ms=5000`；根据 `/v1/health` 响应更新 `data-state` 与文案
- [ ] 9.3 实现状态判定：`healthy`（`status=="ok"` 且 `queue.failed==0`，文案包含 `服务健康/队列正常`）、`unreachable`（请求失败/超时持续 >= `unreachable_grace_ms`，文案包含 `Edge 不可达`）、`degraded`（请求成功但 `status!="ok"` 或 `queue.failed>0` 或 `frame_status!="ok"`）；其中“启动后尚未首帧”（`last_frame_timestamp==null` 且 `frame_status=="stale"` 且 `status=="degraded"` 且 `queue.failed==0`）必须显示 `data-state="degraded"` 且文案包含 `等待首帧`（不得显示 `Edge 不可达`）
- [ ] 9.4 实现自动恢复：从 `unreachable`/`degraded` 状态，任意一次轮询满足 `healthy` 条件后自动切换 `data-state="healthy"`，全程不刷新页面

### 10. Host spool 与 Uploader（v3 链路）

- [ ] 10.1 在 `openrecall/shared/config.py` 中新增 `spool_path = client_data_dir / "spool"`，确保目录启动时自动创建
- [ ] 10.2 新增/改造 spool 写入模块：输出 `.jpg` + `.json`（原子写入 `.tmp` -> `rename`），`capture_id` 使用 UUID v7；保留对旧 `.webp` 项的 drain 兼容（仅清空，不新建）
- [ ] 10.3 新增 `upload_capture()` 函数：multipart 发往 `POST /v1/ingest`；`201`/`200 already_exists` 时删除 spool 项；`503` 时遵守 `retry_after`；网络失败时 exponential backoff（`1s -> 2s -> 4s -> 8s ...` 上限 `60s`）
- [ ] 10.4 实现进程重启后自动续传：启动时扫描 spool 目录中残留的 `.jpg` + `.json` 项并加入上传队列

## Acceptance Verification (P1-S1)

- [ ] 验收口径约束：P1-S1 验收不要求使用 `frames` 以外表的业务能力；但实现与验收脚本 MUST NOT 依赖“除 `frames` 外的表不存在”这一前提（`20260227000001_initial_schema.sql` 按 SSOT 为 P1 全量 DDL）

### 11. 启动与基础验证

- [ ] 11.1 启动 Edge（`./run_server.sh --debug`）并确认：启动日志恰好出现一次 `MRV3 processing_mode=noop`（字面匹配），且无 OCR/provider/model preload 日志
- [ ] 11.2 调用 `GET /v1/ingest/queue/status` 确认 `processing_mode` 值为 `"noop"`，四个计数均为 0
- [ ] 11.3 P1-S1 健康状态枚举验证：在空库与有帧两种场景下多次调用 `GET /v1/health`，确认 `status` 仅出现 `"ok"` 或 `"degraded"`，不得返回 `"error"`
- [ ] 11.4 全生命周期单次锚点验证：在同一 Edge 进程持续运行并处理请求（含 ingest、`/v1/ingest/queue/status`、`/v1/health`）后，日志中 `MRV3 processing_mode=noop` 总出现次数仍为 1；进程重启后允许再次出现 1 次（按“每进程一次”判定）

### 12. Ingest 链路验证

- [ ] 12.1 上传 50 条 capture（唯一 `capture_id`，JPEG 文件），确认每条返回 `201 Created` + `{"capture_id":"...","frame_id":<int>,"status":"queued","request_id":"<uuid-v4>"}`，且响应无 `code` 字段
- [ ] 12.2 回放 10 条重复 `capture_id`，确认均返回 `200 OK` + `{"capture_id":"...","frame_id":<int>,"status":"already_exists","request_id":"<uuid-v4>"}`，且响应无 `code` 字段，`frames` 表无重复行
- [ ] 12.3 调用 `GET /v1/ingest/queue/status` 确认 `pending + processing + completed + failed` = `frames` 表总行数（应为 50）
- [ ] 12.4 验证 `400 INVALID_PARAMS` 不变更 DB：记录请求前后 `frames` 表行数，确认两者相等，且 `GET /v1/ingest/queue/status` 的 `pending/processing/completed/failed` 四计数不变
- [ ] 12.5 验证 `413 PAYLOAD_TOO_LARGE` 不变更 DB：记录请求前后 `frames` 表行数，确认两者相等，且 `GET /v1/ingest/queue/status` 的 `pending/processing/completed/failed` 四计数不变
- [ ] 12.6 验证 `503 QUEUE_FULL` 不变更 DB：记录请求前后 `frames` 表行数，确认两者相等，且 `GET /v1/ingest/queue/status` 的 `pending/processing/completed/failed` 四计数不变（验收可通过临时设置 `OPENRECALL_QUEUE_CAPACITY=0` 并重启 Edge 稳定触发 503）
- [ ] 12.7 验证非 JPEG 上传返回 `400 INVALID_PARAMS` 且不变更 DB：使用 `image/png` 或 `image/webp` 上传，确认返回 `400`；记录请求前后 `frames` 表行数与 `GET /v1/ingest/queue/status` 四计数，均保持不变
- [ ] 12.8 轻量并发与错误契约合并验证：对同一 `capture_id` 发起两条并发 `POST /v1/ingest`，确认结果为“恰好一条 `201 queued` + 一条 `200 already_exists`”且 DB 仅一行；并抽样校验 `400/413/503` 与 `GET /v1/frames/:frame_id` 的 `404` 错误响应均包含 `request_id`

### 13. 帧读取验证

- [ ] 13.1 抽样调用 `GET /v1/frames/:frame_id`，确认 `Content-Type: image/jpeg`，响应为合法 JPEG 二进制
- [ ] 13.2 请求不存在的 `frame_id`，确认返回 `404` + `{"code":"NOT_FOUND"}`
- [ ] 13.3 对 `snapshot_path` 已丢失的 `frame_id` 连续调用 `GET /v1/frames/:frame_id`，确认返回 `404` 或 `500` 错误且不修改队列状态：请求前后 `GET /v1/ingest/queue/status` 的 `pending/processing/completed/failed` 四计数保持不变

### 14. 断连恢复验证

- [ ] 14.1 制造 Host→Edge 断连（至少 3 分钟），期间 Host 继续产生 capture 写入 spool
- [ ] 14.2 恢复连接后确认 Host 自动续传，所有 spool 项最终收到 `201` 或 `200 already_exists`

### 15. UI 健康态验证

- [ ] 15.1 在“尚未写入任何 frame”的前提下访问 `/`、`/search`、`/timeline`，确认三页均存在 `#mr-health[data-state="degraded"]`，文案包含 `等待首帧`，且不包含 `Edge 不可达`
- [ ] 15.2 触发至少 1 条成功 ingest 并等待 health 收敛后，确认三页均可进入 `#mr-health[data-state="healthy"]`，文案包含 `服务健康/队列正常`
- [ ] 15.3 停止 Edge 进程（不刷新页面），确认三页在 15 秒内进入 `data-state="unreachable"`，文案包含 `Edge 不可达`
- [ ] 15.4 恢复 Edge 进程（不刷新页面），确认三页在 10 秒内自动恢复为 `data-state="healthy"`，文案包含 `服务健康/队列正常`
- [ ] 15.5 锚点一致性检查：对比 `proposal.md`、`design.md`、`specs/ui-health-gate/spec.md` 与本任务清单中的 UI 文案锚点，确认至少包含且语义一致：`服务健康/队列正常`、`Edge 不可达`、`等待首帧`

### 16. Legacy 301 验证

- [ ] 16.1 请求 `POST /api/upload`、`GET /api/search`、`GET /api/queue/status`、`GET /api/health`，确认每个返回 `301` + `Location` 头指向对应 `/v1/*`
- [ ] 16.2 确认每次 legacy 请求的服务器日志包含 `[DEPRECATED]` 标记

### 17. 图片格式契约验证

- [ ] 17.1 确认 `frames.snapshot_path` 指向 `${OPENRECALL_SERVER_DATA_DIR}/frames/` 下的 `.jpg`/`.jpeg` 文件
- [ ] 17.2 确认 Host spool 新写入项为 `.jpg` + `.json`（无新 `.webp`）
