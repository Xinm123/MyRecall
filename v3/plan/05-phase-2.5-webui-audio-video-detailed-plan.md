# Phase 2.5 Detailed Plan — WebUI Audio & Video Dashboard Pages

**Phase**: 2.5 (WebUI Dashboard Pages: `/audio` and `/video`)
**Version**: 1.0
**Status**: Executed (Historical Plan)
**Scope Type**: historical
**Timeline**: 5 working days (Executed 2026-02-12)
**Owner**: Solo Developer
**Authority**: `/Users/pyw/newpart/MyRecall/v3/metrics/phase-gates.md`（gate 阈值唯一权威来源）
**ADR References**: ADR-0001 (Python-first), ADR-0002 (Thin client, remote-first API)
**Prerequisites**: Phase 2.0 Engineering Complete（15/17 gates PASS, 477 tests pass）
**Validation Report**: `/Users/pyw/newpart/MyRecall/v3/results/phase-2.5-validation.md`

---

> Historical note: `/audio` dashboards and APIs are preserved for operations/inspection, but audio expansion remains frozen under ADR-0005.

## 1. Goal / Non-Goals

### Goal

交付两个新的 WebUI Dashboard 页面（`/audio` 和 `/video`），为 audio 和 video 管道提供运营可视化能力。每个页面包含：chunk 列表（分页 + 过滤）、inline 媒体播放（HTML5 player）、内容浏览（transcriptions / frames）、处理队列状态、和聚合统计信息。同时交付驱动这些页面所需的最小 backend API endpoints（file serving, statistics, video chunk/frame listing）。

### Non-Goals

1. **新增处理管线** — 本阶段仅 WebUI + API，不改动 recording、transcription、OCR 等处理逻辑。
2. **实时 streaming 播放** — 播放为文件加载模式（HTML5 `<audio>` / `<video>` 加载完整文件），不做 chunked streaming。
3. **波形可视化** — 不做 audio waveform rendering，使用浏览器原生 audio controls。
4. **帧级视频 scrubbing** — 视频播放为整个 mp4 chunk，不做 frame-accurate seeking。
5. **Dashboard 内搜索** — `/audio` 和 `/video` 为运营 dashboard；搜索功能保留在 `/search`。
6. **新 DB migrations** — 不做 schema 变更；所有查询数据已存在于当前 schema。
7. **认证执行** — Auth 保持 placeholder decorator（`@require_auth` pass-through），per Phase 0 design。
8. **Speaker ID 展示** — `speaker_id` 在 Phase 2.0 中始终为 NULL，不做 UI 展示。

---

## 2. Scope (In / Out)

### In Scope

| Area | Deliverable |
|------|-------------|
| **New API: Video chunks** | `GET /api/v1/video/chunks` — 分页列表，支持 status/monitor_id 过滤 |
| **New API: Video frames** | `GET /api/v1/video/frames` — 分页列表，支持 chunk_id/app/window/time 过滤 |
| **New API: Video file serving** | `GET /api/v1/video/chunks/<id>/file` — 提供 mp4 文件供 HTML5 `<video>` 播放 |
| **New API: Audio file serving** | `GET /api/v1/audio/chunks/<id>/file` — 提供 WAV 文件供 HTML5 `<audio>` 播放 |
| **New API: Video stats** | `GET /api/v1/video/stats` — 聚合统计 (chunk count, frame count, duration, storage) |
| **New API: Audio stats** | `GET /api/v1/audio/stats` — 聚合统计 (chunk count, transcription count, duration, storage) |
| **Extend API: Audio chunks** | `GET /api/v1/audio/chunks` — 新增 `device` 过滤参数（additive，不破坏已有行为） |
| **New SQLStore methods** | `get_video_chunks_paginated()`, `get_frames_paginated()`, `get_video_stats()`, `get_audio_stats()` |
| **Flask route: `/audio`** | SSR dashboard 页面 + Alpine.js component |
| **Flask route: `/video`** | SSR dashboard 页面 + Alpine.js component |
| **Template: `audio.html`** | Jinja 模板，extends `layout.html`，匹配已有 macOS design system |
| **Template: `video.html`** | Jinja 模板，extends `layout.html` |
| **Navigation 更新** | 在 `layout.html` toolbar 添加 Audio/Video 图标链接，更新 `data-current-view` 逻辑 |
| **Icons** | 在 `icons.html` 添加 `icon_audio()` 和 `icon_video()` SVG macros |
| **Tests** | 新 API endpoint unit tests、页面渲染 integration tests |
| **Documentation** | `pages/audio.md`, `pages/video.md`, 更新 ROUTE_MAP/DATAFLOW/CHANGELOG |

### Out of Scope

| Area | Reason |
|------|--------|
| Audio waveform rendering | Phase 3+ scope |
| Video frame-level seeking | 复杂度高，Phase 3+ scope |
| Speaker diarization UI | Phase 2.1 (ADR-0004) |
| Audio/video file upload | 已存在于 `POST /api/v1/upload` |
| 从 UI 删除/编辑 chunks | Phase 5 scope (data modification) |
| 新 DB migrations | 当前 schema 已足够 |

---

## 3. Inputs (来自 Phase 0/1/2) / Outputs (给 Phase 3/4/5)

### Inputs from Phase 0 + Phase 1 + Phase 2.0

