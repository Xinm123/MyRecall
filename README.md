# MyRecall

MyRecall is a local-first digital memory system for continuous screen capture, OCR indexing, and timeline/search retrieval.

MyRecall 是一个本地优先的数字记忆系统，聚焦“持续屏幕采集 + OCR 索引 + 时间线/搜索检索”。

## MyRecall-v3 TODO List (Global)

### 中文

状态来源：`/Users/pyw/new/MyRecall/v3/milestones/roadmap-status.md`

- [x] Phase 0: Foundation & Client-Server Boundary（已完成）
- [ ] Phase 1: Screen Recording Pipeline（工程完成，仍需长时证据收集）
- [ ] Phase 2.0: Audio MVP（未开始）
- [ ] Phase 2.1: Speaker Identification（可选，未开始）
- [ ] Phase 3: Multi-Modal Search Integration（未开始）
- [ ] Phase 4: Chat Capability（未开始）
- [ ] Phase 5: Deployment Migration（未开始，关键路径）
- [ ] Phase 6: Streaming Chat（未来阶段）
- [ ] Phase 7: Memory Capabilities（未来阶段）

### English

Status source: `/Users/pyw/new/MyRecall/v3/milestones/roadmap-status.md`

- [x] Phase 0: Foundation & client-server boundary
- [ ] Phase 1: Screen recording pipeline (engineering complete, long-run evidence pending)
- [ ] Phase 2.0: Audio MVP
- [ ] Phase 2.1: Speaker identification (optional)
- [ ] Phase 3: Multi-modal search integration
- [ ] Phase 4: Chat capability
- [ ] Phase 5: Deployment migration (critical path)
- [ ] Phase 6: Streaming chat (future)
- [ ] Phase 7: Memory capabilities (future)

## 项目定位 / Project Positioning

### 中文

这个仓库的主线是 `MyRecall-v3` 全项目路线（Phase 0 到 Phase 7）。  
其中当前可运行与可验证的核心是 Phase 0 + Phase 1：客户端负责采集与上传，服务端负责异步处理、索引和检索。

当前 README 的目标是“全项目视角 + 当前可执行落地”：  
一方面说明 v3 全阶段目标和边界，另一方面帮助你在 10 分钟内跑通现阶段系统并定位常见故障。

### English

This repository tracks the full `MyRecall-v3` program (Phase 0 through Phase 7).  
The currently runnable and validated implementation scope is mainly Phase 0 + Phase 1: client-side capture/upload and server-side async processing/indexing/retrieval.

This README is intentionally practical: whole-program context plus execution-ready guidance for the current implementation.

## 全项目范围（Phase 0~7） / Full Project Scope (Phase 0~7)

### 中文

| 阶段 | 目标 | 当前状态 |
|---|---|---|
| Phase 0 | 数据与接口基础（schema/migration/api-v1/上传队列） | 已完成 |
| Phase 1 | 视频采集与 OCR 索引（monitor-id 管线） | 工程完成，待长时证据 |
| Phase 2.0 | 音频采集与转写 MVP | 未开始 |
| Phase 2.1 | 说话人识别（可选） | 未开始 |
| Phase 3 | 多模态统一检索（vision+audio） | 未开始 |
| Phase 4 | Chat 能力与工具调用 | 未开始 |
| Phase 5 | 部署迁移（thin-client, remote server） | 未开始 |
| Phase 6 | 流式 Chat | 未来阶段 |
| Phase 7 | Memory 能力（摘要 + agent 状态） | 未来阶段 |

说明：本 README 的运行命令与排障步骤主要对应 Phase 0/1 已落地能力；其余阶段按路线图推进。

### English

| Phase | Objective | Status |
|---|---|---|
| Phase 0 | Data/API foundation (schema, migration, api-v1, upload queue) | Completed |
| Phase 1 | Video capture + OCR indexing (monitor-id pipeline) | Engineering complete, long-run evidence pending |
| Phase 2.0 | Audio capture + transcription MVP | Not started |
| Phase 2.1 | Speaker identification (optional) | Not started |
| Phase 3 | Unified multimodal retrieval (vision+audio) | Not started |
| Phase 4 | Chat capability and tool orchestration | Not started |
| Phase 5 | Deployment migration (thin-client, remote server) | Not started |
| Phase 6 | Streaming chat | Future |
| Phase 7 | Memory capabilities (summaries + agent state) | Future |

