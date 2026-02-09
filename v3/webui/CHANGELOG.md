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

## 未来维护规则（强约束）

每次新增 `phase-*-validation.md` 时：
1. 在本文件追加该 Phase 的 WebUI 变化条目。
2. 同步更新受影响页面文档（`pages/*.md`）。
3. 如链路或接口发生变化，更新 `DATAFLOW.md` 与 `ROUTE_MAP.md`。
