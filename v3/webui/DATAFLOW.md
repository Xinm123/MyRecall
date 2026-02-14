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
    R8["Audio Dashboard: /audio (Phase 2.5)"]
    R9["Video Dashboard: /video (Phase 2.5)"]
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
    PA["Audio Dashboard APIs (Phase 2.5)\n/api/v1/audio/stats\n/api/v1/audio/chunks (+ device filter)\n/api/v1/audio/chunks/:id/file"]
    PV["Video Dashboard APIs (Phase 2.5)\n/api/v1/video/stats\n/api/v1/video/chunks\n/api/v1/video/chunks/:id/file\n/api/v1/video/frames"]
 end
 subgraph STORE["存储层 (Storage)"]
    S1["SQLite recall.db\nentries/video_chunks/frames/ocr_text"]
    S2["FTS 索引\nocr_text_fts / ocr_fts\naudio_transcriptions_fts"]
    S3["Server FS\nscreenshots/video_chunks/frames"]
    S4["Client FS\nbuffer/video_chunks"]
    S5["Server FS\naudio/*.wav"]
 end
 subgraph RET["检索层 (Retrieval)"]
    T1["页面展示: Grid/Timeline/Search"]
    T2["API 输出: /api/search /api/v1/search"]
    T3["帧服务: /api/v1/frames/:id"]
    T4["Audio Dashboard 展示 (Phase 2.5)"]
    T5["Video Dashboard 展示 (Phase 2.5)"]
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
    R8 --> PA
    R9 --> PV
    PA --> S1
    PA --> S5
    PV --> S1
    PV --> S3
    PA --> T4
    PV --> T5
    S1 --> T4
    S1 --> T5
    S5 --> T4
    S3 --> T5
