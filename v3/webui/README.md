# WebUI 文档中台

本目录用于描述 MyRecall WebUI 的页面能力、数据链路、接口映射与维护规则。

## 覆盖范围

当前覆盖页面与组件：

- `/`（Home Grid）
- `/timeline`
- `/search`
- `/audio`
- `/video`
- Control Center（布局内全局控制面板）

## Source of Truth

- 页面路由：`openrecall/server/app.py`
- UI 模板：`openrecall/server/templates/layout.html`
- 页面模板：
  - `openrecall/server/templates/index.html`
  - `openrecall/server/templates/timeline.html`
  - `openrecall/server/templates/search.html`
  - `openrecall/server/templates/audio.html`
  - `openrecall/server/templates/video.html`
- API：
  - `openrecall/server/api.py`
  - `openrecall/server/api_v1.py`

## 阅读顺序

1. `OVERVIEW.md`
2. `ROUTE_MAP.md`
3. `DATAFLOW.md`
4. `COMPARISON_V2_TO_V3.md`
5. `pages/*.md`
6. `CHANGELOG.md`

## 文档契约

1. 所有关键行为使用双轨叙事：`Current (verified)` 与 `Target (contract)`。
2. 历史阶段内容必须标记 `historical`，不与 current 混写。
3. 对 screenpipe 的引用必须声明对齐层级：`semantic` / `discipline` / `divergence`。
4. 使用相对路径作为默认引用，避免机器绑定绝对路径。

## 维护规则（按 Phase）

每次新增/更新 `phase-*-validation.md` 时，必须同步更新：

1. `CHANGELOG.md`
2. 受影响页面文档（`pages/*.md`）
3. 若链路变化，更新 `DATAFLOW.md`
4. 若路由/API 变化，更新 `ROUTE_MAP.md`

## 文件导航

- 总览：`OVERVIEW.md`
- 路由/API 映射：`ROUTE_MAP.md`
- 全局数据流：`DATAFLOW.md`
- 前后对比：`COMPARISON_V2_TO_V3.md`
- 变更记录：`CHANGELOG.md`
- 页面文档：`pages/`
- 模板：`templates/`
