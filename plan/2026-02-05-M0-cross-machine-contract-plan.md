# Milestone M0（Sprint 0）：跨机器契约冻结（Transport/Auth/Time）可执行实施计划

> 我正在使用 `superpowers:writing-plans` 技能来创建该实施计划；鉴权/输入校验遵循 `security-review`，Python 与测试风格遵循 `python-patterns` 与 `MyRecall/AGENTS.md`。

**目标（One-liner）**：冻结并落地 Client ↔ Server 跨机器基础契约（`Transport/Auth/Time`），保证**鉴权可控、幂等可审计、时间可诊断**，为后续 `Chat(tool-call 检索)` 与多设备扩展打下稳定地基。

**技术栈/落点**：`Python` + `Flask`（`MyRecall/openrecall/server/api.py`）、`SQLite`（`MyRecall/openrecall/server/database/sql.py`）、`LanceDB`（`MyRecall/openrecall/server/database/vector_store.py`）、`FTS5`（`MyRecall/openrecall/server/database/sql.py` 的 `fts.db`）。

**M0 交付物（固定）**：
- 冻结后的 API 契约（第 2 章：`/api/upload`、`/api/heartbeat`、`/api/search`）
- 数据层迁移方案（第 3 章：`entries` 表字段/索引/唯一约束/回填规则）
- `pytest` 落地测试（第 6 章：单元 + 集成），覆盖鉴权/幂等/冲突/漂移
- 兼容与回滚策略（第 7 章：旧 Client 不升级也不崩、以及 feature flag 回退）

---

## 0. 代码库勘察摘要（只读现状：必须引用关键文件）

### 0.1 Server：`MyRecall/openrecall/server/api.py`

- `GET /api/search`：参数 `q`、`limit`，调用 `SearchEngine.search()`，返回扁平化字段：`id`、`timestamp`（来自 `snap.context.timestamp`）、`app_name`、`window_title`、`caption`、`scene_tag`、`image_path`、`full_data`。
- `POST /api/upload`：`multipart/form-data`，字段：`file`（PNG）+ `metadata`（JSON 字符串：`timestamp`、`app_name`、`window_title`）。
  - 现状：以 `timestamp` 作为文件名保存到 `settings.screenshots_path / f"{timestamp}.png"`，并调用 `SQLStore.insert_pending_entry(timestamp=...)` 写入。
  - 返回：成功 `202`（body 包含 `task_id`），重复 `timestamp` 会 `409`（日志提示 duplicate timestamp）。
- `POST /api/heartbeat`：无请求体，仅更新 `runtime_settings.last_heartbeat` 并返回 `{"status":"ok","config":...}`。
- 现状 **没有** 设备级鉴权（无 `Authorization` 校验）。

### 0.2 DB：`MyRecall/openrecall/server/database/sql.py`

- 元数据库 `entries` 表现状（SQLite）：
  - `timestamp INTEGER UNIQUE`（单列唯一）
  - `CREATE INDEX idx_timestamp ON entries (timestamp)`
- `insert_pending_entry()` 使用 `ON CONFLICT(timestamp) DO NOTHING`，因此：
  - 任何重试/多设备/同秒多张都会被“同 timestamp”吞掉，进而被 Server 当作冲突。
- 现状缺口：`insert_pending_entry(timestamp, app, title, image_path)` 虽传入 `image_path`，但 `entries` 表**没有** `image_path` 列，Worker 只能按 `timestamp` 反推路径。

### 0.3 Search：`MyRecall/openrecall/server/search/engine.py`

- `QueryParser` 来自 `MyRecall/openrecall/server/utils/query_parser.py`：
  - 解析产物 `ParsedQuery(text, start_time, end_time, mandatory_keywords)`，其中 `start_time/end_time` 是 epoch seconds（`float`），关键词来自双引号。
- `where_clause` 现状：仅基于时间过滤，拼接为 `context.timestamp >= ... AND context.timestamp <= ...`（对 `LanceDB` 做 prefilter）。
- 检索流程现状（Stage 1→3）：
  1) embedding → `VectorStore.search()`（`LanceDB`）
  2) `FTS5`：`SQLStore.search()`（`fts.db`）返回 `snapshot_id + bm25`，对命中做 boost，并补回“FTS-only”快照
  3) rerank：对 Top 30 通过 reranker 重排
- 现状风险：在 `settings.debug` 下会把 rerank 的上下文写入 `logs/rerank_debug.log`，上下文包含 `[OCR Content]`（这与“禁止 OCR 原文落日志”的安全目标冲突，需要在 M0 收敛）。

### 0.4 Config：`MyRecall/openrecall/shared/config.py`

- 配置基于 `pydantic-settings`：`OPENRECALL_*` 环境变量映射；已有 `OPENRECALL_API_URL`（Client 指向 Server）。
- 现状 **没有** 设备身份/设备 token 的配置项。

### 0.5 Client 上传链路（必须覆盖 uploader/buffer/consumer/recorder）

- `MyRecall/openrecall/client/uploader.py`：`HTTPUploader.upload_screenshot()` 发送 `POST /api/upload`，metadata 只有 `timestamp/app_name/window_title`，且不带鉴权 header。
- `MyRecall/openrecall/client/buffer.py`：磁盘队列，保存 `*.webp + *.json`；metadata 使用 `timestamp/active_app/active_window`。
- `MyRecall/openrecall/client/consumer.py`：从 buffer 取出后调用 uploader；失败指数退避；成功后 commit 删除文件。
- `MyRecall/openrecall/client/recorder.py`：每 `5s` 调用 `_send_heartbeat()`，现状 `POST /api/heartbeat` **无 body** 且**无鉴权**，仅同步 `recording_enabled/upload_enabled`。

---

## 1. 目标与验收（必须量化）

### 1.1 M0 Done 定义（量化且可验证）

M0 完成的必要条件（全部满足才算 Done）：

1. **鉴权冻结并落地**：
   - `POST /api/upload` 与 `POST /api/heartbeat` 默认启用 `Authorization: Bearer <device_token>` 校验（见第 2 章）。
   - 支持 token 轮换：同一设备 `active_token` 与 `previous_token` 在 `OPENRECALL_TOKEN_GRACE_SECONDS=86400`（24h）窗口内同时有效。
   - `401/403` 行为稳定可测（见 1.2 用例）。

