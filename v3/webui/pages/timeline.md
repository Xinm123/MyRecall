# Timeline 页面文档（`/timeline`）

## 1. 页面定位

- 目标：按时间顺序回看历史画面。
- 用户：回顾特定时间段行为的用户与调试人员。
- 文档模式：`Current (verified)` 与 `Target positioning` 双轨。

## 2. 入口与路由

- URL：`/timeline`
- 后端路由：`openrecall/server/app.py` 中 `timeline()`
- 模板：`openrecall/server/templates/timeline.html`
- 布局：`openrecall/server/templates/layout.html`

## 3. Current (Verified)

1. `/timeline` 页面当前由 `get_recent_memories(limit=1000)` 预聚合注入 `timeline_items`。
2. 页面主视图展示 `timestamp + image_url`，偏向视觉回看。
3. `/api/v1/timeline` 当前默认返回 mixed 数据（video frames + audio transcriptions）。
4. `/api/v1/timeline` 支持 `source` 过滤（如 `source=audio` / `source=video`）。

关键证据路径：

- `openrecall/server/app.py:timeline()`
- `openrecall/server/api_v1.py:timeline_api()`
- `tests/test_phase2_timeline.py`

## 4. Target Positioning

1. Timeline 保持运维/回放视角，可继续 mixed 展示。
2. Search/Chat grounding 维持 vision-only 主线（不依赖 timeline mixed 默认）。
3. 文档语义避免把 “Search/Chat 的 vision-only” 错写为 “Timeline API 已 vision-only”。

## 5. 数据流（Current）

```mermaid
flowchart LR
  U["浏览器 /timeline"] --> R["app.py:timeline()"]
  R --> Q["sql_store.get_recent_memories(limit=1000)"]
  Q --> T["render timeline.html"]
  T --> I["timeline_items: timestamp + image_url"]
  U --> V1["/api/v1/timeline?start_time&end_time&source(optional)"]
  V1 --> M["api_v1 timeline: merge frames + transcriptions"]
```

## 6. 接口映射

| 接口 | 方法 | Current | Target |
|---|---|---|---|
| `/timeline` | GET | SSR 页面，视觉回看主入口 | 保持 |
| `/api/v1/timeline` | GET | 默认 mixed；可按 `source` 过滤 | 保持 mixed 作为 ops 视角 |
| `/api/v1/frames/:id` | GET | 帧图片服务（含 fallback） | 证据 drill-down 基础能力 |

## 7. 风险与盲点

1. 把 timeline 文档写成“vision-only”会与 API 现实冲突。
2. 若忽略 mixed 默认行为，Chat/Search 评估时会错误推断数据语义。
3. Audio Freeze 的主线约束应放在 Search/Chat，而非错误外溢到 timeline API 现实描述。

## 8. 验收清单（文档层）

- [x] 明确 timeline 页面与 timeline API 的语义差异。
- [x] 明确 `/api/v1/timeline` 当前 mixed 默认行为。
- [x] 明确 Search/Chat vision-only 与 timeline mixed 并存关系。

## 9. 相关文档

- `v3/milestones/roadmap-status.md`
- `v3/webui/ROUTE_MAP.md`
- `v3/webui/DATAFLOW.md`