| Input | Source | Used By |
|-------|--------|---------|
| `video_chunks` table schema (id, file_path, device_name, status, created_at, monitor_id, start_time, end_time, ...) | `v3_001` + `v3_002` + `v3_003` + `v3_005` migrations | Video chunks list API, stats |
| `frames` table schema (id, video_chunk_id, offset_index, timestamp, app_name, window_name, focused, browser_url, ...) | `v3_001` migration | Video frames list API |
| `audio_chunks` table schema (id, file_path, timestamp, device_name, status, ...) | `v3_001` + `v3_006` migrations | Audio chunks list, stats |
| `audio_transcriptions` table schema | `v3_001` migration | Audio stats (transcription count) |
| `GET /api/v1/audio/chunks` existing endpoint | `api_v1.py` | Extend with device filter |
| `GET /api/v1/audio/transcriptions` existing endpoint | `api_v1.py` | Audio page 直接使用 |
| `GET /api/v1/queue/status` existing endpoint | `api_v1.py` | 两个页面的 queue status section |
| `GET /api/v1/frames/:id` existing endpoint | `api_v1.py` | Video page frame gallery 图片源 |
| `_parse_pagination()` / `_paginate_response()` utilities | `api_v1.py` | 所有新 endpoint 复用 |
| `@require_auth` decorator | `auth.py` | 所有新 endpoint 应用 |
| `layout.html` base template | `templates/layout.html` | 新页面 extend |
| `icons.html` SVG macro module | `templates/icons.html` | 新增图标 macros |
| Alpine.js vendored (`alpine.min.js`) | `vendor/` | Client-side reactivity |
| `flask_app` + `flask_client` test fixtures | `tests/conftest.py` | 测试新 endpoints |
| `settings.video_chunks_path`, `settings.server_audio_path` | `shared/config.py` | File serving paths |

### Outputs for Phase 3/4/5

| Output | Consumer | Purpose |
|--------|----------|---------|
| `/audio` + `/video` dashboard 页面 | Phase 3 Multi-Modal Search UI | 集成媒体浏览基础 |
| `GET /api/v1/video/chunks` / `GET /api/v1/video/frames` | Phase 5 Remote Deployment | Video data 远程访问 API |
| File serving endpoints | Phase 3+ Chat | Chat UI 可链接到媒体播放 |
| Stats endpoints | Phase 5 Monitoring | 运营 dashboard 遥测 |
| Navigation pattern (5 pages) | Phase 4 Chat page | 添加 `/chat` 的模式参考 |

---

## 4. Day-by-Day 计划 (5 Working Days)

### Day 1: Backend — SQLStore 新方法 + API Endpoints

**Objective**: 实现所有新 SQLStore 方法和 API endpoints，为 Day 2/3 前端工作提供可用 backend。

| Task | Details |
|------|---------|
| 添加 `get_video_chunks_paginated()` | Query `video_chunks` with optional `status` + `monitor_id` filters, LIMIT/OFFSET pagination, return `(chunks_list, total_count)` |
| 添加 `get_frames_paginated()` | Query `frames` joined with `ocr_text` for text preview, optional filters: `chunk_id`, `app_name`, `window_name`, time range. Return `(frames_list, total_count)` |
| 添加 `get_video_stats()` | Aggregate: COUNT from video_chunks, COUNT from frames, SUM duration, filesystem file sizes. Return dict. |
| 添加 `get_audio_stats()` | Aggregate: COUNT from audio_chunks, COUNT from audio_transcriptions, duration, file sizes. Return dict. |
| `GET /api/v1/video/chunks` | Pagination + optional `status` + `monitor_id` filters. 复用 `_parse_pagination()` + `_paginate_response()`. |
| `GET /api/v1/video/chunks/<id>/file` | Lookup chunk by ID, validate file exists, `send_from_directory()` for mp4. 404 on missing. |
| `GET /api/v1/video/frames` | Pagination + optional `chunk_id`, `app`, `window`, `start_time`, `end_time` filters. |
| `GET /api/v1/audio/chunks/<id>/file` | Lookup chunk by ID, validate file path within `server_audio_path`, `send_from_directory()` for WAV. |
| `GET /api/v1/video/stats` | Call `sql_store.get_video_stats()`, return JSON. |
| `GET /api/v1/audio/stats` | Call `sql_store.get_audio_stats()`, return JSON. |
| Extend `GET /api/v1/audio/chunks` | Add optional `device` query parameter for `device_name` filtering (additive). |
| Unit tests | `tests/test_phase25_api.py`: ~20 test cases for all new endpoints |

**Target Files**:
- Modified: `/Users/pyw/newpart/MyRecall/openrecall/server/database/sql.py`
- Modified: `/Users/pyw/newpart/MyRecall/openrecall/server/api_v1.py`
- New: `/Users/pyw/newpart/MyRecall/tests/test_phase25_api.py`

---

### Day 2: `/audio` Dashboard 页面

**Objective**: 构建 `/audio` 页面，SSR data injection + Alpine.js client-side pagination/filtering/playback。

| Task | Details |
|------|---------|
| 添加 `/audio` Flask route in `app.py` | `audio_dashboard()`: fetch initial stats via SQLStore, render `audio.html` |
| 创建 `audio.html` template | 5 sections: (1) Stats bar (4 cards), (2) Chunk table (pagination + status/device filter), (3) Inline `<audio>` playback, (4) Transcription browser, (5) Queue status badges |
| Alpine.js `audioDashboard()` component | State: chunks, transcriptions, stats, queueStatus, filters, pagination. Methods: fetchChunks(), fetchTranscriptions(), fetchStats(), fetchQueueStatus(), playAudio(chunkId) |
| Inline audio playback | Click play → 设置 `<audio src="/api/v1/audio/chunks/{id}/file">`，HTML5 native controls |
| Integration test | `tests/test_phase25_audio_page.py`: GET /audio returns 200, template renders |