2. **幂等/冲突冻结并落地（DB 侧可证明）**：
   - 幂等键固定为 `（device_id, client_ts, image_hash）`。
   - 冲突固定为 `（device_id, client_ts）` 相同但 `image_hash` 不同 → `409`。
   - DB 层具备**组合唯一约束**以支撑上述语义（见第 3 章）。

3. **时间语义冻结并可诊断**：
   - `client_ts` 与 `server_received_at` 统一为 **epoch milliseconds（UTC）整型**。
   - `client_tz` 固定为 IANA 时区名（例如 `America/Los_Angeles`），允许 Server 做 tz-aware 的自然日计算。
   - `heartbeat` 响应包含 `drift_ms`（估计漂移）与 `server_time_ms`（对时基准），并记录审计日志（见第 4 章）。

4. **兼容与回滚可用**：
   - 不升级旧 Client（只发 `timestamp/app_name/window_title` 且无 `Authorization`）时，Server 在 `OPENRECALL_AUTH_MODE=permissive` 下仍可接收并入库（见第 7 章）。
   - 可通过 feature flag 一键退回“旧行为”（至少：关闭强制鉴权/关闭严格幂等）。

5. **测试覆盖**：
   - 新增 `pytest` 测试不少于 `12` 条，其中：`unit >= 6`、`integration >= 6`。
   - 新增测试在默认测试集下可跑：`pytest`（不依赖 `model/perf/security` marker）。

### 1.2 最少 8 条验收用例（成功/失败/重试/冲突/漂移）

以下用例均要求能用 `pytest` 与 `curl` 复现：

1. **上传成功（新契约）**：携带合法 `Authorization` 与完整 metadata（含 `device_id/client_ts/client_tz/image_hash`）→ `202`，返回 `entry_id/task_id/diagnostic_id/server_received_at`，DB 写入新列，磁盘落盘成功。
2. **上传幂等重试（同 key）**：相同 `（device_id, client_ts, image_hash）` 重复上传 → `200`，`idempotent_replay=true`，返回同一个 `entry_id`，DB 不新增行，磁盘不重复写。
3. **上传冲突（同 ts 不同 hash）**：相同 `（device_id, client_ts）` 但 `image_hash` 不同 → `409`，body 返回 `existing.image_hash` 与 `incoming.image_hash`，并产生日志审计记录。
4. **缺失鉴权**：`OPENRECALL_AUTH_MODE=strict` 时缺失 `Authorization` → `401`（不落盘、不入库）。
5. **鉴权但越权**：token 属于 `device_A`，metadata 里伪造 `device_id=device_B` → `403`。
6. **心跳上报与下发**：`POST /api/heartbeat` 带 `queue_depth/last_error/capabilities` → `200`，返回 `config`（保留 `runtime_settings` 字段）+ `server_capabilities` + `server_time_ms`。
7. **漂移诊断（大漂移）**：模拟 `client_ts` 比 `server_time_ms` 偏差 `> 300000ms`（5min）→ `heartbeat` 响应包含 `drift_ms.exceeded=true`，日志包含 `device_id/drift_ms`。
8. **搜索设备隔离（有 auth）**：携带 `device_A` token 调 `GET /api/search?device_id=device_B&q=...` → `403`；调 `device_id=device_A` → 仅返回 A 的结果。
9. **搜索兼容（无 auth）**：浏览器访问 `GET /api/search?q=...`（无 `Authorization`）→ 仍返回结果（默认跨设备聚合，见第 2 章）。
10. **回滚开关有效**：开启 `OPENRECALL_IDEMPOTENCY_STRICT=false` 后，同 `(device_id, client_ts)` 不同 hash 的上传不再 `409`，而是按“新 entry + 诊断日志”策略处理（见第 7 章）。

---

## 2. API 契约冻结（必须给出字段名与语义，不留空）

### 2.1 全局约定（M0 Contract v1）

- **时间单位**：
  - `client_ts`：epoch milliseconds（UTC）整型（示例：`1738752000123`）。
  - `server_received_at`：epoch milliseconds（UTC）整型。
  - `server_time_ms`：epoch milliseconds（UTC）整型。
- **时区**：`client_tz` 为 IANA 时区名（示例：`America/Los_Angeles`）。
- **诊断 ID**：所有非 `2xx` 响应与幂等重放响应必须包含 `diagnostic_id`（UUID 字符串），用于串联日志。
- **错误响应统一格式**（除非明确返回列表）：

```json
{
  "status": "error",
  "code": "SOME_CODE",
  "message": "Human readable message",
  "diagnostic_id": "b3b2d7a4-...",
  "details": {}
}
```

### 2.2 鉴权（每设备 token）

- **Header**：`Authorization: Bearer <device_token>`。
- **token 绑定规则**：token 与 `device_id` 绑定；当 token 属于某设备时，metadata 中的 `device_id` 必须一致，否则 `403`。
- **token 轮换（双 token 并存窗口）**：
  - 每设备维护 `active_token` 与 `previous_token`。
  - `previous_token` 在 `previous_valid_until_ms` 之前仍被接受。
  - 默认窗口：`OPENRECALL_TOKEN_GRACE_SECONDS=86400`（24h）。
- **服务端 token 配置来源**（M0 冻结）：
  - 使用：`OPENRECALL_DEVICE_TOKENS_JSON`（JSON 字符串映射）。

`OPENRECALL_DEVICE_TOKENS_JSON` 结构（固定）：

```json
{
  "mac-01": {
    "active_token": "...",
    "previous_token": "...",
    "previous_valid_until_ms": 0
  }
}
```

- **错误码约定**：
  - `401`：缺失/格式错误/未知 token（`code=AUTH_UNAUTHORIZED`）。
  - `403`：token 有效但与 `device_id` 不匹配、或设备被禁用（`code=AUTH_FORBIDDEN`）。

### 2.3 `POST /api/upload`（契约 v1）

#### 2.3.1 Request