```

## 2. 分层说明

### Request
- 页面请求来自浏览器：`/`、`/timeline`、`/search`。
- **Phase 2.5**：新增 `/audio` 和 `/video` dashboard 页面请求。
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
- Phase 1.5: Worker 管道新增 **metadata_resolver**（`app/window/focused/browser_url` 均按 `frame > chunk > null` 解析）和 **offset_guard**（帧-chunk 对齐预检验），在抽帧与帧写入之间执行；OCR 引擎名通过 `engine_name` 写入 `ocr_text.ocr_engine`。
- **Phase 2.5**：新增 Audio Dashboard APIs（`audio/stats`, `audio/chunks/:id/file`, extend `audio/chunks` with device filter）和 Video Dashboard APIs（`video/stats`, `video/chunks`, `video/chunks/:id/file`, `video/frames`），由新增 SQLStore 方法 `get_video_chunks_paginated()`、`get_frames_paginated()`、`get_video_stats()`、`get_audio_stats()` 驱动。

### Storage
- `recall.db`：页面核心数据来源（entries + video tables + audio tables）。
- FTS：文本检索索引来源（`ocr_text_fts`, `ocr_fts`, `audio_transcriptions_fts`）。
- Server FS：图片、视频分片、帧文件。
- **Phase 2.5**：新增 `audio/*.wav` 文件 serving 路径。
- Client FS：上传失败时缓冲。

### Retrieval
- Web 页面主要通过 server 渲染与 API 拉取展示结果。
- 搜索页可视化显示多阶段评分字段（debug 视角）。
- 帧服务支持"已存在文件直出 + 按需抽帧 fallback"。
- Phase 1.5: Timeline/Search 检索结果支持 `focused` (bool|null) 和 `browser_url` (string|null) 字段；`/api/v1/search` 中 video-frame 行返回真实值，snapshot 行返回 `null`（可选字段，兼容旧客户端）。
- Control Center 排障可配合 capture health 端点确认当前是 `monitor_id`、`legacy` 还是 `paused`。
- **Phase 2.5**：新增 Audio Dashboard（stats bar + chunk table + transcription browser + inline audio playback + queue status）和 Video Dashboard（stats bar + chunk table + frame gallery + inline video playback + queue status）。数据通过 SSR 注入 initial stats + Alpine.js client-side fetch 后续分页/过滤/刷新。

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
6. **Phase 2.5** Audio/Video Dashboard 降级：
   - 无 chunks 数据：显示友好空态提示（"No audio/video chunks recorded yet"）。
   - API fetch 失败：Error banner + auto-retry 10s。
   - 媒体文件缺失（WAV/mp4 不在 disk 上）：API 返回 404 JSON；playback UI 显示 "File not available" toast。
   - 大视频文件：`<video preload="metadata">` 避免自动下载。
   - DB 表不存在（fresh install）：SQLStore 方法 guard 返回 zeros / empty list。

### 4.1 Audio Dashboard 数据流（Phase 2.5）

```mermaid
flowchart TB
    subgraph Browser ["浏览器 /audio"]
        AUDIO_UI["Alpine.js audioDashboard()"]
        AUDIO_STATS["Stats Bar (4 cards)"]
        CHUNK_TABLE["Chunk Table (pagination + filter)"]
        TRANS_LIST["Transcription Browser (pagination + filter)"]
        QUEUE_BADGE["Queue Status Badges"]
        AUDIO_PLAYER["HTML5 Audio Player (sticky bottom bar)"]
    end

    subgraph API ["API Layer"]
        STATS_API["GET /api/v1/audio/stats"]
        CHUNKS_API["GET /api/v1/audio/chunks\n?status=&device="]
        TRANS_API["GET /api/v1/audio/transcriptions\n?start_time=&end_time=&device="]
        FILE_API["GET /api/v1/audio/chunks/:id/file"]
        QUEUE_API["GET /api/v1/queue/status"]
    end

    subgraph Storage ["Storage Layer"]
        DB[("SQLite\naudio_chunks +\naudio_transcriptions")]
        FS["Server FS\n~/MRS/audio/*.wav"]
    end

    AUDIO_UI --> STATS_API
    AUDIO_UI --> CHUNKS_API
    AUDIO_UI --> TRANS_API
    AUDIO_UI --> QUEUE_API
    AUDIO_PLAYER --> FILE_API

    STATS_API --> DB
    CHUNKS_API --> DB
    TRANS_API --> DB
    FILE_API --> FS
    QUEUE_API --> DB

    STATS_API --> AUDIO_STATS
    CHUNKS_API --> CHUNK_TABLE
    TRANS_API --> TRANS_LIST
    QUEUE_API --> QUEUE_BADGE
    FILE_API --> AUDIO_PLAYER
```

### 4.2 Video Dashboard 数据流（Phase 2.5）

```mermaid
flowchart TB
    subgraph Browser ["浏览器 /video"]
        VIDEO_UI["Alpine.js videoDashboard()"]
        VIDEO_STATS["Stats Bar (4 cards)"]
        VCHUNK_TABLE["Chunk Table (pagination + filter)"]
        FRAME_GALLERY["Frame Gallery (grid + modal)"]
        VQUEUE_BADGE["Queue Status Badges"]
        VIDEO_PLAYER["HTML5 Video Player (modal / inline)"]
    end

    subgraph API ["API Layer"]
        VSTATS_API["GET /api/v1/video/stats"]
        VCHUNKS_API["GET /api/v1/video/chunks\n?status=&monitor_id="]
        FRAMES_API["GET /api/v1/video/frames\n?chunk_id=&app=&window="]
        VFILE_API["GET /api/v1/video/chunks/:id/file"]
        FRAME_IMG["GET /api/v1/frames/:id\n(frame image)"]
        VQUEUE_API["GET /api/v1/queue/status"]
    end

    subgraph Storage ["Storage Layer"]
        VDB[("SQLite\nvideo_chunks +\nframes + ocr_text")]
        VFS["Server FS\n~/MRS/video_chunks/*.mp4"]
        FFS["Server FS\n~/MRS/frames/*.png"]
    end

    VIDEO_UI --> VSTATS_API
    VIDEO_UI --> VCHUNKS_API
    VIDEO_UI --> FRAMES_API
    VIDEO_UI --> VQUEUE_API
    VIDEO_PLAYER --> VFILE_API
    FRAME_GALLERY --> FRAME_IMG

    VSTATS_API --> VDB
    VCHUNKS_API --> VDB
    FRAMES_API --> VDB
    VFILE_API --> VFS
    FRAME_IMG --> FFS
    VQUEUE_API --> VDB

    VSTATS_API --> VIDEO_STATS
    VCHUNKS_API --> VCHUNK_TABLE
    FRAMES_API --> FRAME_GALLERY
    VQUEUE_API --> VQUEUE_BADGE
    VFILE_API --> VIDEO_PLAYER
```

## 5. 证据来源

- `/Users/pyw/new/MyRecall/openrecall/server/app.py`
- `/Users/pyw/new/MyRecall/openrecall/server/api.py`
- `/Users/pyw/new/MyRecall/openrecall/server/api_v1.py`
- `/Users/pyw/new/MyRecall/openrecall/server/templates/layout.html`
- `/Users/pyw/new/MyRecall/openrecall/server/templates/index.html`
- `/Users/pyw/new/MyRecall/v3/results/phase-1-post-baseline-changelog.md`

## 6. Phase 1.5 Evidence Matrix

| Change | Code Path | Test Command | Result | UTC Timestamp |
|---|---|---|---|---|
| Frame-level metadata flow uses resolver chain (`frame > chunk > null`) | `/Users/pyw/new/MyRecall/openrecall/server/video/metadata_resolver.py`, `/Users/pyw/new/MyRecall/openrecall/server/video/processor.py` | `python3 -m pytest tests/test_phase1_5_metadata_resolver.py -v` | 12 passed | 2026-02-08T07:50:52Z |
| Upload/process/retrieval flow carries `focused/browser_url` with null semantics | `/Users/pyw/new/MyRecall/openrecall/server/database/sql.py`, `/Users/pyw/new/MyRecall/openrecall/server/api_v1.py` | `python3 -m pytest tests/test_phase1_5_focused_browser_url.py -v` | 10 passed | 2026-02-08T07:50:52Z |
| Offset guard reject path observability in processing chain | `/Users/pyw/new/MyRecall/openrecall/server/video/processor.py` | `python3 -m pytest tests/test_phase1_5_offset_guard.py -v` | 8 passed | 2026-02-08T07:50:52Z |
| Full dataflow regression closure | `/Users/pyw/new/MyRecall/openrecall/server/video/metadata_resolver.py`, `/Users/pyw/new/MyRecall/openrecall/server/video/processor.py`, `/Users/pyw/new/MyRecall/openrecall/server/api_v1.py`, `/Users/pyw/new/MyRecall/openrecall/server/database/sql.py` | `python3 -m pytest tests/test_phase1_* -v` | 170 passed, 8 skipped | 2026-02-08T07:50:08Z |