Note: runnable commands and troubleshooting in this README mainly target implemented Phase 0/1 capabilities.

## 当前架构 / Current Architecture

### 中文

运行链路（当前实现，Phase 0/1）：

1. Client 采集屏幕（优先 monitor-id 视频管线，失败时可降级截图模式）。
2. Client 将数据写入本地缓冲队列，再由 Consumer 上传到 Server。
3. Server 接收截图或视频 chunk，写入 DB，后台 Worker 处理视频：抽帧 -> OCR -> FTS。
4. Web UI 与 API 从 DB/索引读取：Grid、Timeline、Search。

```text
Client Capture
  -> Local Buffer
  -> Upload API (/api or /api/v1)
  -> Server DB (entries/video_chunks/frames/ocr_text)
  -> Workers (video processing + retention)
  -> Search/Timeline/UI
```

### English

High-level runtime flow (currently implemented in Phase 0/1):

1. Client captures the screen (monitor-id video pipeline first, screenshot fallback available).
2. Client buffers locally and uploads via a consumer thread.
3. Server ingests payloads, persists metadata, and processes video chunks asynchronously: frame extraction -> OCR -> FTS.
4. UI and APIs read from SQL + index layers for grid/timeline/search.

## 快速启动（本地单机） / Quick Start (Single Machine)

### 中文

前置要求：

1. Python `3.9`-`3.12`
2. `ffmpeg` 可执行文件在 `PATH`
3. macOS 使用视频模式时需开启 Screen Recording 权限

安装：

```bash
cd /Users/pyw/new/MyRecall
python3 -m pip install -e .[test]
```

使用 Conda 环境 `v3` 启动（推荐）：

1. 在两个终端分别启动。
2. 终端 A（Server）：

```bash
conda activate v3
cd /Users/pyw/new/MyRecall
run_server.sh
```

3. 终端 B（Client）：

```bash
conda activate v3
cd /Users/pyw/new/MyRecall
run_client.sh
```

如果你的 shell 没有将当前目录加入可执行路径，请使用 `./run_server.sh` 和 `./run_client.sh`。

启动 Server：

```bash
cd /Users/pyw/new/MyRecall
./run_server.sh --debug
```

启动 Client：

```bash
cd /Users/pyw/new/MyRecall
./run_client.sh --debug
```

默认访问地址（按仓库 env 模板）：

1. Web UI: `http://127.0.0.1:18083`
2. API Root: `http://127.0.0.1:18083/api`

说明：如果不加载 env，代码默认端口是 `8083`（`OPENRECALL_PORT` 默认值）。

### English

Prerequisites:

1. Python `3.9`-`3.12`
2. `ffmpeg` available in `PATH`
3. Screen Recording permission on macOS for video capture

Install:

```bash
cd /Users/pyw/new/MyRecall
python3 -m pip install -e .[test]
```

Conda startup with environment `v3` (recommended):

1. Start server and client in two terminals.
2. Terminal A (Server):

```bash
conda activate v3
cd /Users/pyw/new/MyRecall
run_server.sh
```

3. Terminal B (Client):

```bash
conda activate v3
cd /Users/pyw/new/MyRecall
run_client.sh
```

If your shell does not execute from current directory by default, use `./run_server.sh` and `./run_client.sh`.

Run server:

```bash
cd /Users/pyw/new/MyRecall
./run_server.sh --debug
```

Run client:

```bash
cd /Users/pyw/new/MyRecall
./run_client.sh --debug
```

With repo env templates, the default UI/API port is `18083`.  
Without env loading, framework default is `8083`.

## 典型部署模式 / Typical Deployment Modes

### 中文

1. 本地一体：client + server 同机运行（开发调试首选）。
2. 远程服务端：client 在工作机采集并上传，server+DB 在另一台机器运行。

脚本支持自定义 env：