- **Auth**：必须（见 2.2），除非 `OPENRECALL_AUTH_MODE=permissive`。
- **Content-Type**：`multipart/form-data`。
- **表单字段**：
  - `file`：图片文件（M0 固定仅接受 `image/png`）。
  - `metadata`：JSON 字符串（字段如下）。

`metadata` 字段（M0 必填项 + 兼容项）：

| 字段 | 类型 | 必填 | 语义 |
|---|---:|---:|---|
| `device_id` | string | 是（新 Client） | 设备唯一标识（推荐：`^[a-zA-Z0-9_-]{3,64}$`） |
| `client_ts` | int | 是（新 Client） | 采集发生时间（epoch ms, UTC） |
| `client_tz` | string | 是（新 Client） | IANA 时区名 |
| `client_seq` | int | 否（推荐） | 设备内单调递增序号（用于诊断丢帧/乱序） |
| `image_hash` | string | 是（新 Client） | `sha256` 十六进制小写（长度 `64`），对 **上传的 PNG bytes** 计算 |
| `app_name` | string | 是 | 当前活跃应用名（沿用现状） |
| `window_title` | string | 是 | 当前窗口标题（沿用现状） |
| `timestamp` | int | 否（兼容旧 Client） | 旧字段：epoch seconds（当 `client_ts` 缺失时使用） |

#### 2.3.2 Server 写入字段

Server 在写入时必须补齐并持久化：
- `server_received_at`：epoch ms（UTC），以 Server 收到请求并完成**幂等判定**的时间为准。

#### 2.3.3 幂等/冲突语义（冻结）

- 幂等键：`（device_id, client_ts, image_hash）`。
- 冲突：`（device_id, client_ts）` 相同但 `image_hash` 不同 → `409`。

#### 2.3.4 Response（必须明确 202/200 语义）

- **`202 Accepted`（首次接收并入队）**：表示服务端创建了新 entry（`status=PENDING`）并进入处理队列。

```json
{
  "status": "accepted",
  "entry_id": 123,
  "task_id": 123,
  "device_id": "mac-01",
  "client_ts": 1738752000123,
  "server_received_at": 1738752000456,
  "image_hash": "<sha256>",
  "idempotency_key": "mac-01:1738752000123:<sha256>",
  "queue": {"pending": 7},
  "diagnostic_id": "b3b2d7a4-..."
}
```

- **`200 OK`（幂等重放）**：表示该截图已存在（同 `(device_id, client_ts)` 且 hash 一致），此次请求不会重复写入。

```json
{
  "status": "ok",
  "idempotent_replay": true,
  "entry_id": 123,
  "task_id": 123,
  "device_id": "mac-01",
  "client_ts": 1738752000123,
  "server_received_at": 1738752000789,
  "original_server_received_at": 1738752000456,
  "existing_status": "PENDING",
  "diagnostic_id": "b3b2d7a4-..."
}
```

- **`409 Conflict`（冲突）**：表示同一 `(device_id, client_ts)` 已存在但 hash 不同。

```json
{
  "status": "conflict",
  "code": "UPLOAD_CONFLICT",
  "message": "Same (device_id, client_ts) but different image_hash",
  "device_id": "mac-01",
  "client_ts": 1738752000123,
  "existing": {"entry_id": 123, "image_hash": "<sha256_a>"},
  "incoming": {"image_hash": "<sha256_b>"},
  "diagnostic_id": "b3b2d7a4-..."
}
```

#### 2.3.5 额外约束（M0 冻结）

- 文件大小上限：`OPENRECALL_MAX_UPLOAD_BYTES=10485760`（10MB）。超过返回 `413`（`code=UPLOAD_TOO_LARGE`）。
- hash 校验：Server 必须对落盘 PNG 重新计算 `sha256`，与 `metadata.image_hash` 不一致返回 `422`（`code=UPLOAD_HASH_MISMATCH`），并删除临时文件。

### 2.4 `POST /api/heartbeat`（契约 v1）

#### 2.4.1 Request

- **Auth**：必须（见 2.2），除非 `OPENRECALL_AUTH_MODE=permissive`。
- **Content-Type**：`application/json`。

请求体字段（全部字段名固定）：

| 字段 | 类型 | 必填 | 语义 |
|---|---:|---:|---|
| `device_id` | string | 是 | 设备唯一标识 |
| `client_ts` | int | 是 | 发送心跳时的本地时间（epoch ms） |
| `client_tz` | string | 是 | IANA 时区名 |
| `queue_depth` | int | 是 | Client 本地 buffer 队列长度（磁盘队列的 `count`） |
| `last_error` | object\|null | 是 | 最近一次错误（可为空），用于 UI 诊断 |
| `capabilities` | object | 是 | Client 能力声明（版本/平台/格式等） |

`last_error` 结构（固定）：

```json
{
  "code": "UPLOAD_TIMEOUT",
  "message": "...",
  "at_ms": 1738752000999
}
```

`capabilities` 结构（固定，字段可扩展但不得删除）：

```json
{
  "client_version": "3.0.0",
  "platform": "macOS",
  "capture": {"primary_monitor_only": true},
  "upload": {"formats": ["png"], "hash": "sha256"}
}
```

#### 2.4.2 Response

- 返回 `200`：
  - `config`：必须包含现有 `runtime_settings.to_dict()` 字段（`recording_enabled/upload_enabled/ai_processing_enabled/...`）。
  - `server_time_ms`：Server 当前时间（epoch ms）。
  - `drift_ms`：对齐诊断。
  - `server_capabilities`：服务端能力声明。

```json
{
  "status": "ok",
  "server_time_ms": 1738752000123,
  "config": {
    "recording_enabled": true,
    "upload_enabled": true,
    "ai_processing_enabled": true,
    "ai_processing_version": 0,
    "ui_show_ai": true,
    "last_heartbeat": 1738752000.0,
    "client_online": true
  },
  "drift_ms": {
    "estimate": 120,
    "exceeded": false,
    "threshold": 300000
  },
  "server_capabilities": {
    "contract_version": 1,
    "time_unit": "ms",
    "auth_mode": "strict",
    "token_rotation": {"grace_seconds": 86400}
  },
  "diagnostic_id": "b3b2d7a4-..."
}
```