**Target Files**:
- Modified: `/Users/pyw/newpart/MyRecall/openrecall/server/app.py`
- New: `/Users/pyw/newpart/MyRecall/openrecall/server/templates/audio.html`
- New: `/Users/pyw/newpart/MyRecall/tests/test_phase25_audio_page.py`

**SSR vs Client-side 数据分工**:

| Data | SSR (Jinja) | Client-side (Alpine.js fetch) |
|------|-------------|-------------------------------|
| Initial audio stats | 注入为 JSON `<script>` tag | 每 10s 刷新 via `GET /api/v1/audio/stats` |
| Audio chunks (page 1) | 注入为 JSON `<script>` tag | 后续分页 via `GET /api/v1/audio/chunks?limit=...&offset=...` |
| Transcriptions | 不做 SSR | Client-side fetch via `GET /api/v1/audio/transcriptions?...` |
| Queue status | 不做 SSR | 每 5s fetch via `GET /api/v1/queue/status` |
| Audio file playback | 不做 SSR | `<audio src="/api/v1/audio/chunks/{id}/file">` on user click |

---

### Day 3: `/video` Dashboard 页面

**Objective**: 构建 `/video` 页面，与 `/audio` 同模式。

| Task | Details |
|------|---------|
| 添加 `/video` Flask route in `app.py` | `video_dashboard()`: fetch initial stats, render `video.html` |
| 创建 `video.html` template | 5 sections: (1) Stats bar, (2) Chunk table (status/monitor filter), (3) Inline `<video>` playback, (4) Frame gallery (grid + modal), (5) Queue status |
| Alpine.js `videoDashboard()` component | State: chunks, frames, stats, queueStatus, filters, pagination. Methods: fetchChunks(), fetchFrames(), fetchStats(), playVideo(chunkId) |
| Frame gallery | 使用 `/api/v1/frames/{frame_id}` 作为 image source 的 grid thumbnails，click → modal（复用 index.html modal 模式） |
| Integration test | `tests/test_phase25_video_page.py`: GET /video returns 200 |

**Target Files**:
- Modified: `/Users/pyw/newpart/MyRecall/openrecall/server/app.py`
- New: `/Users/pyw/newpart/MyRecall/openrecall/server/templates/video.html`
- New: `/Users/pyw/newpart/MyRecall/tests/test_phase25_video_page.py`

---

### Day 4: Navigation 更新、集成、降级处理

**Objective**: 将两个页面接入全局导航，确保样式一致，添加降级处理。

| Task | Details |
|------|---------|
| 添加 `icon_audio()` SVG macro | 16x16px speaker/audio icon in `icons.html` |
| 添加 `icon_video()` SVG macro | 16x16px video camera icon in `icons.html` |
| 更新 `layout.html` toolbar | Add `<a href="/audio">` + `<a href="/video">` icon links, CSS `data-current-view` highlighting |
| Cross-page CSS consistency | 验证两个新页面使用相同 CSS variables、card/table/button styling |
| 降级: empty state | 无数据时友好提示 ("No audio chunks recorded yet" / "No video chunks recorded yet") |
| 降级: API failure | Alpine.js fetch `.catch()` handlers 显示 error banner、auto-retry 10s |
| 降级: missing files | File serving 返回 404 JSON; playback UI 显示 "File not available" |
| 降级: large files | `<video preload="metadata">` / `<audio preload="metadata">` 避免预加载大文件 |
| Navigation integration test | `tests/test_phase25_navigation.py`: 所有 5 page routes return 200 |

**Target Files**:
- Modified: `/Users/pyw/newpart/MyRecall/openrecall/server/templates/layout.html`
- Modified: `/Users/pyw/newpart/MyRecall/openrecall/server/templates/icons.html`
- New: `/Users/pyw/newpart/MyRecall/tests/test_phase25_navigation.py`

---

### Day 5: 测试、Gate 验证、文档、Regression

**Objective**: 全面测试、gate traceability、文档更新、full regression。

| Task | Details |
|------|---------|
| Full test suite | `python -m pytest tests/ -v` — 验证 zero failures, zero regressions |
| Phase 2.5 gate validation | Map to existing + Non-Gating checks (见 Section 6) |
| 创建 `pages/audio.md` | 遵循 page-template.md 格式 9 章节 |
| 创建 `pages/video.md` | 遵循 page-template.md 格式 9 章节 |
| 更新 `ROUTE_MAP.md` | 添加 `/audio`, `/video` 路由和 6 个新 API endpoints |
| 更新 `DATAFLOW.md` | 添加 audio/video dashboard data flow paths |
| 更新 `CHANGELOG.md` | 添加 Phase 2.5 条目 |
| 手动 E2E 验证 | 浏览器打开每个页面，验证: chunk list, pagination, filters, playback, stats, queue status, nav highlighting |
| Regression: 已有页面 | 验证 `/`, `/timeline`, `/search` 无 layout regression |

---

## 5. Work Breakdown

### WB-01: SQLStore — Video Chunks 分页查询

**Purpose**: 添加 `get_video_chunks_paginated()` 方法，供 `/api/v1/video/chunks` endpoint 和 `/video` 页面 SSR 使用。

**Dependencies**: 无（使用已有 table schema）。

**Target File**: `/Users/pyw/newpart/MyRecall/openrecall/server/database/sql.py`

**Interface**:

```python
def get_video_chunks_paginated(
    self,
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    monitor_id: Optional[str] = None,
) -> tuple[list[dict], int]:
    """Query video_chunks with optional filters and pagination.
    Returns (chunks_list, total_count).
    """
```

