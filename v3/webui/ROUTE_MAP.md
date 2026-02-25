# WebUI 路由与接口映射

## 1. 页面路由

| 页面 | URL | Handler | 模板 |
|---|---|---|---|
| Home Grid | `/` | `openrecall/server/app.py:index()` | `index.html` |
| Timeline | `/timeline` | `openrecall/server/app.py:timeline()` | `timeline.html` |
| Search | `/search` | `openrecall/server/app.py:search()` | `search.html` |
| Audio Dashboard | `/audio` | `openrecall/server/app.py:audio()` | `audio.html` |
| Video Dashboard | `/video` | `openrecall/server/app.py:video()` | `video.html` |
| Control Center | 布局内组件 | `layout.html` 前端脚本 | `layout.html` |

> Target contract note: `/audio` 页面属于非默认路径；仅在审批后的调试模式中显式可见。

## 2. 页面依赖 API（Current）

### 2.1 Legacy API

| API | 用途 | 主要调用方 |
|---|---|---|
| `GET /api/memories/recent` | 最近记忆列表 | Home Grid |
| `GET /api/memories/latest` | 增量刷新 | Home Grid |
| `GET /api/search` | 旧 JSON 搜索接口 | 兼容外部调用 |
| `GET/POST /api/config` | 运行时配置读写 | Control Center |
| `POST /api/heartbeat` | 客户端在线状态 | client runtime |
| `GET /api/vision/status` | 采集健康诊断 | Control Center/排障 |
| `POST /api/upload` | 上传入口 | client uploader |
| `GET /api/upload/status` | 上传断点状态 | client uploader |

### 2.2 v1 API

| API | 用途 | Current 语义 |
|---|---|---|
| `GET /api/v1/search` | 标准分页检索接口 | 空 `q` 返回空分页；`start_time` 当前未强制 |
| `GET /api/v1/timeline` | 时间范围分页查询 | 默认 mixed（video + audio）；支持 `source` 过滤 |
| `GET /api/v1/frames/:id` | 帧服务 | 文件直出 + 按需抽帧 fallback |
| `GET/POST /api/v1/config` | v1 配置读写 | 与 legacy 语义一致 |
| `POST /api/v1/heartbeat` | v1 心跳 | 远程模式替代入口 |
| `GET /api/v1/vision/status` | v1 健康诊断 | 只读 |
| `POST /api/v1/upload` | v1 上传入口 | 视频/音频/截图摄取 |
| `GET /api/v1/upload/status` | v1 上传状态 | 断点续传查询 |
| `GET /api/v1/audio/chunks` | 音频 chunk 列表 | 支持 `device` 过滤 |
| `GET /api/v1/audio/transcriptions` | 音频转写列表 | 分页与时间过滤 |
| `GET /api/v1/audio/chunks/<id>/file` | 音频文件服务 | WAV |
| `GET /api/v1/audio/stats` | 音频统计 | dashboard 用 |
| `GET /api/v1/video/chunks` | 视频 chunk 列表 | dashboard 用 |
| `GET /api/v1/video/chunks/<id>/file` | 视频文件服务 | mp4 |
| `GET /api/v1/video/frames` | 帧列表 | dashboard 用 |
| `GET /api/v1/video/stats` | 视频统计 | dashboard 用 |

## 3. Current vs Target（关键差异）

| Surface | Current (verified) | Target (Phase 3/4 contract) | Phase 2.6 Contract Note |
|---|---|---|---|
| `/api/v1/search` empty `q` | 空分页 | browse/feed（有界范围） | — |
| `/api/v1/search` `start_time` | 未强制 | 强制（MyRecall policy） | — |
| Search modality | 仍可能混入 audio candidate | Search/Chat grounding 走 vision-only | **Phase 2.6 target：audio 候选默认排除**；ADR-0005 vision-only contract |
| WebUI audio visibility | `/audio` 页面可见 | 默认隐藏 audio 入口；仅调试模式可见 | **Phase 2.6 target：默认隐藏**；Current 为可见（已知 deviation，Phase 3 收敛） |
| `/api/v1/timeline` | mixed 默认 | target 默认 video-only；audio 仅显式参数/调试模式 | **Phase 2.6 target：video-only**；Current mixed（已知 deviation，Phase 3 收敛） |
| Audio nav icon | nav toolbar 常驻 | 默认不渲染 | **Phase 2.6 target：默认不渲染**；Current 常驻（已知 deviation，Phase 3 收敛） |

## 4. Screenpipe 对齐说明

- `semantic`：search 过滤和 browse 心智模型对齐。
- `discipline`：有界时间查询与小范围分页实践对齐。
- `divergence`：vision-only MVP 与参数策略为 MyRecall 有意差异。

## 5. 路由一致性检查

- [x] 页面路由与模板映射存在且可追溯。
- [x] v1 search/timeline/frames 路由存在。
- [x] audio/video dashboard 路由与 API 存在。
- [x] control-center 配置与心跳接口存在。
