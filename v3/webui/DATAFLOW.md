# WebUI 全局数据流（Request -> Processing -> Storage -> Retrieval）

## 1. 主链路图

```mermaid
---
config:
  layout: dagre
---
flowchart LR
 subgraph REQ["请求层 (Request)"]
    R1["浏览器访问 / /timeline /search"]
    R2["Control Center: GET/POST /api/config"]
    R3["Search Query: /search?q=..."]
    R4["Client Heartbeat: POST /api/heartbeat"]
    R5["Client Upload: POST /api/upload 或 /api/v1/upload"]
    R6["Resume Check: GET /api/upload/status 或 /api/v1/upload/status"]
    R7["Capture Health: GET /api/vision/status 或 /api/v1/vision/status"]
 end
 subgraph PROC["处理层 (Processing)"]
    P1["Flask Router + Jinja 渲染"]
    P2["SearchEngine: vector + FTS + rerank"]
    P3["Runtime Settings 更新与广播"]
    P0["UploaderConsumer + HTTPUploader\n指数退避重试"]
    P5["Upload API Ingestion\n写入 PENDING entry/chunk"]
    P4["VideoProcessingWorker\nFrameExtractor\nRetentionWorker"]
    P6["Capture Health Builder\nruntime_settings -> vision status"]
    PF1["Fallback: upload 失败进入本地 buffer 重试"]
    PF2["Fallback: /api/v1/frames/:id 按需抽帧"]
 end
 subgraph STORE["存储层 (Storage)"]
    S1["SQLite recall.db\nentries/video_chunks/frames/ocr_text"]
    S2["FTS 索引\nocr_text_fts / ocr_fts"]
    S3["Server FS\nscreenshots/video_chunks/frames"]
    S4["Client FS\nbuffer/video_chunks"]
 end
 subgraph RET["检索层 (Retrieval)"]
    T1["页面展示: Grid/Timeline/Search"]
    T2["API 输出: /api/search /api/v1/search"]
    T3["帧服务: /api/v1/frames/:id"]
 end
    R1 --> P1
    R2 --> P3
    R3 --> P2
    R4 --> P3
    R5 --> P5
    R6 --> P0
    R7 --> P6
    P1 --> T1
    P2 --> T2
    P2 --> S1
    P2 --> S2
    P3 --> S1
    P6 --> S1
    P4 --> S1
    P4 --> S2
    P4 --> S3
    PF1 --> S4
    S4 --> P0
    P0 --> P5
    P5 --> S1
    P5 --> S3
    P5 --> P4
    T3 --> PF2
    P6 --> T1
    PF2 --> S3
    S1 --> T1
    S1 --> T2
    S2 --> T2
    S3 --> T1
    S3 --> T3
```

## 2. 分层说明

### Request
- 页面请求来自浏览器：`/`、`/timeline`、`/search`。
- 控制请求来自 Control Center：`GET/POST /api/config`。
- 心跳请求来自 client：`POST /api/heartbeat`，用于 UI 在线状态显示。
- 上传请求来自 client uploader：`POST /api/upload` 与 `POST /api/v1/upload`。
- 断点续传状态查询：`GET /api/upload/status` 与 `GET /api/v1/upload/status`。
- 采集健康诊断查询：`GET /api/vision/status` 与 `GET /api/v1/vision/status`。

### Processing
- Flask 路由层负责页面渲染与 API 转发。
- SearchEngine 负责检索融合与结果排序。
- Runtime settings 负责运行时开关一致性。
- Capture health builder 从 `runtime_settings` 生成只读诊断视图（`status/active_mode/last_sck_error_code/...`）。
- Upload API 负责接收截图/视频并写入 PENDING 记录，再交由 worker 处理。
- Worker 管道负责采集后数据处理（抽帧/OCR/清理），间接影响 WebUI 展示内容。

### Storage
- `recall.db`：页面核心数据来源（entries + video tables）。
- FTS：文本检索索引来源。
- Server FS：图片、视频分片、帧文件。
- Client FS：上传失败时缓冲。

