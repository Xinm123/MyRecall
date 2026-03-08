## Context

MyRecall-v3 在 P1-S1 需要落地“基础链路”闭环：Host 产生 JPEG capture（spool 落盘）→ `POST /v1/ingest` 幂等上传（`capture_id`）→ Edge 入库为 `frames` 行并持久化 snapshot JPEG → QueueDriver（`processing_mode=noop`）推进状态机 → `/v1/ingest/queue/status` 与 `/v1/health` 可观测 → WebUI 三页首屏展示 `#mr-health` 并可自动切换 `data-state`。

现状（代码库）：

- Edge/UI 由 Flask 提供：`openrecall/server/app.py` 注册 `openrecall/server/api.py`（`Blueprint(..., url_prefix="/api")`），并提供 `/`、`/search`、`/timeline` 三个页面路由。
- 当前 `/api/*` 端点面向 v2 语义：例如 `openrecall/server/api.py` 的 `POST /api/upload` 接收 PNG + metadata 并写入 `entries` 表（`openrecall/server/database/sql.py`）。
- 当前启动逻辑会 preload 模型并启动 `ProcessingWorker`：`openrecall/server/__main__.py`。
- 当前 WebUI 基础模板为 `openrecall/server/templates/layout.html`（包含 Alpine.js 的 controlCenter 轮询 `/api/config`），但尚无 `#mr-health`。

约束（SSOT）：

- HTTP 契约：`docs/v3/spec.md` §4.7（ingest/queue/noop）、§4.8.1（UI health）、§4.9（frames/health/errors）；`docs/v3/http_contract_ledger.md`（P1-S1 delta + legacy `/api/*` 301 规则）。
- 数据模型：`docs/v3/data-model.md` §3.0.3（`frames` DDL + `capture_id` UNIQUE + status）、§3.0.6（CapturePayload）。
- Gate 锚点（必须字面一致）：`MRV3 processing_mode=noop`、`MRV3 frame_failed reason=`、`DB_WRITE_FAILED`、`IO_ERROR`、`STATE_MACHINE_ERROR`、`[DEPRECATED]`、`Location`、`#mr-health`、`data-state`、`healthy`、`unreachable`、`degraded`；文案锚点：`服务健康/队列正常`、`Edge 不可达`、`等待首帧`。

screenpipe 参考（本仓库内审计路径）：

- Health 响应与健康端点：`_ref/screenpipe/crates/screenpipe-server/src/routes/health.rs`（`HealthCheckResponse` + `health_check`）。v3 只对齐其子集（vision-only，且 v3 采用更严格的统一错误响应与 request_id）。
- Frame 读取主链路：`_ref/screenpipe/crates/screenpipe-server/src/routes/frames.rs`（snapshot frame 直接 serve 文件）。v3 对齐“snapshot 直接读 JPEG + 固定 `Content-Type: image/jpeg`”，不引入 video chunk 与 ffmpeg 逻辑。
- 内容去重思路（后续阶段）：`_ref/screenpipe/crates/screenpipe-server/src/event_driven_capture.rs`（基于 accessibility tree 的 content hash dedup + 30s floor）。v3 的 `content_hash`/per-device 状态在 P1-S2+ 完整对齐；P1-S1 仅保证 `capture_id` 幂等与 JPEG 读取闭环。

架构草图（P1-S1）：

```
Host (openrecall/client)
  spool: ~/MRC/spool/*.jpg + *.json (capture_id UUID v7)
        |
        | POST /v1/ingest (multipart: capture_id + metadata + file)
        v
Edge (openrecall/server)
  SQLite (edge.db): frames (SSOT counters)
  note: legacy recall.db/fts.db 属 v2 路径；/v1 SSOT 使用单一 edge.db
  disk: frames snapshot JPEG
        |
        | GET /v1/ingest/queue/status  (DB counts + processing_mode=noop)
        | GET /v1/health              (UI polling source)
        | GET /v1/frames/:frame_id    (image/jpeg)
        v
WebUI (Jinja templates)
  #mr-health[data-state="healthy|unreachable|degraded"]
```

