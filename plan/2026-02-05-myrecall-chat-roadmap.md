# MyRecall v3.0 Chat（@yesterday 等）——跨机器架构 + Memory 体系（参考 OpenClaw）Roadmap

> **最后更新**：2026-02-05  
> **目标读者**：MyRecall v3.0 的维护者/开发者（端侧记忆系统：capture/index/search/timeline/chat）  
> **范围说明**：本文是 **Roadmap/技术方案**，用于指导后续实现；不包含业务代码改动。

---

## 0. 已确认前提（Decision Lock）

### 0.1 最终部署形态（Client ↔ Server）

- **Client**：运行在 **Mac**（负责采集/缓冲/上传）
- **Server**：运行在 **Debian 盒子**（负责落盘/处理/索引/检索/Chat）
- **访问方式**：同一局域网内，通过浏览器访问 **Server Web UI**（Timeline + Search + Chat）

### 0.2 隐私边界（原始数据落点）

- 截图/OCR 等原始数据允许 **Server 明文落盘**
- 隐私主要依赖：**磁盘加密/访问控制/最小暴露面**（不做端到端加密）

### 0.3 AI/LLM

- **本地优先**（Server 上运行本地/自建 OpenAI-compatible 推理服务）
- **可选远端**（OpenAI-compatible），**API Key 仅在 Server**（浏览器不持有 Key）

### 0.4 音频

- **第二阶段**纳入（第一阶段只做 screen OCR/vision 的闭环）

### 0.5 向量库

- 目标迁移到 **SQLite 向量扩展**（`sqlite-vec`/`sqlite-vss`）
- 迁移策略：**双写 + 渐进切换**（保留回滚）

### 0.6 Chat UI 形态

- `/timeline` 右侧可折叠 Chat 面板 + 独立 `/chat` 页面

---

## 1. 成功标准（Success Criteria）

### 1.1 用户体验（必须）

1. 在 Web UI 的 `/chat` 里输入：`@yesterday 总结一下我昨天做了什么`（若今天为 2026-02-05，则 yesterday=2026-02-04 本地自然日 00:00–23:59:59.999）
2. 系统输出结构化回答：
   - `### Overview`（一段）
   - `### Timeline`（按时间段列出）
   - `### Patterns`（3–6 条）
   - `### Next actions`（可选）
   - `### Sources`（可点击证据引用：时间戳 + app/window + 跳转到 timeline）
3. Chat 不会“把整库塞进 prompt”，而是通过 **tool-call 检索**按需取证据，并具备严格限额/截断/超时退避。

### 1.2 工程质量（必须）

- **跨机器健壮性**：断网不丢；重试不重复入库；时钟漂移可诊断；可观测性齐全（延迟/错误/队列/吞吐）
- **安全默认值**：Server 端鉴权；设备隔离；LLM key 不下放；最小暴露面（LAN 优先）

---

## 2. 关键差异：单机原型 → 跨机器（Mac Client ↔ Debian Server）

跨机后最常见故障不在算法，而在 **网络、鉴权、幂等、时钟、带宽与可观测性**。因此 Roadmap 把这些作为“数据层准备”的一等公民。

### 2.1 必需工程语义（必须落到协议/表结构/日志）

1. **离线不丢（Client）**
   - 继续使用磁盘 buffer（已存在），失败可重试/退避
2. **幂等与去重（Server）**
   - 上传可能重复：断点续传、网络抖动、Client 重启
   - 必须定义幂等键并在 DB 侧可审计冲突
3. **时间一致性**
   - 同时保存：
     - `client_ts`：活动发生时间（用于 timeline/search/summaries）
     - `server_received_at`：Server 收到时间（用于诊断延迟与漂移）
   - 必须支持“漂移估计”（例如近 N 条样本的 `server_received_at - client_ts` 分布）
4. **鉴权与设备隔离**
   - 至少 `device_id + token`；未来可扩展多 Mac、多用户
5. **最小暴露面**
   - LAN 内 HTTP 可先跑通，但必须为后续 TLS/反代预留位（不改变数据模型）

---

## 3. Memory 体系（参考 OpenClaw：把 Timeline 数据变成可检索资产）

参考链接（概念对齐）：`https://docs.openclaw.ai/concepts/memory`

### 3.1 Memory 的分层目标

- **Frame Memory（证据级）**：可溯源、可跳转、用于“你确定吗/给证据”
- **Episode Memory（RAG 主力）**：连续帧聚合成事件段，减少噪声与重复
- **Summary Memory（长时记忆）**：day/week 的 consolidation，稳定回答长时间范围（如“昨天做了什么”）