**Data contract**: 每个 dict 包含 `video_chunks` 表所有列：`id`, `file_path`, `device_name`, `created_at`, `expires_at`, `encrypted`, `checksum`, `status`, `app_name`, `window_name`, `monitor_id`, `monitor_width`, `monitor_height`, `start_time`, `end_time`。

**Validation Commands**:
```bash
python -m pytest tests/test_phase25_api.py::test_video_chunks_paginated -v
```

---

### WB-02: SQLStore — Frames 分页查询

**Purpose**: 添加 `get_frames_paginated()` 方法，支持多维过滤（chunk_id, app, window, time），供 frame gallery 使用。

**Dependencies**: 无。

**Target File**: `/Users/pyw/newpart/MyRecall/openrecall/server/database/sql.py`

**Interface**:

```python
def get_frames_paginated(
    self,
    limit: int = 50,
    offset: int = 0,
    chunk_id: Optional[int] = None,
    app_name: Optional[str] = None,
    window_name: Optional[str] = None,
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
) -> tuple[list[dict], int]:
    """Query frames with optional filters and pagination.
    Returns (frames_list, total_count). Each frame includes ocr_text snippet (前 200 chars).
    """
```

**Data contract**: 每个 dict 包含 `frame_id`, `video_chunk_id`, `offset_index`, `timestamp`, `app_name`, `window_name`, `focused`, `browser_url`, `ocr_text` (截取前 200 字符), `frame_url` (computed: `/api/v1/frames/{frame_id}`)。

**Validation Commands**:
```bash
python -m pytest tests/test_phase25_api.py::test_frames_paginated -v
```

---

### WB-03: SQLStore — 统计聚合

**Purpose**: 添加 video/audio 聚合统计方法，供 stats API 和 dashboard stats bar 使用。

**Dependencies**: 无。

**Target File**: `/Users/pyw/newpart/MyRecall/openrecall/server/database/sql.py`

**Interface**:

```python
def get_video_stats(self) -> dict:
    """Return video pipeline aggregate statistics.
    Returns: {
        "total_chunks": int,
        "total_frames": int,
        "total_duration_seconds": float,
        "storage_bytes": int,
        "status_counts": {"PENDING": int, "PROCESSING": int, "COMPLETED": int, "FAILED": int}
    }
    """

def get_audio_stats(self) -> dict:
    """Return audio pipeline aggregate statistics.
    Returns: {
        "total_chunks": int,
        "total_transcriptions": int,
        "total_duration_seconds": float,
        "storage_bytes": int,
        "status_counts": {"PENDING": int, "PROCESSING": int, "COMPLETED": int, "FAILED": int},
        "device_counts": {"system_audio": int, "microphone": int, ...}
    }
    """
```

**Implementation note**: `storage_bytes` 通过 filesystem `os.path.getsize()` 累加计算，不存 DB。文件缺失时该文件贡献为 0，emit debug log。`total_duration_seconds` 对 video 使用 `SUM(end_time - start_time)` where both non-NULL；对 audio 类似。无数据时 fallback to 0.0。

**Validation Commands**:
```bash
python -m pytest tests/test_phase25_api.py -k "stats" -v
```

---

### WB-04: API — Video Endpoints

**Purpose**: 暴露 video chunk listing、frame listing、video file serving 和 video statistics via `/api/v1/video/*`。

**Dependencies**: WB-01, WB-02, WB-03 (SQLStore methods)。

**Target File**: `/Users/pyw/newpart/MyRecall/openrecall/server/api_v1.py`

**API/Data Contract Changes**:

#### `GET /api/v1/video/chunks`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 50 | Page size (max 1000) |
| `offset` | int | 0 | Offset |
| `page` | int | — | Alternative to offset (1-based) |
| `page_size` | int | — | Alternative to limit |
| `status` | string | — | Filter: PENDING/PROCESSING/COMPLETED/FAILED |
| `monitor_id` | string | — | Filter by monitor_id |

**Response**: `{ "data": [...], "meta": { "total", "limit", "offset", "has_more" } }`

#### `GET /api/v1/video/chunks/<int:chunk_id>/file`

**Response**: `200` + `Content-Type: video/mp4`（send_from_directory），或 `404` JSON error。
**Security**: 验证 chunk_id 在 DB 中存在且文件在 disk 上可用。不暴露 raw file paths。

#### `GET /api/v1/video/frames`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 50 | Page size |
| `offset` | int | 0 | Offset |
| `chunk_id` | int | — | Filter by video_chunk_id |
| `app` | string | — | Filter by app_name (LIKE match) |
| `window` | string | — | Filter by window_name (LIKE match) |
| `start_time` | float | 0 | Time range start |
| `end_time` | float | now | Time range end |

**Response**: Paginated envelope with frames list。

#### `GET /api/v1/video/stats`

**Response**: `{ "total_chunks": int, "total_frames": int, "total_duration_seconds": float, "storage_bytes": int, "status_counts": {...} }`

**Validation Commands**:
```bash
python -m pytest tests/test_phase25_api.py -k "video" -v
```

---

### WB-05: API — Audio File Serving + Stats + Filter Extension

**Purpose**: 暴露 audio file serving、audio statistics、extend audio chunks with device filter。

**Dependencies**: WB-03 (SQLStore methods)。

**Target File**: `/Users/pyw/newpart/MyRecall/openrecall/server/api_v1.py`

**API/Data Contract Changes**:

#### `GET /api/v1/audio/chunks/<int:chunk_id>/file`

