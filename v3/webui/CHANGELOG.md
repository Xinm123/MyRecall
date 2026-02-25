# WebUI 变更日志

> 记录粒度：按 Phase 汇总 WebUI 相关变化（新增/修改/废弃/兼容）。

## Phase 0

### 新增
- 无新增页面。

### 修改
- 运行时架构进入 v3 基线：引入 `/api/v1/*` 路径体系，但 WebUI 页面入口仍保持 `/`、`/timeline`、`/search`。
- 控制面与页面功能保持兼容；Phase 0 明确“不做 Web UI 改动”。

### 废弃
- 无。

### 影响面
- 前端用户操作路径基本不变。
- 后端 API 版本化为后续阶段（分页、远程优先）打基础。

### 验证
- 见 `/Users/pyw/new/MyRecall/v3/results/phase-0-validation.md` 的 API smoke 与 gate 结果。

### 证据
- `/Users/pyw/new/MyRecall/v3/plan/02-phase-0-detailed-plan.md`（No Web UI changes）
- `/Users/pyw/new/MyRecall/v3/results/phase-0-validation.md`

---

## Phase 1

### 新增
- 无新增 Web 页面，但数据源能力扩展：
  - `GET /api/v1/timeline`
  - `GET /api/v1/frames/:id`
  - 视频 OCR 可检索数据进入搜索链路

### 修改
- `/timeline` 页面在服务端组装的 `image_url` 可指向帧接口（`/api/v1/frames/:id`），支持视频帧展示。
- `/search` 页面对“仅视频结果”路径完成稳定性修复（避免 debug 渲染崩溃）。
- 搜索/timeline v1 分页能力增强并兼容 `page/page_size`（后端兼容，不破坏旧参数）。
- 文档链路口径统一：明确上传异常路径为 `client buffer -> UploaderConsumer -> /api/upload 或 /api/v1/upload -> worker`，并补充 upload status 接口在排障中的作用。
- 采集鲁棒性文档化：新增 SCK 延迟降级、legacy 自动回切、监控器 watcher、结构化错误码等行为说明。
- Control Center 排障口径更新：录制 toggle 明确为 pause/resume（非客户端退出），并新增 `/api/vision/status` 与 `/api/v1/vision/status` 作为采集健康诊断入口。
- Client 侧视频 chunk 命名改为 UTC monitor 时间戳格式：`monitor_{monitor_id}_{YYYY-MM-DD_HH-MM-SS}.mp4`，降低重启后序号重置带来的排障歧义。

### 废弃
- 无。

### 影响面
- 用户可在既有页面体验到视频链路带来的检索/回看增强。
- 页面 URL 不变，但展示数据来源从“纯截图”扩展到“截图 + 视频帧”。
- 运维排障从“仅看日志”提升到“日志 + capture health API”双通道观测。

### 验证
- `tests/test_phase1_timeline_api.py`
- `tests/test_phase1_search_integration.py`
- `tests/test_phase1_search_debug_render.py`
- `tests/test_phase1_gates.py`

### 证据
- `/Users/pyw/new/MyRecall/v3/results/phase-1-validation.md`
- `/Users/pyw/new/MyRecall/v3/results/phase-1-post-baseline-changelog.md`

---

## Phase 1.5 (Metadata Precision Upgrade)

### 新增
- Timeline/Search API 返回中新增 `focused` (bool|null) 和 `browser_url` (string|null) 字段。
- Metadata resolver: 帧级元数据优先于 chunk 级，未知值使用 NULL 而非空字符串或默认值。
- Offset guard: 帧写入前预检验时间窗口、偏移单调性、必填字段，拒绝不合规帧并输出结构化日志。
- OCR 引擎名: `ocr_text.ocr_engine` 记录实际提供者名称（rapidocr/doctr/openai 等），而非硬编码默认值。
- v3_005 迁移: `video_chunks` 表新增 `start_time`/`end_time` 列用于精确偏移校验。