```bash
./run_server.sh --env=/abs/path/to/myrecall_server.env
./run_client.sh --env=/abs/path/to/myrecall_client.env
```

### English

1. All-in-one local mode: client and server on the same machine.
2. Remote server mode: client captures on workstation, uploads to a separate server host.

Both launch scripts support custom env files via `--env=...`.

## 配置指南 / Configuration Guide

### 中文

权威配置文件：

1. Client: `/Users/pyw/new/MyRecall/myrecall_client.env`
2. Server: `/Users/pyw/new/MyRecall/myrecall_server.env`

关键配置分组：

1. 基础连接
   - `OPENRECALL_API_URL`
   - `OPENRECALL_UPLOAD_TIMEOUT`
2. 采集策略
   - `OPENRECALL_RECORDING_MODE` = `auto|video|screenshot`
   - `OPENRECALL_PRIMARY_MONITOR_ONLY`
   - `OPENRECALL_VIDEO_MONITOR_IDS`
3. 视频管线稳定性
   - `OPENRECALL_VIDEO_PIPELINE_RESTART_ON_PROFILE_CHANGE`
   - `OPENRECALL_VIDEO_POOL_MAX_BYTES`
   - `OPENRECALL_VIDEO_SEGMENT_STAGGER_SECONDS`
   - `OPENRECALL_VIDEO_PIPE_WRITE_WARN_MS`
   - `OPENRECALL_VIDEO_COLOR_RANGE`
   - `OPENRECALL_SCK_START_RETRY_MAX`
   - `OPENRECALL_SCK_RETRY_BACKOFF_SECONDS`
   - `OPENRECALL_SCK_PERMISSION_BACKOFF_SECONDS`
   - `OPENRECALL_SCK_RECOVERY_PROBE_SECONDS`
   - `OPENRECALL_SCK_AUTO_RECOVER_FROM_LEGACY`
4. 切片时长（关键）
   - `OPENRECALL_VIDEO_CHUNK_DURATION` 以 **client env** 为权威（采集端实际生效）
   - server env 同名项仅用于运维对齐注释，当前服务端运行时不直接控制采集切片
5. 模型预热
   - `OPENRECALL_PRELOAD_MODELS=true` 时，server 启动会预热可本地运行的 OCR provider（`local`/`rapidocr`/`doctr`）

### English

Authoritative env files:

1. Client: `myrecall_client.env`
2. Server: `myrecall_server.env`

Key groups:

1. Connection: `OPENRECALL_API_URL`, `OPENRECALL_UPLOAD_TIMEOUT`
2. Capture policy: `OPENRECALL_RECORDING_MODE`, `OPENRECALL_PRIMARY_MONITOR_ONLY`, `OPENRECALL_VIDEO_MONITOR_IDS`
3. Pipeline hardening: restart-on-profile-change, pool max bytes, stagger, pipe write warning, color range
   - plus SCK retry/recovery controls (`OPENRECALL_SCK_*`)
4. Chunk duration authority:
   - `OPENRECALL_VIDEO_CHUNK_DURATION` is authoritative on the **client** side
   - same key in server env is an ops-alignment note only
5. Preload:
   - `OPENRECALL_PRELOAD_MODELS=true` preloads local OCR-capable providers on server startup

## 数据流（采集到搜索） / Data Flow (Capture to Search)

### 中文

视频模式（Phase 1 主路径）：

1. `video_recorder.py` 选择 monitor source（macOS 优先 `ScreenCaptureKit`，其余平台 `mss`）
2. 原始帧进入 `FFmpegManager`（rawvideo stdin，按 profile 构造 `-pixel_format/-video_size`）
3. 按 chunk 落盘后由 `UploaderConsumer` 作为 `video_chunk` 上传
4. server `api_v1` 写入 `video_chunks`，`VideoProcessingWorker` 异步处理
5. `FrameExtractor` 抽帧，`VideoChunkProcessor` OCR 并写入 `ocr_text` + `ocr_text_fts`

截图模式（降级或显式设置）：

1. `recorder.py` 周期截图
2. 通过 `entries` 表和旧处理链路入库

### English

Video path:

