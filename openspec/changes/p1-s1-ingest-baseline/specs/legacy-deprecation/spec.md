## ADDED Requirements

### Requirement: legacy 端点 301 重定向

Edge SHALL 对以下 4 个 legacy 端点返回 `301 Moved Permanently`，响应头包含 `Location` 指向对应的 `/v1/*` 路径：

| Legacy 端点 | Location 目标 |
|---|---|
| `POST /api/upload` | `/v1/ingest` |
| `GET /api/search` | `/v1/search` |
| `GET /api/queue/status` | `/v1/ingest/queue/status` |
| `GET /api/health` | `/v1/health` |

#### Scenario: POST /api/upload 重定向

- **WHEN** 客户端请求 `POST /api/upload`
- **THEN** Edge 返回 `301`，响应头 `Location` 值为 `/v1/ingest`

#### Scenario: GET /api/search 重定向

- **WHEN** 客户端请求 `GET /api/search`
- **THEN** Edge 返回 `301`，响应头 `Location` 值为 `/v1/search`

#### Scenario: GET /api/queue/status 重定向

- **WHEN** 客户端请求 `GET /api/queue/status`
- **THEN** Edge 返回 `301`，响应头 `Location` 值为 `/v1/ingest/queue/status`

#### Scenario: GET /api/health 重定向

- **WHEN** 客户端请求 `GET /api/health`
- **THEN** Edge 返回 `301`，响应头 `Location` 值为 `/v1/health`

### Requirement: [DEPRECATED] 日志记录

Edge 在处理上述 4 个 legacy 端点请求时，MUST 记录包含 `[DEPRECATED]` 标记的日志行，格式为 `/api/{endpoint} -> /v1/{endpoint}`。

#### Scenario: legacy 请求产生废弃日志

- **WHEN** 客户端请求 `GET /api/health`
- **THEN** 服务器日志中出现包含 `[DEPRECATED]` 且包含 `/api/health -> /v1/health` 的日志行

#### Scenario: 每次请求记录一次

- **WHEN** 连续 3 次请求 `POST /api/upload`
- **THEN** 服务器日志中出现 3 条 `[DEPRECATED]` 相关日志行

### Requirement: 301 仅为迁移提示，不依赖 redirect 作为功能路径

P1-S1 的 `301` 仅用于"废弃回归检查"。Host 主路径 SHALL 直接调用 `/v1/*`，不依赖 legacy 端点的 redirect 行为。

#### Scenario: 301 不等价于目标端点可用

- **WHEN** 客户端请求 `GET /api/search` 并收到 `301` -> `/v1/search`
- **THEN** 即使 `/v1/search` 在 P1-S1 返回 `404`（P1-S4 才实现），301 行为本身仍为正确（属预期）

### Requirement: 不实现 catch-all /api/* redirect

Edge SHALL NOT 对上述 4 个端点之外的 `/api/*` 路径做 redirect 或特殊处理。其余 `/api/*` 行为不纳入 P1 Gate 口径。

#### Scenario: 非 Gate scope 的 /api 路径不受影响

- **WHEN** 客户端请求 `GET /api/config`（不在 Gate scope 内）
- **THEN** Edge 不返回 301，按现有逻辑处理（可能返回 200 或 404，取决于现有实现）

### Requirement: P1-S4 起切换为 410 Gone

自 P1-S4 起，上述 4 个 legacy 端点 SHALL 从 `301` 切换为 `410 Gone`（完全废弃）。P1-S1 至 P1-S3 期间 SHALL 保持 `301`。

#### Scenario: P1-S1 阶段返回 301

- **WHEN** P1-S1 阶段客户端请求任一 legacy 端点
- **THEN** 返回 `301`（而非 `410`）