### 修改
- `/api/v1/timeline` 响应 frame dict 增加 `focused`、`browser_url` 字段。
- `/api/v1/search` 保持旧字段语义不变，并追加可选 `focused/browser_url`（video-frame 有值，snapshot 为 `null`）。
- `/api/memories/recent` 和 `/api/memories/latest` 的 frame memory 增加 `focused`、`browser_url` 字段。
- 帧写入不再依赖 schema DEFAULT（`focused=0`、`browser_url=''`），改为显式写 NULL 表示未知。

### 废弃
- 无。

### 影响面
- 前端消费 timeline/search 数据时可获取窗口焦点状态和浏览器 URL（新增字段可忽略不影响旧逻辑）。
- NULL 语义变更: `focused=null` 表示"未知"而非"未聚焦"；`browser_url=null` 表示"未知"而非空字符串。

### 验证
- `tests/test_phase1_5_metadata_resolver.py` (12 passed)
- `tests/test_phase1_5_offset_guard.py` (8 passed)
- `tests/test_phase1_5_ocr_engine.py` (3 passed)
- `tests/test_phase1_5_focused_browser_url.py` (10 passed)
- Full regression: `python3 -m pytest tests/test_phase1_* -v` → 170 passed, 8 skipped, 0 failed

### 证据
- `/Users/pyw/new/MyRecall/v3/results/phase-1-validation.md` (v1.6)
- `/Users/pyw/new/MyRecall/v3/results/phase-1-post-baseline-changelog.md` (v1.2)

### 证据矩阵

| Change | Code Path | Test Command | Result | UTC Timestamp |
|---|---|---|---|---|
| Resolver metadata precision (`frame > chunk > null`) | `/Users/pyw/new/MyRecall/openrecall/server/video/metadata_resolver.py` | `python3 -m pytest tests/test_phase1_5_metadata_resolver.py -v` | 12 passed | 2026-02-08T07:50:52Z |
| Timeline/Search optional metadata fields (`focused/browser_url`) | `/Users/pyw/new/MyRecall/openrecall/server/api_v1.py`, `/Users/pyw/new/MyRecall/openrecall/server/database/sql.py` | `python3 -m pytest tests/test_phase1_5_focused_browser_url.py -v` | 10 passed | 2026-02-08T07:50:52Z |
| OCR engine true-value persistence | `/Users/pyw/new/MyRecall/openrecall/server/ai/base.py`, `/Users/pyw/new/MyRecall/openrecall/server/ai/providers.py`, `/Users/pyw/new/MyRecall/openrecall/server/video/processor.py` | `python3 -m pytest tests/test_phase1_5_ocr_engine.py -v` | 3 passed | 2026-02-08T07:50:52Z |
| Offset guard reject-write + structured logging | `/Users/pyw/new/MyRecall/openrecall/server/video/processor.py` | `python3 -m pytest tests/test_phase1_5_offset_guard.py -v` | 8 passed | 2026-02-08T07:50:52Z |
| End-to-end WebUI-visible regression closure | `/Users/pyw/new/MyRecall/openrecall/server/api_v1.py`, `/Users/pyw/new/MyRecall/openrecall/server/database/sql.py`, `/Users/pyw/new/MyRecall/openrecall/server/video/processor.py` | `python3 -m pytest tests/test_phase1_* -v` | 170 passed, 8 skipped | 2026-02-08T07:50:08Z |

---

## Phase 2.0 (Planning Baseline)

### 新增
- 新增 `/Users/pyw/new/MyRecall/v3/results/phase-2-validation.md` 模板，用于 Phase 2.0 执行后回填验收证据。

### 修改
- 补充 `/Users/pyw/new/MyRecall/v3/webui/pages/timeline.md`：标注统一 timeline 的 audio 并入目标已进入 Phase 2.0 规划，当前页面尚未生效。
- 补充 `/Users/pyw/new/MyRecall/v3/webui/pages/search.md`：标注音频 FTS 检索链路处于执行前规划基线，当前页面仍以视觉检索呈现为主。
- 文档口径对齐：Phase 2 gate `2-F-04` 的验收语句保持与 gate 真源一致（`audio_fts`）；若实现表名为 `audio_transcriptions_fts`，须在验证报告提供映射证据。