### 2.5 `GET /api/search`（契约 v1：冻结参数与隔离规则）

#### 2.5.1 Request

- **Auth**：
  - 浏览器 UI（同机访问）可以不带 `Authorization`（保持现状可用）。
  - 当带 `Authorization` 时，启用 device 隔离规则（禁止越权）。
- **Query Params**：
  - `q`：string（可空；空时保持现状返回 `[]`）
  - `limit`：int（默认 `50`，上限 `200`）
  - `device_id`：string（可选）
  - `start_ts_ms`：int（可选，epoch ms）
  - `end_ts_ms`：int（可选，epoch ms）

#### 2.5.2 隔离规则（冻结）

- 若请求带 `Authorization`：
  - `device_id` 缺省 → 默认使用该 token 绑定的设备。
  - `device_id` 指定但不匹配 token → `403`。
- 若请求不带 `Authorization`：
  - `device_id` 缺省 → 默认跨设备聚合（用于 Web UI）。
  - `device_id` 指定 → 仅搜索该设备。

#### 2.5.3 Response（保持兼容 + 补充字段）

- 保持现状返回的扁平字段不变（见 `MyRecall/openrecall/server/api.py` 的 `flat` 结构）。
- M0 新增字段（不破坏旧字段）：
  - `device_id`：结果所属设备。
  - `client_ts`：epoch ms。

---

## 3. 数据层与迁移计划（必须具体到表/列/索引/兼容）

### 3.1 现有问题：`entries.timestamp UNIQUE` 在多设备/重试场景下的缺陷

现状（`MyRecall/openrecall/server/database/sql.py`）：
- `entries.timestamp INTEGER UNIQUE` + `insert_pending_entry()` 的 `ON CONFLICT(timestamp) DO NOTHING`。

问题（跨机器后必然发生）：
- **重试不幂等可审计**：重试被“同 timestamp”吞掉，但无法区分“真正重复上传”还是“同秒不同帧”。
- **多设备直接冲突**：两个设备同一秒截图会冲突。
- **与 M0 契约冲突**：M0 的幂等键与冲突键要求以 `device_id + client_ts` 为主键，而不是单列 `timestamp`。

### 3.2 迁移目标（最小破坏）

- 保留 `timestamp` 列（用于兼容旧逻辑/旧 UI），但：
  - 移除其 `UNIQUE` 约束。
  - 新增 `client_ts`（ms）作为跨机主时间戳。
- 新增跨机必需列并加组合唯一约束：
  - 组合唯一：`UNIQUE(device_id, client_ts)`。
- 引入 `image_relpath`（相对 `settings.screenshots_path`），避免 Worker 依赖 `timestamp` 推导路径。

### 3.3 `entries` 表新增列（冻结）

在 `MyRecall/openrecall/server/database/sql.py` 的 `entries` 表中新增以下列（类型/语义固定）：

| 列名 | 类型 | NULL | 语义 |
|---|---:|---:|---|
| `device_id` | TEXT | NOT NULL | 设备 ID；旧数据回填为 `OPENRECALL_LEGACY_DEVICE_ID`（默认 `legacy`） |
| `client_ts` | INTEGER | NOT NULL | 采集发生时间 epoch ms（新主时间戳） |
| `client_tz` | TEXT | NULL | IANA 时区名；旧数据可为 NULL |
| `client_seq` | INTEGER | NULL | 设备内单调序号 |
| `image_hash` | TEXT | NULL | `sha256` hex；旧数据允许 NULL（按需回填/懒计算） |
| `server_received_at` | INTEGER | NOT NULL | Server 接收时间 epoch ms；旧数据回填为 `timestamp*1000` |
| `image_relpath` | TEXT | NOT NULL | 相对 `settings.screenshots_path` 的路径（例如 `legacy/123.png` 或 `mac-01/1738..._abcd.png`） |

> 说明：之所以允许旧数据 `image_hash/client_tz` 为 NULL，是为了避免全库一次性重算 hash；当出现需要对比 hash 的场景再懒计算并补齐。

### 3.4 新增索引/唯一约束（冻结）

- 组合唯一：`UNIQUE(device_id, client_ts)`。
- 队列索引：`INDEX idx_entries_status_received ON entries(status, server_received_at)`。
- 时间检索索引：`INDEX idx_entries_device_client_ts ON entries(device_id, client_ts)`。
- 兼容索引：保留 `INDEX idx_timestamp ON entries(timestamp)`（若依旧大量使用）。

### 3.5 历史数据迁移（回填规则 + 冲突处理）

#### 3.5.1 回填规则（默认决策）

对旧表中每行：
- `device_id`：回填为 `OPENRECALL_LEGACY_DEVICE_ID`（默认 `legacy`）。
- `client_ts`：回填为 `timestamp * 1000`。
- `server_received_at`：回填为 `timestamp * 1000`（历史数据无真实接收时间，统一按此处理）。
- `client_tz`：回填为 NULL（不猜测）。
- `image_hash`：回填为 NULL（懒计算）。
- `image_relpath`：回填为 `f"{timestamp}.png"`（保持现状磁盘布局，避免破坏 `GET /static/<timestamp>.png`）。

#### 3.5.2 冲突处理（默认决策）

- 旧数据由于 `timestamp UNIQUE`，理论上不会在同 `device_id=legacy` 下产生 `(device_id, client_ts)` 冲突。
- 若出现人为手工导入导致的冲突（极小概率）：
  - 以 `id` 较小者为准保留，较大者标记 `status='FAILED'` 并记录日志（`code=LEGACY_MIGRATION_CONFLICT`）。

### 3.6 FTS/向量索引与 `device_id` 的关联（M0 冻结方案 + 预留）

为避免对现有 `LanceDB` 表做不确定的 schema 演进（可能触发表重建/丢数风险），M0 采用**物理分区**方案：

- 向量库（`LanceDB`）：按设备分目录：`settings.lancedb_path / device_id`。
  - 旧数据：归档为 `device_id=legacy` 使用现有 `settings.lancedb_path`。