### Retrieval
- Web 页面主要通过 server 渲染与 API 拉取展示结果。
- 搜索页可视化显示多阶段评分字段（debug 视角）。
- 帧服务支持“已存在文件直出 + 按需抽帧 fallback”。
- Control Center 排障可配合 capture health 端点确认当前是 `monitor_id`、`legacy` 还是 `paused`。

## 3. 关键子链路

### 3.1 Home Grid 增量刷新链路

```mermaid
sequenceDiagram
  participant UI as index.html
  participant API as /api/memories/latest + /api/memories/recent
  participant DB as SQLStore

  UI->>API: GET /api/memories/latest?since=lastCheck (5s)
  API->>DB: get_memories_since(since)
  DB-->>API: new entries
  API-->>UI: JSON list
  UI->>API: GET /api/memories/recent?limit=200 (5s)
  API->>DB: get_recent_memories(limit)
  DB-->>API: recent entries
  API-->>UI: JSON list
```

> 数据新鲜度说明：若上传处于退避重试阶段，Home Grid 的增量刷新会正常执行，但可见数据会延后出现。

### 3.2 Search 页面链路

```mermaid
sequenceDiagram
  participant Browser as /search?q=...
  participant App as app.py:search()
  participant SE as search_engine.search_debug()
  participant DB as SQL/FTS/Vector

  Browser->>App: GET /search?q=keyword
  App->>SE: search_debug(q, limit=50)
  SE->>DB: 混合召回+重排
  DB-->>SE: candidates + scores
  SE-->>App: debug entries
  App-->>Browser: render search.html
```

### 3.3 Timeline 帧回退链路

```mermaid
sequenceDiagram
  participant UI as Timeline/Search image_url
  participant API as /api/v1/frames/:id
  participant DB as SQLStore.get_frame_by_id
  participant FS as frames_path
  participant FE as FrameExtractor

  UI->>API: GET /api/v1/frames/{frame_id}
  API->>DB: 查询 frame 元信息
  API->>FS: 查找 {frame_id}.png
  alt 文件存在
    FS-->>API: png
    API-->>UI: 200 image/png
  else 文件不存在
    API->>FE: extract_single_frame(chunk_path, offset)
    FE-->>API: 临时帧文件
    API-->>UI: 200 image/png 或 404
  end
```

### 3.4 Capture 健康观测链路

```mermaid
sequenceDiagram
  participant Client as Client Recorder
  participant HB as POST /api/heartbeat
  participant RT as runtime_settings
  participant VS as GET /api(/v1)/vision/status
  participant UI as Control Center / 运维脚本

  Client->>HB: capture_mode + sck_available + last_sck_error + selected_monitors
  HB->>RT: update heartbeat/runtime state
  UI->>VS: read-only status query
  VS->>RT: build vision status
  VS-->>UI: status + active_mode + last_sck_error_code
```

## 4. 失效与降级路径（必须可解释）

1. 上传失败：client 将内容留在本地 buffer，后续经 UploaderConsumer 按退避策略重试上传到 API，再进入 worker 管道；WebUI 可见数据延迟更新。
2. 心跳中断：Control Center 显示 `Offline`，但页面可继续查看已有数据。
3. 帧文件缺失：`/api/v1/frames/:id` 尝试按需抽帧，失败才返回 404。
4. 搜索 debug 视频-only 场景：已在 Phase 1 修复渲染崩溃路径。
5. SCK 启动异常：client 先按短退避重试；达阈值后降级 legacy；若配置允许则周期性 probe 并自动回切 monitor-id。

## 5. 证据来源

- `/Users/pyw/new/MyRecall/openrecall/server/app.py`
- `/Users/pyw/new/MyRecall/openrecall/server/api.py`
- `/Users/pyw/new/MyRecall/openrecall/server/api_v1.py`
- `/Users/pyw/new/MyRecall/openrecall/server/templates/layout.html`
- `/Users/pyw/new/MyRecall/openrecall/server/templates/index.html`
- `/Users/pyw/new/MyRecall/v3/results/phase-1-post-baseline-changelog.md`