1. `video_recorder.py` selects monitor sources (`ScreenCaptureKit` on macOS when available, otherwise `mss`)
2. Raw frames are piped to FFmpeg stdin with profile-aware input args
3. Chunk files are uploaded as `video_chunk`
4. Server persists chunk metadata, then async worker extracts frames + OCR + FTS

Screenshot path:

1. Periodic capture in `recorder.py`
2. Stored through the legacy `entries` pipeline

## API 与页面入口 / API and UI Entry Points

### 中文

主要页面：

1. `/` Grid
2. `/timeline`
3. `/search`

主要 API：

1. Legacy:
   - `POST /api/upload`
   - `GET /api/upload/status`
   - `GET /api/search`
2. v1:
   - `POST /api/v1/upload`
   - `GET /api/v1/upload/status`
   - `GET /api/v1/timeline`
   - `GET /api/v1/frames/<id>`
   - `GET /api/v1/search`
   - `GET /api/v1/vision/status`

3. Capture health:
   - `GET /api/vision/status`
   - `GET /api/v1/vision/status`

兼容行为：legacy `POST /api/upload` 检测到视频 payload 时会转发到 v1 视频处理分支。

### English

UI routes:

1. `/` grid
2. `/timeline`
3. `/search`

API routes include both legacy `/api/*` and versioned `/api/v1/*`.  
Legacy `/api/upload` forwards video payloads to the v1 video handler for compatibility.

## 搜索能力现状与边界 / Search Status and Boundaries

### 中文

当前存在两条结果路径：

1. `search()`（用于 `/api/search` 与 `/api/v1/search`）主要返回 snapshot 对象。
2. `search_debug()`（用于 `/search` 页面渲染）可包含 `video_frame` 候选（`vframe:*`）。

这意味着：你在网页 `/search` 看到的视频帧命中，未必完全等价于 `/api/v1/search` 的输出结构。  
统一多模态搜索契约属于后续 Phase 3 范畴。

### English

Current search has two practical paths:

1. `search()` (used by `/api/search` and `/api/v1/search`) returns snapshot-oriented objects.
2. `search_debug()` (used by `/search` page) can render `video_frame` candidates (`vframe:*`).

So UI debug/search rendering and API payloads are not yet fully unified.  
A unified multimodal contract is a Phase 3 scope.

## 常见故障排查 / Troubleshooting Matrix

| 症状 / Symptom | 关键日志 / Key Log | 常见原因 / Likely Cause | 处理建议 / Action |
|---|---|---|---|
| 上传 MP4 被当图片解析 | `cannot identify image file ...mp4` | 上传分支路由错误或旧逻辑 | 检查 consumer 日志 `item_type` 与 `target`，确认 `video_chunk -> upload_video_chunk` |
| 视频上传 500 | `Failed to insert video chunk` | 迁移未就绪或 DB schema 不匹配 | 确认 server 启动日志出现 migration ensured；检查 DB 路径与权限 |
| 卡片显示 `Unknown` | UI app/title 空 | chunk 未携带 app/window 元数据或历史数据未补齐 | 确认上传 metadata 包含 `app_name/window_title`（兼容 `active_*`）；新数据会修复 |
| 搜索页报错 | `NoneType` / search render error | video-only 结果渲染分支异常（历史问题） | 升级到当前修复版本；运行 `test_phase1_search_debug_render.py` |
| 录制 toggle 后看似离线 | FFmpeg watchdog stop + offline | 运行时 toggle 语义与预期不一致 | 当前语义是 pause/resume monitor source；检查 heartbeat 与 config 状态 |
| 采集异常慢 | `Slow ffmpeg stdin write` | pipe 写入拥塞或机器负载高 | 观察 `OPENRECALL_VIDEO_PIPE_WRITE_WARN_MS` 告警，必要时降 FPS/减少监视器数 |
| SCK 启动失败或 monitor_id 漂移 | `Display not found` / `Timed out starting SCK stream` | 权限、显示器拓扑变化、SCK 回调超时 | 新策略为“先重试再降级 legacy，并定时自动回切”；用 `/api/v1/vision/status` 查看 `status/active_mode/last_sck_error_code` |

## 测试与验证 / Testing and Verification

