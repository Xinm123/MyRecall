## 目标产物
- 新增一份 Markdown 文档，总结当前系统架构，重点解释“截图/图片的处理链路”和“检索链路（含关键词召回、向量召回、RRF 融合、可选 rerank）”。
- 文档会包含：流程图（Mermaid）、关键数据结构、关键配置项、失败/回退逻辑、以及主要代码入口的链接。

## 文档拟定路径与命名
- 建议新增：`/Users/tiiny/Test2/MyRecall/openrecall/docs/system_image_pipeline.md`
  - 如果仓库没有 `docs/`，会先创建目录。

## 文档内容结构（将写入 Markdown）
### 1. 系统组件与职责
- Client：截屏、buffer、上传、heartbeat
- Server：Flask API、DB、后台 Worker、模型 Provider 工厂
- DB：`entries` 主表 + `entries_fts`（FTS5）索引表

### 2. 图片处理（Ingestion & Processing）Pipeline（重点）
- 2.1 Client 侧：捕获截图 → 本地 buffer → `/api/upload`
- 2.2 Server API：保存 png 到 screenshots 目录；插入 `PENDING` entry（异步处理）
- 2.3 Worker：
  - OCR：图片 → `text`
  - Vision：图片 → `vision_description`（JSON 字符串，含 scene/actions/entities/description）
  - Memory Card：`build_memory_card(app,title,timestamp,ocr_text,vision_description)` → 结构化字段 + `embedding_text`
  - Text Embedding：对 `card.embedding_text` 生成 `entries.embedding`
  - MM Embedding：对图片生成 `entries.image_embedding`
  - DB 更新：`status=COMPLETED`；FTS upsert 写入“可读 description”（避免 UI 显示整段 JSON）
- 2.4 失败与回退：
  - OCR/Vision/Embedding/MM Embedding 任一失败时的 fallback（空文本/零向量）
  - “取消处理/恢复僵尸任务”的逻辑

### 3. 检索（Search & Retrieval）Pipeline（重点）
- 3.1 Grid（首页）展示数据流：
  - 初次渲染：`/` 路由序列化时对 `entry.description` 做 `extract_human_description`
  - 前端轮询更新：`/api/memories/latest`、`/api/memories/recent` 返回前同样做 `extract_human_description`（确保卡片底部只显示描述文本）
- 3.2 `/search` 端到端流程：
  - Query Parsing：识别时间表达式，限定候选集合（time range）
  - 候选集合截断：`hard_limit_recent_n`
  - 两路召回：
    - 向量召回（主路）：`mm.embed_text(q)` 与 `image_embedding` 相似度检索（CacheVectorBackend 优化）
    - 关键词召回（FTS）：`entries_fts MATCH q` + `bm25(entries_fts)` 排序
  - RRF 融合：`rrf_fuse([vec_ranked_ids, fts_ranked_ids], k=60)`
  - 兜底：若融合为空，用普通文本 embedding（`entries.embedding`）做 cosine similarity
  - 可选 Rerank：对 topN 候选构造 Memory Card 证据（scene/actions/entities/keywords/ui_text/time_bucket），可选附带 screenshot（data URL），再重排

### 4. 关键数据结构与字段说明
- `entries` 表字段：id/app/title/text/description/timestamp/embedding/image_embedding/status
- `entries_fts` 字段：entry_id/app/title/text/description（description 为“人类可读描述”）
- Memory Card：scene/actions/entities/keywords/ui_text/traceback/code/embedding_text/time_bucket

### 5. 关键配置项（与影响）
- `OPENRECALL_PRELOAD_MODELS`：启动时预加载 local 的 vision/embedding
- `OPENRECALL_MM_EMBEDDING_PROVIDER/MODEL_NAME`：多模态召回主通道的向量来源
- `OPENRECALL_OCR_PROVIDER`：OCR 选择（local/paddleocr/openai/dashscope）
- `OPENRECALL_HARD_LIMIT_RECENT_N`：候选集合截断
- `OPENRECALL_RERANK_*`：重排开关与带图上限

### 6. 常见故障模式与排障建议（简要）
- API base 非 OpenAI-compatible 导致 `/embeddings` 失败
- OCR provider 初始化/参数不兼容
- 端口占用、worker 队列/僵尸任务恢复

### 7. 附录：主要代码入口索引
- Worker、Search、FTS、RRF、Provider Factory、Memory Card、API endpoints 等

## 实施步骤（用户确认后执行）
1. 新建 `docs/system_image_pipeline.md` 并写入上述内容（含 Mermaid 流程图）。
2. 在文档中加入关键源码跳转链接（便于你在 IDE 里点开定位）。
3. 本地快速校验：检查 Markdown 渲染（Mermaid 语法、标题层级、链接格式）无误。

请确认是否按上述路径与结构生成 Markdown 文件。