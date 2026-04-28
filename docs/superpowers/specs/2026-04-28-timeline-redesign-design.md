# Timeline 界面优化设计方案

## 目标

将 Timeline 界面从全局时间线滑块改为以天为粒度的回放器，与 Grid 界面的日历导航系统保持一致，并增加播放功能。

## 当前状态

Timeline 页面（`/timeline`）使用 `timeline.html` 模板，当前是一个跨越全部历史帧的滑块视图（`limit=5000`），通过滑块索引定位到某一帧。没有日历导航，也没有按天分隔的概念。

Grid 页面（`/`）已通过近期重构实现了以天为粒度的日历导航系统，包括：Today 按钮、前后天箭头、日期选择器（带日历弹出）、按天加载数据、日历上标记有数据的日期。

## 设计

### 页面布局

```
┌─────────────────────────────────────────────┐
│ [Today] [‹] [📅 2025-04-28 ▼] [›] [▶ 1x]    │  ← 日期导航 + 播放控制栏
├─────────────────────────────────────────────┤
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │  ← 时间线滑块（当天帧范围）
│         2025-04-28 14:32:18 (15 / 128)       │  ← 时间戳 + 帧计数
├─────────────────────────────────────────────┤
│                                             │
│              [  单张截图大图  ]               │  ← 图片展示区
│                                             │
└─────────────────────────────────────────────┘
```

### 日期导航栏

与 Grid 界面完全一致的组件和交互：

- **Today 按钮**：跳转到今天，加载当天数据，disabled 当已在今天
- **‹ 按钮**：前一天
- **日期选择器**：显示当前日期，点击展开日历弹出
- **› 按钮**：后一天
- **日历弹出**：月份导航（‹ ›）、7x6 日历格、有数据日期标记蓝色圆点、选中日期高亮、今天蓝色边框

日历样式复用 `index.html` 已定义的 CSS 类：`.date-nav-toolbar`, `.today-btn`, `.toolbar-nav-btn`, `.date-picker-btn`, `.calendar-popover`, `.calendar-header`, `.calendar-nav`, `.calendar-weekdays`, `.calendar-days`, `.calendar-day`（含 `.is-other-month`, `.is-selected`, `.is-today`, `.has-data` 状态）。

### 播放控制

- **播放/暂停按钮**：位于日期栏最右侧
  - ▶ 点击开始播放
  - ⏸ 点击暂停播放
  - disabled 当当天无帧或仅 1 帧
- **倍速切换**：紧挨播放按钮，显示当前倍速（1x / 2x / 5x / 10x），点击循环切换
- **帧计数**：滑块下方显示 `(currentIndex + 1) / frames.length`

### 播放行为

- 定时器按 `baseInterval / speed` 递增 `currentIndex`
- `baseInterval = 1000ms`（每帧 1 秒）
- `speed ∈ {1, 2, 5, 10}`
- 图片随 `currentIndex` 自动切换
- 滑块实时跟随 `currentIndex`
- 到达最后一帧（`currentIndex === frames.length - 1`）时**自动停止**，不循环，不跳到下一天
- 播放中当天有新帧到达 → 新帧追加到 `frames` 末尾，播放继续（新帧自然成为后续播放内容）

### 手动交互规则

| 操作 | 行为 |
|------|------|
| 拖动滑块 | 自动暂停播放 |
| 点击前后天箭头 | 停止播放，加载新一天数据 |
| 日历选日 | 停止播放，加载选中日期数据 |
| 点击 Today | 停止播放，回到今天 |
| 键盘 ← → | 切换帧，自动暂停 |

### 数据加载

**按天加载帧：**
- API: `GET /api/memories/by-day?date=YYYY-MM-DD`
- 返回数组：当天所有帧，按时间升序（旧→新）
- 成功：赋值给 `frames`，`currentIndex = 0`
- 失败：`frames = []`，`currentIndex = 0`

**日历数据标记：**
- API: `GET /api/memories/dates?month=YYYY-MM`
- 返回：`{ dates: ["2025-04-01", "2025-04-02", ...] }`
- 用于在日历上标记有数据的日期（`.has-data` 蓝色圆点）

**实时刷新（仅今天）：**
- 每 5 秒调用 `GET /v1/frames/latest?since={timestamp}`
- 有新帧时追加到 `frames` 末尾
- 不在"今天"时不刷新

**首次加载：**
- 默认加载今天的数据（UTC+8）

### 空状态

当 `frames.length === 0` 时显示：
```
No captures on 2025-04-28.
Select another date to browse history.
```
此时滑块 disabled，播放按钮 disabled。

### 边界情况

| 场景 | 行为 |
|------|------|
| 当天无帧 | 空状态，滑块 + 播放 disabled |
| 当天仅 1 帧 | 滑块 disabled（min=max），播放 disabled |
| 播放到达最后一帧 | 自动暂停，恢复 ▶ 状态 |
| 播放中切到另一天 | 停止播放，加载新数据 |
| 数据加载中 | 滑块 + 播放 disabled，显示 loading |
| 播放中新帧到达 | 新帧追加，播放继续 |

### 时间处理

- 所有日期字符串格式：`YYYY-MM-DD`
- 时区：UTC+8（与 Grid 一致）
- `parseTimestamp()` 复用 `layout.html` 中已定义的全局函数

### Alpine.js 状态结构

```javascript
function timelineView() {
  return {
    // 数据
    frames: [],           // 当天所有帧
    currentIndex: 0,      // 当前显示帧索引
    currentDate: '',      // YYYY-MM-DD
    datesWithData: new Set(),

    // 日历
    calendarOpen: false,
    calendarYear: 0,
    calendarMonth: 0,

    // 播放
    isPlaying: false,
    playbackSpeed: 1,     // 1, 2, 5, 10
    playbackTimer: null,
    BASE_INTERVAL: 1000,  // ms

    // UI
    loading: true,
  };
}
```

### 复用的现有机制

| 来源 | 复用内容 |
|------|----------|
| `index.html` Grid | 日历 CSS 样式、日历交互逻辑、日期导航、`_utc8Now()`、`_formatDateStr()` |
| `layout.html` | `parseTimestamp()` 全局函数 |
| Edge API | `/api/memories/by-day`、`/api/memories/dates`、`/v1/frames/latest` |

## 无需后端改动

所有需要的 API 已在 Grid 界面中使用，Timeline 仅复用现有接口，无需新增或修改服务端代码。

## 改动范围

**仅修改一个文件：**
- `openrecall/client/web/templates/timeline.html` —— 重写 Alpine.js 组件逻辑、CSS 样式、HTML 结构

**不修改：**
- 后端 API
- `layout.html`
- `index.html`（仅作为参考，不动其代码）
- 其他模板或路由