## Goals / Non-Goals

**Goals:**

- 在 Edge 上新增 `/v1/*` 的最小对外面（P1-S1）：
  - `POST /v1/ingest`：单帧幂等上传（201/200 already_exists；400/413/503/500 统一错误格式）；其中 400/413/503 MUST NOT 创建/修改任何 `frames` 行。
  - `GET /v1/ingest/queue/status`：返回 `pending/processing/completed/failed/processing_mode/capacity/oldest_pending_ingested_at`；其中四个计数 MUST 与 DB 中 `frames.status` 实时行数一致（P1-S1 `processing_mode` 固定为 `noop`）；当 `pending=0` 时 `oldest_pending_ingested_at` MUST 返回 `null`（不得返回空字符串/0/当前时间）。
  - `GET /v1/frames/:frame_id`：固定返回 `Content-Type: image/jpeg`。
  - `GET /v1/health`：返回对齐 screenpipe `HealthCheckResponse` 子集的健康信息（含 queue 子集）。
- 强制 `processing_mode=noop` 并满足可验证日志锚点：启动后输出且仅输出一次 `MRV3 processing_mode=noop`；失败计数增加时输出 `MRV3 frame_failed reason=` 且 reason 仅允许 `DB_WRITE_FAILED|IO_ERROR|STATE_MACHINE_ERROR`。
- WebUI 三个页面（`/`、`/search`、`/timeline`）首屏可见 `#mr-health`，并按 `data-state` 状态机展示 `healthy`/`unreachable`/`degraded`，满足 Gate 的 15s 不可达与 10s 自动恢复时间窗（不刷新页面）。
- Legacy namespace（P1-S1~S3）：仅对 Gate scope 的 4 个端点返回重定向 + `Location` 指向对应 `/v1/*`，并记录 `[DEPRECATED]` 日志（`POST /api/upload`=308，其余 GET=301；不实现 catch-all `/api/*` redirect）。
  - 澄清：P1-S1~S3 的 legacy 重定向仅用于“迁移提示/废弃回归检查”，不等价于 replacement 端点在当期已完成实现（例如 `/v1/search` 在 P1-S1 可能为 404，属预期）。

**Non-Goals:**

- `/v1/search` 可用性（P1-S4+）。
- `/v1/chat` 可用性（P1-S5+）。
- AX-first/OCR-fallback 处理（P1-S3+）。
- Host 事件驱动 capture（P1-S2）。
- TLS/mTLS 强制（P2+）。
- 让 v3 `frames` 立即驱动现有页面内容（P1-S1 仅要求页面可达 + 健康状态可见；数据展示迁移在后续阶段完成）。

## Decisions

1) `/v1/*` 路由组织：新增独立 v1 Blueprint，不改动现有 `/api/*` Blueprint 的注册方式

- 代码落点：
  - 现有入口：`openrecall/server/app.py`（`app = Flask(__name__)`，`app.register_blueprint(api_bp)`）。
  - 现有 legacy Blueprint：`openrecall/server/api.py`（`api_bp = Blueprint("api", __name__, url_prefix="/api")`）。
- 方案：新增 `openrecall/server/api_v1.py`（或 `openrecall/server/v1/*` 目录）定义 `v1_bp = Blueprint("v1", __name__, url_prefix="/v1")`，把 ingest/frames/health/queue/status 全部挂在 v1_bp 下，并在 `openrecall/server/app.py` 中额外 `app.register_blueprint(v1_bp)`。
- trade-off：
  - A：把 `/v1/*` 混入 `openrecall/server/api.py`（降低文件数，但会把 legacy 与 v3 语义纠缠）。
  - B（选）：独立 v1 Blueprint（清晰隔离，便于后续 P1-S4/P1-S5 增量）。

2) legacy `/api/*` 处理：严格按 SSOT 返回重定向（POST=308, GET=301）+ `Location` + `[DEPRECATED]`，且不依赖 redirect 作为功能路径

