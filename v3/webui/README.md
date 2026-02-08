# WebUI 文档中台

本目录用于系统化描述 MyRecall WebUI 的页面能力、行为变化、数据链路与维护方式。

## 范围

当前仅覆盖已实现页面与组件：
- `/`（Home Grid）
- `/timeline`
- `/search`
- Control Center（布局内全局控制面板）

不在本目录单独展开未来规划页面（如 `/chat`），仅在变更日志中引用 roadmap。

## 事实来源（Source of Truth）

- 页面路由：`/Users/pyw/new/MyRecall/openrecall/server/app.py`
- UI 模板：`/Users/pyw/new/MyRecall/openrecall/server/templates/layout.html`
- 页面模板：
  - `/Users/pyw/new/MyRecall/openrecall/server/templates/index.html`
  - `/Users/pyw/new/MyRecall/openrecall/server/templates/timeline.html`
  - `/Users/pyw/new/MyRecall/openrecall/server/templates/search.html`
- API：
  - `/Users/pyw/new/MyRecall/openrecall/server/api.py`
  - `/Users/pyw/new/MyRecall/openrecall/server/api_v1.py`

## 对比基线

“相比之前”的默认基线固定为：
- `/Users/pyw/new/MyRecall/v3/references/myrecall-v2-analysis.md`
- `/Users/pyw/new/MyRecall/v3/results/phase-0-validation.md`
- `/Users/pyw/new/MyRecall/v3/results/phase-1-validation.md`
- `/Users/pyw/new/MyRecall/v3/results/phase-1-post-baseline-changelog.md`

## 建议阅读顺序

1. `OVERVIEW.md`
2. `ROUTE_MAP.md`
3. `DATAFLOW.md`
4. `COMPARISON_V2_TO_V3.md`
5. `pages/*.md`
6. `CHANGELOG.md`

## 维护规则（按 Phase）

每次新增/更新 `phase-*-validation.md` 时，必须同步更新：
1. `CHANGELOG.md`
2. 受影响页面文档（`pages/*.md`）
3. 如链路变化，更新 `DATAFLOW.md`（含 request/processing/storage/retrieval 与 fallback）
4. 如路由/API 变化，更新 `ROUTE_MAP.md`（含 upload/upload status 这类间接影响页面数据的新鲜度接口）

## 文档质量门槛

- 可读：读者无需打开代码也能理解页面行为。
- 可追溯：关键结论有代码路径或结果文档来源。
- 可维护：新 Phase 可按模板增量维护，不重写历史。

## 文件导航

- 总览：`OVERVIEW.md`
- 路由/API 映射：`ROUTE_MAP.md`
- 全局数据流：`DATAFLOW.md`
- 前后对比：`COMPARISON_V2_TO_V3.md`
- 变更记录：`CHANGELOG.md`
- 页面文档：`pages/`
- 模板：`templates/`