**Response**: `200` + `Content-Type: audio/wav`（send_from_directory），或 `404` JSON error。
**Security**: Path validation via `resolve().is_relative_to(settings.server_audio_path)`。

#### `GET /api/v1/audio/stats`

**Response**: `{ "total_chunks": int, "total_transcriptions": int, "total_duration_seconds": float, "storage_bytes": int, "status_counts": {...}, "device_counts": {...} }`

#### Extend `GET /api/v1/audio/chunks`

新增 optional `device` query parameter。Present 时添加 `WHERE device_name = ?`。**Additive-only**，无 `device` 参数时行为不变。

**Validation Commands**:
```bash
python -m pytest tests/test_phase25_api.py -k "audio" -v
```

---

### WB-06: `/audio` Page — Flask Route + Template

**Purpose**: Server-rendered audio dashboard 页面。

**Dependencies**: WB-04, WB-05 (API endpoints 可用)。

**Target Files**:
- Modified: `/Users/pyw/newpart/MyRecall/openrecall/server/app.py`
- New: `/Users/pyw/newpart/MyRecall/openrecall/server/templates/audio.html`

**Flask Route**:
```python
@app.route("/audio")
def audio_dashboard():
    """Audio pipeline dashboard."""
    try:
        stats = sql_store.get_audio_stats()
    except Exception:
        stats = {"total_chunks": 0, "total_transcriptions": 0,
                 "total_duration_seconds": 0.0, "storage_bytes": 0,
                 "status_counts": {}, "device_counts": {}}
    return render_template("audio.html", stats=stats)
```

**Template 结构**:
1. **Stats bar**: 4 stat cards（Total Chunks, Total Transcriptions, Total Duration, Storage Size）
2. **Chunk table**: ID, Device, Status, Created At, Duration, Checksum (truncated). 每行有 Play button。Filter bar: Status dropdown + Device text input。
3. **Transcription browser**: 分页列表：timestamp, device, text (truncated), duration。Filter: time range + device。
4. **Queue status**: 4 colored badges（Pending=yellow, Processing=blue spinner, Completed=green, Failed=red）
5. **Audio player**: Sticky bottom bar with `<audio>` element，选中 chunk 时出现。`preload="metadata"`。

**Validation Commands**:
```bash
python -m pytest tests/test_phase25_audio_page.py -v
```

---

### WB-07: `/video` Page — Flask Route + Template

**Purpose**: Server-rendered video dashboard 页面。

**Dependencies**: WB-04, WB-05 (API endpoints 可用)。

**Target Files**:
- Modified: `/Users/pyw/newpart/MyRecall/openrecall/server/app.py`
- New: `/Users/pyw/newpart/MyRecall/openrecall/server/templates/video.html`

**Flask Route**:
```python
@app.route("/video")
def video_dashboard():
    """Video pipeline dashboard."""
    try:
        stats = sql_store.get_video_stats()
    except Exception:
        stats = {"total_chunks": 0, "total_frames": 0,
                 "total_duration_seconds": 0.0, "storage_bytes": 0,
                 "status_counts": {}}
    return render_template("video.html", stats=stats)
```

**Template 结构**:
1. **Stats bar**: 4 stat cards（Total Chunks, Total Frames, Total Duration, Storage Size）
2. **Chunk table**: ID, Device, Monitor, Status, Start Time, End Time, Created At. 每行 Play button。Filter: Status dropdown + Monitor ID input。
3. **Frame gallery**: Grid thumbnails（source: `/api/v1/frames/{frame_id}`），分页，click → modal（复用 index.html modal 模式）。Filter: app/window/time range。
4. **Queue status**: 同 audio 4-badge pattern
5. **Video player**: Modal 或 inline `<video>` with native controls。`preload="metadata"`。

**Validation Commands**:
```bash
python -m pytest tests/test_phase25_video_page.py -v
```

---

### WB-08: Navigation + Icons 更新

**Purpose**: 将 `/audio` 和 `/video` 接入全局 toolbar 导航。

**Dependencies**: WB-06, WB-07 (pages exist)。

**Target Files**:
- Modified: `/Users/pyw/newpart/MyRecall/openrecall/server/templates/layout.html`
- Modified: `/Users/pyw/newpart/MyRecall/openrecall/server/templates/icons.html`

**icons.html 新增**:
- `icon_audio()` macro: 16x16px speaker + sound wave SVG
- `icon_video()` macro: 16x16px video camera SVG

**layout.html 变更**:
- `toolbar-icons-container` 添加 `<a href="/audio">` + `<a href="/video">` icon links
- CSS: `html[data-current-view="audio"] a[href="/audio"]` + `html[data-current-view="video"] a[href="/video"]` active highlight
- JS: extend `currentPath` detection for `/audio` and `/video`

**Validation Commands**:
```bash
python -m pytest tests/test_phase25_navigation.py -v
```

---

### WB-09: 降级处理

**Purpose**: 确保两个页面在数据为空、文件缺失、API 故障时的优雅降级。

**Dependencies**: WB-06, WB-07, WB-08。

**Target Files**:
- Modified: `audio.html`, `video.html` templates

**降级矩阵**:

| Scenario | Expected Behavior | Implementation |
|----------|-------------------|----------------|
| 无 audio/video chunks | 友好空态消息 | Alpine.js: `x-if="chunks.length === 0"` |
| 文件在 disk 上缺失 | Playback UI 显示 "File not available" toast | API 返回 404 JSON; `.catch()` handler |
| API fetch 失败 | Banner: "Could not load data. Retrying..." | `.catch()` sets `error` state, auto-retry 10s |
| 大视频文件 | 不自动下载 | `<video preload="metadata">` |
| DB 表不存在（fresh install） | Stats 返回 zeros, chunk list 为空 | SQLStore 方法 wrap `_table_exists()` guard |