### 中文

最小回归（覆盖 Phase 0 + Phase 1，推荐先跑）：

```bash
cd /Users/pyw/new/MyRecall
python3 -m pytest tests/test_phase0_gates.py -v
python3 -m pytest tests/test_phase1_search_debug_render.py -v
python3 -m pytest tests/test_phase1_server_startup.py -v
python3 -m pytest tests/test_phase1_monitor_upload_api.py -v
python3 -m pytest tests/test_phase5_buffer.py -k TestUploaderConsumer -v
```

全量（默认排除 e2e/perf/security/model/manual）：

```bash
cd /Users/pyw/new/MyRecall
python3 -m pytest
```

### English

Recommended minimal regression suite (covers Phase 0 + Phase 1):

```bash
cd /Users/pyw/new/MyRecall
python3 -m pytest tests/test_phase0_gates.py -v
python3 -m pytest tests/test_phase1_search_debug_render.py -v
python3 -m pytest tests/test_phase1_server_startup.py -v
python3 -m pytest tests/test_phase1_monitor_upload_api.py -v
python3 -m pytest tests/test_phase5_buffer.py -k TestUploaderConsumer -v
```

Run full default suite:

```bash
cd /Users/pyw/new/MyRecall
python3 -m pytest
```

## v3 路线图与验证文档 / v3 Roadmap and Validation Docs

高信号文档：

1. 路线图状态: `/Users/pyw/new/MyRecall/v3/milestones/roadmap-status.md`
2. Phase 0 计划与验证:
   - `/Users/pyw/new/MyRecall/v3/plan/02-phase-0-detailed-plan.md`
   - `/Users/pyw/new/MyRecall/v3/results/phase-0-validation.md`
3. Phase 1 计划与验证:
   - `/Users/pyw/new/MyRecall/v3/plan/03-phase-1-detailed-plan.md`
   - `/Users/pyw/new/MyRecall/v3/results/phase-1-validation.md`
   - `/Users/pyw/new/MyRecall/v3/results/phase-1-post-baseline-changelog.md`
4. 架构决策（ADR）:
   - `/Users/pyw/new/MyRecall/v3/decisions/ADR-0001-python-first.md`
   - `/Users/pyw/new/MyRecall/v3/decisions/ADR-0002-thin-client-architecture.md`
   - `/Users/pyw/new/MyRecall/v3/decisions/ADR-0003-p3-memory-scope.md`
   - `/Users/pyw/new/MyRecall/v3/decisions/ADR-0004-speaker-id-optional.md`
5. 阶段验收门槛: `/Users/pyw/new/MyRecall/v3/metrics/phase-gates.md`
6. 隐私与保留策略:
   - `/Users/pyw/new/MyRecall/v3/results/pii-classification-policy.md`
   - `/Users/pyw/new/MyRecall/v3/results/retention-policy-design.md`
7. 参考资料:
   - `/Users/pyw/new/MyRecall/v3/references/encryption.md`
   - `/Users/pyw/new/MyRecall/v3/references/hardware.md`
   - `/Users/pyw/new/MyRecall/v3/references/myrecall-vs-screenpipe.md`

## 安全与隐私说明 / Security and Privacy Notes

### 中文

1. 数据本地优先存储，路径由 `OPENRECALL_SERVER_DATA_DIR` 与 `OPENRECALL_CLIENT_DATA_DIR` 控制。
2. `screenpipe` 在本仓库中是 **reference-only**，不是运行时依赖。
3. 绝对不要把真实 API key 提交到仓库；`*.env` 中应使用占位符或本地私有值。
4. 推荐在加密卷或受控目录保存服务端数据目录。

### English

1. Data is local-first, controlled by server/client data dir envs.
2. `screenpipe` is reference-only in this workspace, not a runtime dependency.
3. Never commit real API keys; keep secrets in private env files.
4. Prefer encrypted/controlled storage for server data.

## 贡献与许可证 / Contributing and License

欢迎通过 issue/PR 提交问题与改进建议。  
Contributions are welcome via issues and pull requests.

License: AGPLv3 (`/Users/pyw/new/MyRecall/LICENSE`).