- SSOT：`docs/v3/http_contract_ledger.md` §4.0/§4.1；`docs/v3/runbook_phase1.md` §6。
- 方案：对以下 4 个端点做“显式覆盖”并返回重定向：
  - `POST /api/upload` -> `308` `/v1/ingest`
  - `GET /api/search` -> `301` `/v1/search`
  - `GET /api/queue/status` -> `301` `/v1/ingest/queue/status`
  - `GET /api/health` -> `301` `/v1/health`
- 记录日志锚点：`[DEPRECATED]` + 旧路径 + 新路径；响应头包含 `Location`。
- trade-off：
  - A（选）：`POST /api/upload` 使用 308（保持方法）+ 其余 GET 保持 301（维持迁移提示语义）。
  - B：全部保持 301（实现简单，但 POST 在部分客户端会降级为 GET）。
  - 结论：P1-S1 legacy 重定向仅用于“废弃回归检查”，Host 主路径直接调用 `/v1/*`；同时 `POST /api/upload` 用 308 避免方法降级踩坑。
- screenpipe 参考：无直接对照（screenpipe 没有 `/api`→`/v1` 迁移历史）。

3) 数据模型与迁移：按 SSOT 建立 v3 P1 初始 schema（`20260227000001_initial_schema.sql`），并在 P1-S1 仅启用 `frames` 业务链路

- SSOT：`docs/v3/data-model.md` §3.0.3（DDL）/§3.0.7（迁移策略）。
- 现状：`openrecall/server/database/sql.py` 初始化 `entries` 与 `ocr_fts`（旧路径）。
- 方案（最小破坏）：
  - 新增 `openrecall/server/database/migrations/`（按 SSOT 文件名规范，例如 `20260227000001_initial_schema.sql`）。
  - `20260227000001_initial_schema.sql` 按 `docs/v3/data-model.md` §3.0.7 为 P1 全量 DDL（`frames/ocr_text/accessibility/frames_fts/ocr_text_fts/accessibility_fts/chat_messages`）；P1-S1 仅实现并依赖 `frames` + `schema_migrations` 链路。
  - 新增迁移执行器（例如 `openrecall/server/database/migrations_runner.py`），启动时对 `settings.db_path` 执行 `schema_migrations` + DDL；P1-S1 约束：`settings.db_path` MUST 指向 `${OPENRECALL_SERVER_DATA_DIR}/db/edge.db`（不允许继续指向 `recall.db`）。
  - 若检测到现有 `settings.db_path=${OPENRECALL_SERVER_DATA_DIR}/db/recall.db`，启动日志需给出明确迁移/配置提示，并拒绝以 v3 `/v1/*` 路径进入 Pass 验收。
  - 新增 v3 专用 store（例如 `openrecall/server/database/frames_store.py`）只负责 `frames` 相关读写与计数（不修改 `SQLStore` 的 `entries` 逻辑），避免在 P1-S1 破坏 `/`、`/search`、`/timeline` 现有渲染。
- trade-off：
  - A（选）：并行保留 legacy `entries`（现有 UI 继续用）+ 新增 v3 `frames`（/v1 SSOT）。
  - B：直接把 UI 与 worker 全部切换到 `frames`（风险高，超出 P1-S1）。
- screenpipe 对照：
  - 对齐：以 DB 为 SSOT（screenpipe 亦基于 DB 状态提供 API）。
  - 差异：screenpipe 的 DB schema 与迁移体系是 Rust/sqlx 风格；v3 采用 Python + 手写 SQL（但命名规范对齐）。

4) `POST /v1/ingest` 幂等与响应：capture_id 作为幂等键；201/200 表示幂等成功；错误统一格式包含 request_id