- FTS（`fts.db`）：按设备分文件：
  - 新设备：`settings.server_data_dir / "fts" / f"{device_id}.db"`。
  - 旧数据：继续使用 `settings.fts_path`（即 `server_data_dir/fts.db`）作为 `legacy`。

这样 `device_id` 与索引天然绑定：Search 时只查询对应设备的索引；跨设备聚合则并行查询多个设备索引并做 merge。

---

## 4. 安全与运维（LAN 优先，但要可扩展）

### 4.1 默认部署建议（M0）

- **LAN 内先跑通**：允许 `HTTP`（例如 `http://<debian-ip>:8083`），但必须确保：
  - `OPENRECALL_AUTH_MODE=strict`（生产默认）
  - Debian 侧磁盘加密 + 最小开放端口
- **预留 TLS/反代位（未来选项）**：
  - 反代建议：`Nginx` 或 `Caddy`
  - 未来切换策略：保持后端仍为 `http://127.0.0.1:<port>`，由反代做 `TLS` 与访问控制
- **跨公网（未来选项）**：
  - 优先：`Tailscale`（设备级 ACL）
  - 备选：隧道（如 `cloudflared tunnel`），但必须保持 `Authorization` 且限制来源

### 4.2 日志与审计（必须打点 + 禁止项）

#### 4.2.1 必须打点字段（M0）

所有 `upload/heartbeat` 请求至少记录：
- `device_id`
- `diagnostic_id`
- `client_ts` 与 `server_received_at`
- `drift_ms`（`server_received_at - client_ts`）
- `queue_depth`（heartbeat）
- `idempotency_key`（upload）
- `conflict_detail`（409 时：existing/incoming hash）

#### 4.2.2 禁止落日志内容（M0 强约束）

- 禁止记录：`OCR 原文全文`、`fusion_text` 全文、`rerank context` 中的 `[OCR Content]`。
- 实现开关：仅当 `OPENRECALL_LOG_SENSITIVE=true` 时才允许写入上述敏感调试日志，并且必须在日志中显式标注 `SENSITIVE_LOGGING_ENABLED`。

对应需收敛的现状代码点：
- `MyRecall/openrecall/server/search/engine.py`：`logs/rerank_debug.log` 写入需要改为默认禁用/脱敏。
- `MyRecall/openrecall/server/worker.py`：OCR preview 与 `OPENRECALL_FUSION_LOG_ENABLED` 需要受 `OPENRECALL_LOG_SENSITIVE` 约束。

### 4.3 速率限制/资源隔离（M0 接口约束/预留）

- **上传与 Chat/tool-call 分开限流**（即使 Chat 还未实现也先预留配置）：
  - `OPENRECALL_RATE_LIMIT_UPLOAD_RPS=5`
  - `OPENRECALL_RATE_LIMIT_CHAT_RPS=1`
- M0 实现最小限流：只对 `POST /api/upload` 生效（按 `device_id` 或 token 计数），返回 `429`（`code=RATE_LIMITED`）。

---

## 5. 实现步骤（必须是可执行任务清单：2–15 分钟粒度）

> 说明：以下每个 Task 都包含：要改的文件、预期改动点、对应测试、验证命令与 `curl` 示例。所有命令/路径/环境变量均用反引号。

### Task 1：冻结 Contract 常量与校验模型（5–10 分钟）

- 文件：
  - 新建：`MyRecall/openrecall/shared/contract_m0.py`
- 改动点：
  - 定义常量：`CONTRACT_VERSION=1`、`LEGACY_DEVICE_ID`、`DRIFT_THRESHOLD_MS=300000`、`TIME_UNIT=ms`
  - 定义 Pydantic 模型：`UploadMetadataV1`、`HeartbeatRequestV1`、`ErrorEnvelope`
  - 提供兼容解析：旧字段 `timestamp` → `client_ts=timestamp*1000`
- 测试：
  - 新建：`MyRecall/tests/test_m0_contract_validation.py`
  - 用例：`test_upload_metadata_legacy_timestamp_maps_to_client_ts_ms`
- 验证：
  - 命令：`pytest MyRecall/tests/test_m0_contract_validation.py::test_upload_metadata_legacy_timestamp_maps_to_client_ts_ms -q`
  - `curl`（健康检查占位，用于确认 Server 可访问）：`curl -sS http://localhost:8083/api/health`

### Task 2：补齐 Settings（Auth/限流/兼容开关）（10–15 分钟）

- 文件：
  - 修改：`MyRecall/openrecall/shared/config.py`
- 改动点：
  - 新增 Server 侧配置：
    - `OPENRECALL_AUTH_MODE`（枚举：`strict|permissive|disabled`，默认 `strict`）
    - `OPENRECALL_DEVICE_TOKENS_JSON`（JSON 字符串）
    - `OPENRECALL_TOKEN_GRACE_SECONDS`（默认 `86400`）
    - `OPENRECALL_MAX_UPLOAD_BYTES`（默认 `10485760`）
    - `OPENRECALL_LOG_SENSITIVE`（默认 `false`）
    - `OPENRECALL_RATE_LIMIT_UPLOAD_RPS`、`OPENRECALL_RATE_LIMIT_CHAT_RPS`
    - `OPENRECALL_IDEMPOTENCY_STRICT`（默认 `true`）
    - `OPENRECALL_LEGACY_DEVICE_ID`（默认 `legacy`）
  - 新增 Client 侧配置：
    - `OPENRECALL_DEVICE_ID`（默认 `platform.node()`）
    - `OPENRECALL_DEVICE_TOKEN`（默认空；在 strict 模式必须配置）
- 测试：
  - 新建：`MyRecall/tests/test_m0_settings.py`
  - 用例：`test_settings_auth_mode_defaults_to_strict`
- 验证：
  - 命令：`pytest MyRecall/tests/test_m0_settings.py::test_settings_auth_mode_defaults_to_strict -q`
  - `curl`：`curl -sS http://localhost:8083/api/config | head -c 200`

### Task 3：实现设备 token 校验工具（10–15 分钟）

- 文件：
  - 新建：`MyRecall/openrecall/server/utils/auth.py`
  - 修改：`MyRecall/openrecall/server/api.py`