### 3.2 Memory 生命周期（写入→索引→检索→写回→遗忘）

1. 写入（Capture/Worker）
2. 索引（FTS + Vector）
3. 混合检索（Hybrid retrieval）
4. 写回 consolidation（DaySummary/WeekSummary、Pinned memory）
5. 遗忘/保留（Forget/Retention）：删除必须影响 FTS/Vector/引用关系，避免“幽灵记忆”

---

## 4. 数据建模（跨机器 + Memory + Chat 必需字段）

> 目标：让所有后续工作都能围绕稳定的数据契约推进；不在实现期反复改协议。

### 4.1 Client → Server 上传 metadata（扩展契约，Milestone M0 冻结）

在现有 `/api/upload` 的 metadata JSON 中增加（字段名固定，不再改）：

- `device_id`：字符串（设备唯一标识）
- `client_ts`：整数/浮点（epoch seconds，活动发生时间）
- `client_tz`：IANA 时区名（例如 `America/Los_Angeles`）
- `client_seq`：整数（单调递增序号，可选但推荐）
- `image_hash`：字符串（推荐 sha256；用于幂等/冲突诊断）
- `app_name`、`window_title`：沿用现有

Server 在入库时必须补齐：

- `server_received_at`：epoch seconds（服务端接收时间）

### 4.2 幂等键（默认推荐策略）

- 幂等键：`(device_id, client_ts, image_hash)`
- 语义：
  - 同幂等键重复上传：返回 202/200（idempotent ok）
  - `(device_id, client_ts)` 相同但 `image_hash` 不同：返回 409 + 记录冲突（用于排障与漂移诊断）

---

## 5. @mentions 与“时间语义”规范（Chat 与检索共用）

### 5.1 第一阶段必须支持的 mentions

- 时间：
  - `@today`：本地日 00:00 → now
  - `@yesterday`：本地“上一自然日”00:00 → 23:59:59.999
  - `@last-hour`：now-60min → now
  - `@last-week`：now-7d → now
  - `@range(ISO_START,ISO_END)`：显式范围（高级/调试）
- 内容类型：
  - `@screen`/`@ocr`（第一阶段）
  - `@audio`（第二阶段启用）
  - `@input`（未来 UI events）
- app：
  - `@app:chrome`（推荐规范）
  - 兼容 alias：`@chrome`、`@vscode`（映射表）
- selection：
  - `@selection`：由 timeline 选择范围注入；无选择时忽略并提示

### 5.2 自然语言时间兼容（中文）

用户不写 `@yesterday`，但输入包含“昨天/今天/上周/最近一小时”等时：

- 解析出确定的 time range（tz-aware）
- 在 UI 显示为可编辑 filters chips（最终范围锁定，避免“模型自己猜”）

---

## 6. 检索链路（RAG 的“强约束工具化检索”）

### 6.1 工具白名单（第一阶段）

- `search_content`（核心：从 Memory/索引中取证据片段）
- `memory_get`（按 refs 批量取 snippet + sources）
- `get_day_summary`（若存在则优先）
- `get_frame`（用于证据引用：图片路径/时间戳/app/window 等元数据）

### 6.2 `search_content` 强约束（必须写进 system prompt + server guard）

- `start_time` **必填**（无则 server 补默认 last 2 hours，并在 UI 显示）
- `limit`：
  - 默认 8
  - 上限 12（超过 clamp）
- 截断：
  - 单条结果文本：400 chars
  - 总 tool_result：10k chars
- 超时：30s
  - 自动缩窗重试（2h → 60m → 30m）
  - 最多 2 次
- 返回必须包含可引用字段：
  - `start_ts/end_ts`（或单点 ts）
  - `app/window`
  - `source_frame_ts[]`（或 frame ids）
  - `screenshot_path`（或用于跳转 timeline 的定位 key）

### 6.3 Context packing（固定规则，避免上下文爆炸）

默认顺序：

1. Summary Memory（范围大/命中 day_summary 时优先）
2. Episode Memory（topK）
3. Frame Memory（只用于 sources 引用与少量关键证据）

---

## 7. 向量存储迁移（LanceDB → sqlite-vec/sqlite-vss）

### 7.1 迁移节奏（不留决策）

1. 阶段 A：引入 SQLite 向量扩展，建立新表；开始 **双写**（LanceDB + sqlite-vec）
2. 阶段 B：读路径灰度
   - 开关：`VECTOR_BACKEND={lancedb|sqlite_vec}`
   - 例行对比：TopK overlap、延迟、失败率（按天/按 app 分层统计）
