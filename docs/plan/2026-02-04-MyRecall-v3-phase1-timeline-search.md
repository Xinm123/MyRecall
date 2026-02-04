# Phase 1 (Timeline + Keyword) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 交付 timeline-v3（滚动/分页/增量 polling）与 keyword 高亮/snippet，并实现“搜索结果跳转 timeline”的联动。

**Architecture:** timeline-v3 使用 `/api/v3/frames` 做初始加载 + before 分页 + after 增量；keyword 搜索使用 FTS5 `snippet/highlight` 返回可渲染片段；点击结果跳转到 `/timeline-v3#ts=<timestamp>`。

**Tech Stack:** Flask templates（现有）、vanilla JS、SQLite FTS5（现有）、LanceDB（用于把 snapshot_id 映射到 timestamp）

## Scope
- In:
  - 新页面 `/timeline-v3`
  - 无限滚动 + 懒加载图片 + 增量 polling（2-3s）
  - `GET /api/v3/search/keyword`（snippet 高亮最小可用）
  - Search → Timeline 跳转
- Out:
  - positions 精确坐标（先不做）
  - WS/SSE（不做）

## Sources of Truth
- 旧 timeline：`MyRecall/openrecall/server/templates/timeline.html`
- Search UI：`MyRecall/openrecall/server/templates/search.html`
- screenpipe Chat/keyword 思路（参考）：`screenpipe/docs/dataflow-pipeline.zh-en.md`

---

### Task 1: 新增 `/timeline-v3` 页面骨架

**Files:**
- Modify: `MyRecall/openrecall/server/app.py`
- Create: `MyRecall/openrecall/server/templates/timeline_v3.html`
- (Optional) Modify: `MyRecall/openrecall/server/templates/layout.html`（加入口）

**Steps**
1) 先做页面可访问、空态可见（不接 API）
2) 再接 `/api/v3/frames?limit=200` 初始加载
3) 再加无限滚动（before 分页）
4) 再加 polling（after 增量）+ 去重排序

**验收**
- 空库：显示提示
- 有数据：首批卡片渲染成功，滚动加载更多成功

---

### Task 2: timeline-v3 前端实现（分页/增量/去重/懒加载）

**Files:**
- Modify: `MyRecall/openrecall/server/templates/timeline_v3.html`

**关键要求（必须写进实现）**
- `limit` 固定上限（例如 200）
- 去重：按 `timestamp` 去重（Set）
- 排序：timestamp desc（新在上）
- polling：每 2-3s 拉 `after=latest_ts`
- 懒加载：IntersectionObserver 只在进入视口时设置 `img.src`

**手工验收清单**
- 连续滚动 1 分钟不卡死
- 新截图进入时不会重复插入
- 点击卡片可打开大图（直接新标签或 modal 均可）

---

### Task 3: 新增 `GET /api/v3/search/keyword`（snippet/highlight MVP）

**Files:**
- Modify: `MyRecall/openrecall/server/api_v3.py`
- Modify: `MyRecall/openrecall/server/database/sql.py`
- (Likely) Modify: `MyRecall/openrecall/server/database/vector_store.py`
- Test: `MyRecall/tests/test_api_v3_search_keyword.py`

**实现策略（MVP）**
1) 在 FTS DB 查询：
   - 返回 `snapshot_id` + `bm25` + `snippet`（用 `<mark>` 包裹命中）
2) 用 `vector_store.get_snapshots(ids)` 把 `snapshot_id -> timestamp/app/window` 映射出来
3) 返回：
   - `matches: [{snapshot_id,timestamp,app_name,window_title,bm25,snippet,image_url}]`

**测试要点**
- snippet 含 `<mark>`
- limit 上限生效
- 时间范围过滤（可选：如果你在 keyword endpoint 支持 start/end）

---

### Task 4: Search UI 增加“跳转到 timeline-v3”

**Files:**
- Modify: `MyRecall/openrecall/server/templates/search.html`

**行为**
- 每条结果新增按钮：`Timeline`
- 点击跳转：`/timeline-v3#ts=<timestamp>`

**验收**
- 点击后 timeline 定位到对应时间附近（最小实现：滚到包含该 timestamp 的卡片；或直接把该 ts 置顶显示）

---

### Task 5: 文档同步（本阶段变更点）

**Files:**
- Modify: `MyRecall/docs/plan/2026-02-04-MyRecall-v3-roadmap.md`（如实现细节与文档不一致）