- SSOT：`docs/v3/spec.md` §4.7；`docs/v3/spec.md` §4.9（统一错误格式；2xx 不带 code）。
- 方案：
  - DB：`frames.capture_id` UNIQUE；插入成功 -> 201，响应体必须包含 `{"capture_id":"...","frame_id":123,"status":"queued","request_id":"uuid-v4"}`；幂等冲突 -> 200，响应体必须包含 `{"capture_id":"...","frame_id":123,"status":"already_exists","request_id":"uuid-v4"}`。
  - 错误：400/413/503/500 返回 `{"error", "code", "request_id"}`；其中 503 返回 `retry_after`；并严格保证 400/413/503 不创建/修改任何 `frames` 行。
  - `503 QUEUE_FULL` 触发条件：当 DB 实时 `pending >= capacity` 时，`POST /v1/ingest` MUST 返回 `503` + `code=QUEUE_FULL` + `retry_after`。
  - 一致性约束：`capacity` 的判定来源与 `/v1/ingest/queue/status` 相同（同一配置值、同一时刻 DB `pending` 口径），避免返回字段与拒绝策略不一致。
  - 2xx 成功响应不包含错误 `code` 字段（但包含 `request_id`）。
- screenpipe 对照：
  - 对齐：幂等/去重核心依赖 DB 约束（screenpipe 的 content dedup 亦以 state + hash 判定是否写入）。
  - 差异：v3 在 API 层引入统一错误 `code` + `request_id`（screenpipe 更轻量，常用 `{"error":...}`）。

5) JPEG 主链路与 `GET /v1/frames/:frame_id`：snapshot_path 持久化 JPEG，读取端固定 `Content-Type: image/jpeg`

- SSOT：`docs/v3/spec.md` §4.7（JPEG 口径）与 §4.9（frames endpoint）。
- 方案：
  - `frames.snapshot_path` 存储 JPEG 文件路径（推荐 `.jpg`/`.jpeg`）。
  - 新增 v3 snapshot 目录（例如 `${OPENRECALL_SERVER_DATA_DIR}/frames/`），避免与现有 `settings.screenshots_path` 的 `.png` 命名混淆（P1-S1 允许共存）。
  - `GET /v1/frames/:frame_id` 从 DB 取 snapshot_path 并直接 serve 文件；无二次转码。
  - `GET /v1/frames/:frame_id` 错误契约：frame 不存在时返回 `404` + `{"error":"frame not found","code":"NOT_FOUND","request_id":"uuid-v4"}`（统一错误格式）。
- screenpipe 对照：`_ref/screenpipe/crates/screenpipe-server/src/routes/frames.rs` 中 snapshot frame 分支（`is_snapshot` 时直接 `serve_file(&file_path)`）与 v3 目标一致；v3 不引入 video chunk。

6) QueueDriver（noop）与启动行为：不 preload 模型，不启动 AI worker；仅推进 frames 状态机并提供可观测闭环

- SSOT：`docs/v3/spec.md` §4.7（QueueDriver noop + 日志锚点）。
- 现状：`openrecall/server/__main__.py` 默认 `preload_ai_models()` 且 `init_background_worker(app)` 启动 `ProcessingWorker`（会产生 OCR/provider/model preload 日志）。
- 方案（P1-S1）：
  - 引入显式运行模式开关（`OPENRECALL_PROCESSING_MODE`，P1-S1 默认/固定为 `noop`），在 `openrecall/server/__main__.py`：
    - noop：跳过 `preload_ai_models()`；不启动 `ProcessingWorker`；启动 `NoopQueueDriver`（可为轻量线程）推进 `pending -> completed`。
    - 必须输出且仅输出一次：`MRV3 processing_mode=noop`。
  - 当 `failed` 计数增加时，输出 `MRV3 frame_failed reason=<REASON> request_id=<uuid-v4> capture_id=<uuid-v7> frame_id=<int_optional>`。
- screenpipe 对照：
  - 对齐：以“轻量 capture + DB 写入”为主路径，避免不必要的推理开销。
  - 差异：screenpipe 仍有完整 pipeline 与丰富健康指标；v3 P1-S1 明确禁止任何模型初始化。

7) `GET /v1/ingest/queue/status` 与 `GET /v1/health`：计数必须实时来自 DB，不允许进程累计计数器

