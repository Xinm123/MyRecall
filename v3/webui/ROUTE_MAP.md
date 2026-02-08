# WebUI 路由与接口映射

## 1. 页面路由映射

| 页面 | URL | Flask Handler | 模板 | 说明 |
|---|---|---|---|---|
| Home Grid | `/` | `openrecall/server/app.py:index()` | `openrecall/server/templates/index.html` | 默认落地页，展示 recent memories |
| Timeline | `/timeline` | `openrecall/server/app.py:timeline()` | `openrecall/server/templates/timeline.html` | 时间滑杆浏览 |
| Search | `/search` | `openrecall/server/app.py:search()` | `openrecall/server/templates/search.html` | 查询与结果调试展示 |
| Control Center | 嵌入布局（无单独 URL） | `layout.html` 中前端脚本 | `openrecall/server/templates/layout.html` | 全局运行时开关 |

## 2. 页面模板关系

```mermaid
flowchart LR
  L["layout.html"] --> I["index.html"]
  L --> T["timeline.html"]
  L --> S["search.html"]
  I --> API1["/api/memories/latest\n/api/memories/recent"]
  T --> APIT["timeline_items(JSON) from server"]
  S --> APIS["/search query -> search_debug"]
  L --> APIC["/api/config\nPOST /api/config"]
  L -.排障.-> APIV["/api/vision/status\n/api/v1/vision/status"]
```

## 3. Control Center 接口映射

| 功能 | 前端触发 | API | 方法 | 说明 |
|---|---|---|---|---|
| 拉取配置 | `refreshConfig()` | `/api/config` | `GET` | 每 5 秒轮询 |
| 修改开关 | `toggleSetting(key)` | `/api/config` | `POST` | 更新 `recording_enabled/upload_enabled/ai_processing_enabled/ui_show_ai` |
| 采集健康诊断 | 手工调用（排障） | `/api/vision/status` | `GET` | 返回 `status/active_mode/last_sck_error_code/selected_monitors` |
| 事件广播 | `openrecall-config-changed` | 前端事件 | - | 通知页面刷新数据 |
| 心跳（由 client 发起） | Client runtime | `/api/heartbeat` | `POST` | 更新 `client_online` 状态 |

## 4. 页面依赖 API（本计划要求）

### 4.1 Legacy API

| API | 用途 | 主要调用方 |
|---|---|---|
| `GET /api/memories/recent` | 拉取最近记忆（含状态更新） | `index.html` |
| `GET /api/memories/latest` | 拉取增量记忆 | `index.html` |
| `GET /api/search` | 旧搜索接口（JSON） | 外部调用/兼容 |
| `GET /api/config` | 读运行时配置 | `layout.html` |
| `POST /api/config` | 写运行时配置 | `layout.html` |
| `POST /api/heartbeat` | 客户端心跳 | client 进程（间接影响 UI） |
| `GET /api/vision/status` | 采集健康诊断（只读） | Control Center 排障/运维脚本 |
| `POST /api/upload` | 截图/视频入口（视频会转发到 v1 视频处理） | client uploader（间接影响 UI 数据新鲜度） |
| `GET /api/upload/status` | 上传断点状态查询 | client uploader（间接影响 UI 数据新鲜度） |

### 4.2 v1 API

| API | 用途 | 与 WebUI 的关系 |
|---|---|---|
| `GET /api/v1/search` | v1 检索 | 目前页面主入口是 `/search`，但 v1 是远程优先标准接口 |
| `GET /api/v1/timeline` | 时间范围分页查询 | timeline 数据源能力（server 侧可接入） |
| `GET /api/v1/frames/:id` | 帧图片服务（含按需抽帧 fallback） | timeline/search 的 `image_url` 可指向该接口 |
| `GET /api/v1/config` | v1 配置读取 | 与 legacy config 语义一致（供远程模式） |
| `POST /api/v1/config` | v1 配置更新 | 与 legacy config 语义一致（供远程模式） |
| `POST /api/v1/heartbeat` | v1 心跳 | 远程模式下可替代 legacy heartbeat |
| `GET /api/v1/vision/status` | v1 采集健康诊断（只读） | 远程模式排障入口 |
| `POST /api/v1/upload` | v1 视频上传入口 | client uploader（间接影响 UI 数据新鲜度） |
| `GET /api/v1/upload/status` | v1 上传断点状态查询 | client uploader（间接影响 UI 数据新鲜度） |

## 5. 上传链路与页面可见性映射

```mermaid
flowchart LR
  C["Client Recorder"] --> B["Local Buffer"]
  B --> U["UploaderConsumer + HTTPUploader"]
  U --> L1["POST /api/upload"]
  U --> L2["POST /api/v1/upload"]
  U --> S1["GET /api/upload/status"]
  U --> S2["GET /api/v1/upload/status"]
  L1 --> DB["SQLite + Server FS"]
  L2 --> DB
  DB --> UI["/, /timeline, /search 展示更新"]
```

说明：
- `upload_enabled=false` 时，client 会继续采集但上传会暂停，页面更新可能延迟。
- 上传恢复后，buffer 数据回放上传，页面展示会追平。

## 6. Route Consistency Checklist

- [x] `app.py` 中页面路由仅有 `/`、`/timeline`、`/search`
- [x] Control Center 为布局内组件，无单独页面路由
- [x] `api.py` 与 `api_v1.py` 均存在 `config/heartbeat/search`
- [x] `api.py` 与 `api_v1.py` 均存在 `vision/status`
- [x] `api_v1.py` 存在 `timeline` 与 `frames/:id`
- [x] `api.py` 与 `api_v1.py` 均存在 `upload` 与 `upload/status`

## 7. 代码来源

- 页面路由：`/Users/pyw/new/MyRecall/openrecall/server/app.py`
- Legacy API：`/Users/pyw/new/MyRecall/openrecall/server/api.py`
- v1 API：`/Users/pyw/new/MyRecall/openrecall/server/api_v1.py`
- 布局模板：`/Users/pyw/new/MyRecall/openrecall/server/templates/layout.html`
