# OpenRecall 系统分析（图片处理与检索 Pipeline）

本文聚焦两件事：
- 截图（图片）从产生到入库再到可检索的完整处理链路
- 检索（Grid 展示 + /search 检索）端到端的召回、融合与重排逻辑

文档基于仓库当前实现整理，关键代码入口见文末“源码索引”。

---

## 1. 系统组件与职责

### 1.1 Client（截图采集与上传）
- 负责周期性截屏（Producer）与上传（Consumer）
- 支持本地 buffer：当 server 不可用时先落盘，恢复后补传
- 关键入口：`python -m openrecall.client`

### 1.2 Server（API + DB + Worker）
- Flask API：
  - 接收截图上传（快速入队，不在请求内做 AI）
  - 提供 Grid 与检索页面，以及前端轮询接口
- DB（SQLite）：
  - `entries` 主表：存任务状态、OCR 文本、VL 描述、向量等
  - `entries_fts` 虚拟表：FTS5 全文检索索引
- Worker（后台线程）：
  - 从 `PENDING/PROCESSING` 状态队列中取任务，执行 OCR / Vision / Embedding / MM Embedding
  - 写回 DB 与 FTS

---

## 2. 图片处理 Pipeline（采集 → 入库 → 异步处理）

### 2.1 总览（Mermaid）

```mermaid
flowchart LR
  subgraph Client[Client]
    C1[定时截屏] --> C2[本地 buffer]
    C2 --> C3[POST /api/upload]
  end

  subgraph Server[Server]
    S1[接收 upload] --> S2[保存 screenshots/<ts>.png]
    S2 --> S3[DB 插入 entries: PENDING]
    S3 --> W1[Worker 取任务并标记 PROCESSING]
    W1 --> O1[OCR: image -> text]
    W1 --> V1[Vision: image -> vision_description(JSON/回退文本)]
    O1 --> M1[Memory Card 构造]
    V1 --> M1
    M1 --> E1[Text Embedding: embedding_text -> embedding]
    W1 --> ME1[MM Embedding: image -> image_embedding]
    E1 --> S4[DB 写回: text/description/embedding/image_embedding, status=COMPLETED]
    ME1 --> S4
    S4 --> FTS[FTS upsert: text + 人类可读 description]
  end
```

### 2.2 关键数据落点（entries 表）
- `screenshots/<timestamp>.png`：原始截图文件
- `entries.text`：OCR 结果（可能为空）
- `entries.description`：Vision 输出的原始字符串（通常是 JSON 文本；解析失败则为普通文本）
- `entries.embedding`：对 Memory Card 的 `embedding_text` 生成的文本向量（固定维度）
- `entries.image_embedding`：对图片生成的多模态向量（用于主召回）
- `entries.status`：`PENDING / PROCESSING / COMPLETED / FAILED / CANCELLED`

补充：`entries_fts`（FTS5 虚拟表）用于关键词召回，字段为 `entry_id/app/title/text/description`，其中 `description` 会写入“人类可读描述”（优先 vision JSON 的 `description` 或 `scene`），而不是整段 JSON。

### 2.3 API 入队：为什么 upload 很快

`POST /api/upload` 的设计是“Fire-and-Forget”：
- 请求内只做：保存 PNG + 插入 `entries(status='PENDING')`
- 不在请求内做 OCR/Vision/Embedding，避免首包超时与阻塞

upload 请求载荷（JSON）是“扁平化 numpy array”：
- `image`: 扁平数组（list）
- `shape`: 原始 shape（list）
- `dtype`: numpy dtype 名
- `timestamp`: unix 秒级时间戳
- `active_app` / `active_window`: 活动应用/窗口标题

响应是 202 Accepted，返回 `task_id`（entry_id）。

实现参考：
- upload handler：[api.py:L141-L232](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/api.py#L141-L232)
- 入队写库（PENDING）：[database.py:L270-L308](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/database.py#L270-L308)

### 2.4 Worker 细节（OCR → Vision → Memory Card → 向量写回）

Worker 的单条任务处理核心是：
1) OCR：`ocr_provider.extract_text(image_path)` → `text`
2) Vision：`ai_provider.analyze_image(image_path)` → `vision_description`
3) Memory Card：`build_memory_card(app,title,timestamp,ocr_text,vision_description)` → 结构化字段 + `embedding_text`
4) Text Embedding：`embedding_provider.embed_text(card.embedding_text)` → `entries.embedding`
5) MM Embedding：`mm_embedding_provider.embed_image(image_path)` → `entries.image_embedding`
6) DB 写回：
   - `entries.description` 存原始 `vision_description`（通常是 JSON）
   - FTS 写入“人类可读的描述”（避免 UI 显示 JSON）