- 改动点：
  - `parse_bearer_token()`：解析 `Authorization` header
  - `resolve_device_id_from_token()`：将 token 映射到 device
  - `require_device_auth(requested_device_id)`：输出 `(device_id, auth_mode)` 或抛出可序列化错误
- 测试：
  - 新建：`MyRecall/tests/test_m0_auth.py`
  - 用例：`test_auth_missing_header_returns_401`
- 验证：
  - 命令：`pytest MyRecall/tests/test_m0_auth.py::test_auth_missing_header_returns_401 -q`
  - `curl`：`curl -sS -X POST http://localhost:8083/api/heartbeat -H 'Content-Type: application/json' -d '{}' -i | head -n 20`

### Task 4：SQLite 迁移框架（无外部工具，启动时自动迁移）（10–15 分钟）

- 文件：
  - 修改：`MyRecall/openrecall/server/database/sql.py`
- 改动点：
  - 在 `SQLStore._init_db()` 中加入 `migrate_entries_schema_to_m0()`：
    - 检测 `entries` 是否仍为旧 schema（通过 `PRAGMA table_info(entries)`）
    - 备份：复制 `recall.db` 到 `recall.db.bak_m0_<date>`
    - 通过“建新表 → 拷贝 → rename”移除 `timestamp UNIQUE` 并新增列/索引/唯一约束
- 测试：
  - 新建：`MyRecall/tests/test_m0_db_migration.py`
  - 用例：`test_m0_migration_removes_timestamp_unique_adds_device_client_ts_unique`
- 验证：
  - 命令：`pytest MyRecall/tests/test_m0_db_migration.py::test_m0_migration_removes_timestamp_unique_adds_device_client_ts_unique -q`
  - `curl`：`curl -sS http://localhost:8083/api/health`

### Task 5：SQLStore 写入新列与幂等查询（10–15 分钟）

- 文件：
  - 修改：`MyRecall/openrecall/server/database/sql.py`
  - 修改：`MyRecall/openrecall/shared/models.py`
- 改动点：
  - `RecallEntry` 增加字段：`device_id/client_ts/server_received_at/image_relpath/image_hash/client_tz/client_seq`
  - 新增方法：
    - `get_entry_by_device_client_ts(device_id, client_ts)`
    - `insert_pending_entry_v1(...)`：写入新列并返回 `entry_id`
- 测试：
  - 新建：`MyRecall/tests/test_m0_sqlstore_idempotency.py`
  - 用例：`test_insert_pending_entry_v1_persists_device_and_client_ts`
- 验证：
  - 命令：`pytest MyRecall/tests/test_m0_sqlstore_idempotency.py::test_insert_pending_entry_v1_persists_device_and_client_ts -q`
  - `curl`：`curl -sS http://localhost:8083/api/health`

### Task 6：实现 `POST /api/upload` 新契约（15 分钟）

- 文件：
  - 修改：`MyRecall/openrecall/server/api.py`
- 改动点：
  - 解析 `metadata`：优先 `client_ts/client_tz/device_id/image_hash`；兼容旧 `timestamp`
  - 校验：文件类型/大小/hash/字段格式
  - 调用 `auth.require_device_auth()`
  - 幂等逻辑：
    - 若 `(device_id, client_ts)` 已存在：hash 相同 → `200`；hash 不同 → `409`
    - 否则：落盘（原子写）→ DB 插入 → `202`
  - 必须写入 `server_received_at`
- 测试：
  - 新建：`MyRecall/tests/test_m0_upload_contract_integration.py`
  - 用例：
    - `test_upload_valid_contract_returns_202_and_persists_new_columns`
    - `test_upload_idempotent_replay_returns_200`
    - `test_upload_conflict_returns_409`
- 验证：
  - 命令：`pytest MyRecall/tests/test_m0_upload_contract_integration.py -q`
  - `curl`（示例：需替换 token 与图片路径）：

```bash
curl -sS -X POST 'http://localhost:8083/api/upload' \
  -H 'Authorization: Bearer <device_token>' \
  -F 'file=@/tmp/test.png;type=image/png' \
  -F 'metadata={"device_id":"mac-01","client_ts":1738752000123,"client_tz":"America/Los_Angeles","client_seq":1,"image_hash":"<sha256>","app_name":"TestApp","window_title":"TestWin"}' \
  -i | head -n 30
```

### Task 7：实现 `POST /api/heartbeat` 新契约（10–15 分钟）

- 文件：
  - 修改：`MyRecall/openrecall/server/api.py`
  - 修改：`MyRecall/openrecall/server/config_runtime.py`
- 改动点：
  - `heartbeat` 支持 JSON body：`device_id/client_ts/client_tz/queue_depth/last_error/capabilities`
  - 按 token 绑定 `device_id` 做越权校验
  - 计算 `drift_ms` 并在响应返回
  - 仍返回 `runtime_settings.to_dict()`（兼容现状），并补齐 `server_capabilities`
- 测试：
  - 新建：`MyRecall/tests/test_m0_heartbeat_contract_integration.py`
  - 用例：`test_heartbeat_returns_server_time_and_drift`
- 验证：
  - 命令：`pytest MyRecall/tests/test_m0_heartbeat_contract_integration.py::test_heartbeat_returns_server_time_and_drift -q`
  - `curl`：

```bash
curl -sS -X POST 'http://localhost:8083/api/heartbeat' \
  -H 'Authorization: Bearer <device_token>' \
  -H 'Content-Type: application/json' \
  -d '{"device_id":"mac-01","client_ts":1738752000123,"client_tz":"America/Los_Angeles","queue_depth":3,"last_error":null,"capabilities":{"client_version":"3.0.0","platform":"macOS","capture":{"primary_monitor_only":true},"upload":{"formats":["png"],"hash":"sha256"}}}' \
  -i | head -n 40
```

### Task 8：Client 上传 metadata 升级（10–15 分钟）

- 文件：
  - 修改：`MyRecall/openrecall/client/recorder.py`
  - 修改：`MyRecall/openrecall/client/consumer.py`
  - 修改：`MyRecall/openrecall/client/uploader.py`
