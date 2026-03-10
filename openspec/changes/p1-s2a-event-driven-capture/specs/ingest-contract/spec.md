## MODIFIED Requirements

### Requirement: POST /v1/ingest capture_trigger contract
系统 MUST 在 P1-S2a 起对 `POST /v1/ingest` 的新上报 payload 强制校验 `capture_trigger`。允许值必须限定为 `idle`、`app_switch`、`manual`、`click`。当字段缺失、为 null 或不在枚举中时，接口 MUST 返回 `400 INVALID_PARAMS`，且 MUST NOT 创建或修改任何 `frames` 记录。历史存量数据可保留数据库中的 `NULL` 值，但该兼容不得扩展到 S2a 之后的新上报。

### Requirement: POST /v1/ingest event_ts observation contract
系统 MUST 将 `event_ts` 视为 `capture_latency_ms` 观测口径字段（Host 触发时刻，UTC ISO8601）。当 `event_ts` 缺失、非法或晚于入库时刻（会导致负延迟）时，服务端 MAY 继续按 ingest 成功路径处理该 capture，但该样本 MUST NOT 进入 `capture_latency_p95` 统计，并 MUST 计入观测异常计数。

#### Scenario: Return INVALID_PARAMS for invalid trigger enum
- **WHEN** 客户端向 `POST /v1/ingest` 提交的 `capture_trigger` 为 null、缺失或非法值
- **THEN** 服务端 MUST 返回 400 与 `INVALID_PARAMS` 并保持 `frames` 持久化状态不变

#### Scenario: Exclude invalid event_ts from latency statistics
- **WHEN** 客户端向 `POST /v1/ingest` 提交的 `event_ts` 缺失或格式非法
- **THEN** 服务端 MAY 接受该 ingest 请求，但 MUST 将该 capture 排除在 `capture_latency_p95` 样本之外并记录观测异常

#### Scenario: Exclude future/negative-latency event_ts from latency statistics
- **WHEN** 客户端向 `POST /v1/ingest` 提交的 `event_ts` 晚于该 capture 的入库时刻并导致负延迟
- **THEN** 服务端 MAY 接受该 ingest 请求，但 MUST 将该 capture 排除在 `capture_latency_p95` 样本之外并记录观测异常