### 废弃
- 无。

### 影响面
- 本次仅文档治理更新，不引入运行时 WebUI 行为变化。

### 验证
- 文档一致性检查：Phase 2 计划、roadmap、validation 模板与 WebUI 页面说明对齐。

### 证据
- `/Users/pyw/new/MyRecall/v3/plan/04-phase-2-detailed-plan.md`
- `/Users/pyw/new/MyRecall/v3/milestones/roadmap-status.md`
- `/Users/pyw/new/MyRecall/v3/results/phase-2-validation.md`
- `/Users/pyw/new/MyRecall/v3/webui/pages/timeline.md`
- `/Users/pyw/new/MyRecall/v3/webui/pages/search.md`

---

## Phase 2.5 (Complete — WebUI Audio & Video Dashboard Pages)

### 新增
- 新增 `/audio` 页面：Audio pipeline 综合 dashboard（chunk 列表 + 分页过滤 + inline 播放 + transcription 浏览 + queue 状态 + 统计概览）。
- 新增 `/video` 页面：Video pipeline 综合 dashboard（chunk 列表 + 分页过滤 + inline 播放 + frame gallery + queue 状态 + 统计概览）。
- 新增 `icon_audio()` 和 `icon_video()` SVG macro 于 `icons.html`。
- 新增 6 个 API endpoints：
  - `GET /api/v1/video/chunks` — video chunks 分页列表（status/monitor_id filter）
  - `GET /api/v1/video/chunks/<id>/file` — mp4 文件 serving（path traversal prevention）
  - `GET /api/v1/video/frames` — frames 分页列表（chunk_id/app/window/time filter + OCR snippet）
  - `GET /api/v1/video/stats` — video 聚合统计
  - `GET /api/v1/audio/chunks/<id>/file` — WAV 文件 serving（path traversal prevention）
  - `GET /api/v1/audio/stats` — audio 聚合统计

### 修改
- `layout.html` 导航条新增 Audio/Video icon 链接，`data-current-view` 高亮逻辑扩展到 5 个页面。
- `GET /api/v1/audio/chunks` 新增 `device` 可选过滤参数（additive，不破坏已有行为）。
- Navigation 从 3 page icons 扩展到 5 page icons（+Audio/Video）。

### 废弃
- 无。

### 影响面
- 用户可通过独立 dashboard 查看和管理 audio/video pipeline 数据，减少对命令行检查的依赖。
- 新增页面不影响已有页面（`/`、`/timeline`、`/search`）的行为。
- 新增媒体 file serving endpoints 为 Phase 3+ 提供基础。
- Navigation 变更影响所有页面（layout.html 全局变化）。

### 验证
- `tests/test_phase25_api.py` — 30 passed, 0 failed
- `tests/test_phase25_audio_page.py` — 8 passed, 0 failed
- `tests/test_phase25_video_page.py` — 8 passed, 0 failed
- `tests/test_phase25_navigation.py` — 13 passed, 0 failed
- Full regression: 553 passed, 12 skipped, 0 failed

### 证据
- `/Users/pyw/new/MyRecall/v3/plan/05-phase-2.5-webui-audio-video-detailed-plan.md`
- `/Users/pyw/new/MyRecall/v3/results/phase-2.5-validation.md`
- `/Users/pyw/new/MyRecall/v3/webui/pages/audio.md`
- `/Users/pyw/new/MyRecall/v3/webui/pages/video.md`

### 证据矩阵