3. 阶段 C：默认切主读到 sqlite-vec；LanceDB 保留回滚窗口
4. 阶段 D：停用 LanceDB 写入并提供清理/导出方案

### 7.2 一致性验收指标（量化）

- 抽样 query ≥ 200：
  - Top10 overlap ≥ 0.7（按天/按 app 分层）
  - p95 检索延迟不高于 LanceDB +20%
  - 维度不匹配/查询异常：0

---

## 8. UI/UX 交互（Web UI：/chat + timeline panel）

### 8.1 `/chat` 页面（第一阶段必须）

- Conversation 列表（最近、可搜索）
- 消息流（支持 streaming）
- 输入框：
  - `@` 提示（时间/内容类型/app/selection）
  - filters chips（可编辑 time/app/type）
- 每条 assistant 消息下展示 `Sources`（可折叠）

### 8.2 `/timeline` 右侧折叠 Chat 面板（第一阶段必须）

- Timeline 顶部范围控件：
  - Today / Yesterday / Last hour
  - start/end 手动输入（最小可用）
- `Ask about this range`：
  - 一键将 selection_range 注入 Chat（等价 `@selection`）

### 8.3 `/search` → Chat Prefill（第一阶段必须）

- 结果卡片新增 “Ask in Chat”
- Prefill 内容固定格式（便于模型稳定引用）：
  - `[time] [app/window]`
  - `caption`
  - `ocr_head`
  - `timestamp / screenshot_path`

---

## 9. Roadmap（四维度拆解 + Milestones）

> 四维度：**数据层准备 / 检索链路优化 / LLM 接入 / UI/UX 交互**  
> 每个里程碑必须有：明确产出 + 验收标准。

### Milestone M0（Sprint 0）：跨机器契约冻结（Transport/Auth/Time）

**数据层准备**
- 冻结上传 metadata 扩展字段（device_id/client_ts/client_tz/client_seq/image_hash）
- 冻结幂等与冲突语义（见 4.2）
- 冻结鉴权策略：
  - `Authorization: Bearer <device_token>`
  - token 轮换机制（双 token 并存窗口）

**检索链路优化**
- 所有检索与 tool-call 路由必须支持 `device_id` 过滤（未来多 client）

**LLM 接入**
- 确认：LLM provider 配置全部在 Server；浏览器不持有 key

**UI/UX**
- 设备状态面板规划（不一定实现）：
  - 最近心跳、队列积压、漂移估计、失败原因 topN

**验收产出**
- 《跨机 API 契约 + 鉴权/幂等/时间语义》章节写入本文
- yesterday 示例固定：若今天为 2026-02-05，则 yesterday=2026-02-04 本地自然日

---

### Milestone M1（Sprint 1–2）：Memory 数据模型落地（Episode/Summary 先于 Chat）

**数据层准备**
- Episode Memory 生成规则落地（确定性切段 + OCR 去重 + episode_summary）
- DaySummary 任务骨架（离线/按需触发即可）
- 引入 sqlite-vec/sqlite-vss：建表 + 双写启动

**检索链路优化**
- 增加 memory 检索入口（供未来 Chat tool-call 使用）：
  - `memory_search(filters...)`：time/app/type + hybrid（vec+fts）→ refs
  - `memory_get(refs...)`：批量取 snippet + sources
- 默认 hybrid 公式（可配置）：
  - `score = 0.55*vec_sim + 0.45*keyword_score`
  - `score *= recency_boost(0.9~1.1)`
  - `score *= importance_boost(1.0~1.5)`

**LLM 接入**
- 用最小 LLM 能力生成 episode_summary（本地优先）
- embedding cache 设计（按 `text_hash + embedding_model`）

**UI/UX**
- `/timeline` 增加范围选择控件（Today/Yesterday/Last hour + start/end）
- `/search` “Ask in Chat” 仅先实现跳转 + prefill 参数传递

**验收**
- 任意一天：EpisodeChunks 可生成并可检索；DaySummary 可生成并入库
- sqlite-vec 双写不影响现有 LanceDB 搜索；维度一致

---

### Milestone M2（Sprint 3–4）：Chat tool-call（RAG 闭环）最小可用

**数据层准备**
- Conversation/Message 存储（含 filters、tool-call trace、sources refs、模型信息）

**检索链路优化**
- 定义并实现 `search_content` 工具语义（见 6.2，强约束）
- Context packing 固定（Summary→Episode→Frame）

