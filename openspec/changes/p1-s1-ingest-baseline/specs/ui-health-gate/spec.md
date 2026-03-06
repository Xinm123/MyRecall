## ADDED Requirements

### Requirement: #mr-health DOM 锚点

`/`、`/search`、`/timeline` 三个页面首屏 MUST 存在稳定 DOM 元素，`id="mr-health"`。该元素 MUST 首屏可见（不得要求点击展开才能看到）。

#### Scenario: 三页均存在 #mr-health

- **WHEN** 浏览器依次访问 `/`、`/search`、`/timeline`
- **THEN** 每个页面的 DOM 中存在 `#mr-health` 元素，且在首屏可见区域内可见

### Requirement: data-state 状态机

`#mr-health` 元素 MUST 暴露 `data-state` 属性，取值为 `"healthy"`、`"unreachable"` 或 `"degraded"` 之一。

#### Scenario: 服务正常时显示 healthy

- **WHEN** 浏览器可成功请求 `GET /v1/health` 且 `status == "ok"` 且 `frame_status == "ok"` 且 `queue.failed == 0`
- **THEN** `#mr-health[data-state="healthy"]`，且页面文案包含 `服务健康/队列正常`

#### Scenario: 启动后尚未收到任何帧时显示 degraded（等待首帧）

- **WHEN** 浏览器可成功请求 `GET /v1/health`，且 `last_frame_timestamp == null` 且 `frame_status == "stale"` 且 `status == "degraded"` 且 `queue.failed == 0`
- **THEN** `#mr-health[data-state="degraded"]`，且页面文案包含 `等待首帧`（不得显示 `Edge 不可达`）

#### Scenario: 请求失败超过 grace 期显示 unreachable

- **WHEN** 浏览器请求 `GET /v1/health` 失败或超时，且连续持续时间 >= `unreachable_grace_ms`（5000ms）
- **THEN** `#mr-health[data-state="unreachable"]`，且页面文案包含 `Edge 不可达`

#### Scenario: 请求成功但状态异常显示 degraded

- **WHEN** 浏览器可成功请求 `GET /v1/health`，但 `status != "ok"` 或 `queue.failed > 0` 或 `frame_status != "ok"`
- **THEN** `#mr-health[data-state="degraded"]`，且页面文案为明确错误提示

### Requirement: 轮询参数固定

UI 轮询 `GET /v1/health` 的参数 SHALL 固定为：`poll_interval_ms=5000`、`request_timeout_ms=2000`、`unreachable_grace_ms=5000`。验收以此为口径。

#### Scenario: 轮询间隔验证

- **WHEN** 观察浏览器网络请求
- **THEN** 对 `/v1/health` 的请求间隔约为 5 秒（`poll_interval_ms=5000`）

#### Scenario: 请求超时为 2 秒

- **WHEN** `/v1/health` 响应延迟超过 2 秒
- **THEN** 浏览器端视为请求失败（超时）

### Requirement: 15 秒内进入 unreachable

在页面完成首屏渲染后（不刷新页面），制造浏览器侧对 `GET /v1/health` 的请求失败/超时后，页面 MUST 在 15 秒内进入 `data-state="unreachable"`。

#### Scenario: 停止 Edge 后 15 秒内显示不可达

- **WHEN** 页面已完成首屏渲染（显示 `healthy`），然后停止 Edge 进程
- **THEN** 该页面在 15 秒内将 `data-state` 切换为 `"unreachable"`，文案包含 `Edge 不可达`；期间不刷新页面

### Requirement: 10 秒内自动恢复

从 `unreachable` 或 `degraded` 状态，只要任意一次后续轮询满足 `healthy` 条件，UI MUST 在不刷新页面的情况下在 10 秒内自动回到 `data-state="healthy"`。

#### Scenario: 恢复 Edge 后 10 秒内回到 healthy

- **WHEN** 页面处于 `data-state="unreachable"` 状态，然后恢复 Edge 进程（`GET /v1/health` 恢复可达）
- **THEN** 该页面在 10 秒内将 `data-state` 切换回 `"healthy"`，文案包含 `服务健康/队列正常`；期间不刷新页面

### Requirement: 故障注入与恢复禁止刷新页面

unreachable 检测与自动恢复的整个过程 SHALL NOT 依赖页面刷新。状态切换 MUST 通过 JS 轮询与 DOM 更新完成。

#### Scenario: 全程无页面刷新

- **WHEN** 从 `healthy` -> `unreachable` -> `healthy` 的完整状态转换过程中
- **THEN** 浏览器不发生页面导航或 F5 刷新，所有状态变更通过 JS 动态更新 `#mr-health` 的 `data-state` 属性和文案

### Requirement: layout.html 一次注入覆盖三页

`#mr-health` 组件 SHALL 在 `openrecall/server/templates/layout.html` 中实现一次注入，由 `/`、`/search`、`/timeline` 三个页面通过模板继承自动获得。不逐页复制。

#### Scenario: 新增页面自动获得健康组件

- **WHEN** `layout.html` 中包含 `#mr-health` 组件，且三个页面模板均继承 `layout.html`
- **THEN** 三个页面首屏均可见 `#mr-health`，无需逐页添加

### Requirement: "Edge 不可达"的验收前提

"不可达"指页面已完成首屏渲染后浏览器侧对 `/v1/health` 不可达/超时。不要求在 Edge 无法提供页面（首屏无法加载）的前提下展示"错误态 UI"。

#### Scenario: 首屏未加载时不要求展示错误态

- **WHEN** Edge 完全不可用导致页面无法加载（首屏渲染失败）
- **THEN** 不要求展示 `#mr-health[data-state="unreachable"]`（因为页面本身不存在）