| Change | Code Path | Test Command | Result | UTC Timestamp |
|---|---|---|---|---|
| Audio/Video dashboard pages + API endpoints | `openrecall/server/app.py`, `openrecall/server/api_v1.py`, `openrecall/server/database/sql.py` | `python3 -m pytest tests/test_phase25_api.py -v` | 30 passed | 2026-02-12 |
| Audio dashboard page (SSR + Alpine.js) | `openrecall/server/templates/audio.html` | `python3 -m pytest tests/test_phase25_audio_page.py -v` | 8 passed | 2026-02-12 |
| Video dashboard page (SSR + Alpine.js) | `openrecall/server/templates/video.html` | `python3 -m pytest tests/test_phase25_video_page.py -v` | 8 passed | 2026-02-12 |
| Navigation icons + highlighting (5-page toolbar) | `openrecall/server/templates/layout.html`, `openrecall/server/templates/icons.html` | `python3 -m pytest tests/test_phase25_navigation.py -v` | 13 passed | 2026-02-12 |
| Path traversal prevention (GATING 2.5-DG-01) | `openrecall/server/api_v1.py` | `python3 -m pytest tests/test_phase25_api.py -k "PathSecurity or path_traversal" -v` | 4 passed | 2026-02-12 |
| Full regression closure | All Phase 0/1/2/2.5 code | `python3 -m pytest tests/ -v --tb=short` | 553 passed, 12 skipped | 2026-02-12 |

---

## Phase 2.6: Audio Freeze Governance WebUI Contract（计划态）

**日期**: 2026-02-25（计划；实际执行时更新）
**状态**: ⬜️ Planned
**Phase 2.6 详细计划**: `v3/plan/07-phase-2.6-audio-freeze-governance-detailed-plan.md`
**Code Changes**: NONE（本阶段仅更新文档契约）

### 变更内容（计划态，非 Done）

| 变更项 | 文件 | 当前行为 | 目标契约（Phase 2.6 声明） | 收敛阶段 |
|--------|------|---------|--------------------------|---------|
| `/audio` 页面可见性契约 | `v3/webui/ROUTE_MAP.md` | 可见（nav icon 常驻） | **默认隐藏**；仅 debug 模式或批准 ExceptionRequest 激活期可见 | 文档声明（Phase 3 代码收敛） |
| Audio nav icon 渲染 | `v3/webui/ROUTE_MAP.md` | 5-page toolbar 常驻 | **Phase 2.6 target：默认不渲染** | Phase 3 |
| Search/Chat grounding 模态 | `v3/webui/DATAFLOW.md` | 可能混入 audio candidate | **vision-only**；audio 候选默认排除 | Phase 3 → Phase 4 |
| Timeline 默认显示范围 | `v3/webui/DATAFLOW.md` | mixed 默认（video + audio） | **target 默认 video-only**；audio 仅 explicit param/debug | Phase 3 |
| Audio Freeze 全链路契约 | `v3/webui/DATAFLOW.md` | 无 freeze contract 条目 | 新增 Section 3 第 6 条（Audio Freeze 全链路契约声明） | Phase 2.6 |
| `/audio` 页面 Phase 2.6 状态标注 | `v3/webui/pages/audio.md` | 无 freeze 状态标注 | 新增 Section 10：Phase 2.6 Freeze Status | Phase 2.6 |
| `/video` 页面 Phase 2.6 对比说明 | `v3/webui/pages/video.md` | 无 Phase 2.6 说明 | 新增 Section 10：Phase 2.6 Freeze Scope — Video 不受影响的声明 | Phase 2.6 |

### 关联 Gates（authority: `v3/metrics/phase-gates.md`）

- 2.6-G-03: UI/retrieval contract verified — 本批文档更新是 2.6-G-03 的主要 evidence artifact
- 2.6-G-01/G-02: Capture/Processing pause — WebUI 入口契约间接支撑

### 验证命令（计划态）

```bash
# 验证 5 个 WebUI 文件均含 Phase 2.6 标注
grep -l "Phase 2.6" \
  v3/webui/CHANGELOG.md \
  v3/webui/ROUTE_MAP.md \
  v3/webui/DATAFLOW.md \
  v3/webui/pages/audio.md \
  v3/webui/pages/video.md
# 预期：5 行
```

---

## 未来维护规则（强约束）

每次新增 `phase-*-validation.md` 时：
1. 在本文件追加该 Phase 的 WebUI 变化条目。
2. 同步更新受影响页面文档（`pages/*.md`）。
3. 如链路或接口发生变化，更新 `DATAFLOW.md` 与 `ROUTE_MAP.md`。
