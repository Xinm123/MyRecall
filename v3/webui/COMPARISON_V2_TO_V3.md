# WebUI 对比：V2 形态 -> V3（Phase 0/1）

## 1. 说明

本对比使用以下基线：
- 旧形态基线：`/Users/pyw/new/MyRecall/v3/references/myrecall-v2-analysis.md`
- V3 实施证据：
  - `/Users/pyw/new/MyRecall/v3/results/phase-0-validation.md`
  - `/Users/pyw/new/MyRecall/v3/results/phase-1-validation.md`
  - `/Users/pyw/new/MyRecall/v3/results/phase-1-post-baseline-changelog.md`

## 2. 变化总览（按维度）

| 维度 | V2 基线行为 | V3 当前行为（Phase 0/1） | 影响 |
|---|---|---|---|
| 页面入口 | 主要使用 `/`、`/timeline`、`/search` | 页面入口保持不变 | 用户路径稳定，学习成本低 |
| 控制面 | Control Center 通过 `/api/config` 与 `/api/heartbeat` 驱动状态 | 机制延续，保留轮询与开关语义 | 兼容性高，运行时可观测性保持 |
| 搜索结果渲染 | search debug 路径在特殊数据集可能脆弱 | Phase 1 修复 video-only 结果渲染崩溃 | 稳定性提升，错误率下降 |
| 数据来源 | 以 screenshot 链路为主 | 扩展到 screenshot + video frame（通过 `image_url` 与 `/api/v1/frames/:id`） | 时间回放与检索样本更完整 |
| API 形态 | legacy `/api/*` 为主 | 增加 `/api/v1/*`（分页、版本化、remote-first 准备） | 对外契约更清晰，为远程架构铺路 |
| 上传韧性 | 上传失败后的可见路径说明较弱 | 明确 `buffer -> uploader retry -> upload API -> worker` 链路与状态查询接口 | 异常场景可解释性更强，排障成本下降 |
| Timeline 能力 | 页面级时间滑杆，后端数据偏截图语义 | Phase 1 增强到视频帧时间线 API 能力（`/api/v1/timeline`） | 后续 UI 迭代空间变大 |

## 3. 行为对比（页面）

### 3.1 Home Grid (`/`)

| 项目 | 之前 | 当前 | 证据 |
|---|---|---|---|
| 展示对象 | 最近记忆条目 | 仍为最近记忆条目，但可包含视频链路派生数据 | `app.py:index()` + `index.html` |
| 刷新策略 | 轮询增量/全量刷新 | 保持 5 秒轮询（`latest + recent` 双通道） | `index.html` 中 `checkNew()/refreshRecent()` |
| AI 文案显示 | 受开关影响 | 受 `ui_show_ai` 控制，关闭时统一隐藏 | `layout.html` + `index.html` |

### 3.2 Timeline (`/timeline`)

| 项目 | 之前 | 当前 | 证据 |
|---|---|---|---|
| 页面形态 | slider + 图片显示 | 形态保持 | `timeline.html` |
| 图片来源 | 主要是截图静态文件 | 支持 `image_url` 指向帧接口（可按需抽帧） | `app.py:timeline()` + `api_v1.py:serve_frame()` |
| 时间范围 API | 非主路径 | 已具备 `/api/v1/timeline` 标准接口能力 | `api_v1.py:timeline_api()` |

### 3.3 Search (`/search`)

| 项目 | 之前 | 当前 | 证据 |
|---|---|---|---|
| 数据来源 | 混合检索（debug 视角） | 混合检索延续 + 视频 OCR 结果可入检索 | `app.py:search()` + `search.engine` |
| 结果稳定性 | video-only 场景存在崩溃风险 | 已修复（post-baseline hardening） | `phase-1-post-baseline-changelog.md` |
| 展示维度 | 排名与分数可视化 | 保持并强化对多来源候选的展示 | `search.html` |

### 3.4 Control Center（布局内）

| 项目 | 之前 | 当前 | 证据 |
|---|---|---|---|
| 开关集合 | recording/upload/ai/ui | 集合保持一致 | `layout.html` + `api.py` |
| 在线状态 | heartbeat 驱动 | 机制保持，`client_online` 语义不变 | `api.py:get_config()/heartbeat()` |
| 兼容层 | 主要 legacy | v1 同步具备 config/heartbeat 路径 | `api_v1.py` |

## 4. 风险与收益

### 收益
1. 页面 URL 与操作习惯稳定，迁移成本低。
2. 数据链路增强（视频帧 + OCR）带来更强的检索与回看能力。
3. v1 API 让 WebUI 与 remote-first 路线更易对齐。

### 风险
1. 当前 UI 仍是 SSR + 轮询，面对大规模数据时体验上限受限。
2. 上传暂停或网络抖动时，页面数据会出现可预期延迟（需结合 buffer 与 upload/status 观察）。
3. `/search` 页面仍以 debug 展示为主，和正式产品检索体验有差距。
4. Timeline 仍是单页 slider 形态，尚未演进到流式/增量时间轴。

## 5. 结论

V3 在 Phase 0/1 的 WebUI策略是“稳定入口 + 增强数据底座”：
- 页面层面保持轻改，避免重构风险。
- 后端接口与数据能力显著增强。
- 为后续 Phase 3/4 的统一检索与聊天页面演进留出结构化空间。