**Validation Commands**:
```bash
python -m pytest tests/test_phase25_api.py -k "missing_file or empty_db" -v
```

---

### WB-10: Test Suite

**Purpose**: 全面 unit + integration 测试。

**Dependencies**: WB-01 through WB-09。

**New Test Files**:
- `tests/test_phase25_api.py` — ~20 API endpoint tests
- `tests/test_phase25_audio_page.py` — ~5 audio page rendering tests
- `tests/test_phase25_video_page.py` — ~5 video page rendering tests
- `tests/test_phase25_navigation.py` — ~5 navigation integration tests

**Test Cases (test_phase25_api.py)**:
1. `test_video_chunks_list` — 分页数据
2. `test_video_chunks_status_filter` — status=COMPLETED 过滤
3. `test_video_chunks_monitor_filter` — monitor_id 过滤
4. `test_video_chunks_pagination` — offset/limit, has_more
5. `test_video_chunk_file_serve` — mp4 file content-type
6. `test_video_chunk_file_404` — chunk 不存在
7. `test_video_chunk_file_missing` — DB 有记录但文件缺失
8. `test_video_frames_list` — 分页
9. `test_video_frames_chunk_filter` — chunk_id 过滤
10. `test_video_frames_app_filter` — app name 过滤
11. `test_video_frames_time_range` — time range 过滤
12. `test_video_stats` — 聚合统计正确
13. `test_video_stats_empty_db` — 无数据返回 zeros
14. `test_audio_chunk_file_serve` — WAV file serving
15. `test_audio_chunk_file_404` — chunk 不存在
16. `test_audio_chunk_file_path_traversal` — 路径遍历攻击返回 400/404
17. `test_audio_stats` — 聚合统计正确
18. `test_audio_stats_empty_db` — 无数据返回 zeros
19. `test_audio_chunks_device_filter` — device 过滤
20. `test_audio_chunks_device_filter_backward_compat` — 无 device 参数行为不变

**Validation Commands**:
```bash
# Phase 2.5 specific
python -m pytest tests/test_phase25_*.py -v

# Full regression
python -m pytest tests/ -v --tb=short
```

---

### WB-11: 文档更新

**Purpose**: 按 `phase-update-checklist.md` 同步 WebUI 文档。

**Dependencies**: WB-01 through WB-10。

**Target Files**:
- New: `/Users/pyw/newpart/MyRecall/v3/webui/pages/audio.md`
- New: `/Users/pyw/newpart/MyRecall/v3/webui/pages/video.md`
- Modified: `/Users/pyw/newpart/MyRecall/v3/webui/ROUTE_MAP.md`
- Modified: `/Users/pyw/newpart/MyRecall/v3/webui/DATAFLOW.md`
- Modified: `/Users/pyw/newpart/MyRecall/v3/webui/CHANGELOG.md`

---

### WB-12: Regression & Gate Closure

**Purpose**: Full test suite 执行，验证 zero regressions，关闭 gate traceability。

**Validation Commands**:
```bash
# Full regression
python -m pytest tests/ -v --tb=short

# Phase 2.5 specific
python -m pytest tests/test_phase25_*.py -v

# Existing page regression
python -m pytest tests/test_phase0_api_v1.py tests/test_phase1_timeline_api.py tests/test_phase1_search_integration.py tests/test_phase2_search.py tests/test_phase2_timeline.py -v
```

---

## 6. Gate Traceability Matrix

Phase 2.5 在 `/Users/pyw/newpart/MyRecall/v3/metrics/phase-gates.md` 中**没有专属 gates**。以下所有项映射到已有 Phase gates 或标注为 **Non-Gating**。

| ID | Gate / Check | Maps to | Status | Validation |
|----|-------------|---------|--------|------------|
| 2.5-F-01 | `/audio` 页面可渲染并展示数据 | Non-Gating（UI-only，无管线变更） | Planned | `GET /audio` returns 200, Alpine.js component initializes |
| 2.5-F-02 | `/video` 页面可渲染并展示数据 | Non-Gating | Planned | `GET /video` returns 200 |
| 2.5-F-03 | `GET /api/v1/video/chunks` 返回正确分页数据 | Phase 5 0-F-01 (API Versioning Coverage) | Planned | Unit test with mock data |
| 2.5-F-04 | `GET /api/v1/video/frames` 返回正确过滤数据 | Phase 5 0-F-01 | Planned | Unit test with filters |
| 2.5-F-05 | `GET /api/v1/video/chunks/<id>/file` 提供 mp4 | Non-Gating | Planned | Unit test |
| 2.5-F-06 | `GET /api/v1/audio/chunks/<id>/file` 提供 WAV | Non-Gating | Planned | Unit test |
| 2.5-F-07 | Inline audio playback 可用 | Non-Gating | Planned | Manual: click play, hear audio |
| 2.5-F-08 | Inline video playback 可用 | Non-Gating | Planned | Manual: click play, see video |
| 2.5-F-09 | Stats endpoints 返回正确聚合数据 | Non-Gating | Planned | Unit test |
| 2.5-F-10 | Navigation icons 可见且正确 highlight | Non-Gating | Planned | Manual + integration test |
| 2.5-F-11 | Audio device filter（additive） | Phase 5 0-F-03 (Pagination on List Endpoints) | Planned | Unit test |
| 2.5-P-01 | Stats endpoint 响应 < 500ms on 10K rows | Non-Gating benchmark（参考 Phase 3 latency 目标） | Planned | Benchmark test (non-gating) |
| 2.5-S-01 | 无已有测试 regression | Phase 2.0 test baseline (477 passed) | Planned | Full `pytest` run |
| 2.5-R-01 | File serving 不将整个文件加载到内存 | Non-Gating (uses send_from_directory) | Planned | Code review |
| 2.5-DG-01 | File serving 验证路径（no traversal） | Phase 0 DG-04 (Auth Placeholder) | Planned | Security test case |

