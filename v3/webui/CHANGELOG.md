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

## 未来维护规则（强约束）

每次新增 `phase-*-validation.md` 时：
1. 在本文件追加该 Phase 的 WebUI 变化条目。
2. 同步更新受影响页面文档（`pages/*.md`）。
3. 如链路或接口发生变化，更新 `DATAFLOW.md` 与 `ROUTE_MAP.md`。