- SSOT：`docs/v3/spec.md` §4.7（计数一致性约束）；`docs/v3/spec.md` §4.9（health response）。
- 方案：
  - queue/status：每次请求实时读取 `frames`，并返回 `pending/processing/completed/failed/processing_mode/capacity/oldest_pending_ingested_at`（计数可用 `SELECT COUNT(*) ... WHERE status=...` 或等价 GROUP BY）。
  - health：返回对齐 screenpipe `HealthCheckResponse` 子集（`status`、`last_frame_timestamp`、`frame_status`、`message`、`queue{pending,processing,failed}`），并把 `frame_status` 的 stale 判定阈值固定为 5 分钟（SSOT）；P1-S1 阶段 `status` 仅允许 `ok/degraded`，不返回 `error`。
- screenpipe 对照：
  - `_ref/screenpipe/crates/screenpipe-server/src/routes/health.rs` 的 `HealthCheckResponse` 是更大集合；v3 只对齐最小子集。

8) WebUI `#mr-health`：在 layout.html 中实现一次注入，覆盖三页首屏；轮询 `/v1/health` 并更新 `data-state`

- SSOT：`docs/v3/spec.md` §4.8.1；`docs/v3/gate_baseline.md` §3.3（poll/timeout/grace + 15s/10s 时间窗）。
- 方案：
  - 在 `openrecall/server/templates/layout.html` 中加入 `#mr-health` 组件（避免逐页复制）。
  - JS 轮询参数固定为：`poll_interval_ms=5000`、`request_timeout_ms=2000`、`unreachable_grace_ms=5000`。
  - 状态机：
    - `healthy`：请求成功且 `status=="ok"` 且 `queue.failed==0`；文案包含 `服务健康/队列正常`。
    - `unreachable`：请求失败/超时持续 >= unreachable_grace_ms；文案包含 `Edge 不可达`。
    - `degraded`：请求成功但 `status != "ok"` 或 `queue.failed > 0` 或 `frame_status != "ok"`；其中“尚未首帧”子场景（`last_frame_timestamp==null` 且 `frame_status=="stale"` 且 `status=="degraded"` 且 `queue.failed==0`）文案必须包含 `等待首帧`，且不得显示 `Edge 不可达`。
- screenpipe 对照：screenpipe UI 通过健康端点反映服务状态（后端路由存在 `GET /health`，见 `_ref/screenpipe/crates/screenpipe-server/src/server.rs`），但 v3 的 Gate 以 DOM 锚点判定，属于 v3 的流程约束增强。

9) Host spool 与上传：新增 `~/MRC/spool`（`.jpg` + `.json`）并对齐 CapturePayload；Uploader 支持 201/200 幂等成功与 503 retry_after

- SSOT：`docs/v3/spec.md` §4.7（Host spool 与重试）；`docs/v3/data-model.md` §3.0.6（CapturePayload 验证）。
- 现状：`openrecall/client/buffer.py` 生成 `.webp`；`openrecall/client/uploader.py` 发送 PNG 到 `/api/upload`。
- 方案：
  - config：在 `openrecall/shared/config.py` 增加 `spool_path = client_data_dir / "spool"` 并确保目录创建。
  - spool：新增/改造本地队列模块输出 `.jpg` + `.json`（原子写入 `.tmp -> rename`），并保留对旧 `.webp` 的 drain 兼容（仅用于清空历史项）。
  - uploader：新增 `upload_capture()` 使用 multipart 发往 `/v1/ingest`；成功条件为 201 或 200 already_exists（两者都删除 spool 项）；503 时遵守 `retry_after`；网络失败无限重试；重试退避使用 exponential backoff：`1s -> 2s -> 4s -> 8s ...` 上限 `60s`。
- screenpipe 对照：
  - 对齐：content dedup/backoff 的精神与边界条件（见 `_ref/screenpipe/crates/screenpipe-server/src/event_driven_capture.rs` 的 dedup + floor）。
  - 差异：screenpipe 同进程直写，不经 LAN 传输；v3 以 Host/Edge 拓扑实现可恢复传输。

10) WebUI（grid/timeline）在 P1-S1 采用“frames 兼容桥接”，避免 `entries` 双写