**LLM 接入**
- Server 代理 streaming（SSE 优先）
- system prompt 固化：
  - 只能使用 sources；需要更多信息必须 tool-call
- 工具白名单与参数校验：
  - 拒绝无时间范围、超大 limit、越权 device_id

**UI/UX**
- `/chat` 页面上线：
  - @mentions 下拉 + filters chips
  - Sources 列表可跳转 `/timeline`
- `/timeline` 右侧折叠 Chat 面板：
  - “Ask about this range” 注入 selection_range

**验收**
- `@yesterday 总结一下我昨天做了什么`：
  - 稳定输出结构化总结 + ≥10 条可跳转 sources
  - 检索过程始终受限额/截断/超时退避保护

---

### Milestone M3（Sprint 5–6）：长时记忆强化（Consolidation 写回 + 稳定长范围）

**数据层准备**
- DaySummary 自动化：
  - 每日定时/首次查询触发生成
  - summary 入 FTS + 向量（可第一跳命中）
- Forgetting/Retention：
  - 按天/按 app 删除（同时清理 FTS/vec/refs）
  - Pin memory（importance 提升）

**检索链路优化**
- 大范围问答默认分层：Summary → Episode → Frame
- embedding cache 完整落地；模型切换时重建策略

**LLM 接入**
- 固定模板：
  - Daily Review（昨日总结）
  - Worklog（按 app/主题聚合）
- 远端模式默认脱敏（regex + 可配置）；UI 明确开关

**UI/UX**
- Chat 操作：
  - Save as Memory / Pin / Forget
  - 展示本次回答使用了哪些 summary/episode（可折叠）

**验收**
- 连续两天使用：第二天问昨天可优先命中 day_summary（更快更稳），追问可下钻并引用证据

---

### Milestone M4（Sprint 7+）：音频转写纳入（第二阶段）

**数据层准备**
- Audio capture + VAD chunk + STT → AudioEpisodeChunk（先不做 speaker）
- 与 timeline 对齐（每段有 start/end，可与 OCR Episode 重叠）

**检索链路优化**
- `content_type=audio` + 时间合并检索
- “昨日总结”自动合并会议/通话摘要

**LLM 接入**
- Meeting summary 模板（决策/行动项/参与者）

**UI/UX**
- Sources 支持音频片段引用（先文本+时间，播放器后置）

**验收**
- `@yesterday` 总结可包含会议/通话要点，并支持 audio-only 过滤追问

---

## 10. 必须写清楚的接口（为跨机与 tool-call 准备）

### 10.1 跨机基础接口（Client → Server）

- `POST /api/heartbeat`
  - 上报：`device_id`, `client_ts`, `queue_depth`, `last_error`
  - 下发：`recording_enabled`, `upload_enabled`, `server_capabilities`（例如 chat enabled、vector backend）
- `POST /api/upload`
  - header：`Authorization: Bearer <device_token>`
  - body：image + metadata（见 4.1）

### 10.2 Chat/Memory 接口（Browser → Server）

- `POST /api/chat/stream`（SSE）
- `GET /api/chat/conversations`
- `POST /api/chat/conversations`
- `GET /api/memory/search`（供 UI 调试，也供 tool-call 内部复用）
- `GET /api/memory/get`

---

## 11. 安全清单（跨机默认必须具备）

- 认证：每设备 token；最小权限（只能访问自己的 device_id 数据）
- 传输：LAN 内可先 HTTP，但必须为反代 TLS（Nginx/Caddy）预留位；跨公网时使用隧道（可选项）
- 限流：upload 与 chat/tool-call 分开限流（避免 chat 影响摄入）
- 日志：默认不记录原始 OCR 全文；仅记录 hashes、ref ids、性能指标（可配置 debug）
- Server 落盘：Debian 盒子使用磁盘加密/加密卷；备份与恢复演练作为后续里程碑

---

## 12. 默认值（实现时不再做决策）

- `@yesterday`：用户本地时区上一自然日 00:00:00–23:59:59.999（例如 2026-02-05 → 2026-02-04）
- tool `search_content`：
  - 默认范围：last 2 hours（除非显式 @today/@yesterday/@range）
  - limit：默认 8，上限 12
  - 截断：单条 400 chars，总 10k chars
  - 超时：30s；缩窗重试最多 2 次（2h→60m→30m）
- Hybrid 权重：`0.55*vec + 0.45*keyword`（importance/recency 作为可配置乘子）
- LLM key：只在 Server；浏览器永不持有 key