#### 2.4.1 状态机（PENDING/PROCESSING/COMPLETED/FAILED/CANCELLED）

状态流转（简化）：
- `PENDING`：upload 插入后等待 worker
- `PROCESSING`：worker 取到任务后标记（用于“崩溃恢复/取消处理”）
- `COMPLETED`：成功写回 text/description/embedding/image_embedding
- `FAILED`：图片缺失或不可恢复错误
- `CANCELLED`：运行中关闭 AI processing 或切换版本，软取消当前处理

崩溃恢复：
- server 启动时会把上次 session 卡在 `PROCESSING` 的任务重置回 `PENDING`（避免僵尸任务永远不再处理）。

实现参考：
- Worker 主循环（FIFO/LIFO + 标记 PROCESSING）：[worker.py:L73-L168](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/worker.py#L73-L168)
- 单任务处理（OCR/Vision/写回）：[worker.py:L181-L329](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/worker.py#L181-L329)
- 状态写库：`reset_stuck_tasks/mark_task_processing/mark_task_completed/mark_task_failed`：[database.py:L506-L648](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/database.py#L506-L648)

#### 2.4.2 向量维度与归一化（为什么能混用不同 provider）

系统在多处统一了“向量形状与数值域”：
- 固定维度：所有 embedding 都会被裁剪/补零到 `settings.embedding_dim`
- L2 归一化：向量召回阶段使用内积（dot），归一化后等价 cosine

其中向量召回后端（CacheVectorBackend / SQLiteVSSBackend）在 upsert/query 时都会做 `_fit_dim` + `_l2_normalize`，保证不同来源的向量能进入同一检索流程。

实现参考：
- 向量维度对齐与归一化：[vector_backend.py:L11-L65](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/vector_backend.py#L11-L65)
- SQLiteVSS 查询将 `distance` 取负作为“相似度”返回：[vector_backend.py:L110-L142](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/vector_backend.py#L110-L142)

### 2.4 为什么引入 Memory Card（避免 OCR 淹没“场景信号”）

直接把 `OCR全文 + 视觉描述` 拼成 embedding 输入的风险：
- OCR 往往很长（尤其 IDE/日志/代码），容易让向量只学到“代码相似”，而不是“你在做什么”
- 视觉描述与 OCR 的权重不可控（文本越长，场景越容易被稀释）

Memory Card 的策略是把截图归纳成“回忆线索”：
- 主干：`scene/actions/entities/keywords/ui_text/time_bucket`
- 附加证据（可选、强截断）：`traceback/code`
- 生成统一长度上限的 `embedding_text`，用于 Text Embedding

#### 2.4.3 Memory Card 的“证据分层”与可控长度

Memory Card 的目的不是复刻截图全部文字，而是构造“可回忆”的特征集合：
- `scene`：默认优先使用 vision JSON 的 `description`（人类可读）；若缺失再用 `scene` 字段；最后回退原始文本
- `actions/entities/keywords/ui_text`：用于增强检索/重排的判别证据
- `traceback/code`：只在检测到“足够像”时才加入，并强截断（避免 IDE/日志场景被 OCR 长文本带偏）

最终产出：
- `embedding_text`：用于 Text Embedding（`entries.embedding`）
- 字段化证据：用于 rerank（如果开启）

### 2.5 Provider 选择与配置优先级（Vision/OCR/Embedding/MM Embedding）

系统通过 provider factory 选择具体实现，基本规则是：
- Vision：`vision_provider` 优先，其次 `ai_provider`
- OCR：`ocr_provider` 优先，其次 `ai_provider`
- Text Embedding：`embedding_provider` 优先，其次 `ai_provider`
- MM Embedding：`mm_embedding_provider` 独立配置（默认 `api`），失败会回退“全零向量 provider”

重要影响：
- 你可以把 `mm_embedding` 单独切到本地（例如 Qwen3-VL-Embedding），同时 Vision/Embedding/OCR 继续用 local 或 API。
- 任一 provider 初始化失败不会让系统整体崩掉（会回退空文本/零向量），但对应能力会弱化（例如向量召回不再有效）。

实现参考：
- provider 配置解析与 mm_embedding fallback：[ai/factory.py:L39-L196](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/ai/factory.py#L39-L196)

### 2.6 向量与字段在 DB 中的序列化方式

SQLite 不直接存 numpy 数组，写入时会做：
- `embedding.astype(np.float32).tobytes()` 写入 BLOB
- `image_embedding.astype(np.float32).tobytes()` 写入 BLOB

读取时由 Pydantic/模型层反序列化（并在检索后端再次做维度对齐与归一化）。

---

## 3. 检索 Pipeline（Grid 展示 + /search 召回/融合/重排）

### 3.1 Grid（首页）卡片底部为何只显示 description

现状：`entries.description` 在 DB 里可能是 Vision JSON 字符串。为了避免 Grid 卡片底部直接显示整段 JSON：
- 首次渲染 `/` 路由会对 `entry.description` 执行 `extract_human_description`，只取 JSON 中的 `description`（优先）或 `scene`
- 前端轮询接口 `/api/memories/latest`、`/api/memories/recent` 也会在返回前执行同样的提取

效果：
- UI 卡片底部展示的是“自然语言描述”
- DB 仍保留原始 JSON（用于更强的检索/重排证据）

实现参考：
- 首页首次渲染时提取可读描述：[app.py:L54-L83](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/app.py#L54-L83)
- 轮询接口返回前提取可读描述：[/api/memories/latest](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/api.py#L43-L68)、[/api/memories/recent](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/api.py#L70-L95)
- JSON→可读描述提取：[extract_human_description](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/memory_card.py#L31-L41)

### 3.2 /search 的端到端流程（重点）

```mermaid
flowchart TB
  Q[用户输入 q] --> P[时间解析/清洗]
  P --> C[生成候选集合 entries\n(按时间过滤 + recent hard limit)]
  C --> V[向量召回\nmm.embed_text(q) vs image_embedding]
  C --> F[FTS 关键词召回\nentries_fts MATCH q]
  V --> R[RRF 融合]
  F --> R
  R --> Z{融合结果为空?}
  Z -->|是| FB[兜底：text embedding cosine\n(get_embedding vs entries.embedding)]
  Z -->|否| OUT[候选排序输出]
  OUT --> RR{rerank_enabled?}
  RR -->|否| UI[渲染 search.html\n并生成 reasons/snippet]
  RR -->|是| RR2[对 topN 构造 Memory Card 证据\n可选附带截图 data URL]
  RR2 --> UI
```

#### 3.2.1 候选集合与时间过滤
- 支持从 query 中解析自然语言时间范围（如“昨天下午”），从而减少检索范围
- 支持 `hard_limit_recent_n`：只保留最近 N 条，避免全量扫描

实现参考：
- 时间解析：`parse_time_range/split_query`：[query_parsing.py:L50-L147](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/query_parsing.py#L50-L147)

#### 3.2.2 两路召回（Recall）

向量召回（主路）：
- 计算 query 向量：`mm.embed_text(q)`
- 与每条 entry 的 `image_embedding` 做相似度检索
- 对 CacheVectorBackend 做了 bulk_upsert 的优化路径（减少频繁写入）

向量召回的两个后端：
- CacheVectorBackend：内存字典 + `mat @ q` 计算（简单、无需扩展）
- SQLiteVSSBackend：sqlite_vss 扩展的 ANN 检索（如果可用）

关键词召回（FTS）：
- SQLite FTS5：`entries_fts MATCH ?`
- 使用 `bm25(entries_fts)` 排序（小值更相关）
- 索引内容来自：`app/title/text/description(可读描述)`

FTS 的关键特性：
- 强“字面命中”：人名、域名、按钮文案、错误类型、路径等
- 弱“同义/语义”：同义表达必须依赖向量召回或 rerank

实现参考：
- /search 主逻辑（候选、两路召回、RRF、fallback、rerank、reasons）：[app.py:L93-L323](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/app.py#L93-L323)
- 向量后端选择与实现：`CacheVectorBackend/SQLiteVSSBackend`：[vector_backend.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/vector_backend.py)
- FTS 查询（MATCH + bm25）：[database.py:L129-L151](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/database.py#L129-L151)

#### 3.2.3 RRF 融合（Reciprocal Rank Fusion）
RRF 用名次融合多路结果，不依赖不可比的 raw score。
- 每条 doc 的融合分数：`sum_i 1/(k + rank_i)`
- 默认 `k=60`，使 top1 与 top10 的差距更平滑

实现参考：
- RRF 实现：[fusion.py:L4-L18](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/fusion.py#L4-L18)

#### 3.2.4 兜底（Fallback）
当两路召回融合后为空：
- 使用普通文本 embedding（`entries.embedding`）做 cosine similarity 排序
- 这条路依赖 Worker 入库时写入的 `entries.embedding`

设计意图：
- 主路是“以文搜图”（q 的 mm 向量对齐 image_embedding）
- 兜底是“以文搜回忆卡片”（q 的 text embedding 对齐 card.embedding_text）

#### 3.2.5 可选 Rerank（证据增强）
开启 rerank 后，对 topN 候选重排：
- 每条候选构造 Memory Card 证据字段：
  - `scene/actions/entities/keywords/ui_text/time_bucket`
  - 以及保留 `text/description/description_text`
- 可选附带截图（data URL base64），并在 reranker 内自动切换到“逐条多模态打分”

#### 3.2.6 结果解释（reasons/tags/snippet）

`/search` 会为每条 entry 生成可解释信息：
- `tags`：是否来自 `FTS`（关键词）与 `Vec`（语义）通道
- `snippet`：从 `(OCR text + 可读 description)` 拼接文本中截取窗口，并对 query 的若干关键词做高亮

这部分主要用于 UI 展示“为什么这条被召回/排序靠前”。

实现参考：
- tags/snippet 生成（关键词高亮 + reasons）：[app.py:L280-L323](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/app.py#L280-L323)

---

## 4. 关键配置项（与影响）

### 4.1 性能相关
- `OPENRECALL_PRELOAD_MODELS`：启动时预加载本地 vision/embedding（减少首任务延迟）
- `OPENRECALL_HARD_LIMIT_RECENT_N`：限制检索候选规模
- `OPENRECALL_PROCESSING_LIFO_THRESHOLD`：队列积压时切换 LIFO/FIFO（更偏向“最新截图优先”）

### 4.2 模型相关
- `OPENRECALL_VISION_PROVIDER / OPENRECALL_VISION_MODEL_NAME`
- `OPENRECALL_EMBEDDING_PROVIDER / OPENRECALL_EMBEDDING_MODEL_NAME`
- `OPENRECALL_MM_EMBEDDING_PROVIDER / OPENRECALL_MM_EMBEDDING_MODEL_NAME`
- `OPENRECALL_OCR_PROVIDER`

### 4.3 Rerank（可选）
- `OPENRECALL_RERANK_ENABLED`
- `OPENRECALL_RERANK_TOPK`
- `OPENRECALL_RERANK_INCLUDE_IMAGE`
- `OPENRECALL_RERANK_IMAGE_TOPK`

### 4.4 建议配置组合（按“图片检索优先”）

如果重点是“以文搜图/搜截图语义”，建议至少确保：
- `OPENRECALL_MM_EMBEDDING_PROVIDER` 可用（本地或 API）
- Worker 端能成功写入 `entries.image_embedding`（否则向量召回会大量退化为 0 向量）

在 API 不稳定/不兼容时，最稳组合是：
- Vision=local、Embedding=local、OCR=local、MM Embedding=local

---

## 5. 失败与回退策略（关键“不中断”设计）

- OCR 失败：`text=""`（继续走 Vision 与 embedding）
- Vision 失败：`vision_description=""`（仍可用 OCR + 结构化抽取）
- Text Embedding 失败：写入零向量（避免 DB 写回失败）
- MM Embedding 失败：写入零向量（向量召回会弱化，但系统仍可用 FTS/兜底）
- 运行中可取消 AI 处理：通过 runtime settings 版本号实现软取消
- Server 启动会恢复上次 session 的“僵尸任务”（PROCESSING → PENDING）

---

## 6. 源码索引（主要入口）

### 6.1 图片处理链路
- Client 入口：[client/__main__.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/client/__main__.py)
- 上传 API：[api.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/api.py)（`/api/upload`）
- Worker 核心：[worker.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/worker.py)
- Provider 工厂：[ai/factory.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/ai/factory.py)
- Providers 实现：[ai/providers.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/ai/providers.py)
- Memory Card：[memory_card.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/memory_card.py)
- DB 与 FTS：[database.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/database.py)
- 向量后端：[vector_backend.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/vector_backend.py)

### 6.2 检索链路
- Grid：首页：[app.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/app.py)（`/`）
- Grid 轮询接口：[api.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/api.py)（`/api/memories/latest`、`/api/memories/recent`）
- Search：[app.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/app.py)（`/search`）
- FTS：[database.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/database.py)（`fts_search`）
- RRF：[fusion.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/fusion.py)（`rrf_fuse`）