- 背景：P1-S1 已将 `/v1/*` + `frames` 设为 SSOT；但现有页面（`/`、`/timeline`）仍沿用 legacy 渲染假设（`entries` + `/screenshots/{timestamp}.png`），会导致“ingest 成功但页面无图”。
- 方案：
  - `openrecall/server/app.py` 的 `index/timeline` 首屏数据改为读取 `frames`（通过 v3 store 导出 legacy 形状）；
  - `openrecall/server/api.py` 的 `/api/memories/latest|recent` 改为读取 `frames`（兼容现有前端轮询）；
  - `openrecall/server/templates/index.html` 与 `timeline.html` 图片 URL 统一为 `/v1/frames/:frame_id`。
- 约束：不新增 `frames -> entries` 双写，不回退 SSOT；兼容桥接仅用于 P1-S1 的 UI 可见性闭环。
- trade-off：
  - A（选）：页面读取源桥接到 `frames`（改动小、风险低、与 SSOT 一致）。
  - B：引入双写维持 `entries`（实现快但长期易漂移，不选）。

## Risks / Trade-offs

- legacy 重定向对 POST 的行为差异 → Mitigation：`POST /api/upload` 使用 308；Host 主路径仍直接调用 `/v1/ingest`；legacy 仅用于“废弃回归检查”。
- 现有启动逻辑默认 preload 模型与启动 ProcessingWorker（违反 noop） → Mitigation：为 P1-S1 引入明确 processing_mode 开关；noop 时跳过 preload/worker；并强制输出 `MRV3 processing_mode=noop`（一次且仅一次）。
- 现有 DB 仍包含 legacy `entries`，新增 `frames` 可能带来“双源并存” → Mitigation：P1-S1 明确 `/v1/*` 以 `frames` 为 SSOT；现有页面内容迁移推迟，不做双写；仅在 UI health 组件层与 v1 health 发生耦合。
- UI 轮询导致 DB 锁竞争（SQLite） → Mitigation：health/queue/status 查询保持短事务、只读、索引友好（按 status GROUP BY/COUNT）；轮询间隔遵守 `poll_interval_ms=5000`。
- Gate 锚点字符串漂移（多处拼写/大小写差异） → Mitigation：将 `MRV3 processing_mode=noop`、`MRV3 frame_failed reason=`、`[DEPRECATED]` 等锚点作为常量集中定义并复用；在验收脚本中做字面匹配。
- JPEG 转码与尺寸限制（10MB）在 Host/Edge 两侧处理不一致 → Mitigation：以 Edge 为最终约束：超过上限返回 413；Host 侧尽量生成 JPEG（质量/分辨率可配置）以降低失败率。

## Migration Plan

- P1-S1：引入 `schema_migrations` + migrations runner，并应用 `20260227000001_initial_schema.sql`（P1 全量 DDL）；当期仅实现/使用 `frames` 链路（`/v1/ingest`、`/v1/ingest/queue/status`、`/v1/frames/:frame_id`、`/v1/health`）、新增 `#mr-health`、legacy 4 端点按规则重定向（POST=308, GET=301）。
- P1-S2：补齐 Host 侧 CapturePayload 字段（`capture_trigger` 等）与 per-device 去重状态（last_content_hash, last_write_time）。
- P1-S3：切换 `processing_mode=ax_ocr`，启用 AX-first/OCR-fallback 写入（Scheme C）与 `ocr_text/accessibility/FTS` 等既有表的读写路径（表已由 `20260227000001_initial_schema.sql` 预置）。
- P1-S4+：实现 `/v1/search`，逐步迁移 WebUI 的数据展示与交互到 v3 结构。

## Open Question Closure

- 决策（P1-S1）：v3 `frames` 的 snapshot JPEG 使用独立目录 `${OPENRECALL_SERVER_DATA_DIR}/frames/`；不复用 `settings.screenshots_path`（`${OPENRECALL_SERVER_DATA_DIR}/screenshots`）。`frames.snapshot_path` 存储该 JPEG 文件的绝对路径。