---

## 7. Test & Verification Plan

### 7.1 Unit Tests (Automated)

| Test File | Count | Scope |
|-----------|-------|-------|
| `tests/test_phase25_api.py` | ~20 | 所有新 API endpoints: pagination, filters, file serving, stats, error cases |
| `tests/test_phase25_audio_page.py` | ~5 | Audio page rendering, SSR data injection, empty state |
| `tests/test_phase25_video_page.py` | ~5 | Video page rendering, SSR data injection, empty state |
| `tests/test_phase25_navigation.py` | ~5 | 所有 5 routes return 200, layout contains icons, current-view highlighting |

### 7.2 Integration Tests (Automated)

| Scenario | Method |
|----------|--------|
| Full regression: 已有 477+ tests pass | `python -m pytest tests/ -v` |
| Phase 1 timeline API 不变 | `python -m pytest tests/test_phase1_timeline_api.py -v` |
| Phase 2 search/timeline 不变 | `python -m pytest tests/test_phase2_search.py tests/test_phase2_timeline.py -v` |
| Page routes 全部 200 | `test_phase25_navigation.py` |

### 7.3 Manual Verification Checklist

| Item | Steps | Expected |
|------|-------|----------|
| Audio page loads | Navigate to `/audio` | Stats bar, chunk list, empty or populated |
| Audio chunk pagination | Click next page | New chunk data, page indicator 更新 |
| Audio chunk filter by status | Select "COMPLETED" | Only completed chunks shown |
| Audio chunk filter by device | Type device name | Only matching device chunks |
| Audio playback | Click play on chunk row | Audio plays, native controls visible |
| Audio transcription browser | View transcriptions section | Paginated list with timestamps |
| Video page loads | Navigate to `/video` | Stats bar, chunk list |
| Video chunk pagination | Click next | New data |
| Video chunk filter by status | Select "PENDING" | Filtered list |
| Video chunk filter by monitor | Type monitor_id | Filtered |
| Video playback | Click play on chunk | Video plays |
| Frame gallery | View frames section | Grid thumbnails loading from `/api/v1/frames/` |
| Frame gallery pagination | Click next | New frames |
| Frame gallery filters | Filter by app/window/time | Correct filtering |
| Navigation: audio highlight | Navigate to `/audio` | Audio icon highlighted in toolbar |
| Navigation: video highlight | Navigate to `/video` | Video icon highlighted |
| Navigation: existing pages | Visit `/`, `/timeline`, `/search` | No regressions |
| Empty state: no data | Fresh DB, visit `/audio` + `/video` | Friendly empty state messages |
| Missing file: audio | Delete WAV, try playback | "File not available" |
| Missing file: video | Delete mp4, try playback | "File not available" |

### 7.4 API Smoke Test Sequence

```
1. GET /api/v1/video/stats → 200 + stats JSON
2. GET /api/v1/video/chunks?limit=10 → 200 + paginated chunks
3. GET /api/v1/video/chunks/1/file → 200 video/mp4 (or 404)
4. GET /api/v1/video/frames?limit=10 → 200 + paginated frames
5. GET /api/v1/audio/stats → 200 + stats JSON
6. GET /api/v1/audio/chunks?device=microphone → 200 + filtered chunks
7. GET /api/v1/audio/chunks/1/file → 200 audio/wav (or 404)
8. GET /audio → 200 HTML
9. GET /video → 200 HTML
```

---

## 8. Risks / Failure Signals / Fallback

| # | Risk | Probability | Impact | Failure Signal | Fallback |
|---|------|------------|--------|----------------|----------|
| R1 | 大视频文件导致 browser memory 问题 | Medium | Medium | Browser tab crash or OOM during playback | 使用 `<video preload="metadata">` + `type="video/mp4"` 启用 progressive playback；未来考虑 chunk duration limits |
| R2 | Audio WAV 文件对 browser `<audio>` 太大 | Low | Low | Playback 失败或启动很慢 | WAV files are 60s@16kHz mono (~1.9MB each), well within browser limits。Fallback: 未来 server-side transcode to mp3/opus |
| R3 | SQLite aggregate queries 在大数据集（100K+ chunks）上慢 | Medium | Medium | Stats endpoint latency > 1s; 页面感觉卡 | 对 video_chunks/audio_chunks status 列添加 index; 10s TTL in-memory cache |
| R4 | File serving 暴露路径遍历漏洞 | Low | High | 攻击者访问 data 目录外文件 | Path validation via `resolve().is_relative_to()`; unit test for traversal attempt |
| R5 | Alpine.js component 复杂度导致维护负担 | Medium | Low | Hard to debug client-side state issues | 保持 component 简单 (<150 行); 使用与 `memoryGrid()` in `index.html` 相同模式 |
| R6 | Template CSS 与已有页面冲突 | Low | Medium | 已有页面 layout 破损 | 所有新 CSS scoped 在 page-specific `<style>` blocks, 不是 global。Navigation CSS 使用 specific `data-current-view` selectors。|
| R7 | Pagination offset 超出总行数 | Low | Low | 空页面 with "has_more: false" | `_paginate_response()` 已处理 — empty `data[]` + correct `meta`。UI shows empty state。|
| R8 | Queue status endpoint schema 变更 break dashboard | Low | Medium | Dashboard 显示错误或缺失数据 | `GET /api/v1/queue/status` 已返回 `video_queue` + `audio_queue` objects。Defensive coding: default 0 for missing keys。|
| R9 | send_from_directory 不支持 Range requests for seek | Medium | Low | 用户无法 seek video/audio playback | Flask `send_from_directory` via Werkzeug 原生支持 Range headers。如不支持, 添加 `conditional=True`。|
| R10 | 并发 file serving requests 压垮 server | Low | Medium | Server unresponsive when multiple streams | Flask dev server single-threaded; gunicorn/uwsgi in production handles concurrency。localhost Phase 2.5 无需额外处理。|

