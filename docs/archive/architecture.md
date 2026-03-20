# Chat Architecture

- 版本：v1.0
- 日期：2026-03-19
- 状态：Draft
- 角色：记录 Chat 运行架构、部署边界与待定架构决策；不定义 Entry Gate

---

## 1. 文档角色

本文件只讨论：

- Host / Edge 职责划分
- Chat agent 的数据访问路径
- provider / process / UI 放置问题
- 需要后续继续收口的架构与安全边界

本文件不定义哪些能力是 Chat 开发前的硬门槛；该问题以 `docs/v3/chat/prerequisites.md` 为准。

---

## 2. 当前已确认的架构约束

### 2.1 Confirmed Constraints

- 后续 Host 与 Edge 会运行在不同机器上
- 当前 Host 侧 Chat runtime / capture assumptions 暂时只考虑 macOS
- Host agent 不直接访问 Edge 的 SQLite 文件
- Host agent 通过 Edge 暴露的 HTTP(S) API 获取数据能力

这些是当前架构讨论中的强约束，而不是暂时偏好。

### 2.2 Host agent 的数据访问路径

当前约束下，Host agent 应通过以下 Edge API 访问数据面：

- `GET /v1/search`
- `GET /v1/activity-summary`
- `GET /v1/elements`
- `GET /v1/frames/{id}/context`
- `GET /v1/frames/{id}/elements`
- `POST /v1/raw_sql`

### 2.3 `/v1/raw_sql` 的架构含义

- 对 Host agent 而言，`/v1/raw_sql` 是远程查询 API，不是本地数据库访问
- 当前阶段允许保留 screenpipe-like 能力
- 其 `Entry Gate / P0-support` 身份不因后续安全收口要求而改变
- 但在 Host/Edge 分机前必须复审是否收紧为受限只读 SQL API

### 2.4 推荐的数据访问抽象

当前推荐在 Host 侧增加一个薄的 `EdgeClient` / `ChatDataAccess` 抽象，用于：

- endpoint 封装
- 参数规范化
- 错误归一化
- timeout / auth 策略收口

该抽象应接近 screenpipe `fetchAPI()` 的方向，但比单纯 HTTP helper 更正式；同时不演化为重型 service layer。

---

## 3. Preferred Runtime Direction

### 3.1 Agent-first runtime

当前方向采用 `Agent-first runtime`，而不是简单的搜索增强聊天。

这意味着运行时需要优先支持：

- 长会话状态
- 流式文本输出
- 工具调用事件流
- 多步工具编排
- provider 统一入口

### 3.2 Host-side sidecar orchestration

当前首选方向是：

- agent runtime 运行在 Host
- 采用与 screenpipe 对齐的 `PiManager`-style local sidecar 模式

说明：

- 这是当前首选运行方向，不等于所有实现细节已经最终拍板
- 与之配套的核心原则仍然是 `API-first data access`

### 3.3 Event-stream-first

当前首选交互模型是：

- 请求/命令负责启动一个 turn 或控制 session
- UI 的实时更新依赖事件流，而不是等待完整响应

这与 screenpipe 当前的 agent/tool event 模式对齐。

---

## 4. Preferred Ownership Model

### 4.1 PiManager 与 UI 的边界

- `PiManager` 持有 agent runtime 的真实运行状态
- UI 只消费归一化后的会话状态和事件
- UI 不应直接成为 sidecar/runtime 的 owner

### 4.2 Session / Controller 层

当前建议在 Host 侧增加 `ChatSession` / `ChatController` 一层，用于：

- 归一化 PiManager 原始事件
- 维护会话级状态
- 向 UI 投影稳定的会话事件流

这意味着：

- `PiManager` 负责 runtime 执行
- `ChatSession` / `ChatController` 负责会话语义与 UI 边界
- UI 负责展示与交互

### 4.3 Chat history ownership

- 运行中会话状态：Host `ChatSession` / `ChatController`
- 历史持久化：当前优先在 Host，本地为真源
- Edge 不作为 Chat session/source-of-truth

### 4.4 Provider routing ownership

- provider routing 归属于 Host 的 `PiManager` / agent runtime 层
- 不放在 UI
- 不放在 Edge

---

## 5. Open / Provisional Architecture Decisions

以下问题不再作为 prerequisites 议题维护，而作为架构议题继续收口：

| 决策 | 当前状态 | 说明 |
|------|----------|------|
| `C1` Agent 运行位置 | Preferred direction chosen | 当前方向为 Host-side agent runtime，但仍保留实现细节开放 |
| `C2` Host 是否增加 PiManager | Preferred direction chosen | 当前方向倾向 `PiManager`-style sidecar，但边界仍待细化 |
| `C3` Host 是否增加 UI / 是否迁移 UI | Reopened | 属于产品与部署架构议题 |
| `C4` LLM 调用方式 | Preferred direction chosen | 当前方向为 provider routing in Host runtime，具体模型仍待定 |

当前只保留一个总原则：

- 这些问题不会决定能否开始 Chat 开发
- 它们会影响 Chat 最终运行形态与部署边界

---

## 6. Chat 数据访问路径

```text
Host UI
  <- ChatSession / ChatController event stream
     <- PiManager / local sidecar agent
        -> EdgeClient / ChatDataAccess
           -> Edge /v1/search
           -> Edge /v1/activity-summary
           -> Edge /v1/elements
           -> Edge /v1/frames/{id}/context
           -> Edge /v1/frames/{id}/elements
           -> Edge /v1/raw_sql
```

这条路径对应的核心原则是：

- 数据面在 Edge
- agent orchestration 在 Host
- 跨机通信通过 API 契约完成，而不是共享数据库文件
- UI 通过 session/controller 消费归一化事件，而不是直接持有 runtime 真状态

---

## 7. Open Details / 后续复审点

| 议题 | 复审触发点 | 当前状态 |
|------|------------|----------|
| `/v1/raw_sql` 收紧策略 | Chat 主链路跑通后、Host/Edge 分机前 | 必须复审 |
| Host -> Edge 鉴权模型 | Host/Edge 分机前 | 待定 |
| Browser URL 获取路径与优先级 | Chat 架构继续细化时 | 待定；不影响其进入 capture metadata 与 search-facing 结果的硬要求 |
| PiManager 与 ChatSession 的边界 | 架构阶段 | 待定细化 |
| UI 事件协议 / event bridge 形状 | 架构阶段 | 待定 |
| history persistence 的具体存储介质 | 架构阶段 | 待定 |
| provider routing 的具体配置模型 | 架构阶段 | 待定 |

---

## 8. 与 prerequisites 的边界

以下内容由 `docs/v3/chat/prerequisites.md` 管理，而不是本文件：

- `Entry Gate / Parity Gate` 分类
- `P0-core / P0-support` 分类
- `activity-summary`、`elements`、`search`、`tree walker` 是否属于 Chat 前置能力

本文件只负责说明这些能力未来如何被 Host 侧 Chat 系统消费。