- 改动点：
  - recorder 采集时写入 metadata：`device_id/client_ts/client_tz/client_seq`
  - uploader 计算 `image_hash=sha256(png_bytes)`，并带 `Authorization: Bearer <device_token>`
  - consumer 透传新字段，不再仅依赖旧 `timestamp`
- 测试：
  - 新建：`MyRecall/tests/test_m0_client_metadata_unit.py`
  - 用例：`test_client_builds_upload_metadata_includes_device_and_hash`
- 验证：
  - 命令：`pytest MyRecall/tests/test_m0_client_metadata_unit.py::test_client_builds_upload_metadata_includes_device_and_hash -q`
  - `curl`（用 Server 端 `GET /api/config` 确认 client_online）：`curl -sS http://localhost:8083/api/config | rg -n 'client_online'`

### Task 9：Client heartbeat 上报升级（10–15 分钟）

- 文件：
  - 修改：`MyRecall/openrecall/client/recorder.py`
- 改动点：
  - `_send_heartbeat()` 改为发送 JSON body（见 2.4），并带 `Authorization` header
  - `queue_depth` 使用 `LocalBuffer.count()`
  - `last_error` 从 consumer/uploader 暴露的最近错误读取（M0 默认：网络错误/上传失败）
- 测试：
  - 新建：`MyRecall/tests/test_m0_client_heartbeat_unit.py`
  - 用例：`test_recorder_send_heartbeat_sends_json_body`
- 验证：
  - 命令：`pytest MyRecall/tests/test_m0_client_heartbeat_unit.py::test_recorder_send_heartbeat_sends_json_body -q`
  - `curl`：同 Task 7 的 heartbeat 示例

### Task 10：Worker 使用 `image_relpath`，避免 `timestamp` 推导路径（10–15 分钟）

- 文件：
  - 修改：`MyRecall/openrecall/server/worker.py`
  - 修改：`MyRecall/openrecall/server/database/sql.py`
- 改动点：
  - `get_next_task()` 查询返回 `image_relpath/device_id/client_ts` 等
  - Worker 读取图片路径改为：`settings.screenshots_path / image_relpath`
- 测试：
  - 新建：`MyRecall/tests/test_m0_worker_image_path_integration.py`
  - 用例：`test_worker_uses_image_relpath_to_locate_file`
- 验证：
  - 命令：`pytest MyRecall/tests/test_m0_worker_image_path_integration.py::test_worker_uses_image_relpath_to_locate_file -q`
  - `curl`：上传一张图后检查 `GET /screenshots/<path>` 可访问：`curl -sS -I 'http://localhost:8083/screenshots/<image_relpath>' | head -n 5`

### Task 11：向量/FTS 按设备物理分区（15 分钟）

- 文件：
  - 修改：`MyRecall/openrecall/server/database/vector_store.py`
  - 修改：`MyRecall/openrecall/server/database/sql.py`
  - 修改：`MyRecall/openrecall/server/search/engine.py`
- 改动点：
  - `VectorStore` 支持 `device_id` 参数：
    - `legacy` → 仍使用 `settings.lancedb_path`
    - 其他 → 使用 `settings.lancedb_path / device_id`
  - `SQLStore` 的 FTS 支持按设备选择路径：
    - `legacy` → `settings.fts_path`
    - 其他 → `settings.server_data_dir / "fts" / f"{device_id}.db"`
  - `SearchEngine.search()` 支持传入 `device_id`，并只查询该设备索引
- 测试：
  - 新建：`MyRecall/tests/test_m0_search_device_partition_unit.py`
  - 用例：`test_search_engine_uses_device_scoped_vector_and_fts_paths`
- 验证：
  - 命令：`pytest MyRecall/tests/test_m0_search_device_partition_unit.py::test_search_engine_uses_device_scoped_vector_and_fts_paths -q`
  - `curl`：`curl -sS 'http://localhost:8083/api/search?q=test&device_id=legacy' | head -c 200`

### Task 12：`GET /api/search` 增加 `device_id/start_ts_ms/end_ts_ms`（10–15 分钟）

- 文件：
  - 修改：`MyRecall/openrecall/server/api.py`
  - 修改：`MyRecall/openrecall/server/search/engine.py`
- 改动点：
  - API 层解析 `start_ts_ms/end_ts_ms` 并转换为 seconds 过滤（对接现有 `where_clause` 使用的 `context.timestamp`）
  - 带 auth 时执行越权校验（见 2.5）
  - 响应补充 `device_id/client_ts` 字段
- 测试：
  - 新建：`MyRecall/tests/test_m0_search_contract_integration.py`
  - 用例：`test_search_with_auth_rejects_other_device_returns_403`
- 验证：
  - 命令：`pytest MyRecall/tests/test_m0_search_contract_integration.py::test_search_with_auth_rejects_other_device_returns_403 -q`
  - `curl`：`curl -sS -H 'Authorization: Bearer <device_token>' 'http://localhost:8083/api/search?q=test&device_id=mac-01&limit=5' | head -c 300`

### Task 13：收敛敏感日志（默认不落 OCR 原文）（10–15 分钟）

- 文件：
  - 修改：`MyRecall/openrecall/server/search/engine.py`
  - 修改：`MyRecall/openrecall/server/worker.py`
  - 修改：`MyRecall/openrecall/shared/config.py`
- 改动点：
  - 引入 `OPENRECALL_LOG_SENSITIVE`：默认 `false`
  - 当 `false`：
    - 禁止写 `logs/rerank_debug.log` 的全文上下文
    - 禁止写 `logs/fusion_debug.log` 的 OCR 全文
    - 禁止在 worker 日志打印 OCR preview
  - 当 `true`：允许但必须显式标注
- 测试：
  - 新建：`MyRecall/tests/test_m0_sensitive_logging.py`
  - 用例：`test_sensitive_logs_disabled_does_not_write_rerank_debug_log`
- 验证：
  - 命令：`pytest MyRecall/tests/test_m0_sensitive_logging.py::test_sensitive_logs_disabled_does_not_write_rerank_debug_log -q`
  - `curl`：触发一次搜索后检查 `logs/rerank_debug.log` 不新增：`curl -sS 'http://localhost:8083/api/search?q=test' > /dev/null`