---

## 9. Deliverables Checklist

### New Files

| File | WB | Purpose |
|------|-----|---------|
| `openrecall/server/templates/audio.html` | WB-06 | Audio dashboard page template |
| `openrecall/server/templates/video.html` | WB-07 | Video dashboard page template |
| `tests/test_phase25_api.py` | WB-10 | API endpoint tests |
| `tests/test_phase25_audio_page.py` | WB-10 | Audio page rendering tests |
| `tests/test_phase25_video_page.py` | WB-10 | Video page rendering tests |
| `tests/test_phase25_navigation.py` | WB-10 | Navigation integration tests |
| `v3/webui/pages/audio.md` | WB-11 | Audio page documentation |
| `v3/webui/pages/video.md` | WB-11 | Video page documentation |

### Modified Files

| File | WB | Changes |
|------|-----|---------|
| `openrecall/server/database/sql.py` | WB-01,02,03 | Add 4 new methods |
| `openrecall/server/api_v1.py` | WB-04,05 | Add 6 new endpoints + extend 1 |
| `openrecall/server/app.py` | WB-06,07 | Add `/audio` + `/video` Flask routes |
| `openrecall/server/templates/layout.html` | WB-08 | Add audio/video nav icons + current-view |
| `openrecall/server/templates/icons.html` | WB-08 | Add `icon_audio()` + `icon_video()` macros |
| `v3/webui/ROUTE_MAP.md` | WB-11 | Add /audio, /video + 6 API endpoints |
| `v3/webui/DATAFLOW.md` | WB-11 | Add dashboard data flow paths |
| `v3/webui/CHANGELOG.md` | WB-11 | Add Phase 2.5 entry |

**Total: 8 new files, 8 modified files**

---

## 10. Execution Readiness Checklist

| # | Prerequisite | Status | Notes |
|---|-------------|--------|-------|
| 1 | Phase 2.0 Engineering Complete | ✅ | 15/17 gates PASS, 477 tests pass |
| 2 | `video_chunks` 表有 `status`, `monitor_id`, `start_time`, `end_time` 列 | ✅ | Migrations v3_001 through v3_005 |
| 3 | `audio_chunks` 表有 `status` 列 | ✅ | Migrations v3_001 + v3_006 |
| 4 | `frames` 表有 `app_name`, `window_name`, `focused`, `browser_url` | ✅ | Migration v3_001 |
| 5 | `settings.video_chunks_path` + `settings.server_audio_path` 已配置 | ✅ | In `shared/config.py` |
| 6 | Alpine.js vendored at `vendor/alpine.min.js` | ✅ | Already served |
| 7 | `flask_client` test fixture 可用 | ✅ | In `tests/conftest.py` |
| 8 | `@require_auth` decorator 可用 | ✅ | In `openrecall/server/auth.py` |
| 9 | `_paginate_response()` + `_parse_pagination()` utilities 可用 | ✅ | In `api_v1.py` |
| 10 | 2-S-01 (24h stability) 不阻塞 WebUI work | ✅ | Stability 是 non-blocking for UI |

---

## 11. Documentation Sync Matrix

按 `/Users/pyw/newpart/MyRecall/v3/webui/templates/phase-update-checklist.md` 执行：

| Checklist Item | Answer | Action | When |
|----------------|--------|--------|------|
| 新增页面路由？ | Yes (`/audio`, `/video`) | Create page docs, update ROUTE_MAP | Day 5 |
| 修改现有页面行为？ | Yes (layout.html nav) | Update DATAFLOW, ROUTE_MAP | Day 5 |
| 新增/变更 API 依赖？ | Yes (6 new, 1 extended) | Update ROUTE_MAP section 4 | Day 5 |
| 新增降级路径？ | Yes (empty state, missing files, API failure) | Document in page docs section 8 | Day 5 |
| CHANGELOG 更新？ | Planned | Add Phase 2.5 entry | Day 5 |
| 页面文档 9 章节？ | Planned | Follow `page-template.md` | Day 5 |
| DATAFLOW 主图更新？ | Planned | Add `/audio` + `/video` nodes | Day 5 |
| Upload/upload status 接口变更？ | No | No action needed | — |
| `results/README.md` 维护约束？ | Intact | No change | — |
| `v3/README.md` WebUI 入口？ | 需检查 | 如有链接更新 | Day 5 |

---

## 12. Last Updated

**Date**: 2026-02-12
**Author**: Solo Developer (Phase 2.5 planning)
**Status**: EXECUTED — Engineering complete, validation closed
**Next Action**: No execution action under current roadmap; maintain as historical documentation.