### Task 14：最小限流（仅 upload 生效，chat 预留）（10–15 分钟）

- 文件：
  - 修改：`MyRecall/openrecall/server/api.py`
  - 修改：`MyRecall/openrecall/shared/config.py`
- 改动点：
  - 实现内存级 token bucket（按 `device_id`）限制 `POST /api/upload`
  - 超限返回 `429`（`code=RATE_LIMITED`）
- 测试：
  - 新建：`MyRecall/tests/test_m0_rate_limit.py`
  - 用例：`test_upload_rate_limited_returns_429`
- 验证：
  - 命令：`pytest MyRecall/tests/test_m0_rate_limit.py::test_upload_rate_limited_returns_429 -q`
  - `curl`：快速并发两次上传（可用 `xargs -P`）：`printf '%s\n' 1 2 3 4 5 6 | xargs -I{} -P 6 curl -sS -o /dev/null -w '%{http_code}\n' -X POST 'http://localhost:8083/api/upload' -H 'Authorization: Bearer <device_token>' -F 'file=@/tmp/test.png;type=image/png' -F 'metadata={...}'`

---

## 6. 测试计划（必须落地到 pytest）

### 6.1 单元测试（建议标记 `pytest.mark.unit`，但不使用 `security` marker 以免默认被跳过）

必测点（示例 test 名称，遵循 `test_<action>_<scenario>_<expected>`）：

1. `test_upload_metadata_legacy_timestamp_maps_to_client_ts_ms`（`MyRecall/tests/test_m0_contract_validation.py`）
2. `test_auth_missing_header_returns_401`（`MyRecall/tests/test_m0_auth.py`）
3. `test_auth_token_device_mismatch_returns_403`（`MyRecall/tests/test_m0_auth.py`）
4. `test_insert_pending_entry_v1_persists_device_and_client_ts`（`MyRecall/tests/test_m0_sqlstore_idempotency.py`）
5. `test_search_engine_uses_device_scoped_vector_and_fts_paths`（`MyRecall/tests/test_m0_search_device_partition_unit.py`）
6. `test_sensitive_logs_disabled_does_not_write_rerank_debug_log`（`MyRecall/tests/test_m0_sensitive_logging.py`）

### 6.2 集成测试（Flask `test_client` + 临时目录 DB，沿用现有 fixture）

- 使用 `MyRecall/tests/conftest.py` 的 `flask_client`（会通过 `OPENRECALL_DATA_DIR` 创建隔离 DB）。

必测点（示例）：

1. `test_upload_valid_contract_returns_202_and_persists_new_columns`（`MyRecall/tests/test_m0_upload_contract_integration.py`）
2. `test_upload_idempotent_replay_returns_200`（同上）
3. `test_upload_conflict_returns_409`（同上）
4. `test_heartbeat_returns_server_time_and_drift`（`MyRecall/tests/test_m0_heartbeat_contract_integration.py`）
5. `test_search_with_auth_rejects_other_device_returns_403`（`MyRecall/tests/test_m0_search_contract_integration.py`）
6. `test_upload_rate_limited_returns_429`（`MyRecall/tests/test_m0_rate_limit.py`）

### 6.3 测试执行命令（固定）

- 跑 M0 新增测试：`pytest MyRecall/tests/test_m0_* -q`
- 跑默认全量（不含 `model/perf/security/e2e/manual`）：`pytest`

---

## 7. 回滚与兼容（必须给默认策略）

### 7.1 Server 向后兼容旧 Client（不升级也能跑）

- 旧 Client 现状（`MyRecall/openrecall/client/uploader.py`）：只发送 `metadata.timestamp/app_name/window_title` 且无 `Authorization`。
- M0 默认兼容策略：
  1) 当 `OPENRECALL_AUTH_MODE=permissive`：
     - `Authorization` 可缺省；缺省时 `device_id` 强制回填为 `OPENRECALL_LEGACY_DEVICE_ID`（默认 `legacy`）。
  2) metadata 缺 `client_ts`：使用 `timestamp*1000` 作为 `client_ts`。
  3) metadata 缺 `client_tz/image_hash`：允许为 NULL，但会在日志记录 `code=LEGACY_METADATA_MISSING_FIELDS`。

> 生产切换步骤（固定）：先用 `OPENRECALL_AUTH_MODE=permissive` 运行并升级 Client 配置 `OPENRECALL_DEVICE_ID/OPENRECALL_DEVICE_TOKEN`，确认 24h 无异常后切到 `OPENRECALL_AUTH_MODE=strict`。

### 7.2 DB schema 回滚

- 迁移前必须备份：`recall.db` → `recall.db.bak_m0_<date>`（由 `SQLStore.migrate_entries_schema_to_m0()` 自动完成）。
- 回滚方式（固定）：
  - 停服务 → 用备份文件覆盖 `settings.db_path` → 启服务。

### 7.3 Feature Flags（最小可用回退）

- `OPENRECALL_AUTH_MODE=disabled`：完全关闭鉴权（仅用于本地调试）。
- `OPENRECALL_IDEMPOTENCY_STRICT=false`：
  - 遇到 `(device_id, client_ts)` 相同但 hash 不同不再 `409`，而是创建新 entry，并在 entry 上记录 `code=UPLOAD_WEAK_DEDUP_CREATED_NEW`（用于临时止血）。
- `OPENRECALL_LOG_SENSITIVE=false`：强制关闭敏感日志（生产默认）。

---

## 附录 A：本地手工验证脚本（可复制执行）

### A.1 生成测试 token（示例）

- 生成 32 字节随机 token：`python - <<'PY'\nimport secrets\nprint(secrets.token_urlsafe(32))\nPY`

### A.2 计算图片 sha256（示例）

- 计算 `image_hash`：`python - <<'PY'\nimport hashlib\nfrom pathlib import Path\np=Path('/tmp/test.png')\nprint(hashlib.sha256(p.read_bytes()).hexdigest())\nPY`

### A.3 upload（新契约）

- `curl`：见 Task 6 的示例（务必替换 `<device_token>` 与 `<sha256>`）。

### A.4 heartbeat（新契约）

- `curl`：见 Task 7 的示例。
