# Grid 单日视图 + 浮动日期选择器 — 设计文档

## 概述

将 Grid 首页从"平铺所有 frames（limit=500）"改为"**单日视图**：选中某天，展示该天全部 captures，无 limit"。通过浮动日期选择器切换日期，日历显示当月有 captures 的日期标记。

## 动机

- 当前 `/api/memories/recent?limit=500` 平铺显示，难以按天浏览历史
- 一天 captures 数量可能很大（高频场景下数千条），需要真正的按天分页
- 用户需要快速跳转到特定日期查看当天的所有活动

## 架构

### 数据流

```
页面加载 → GET /api/memories/by-day?date=today
              ↓
         渲染日期标题 + Stats + Grid
              ↓
         同时 GET /api/memories/dates?month=current_month
              ↓
         渲染日历标记（有数据的日期显示圆点）
              ↓
点击日期按钮 → 弹出日历浮层 → 选择日期 → 关闭浮层
              ↓
         GET /api/memories/by-day?date=selected
              ↓
         替换 Grid + 更新标题 + 更新 Stats
```

### 组件

| 组件 | 位置 | 说明 |
|------|------|------|
| DatePickerButton | 顶部工具栏 | 显示当前日期，点击弹出日历 |
| CalendarPopover | 浮动面板 | 月历视图，有数据的日期带圆点 |
| DayHeader | Grid 上方 | 日期标题 + 当天 Stats |
| PrevNextNav | DayHeader 旁 | ◀ ▶ 快速切换前后天 |
| TodayButton | 顶部工具栏 | 一键跳回今天 |
| DayGrid | 主区域 | 当天全部 cards，无 limit |

## API 设计

### `GET /api/memories/by-day`

返回指定日期全部 frames，按 `local_timestamp` 倒序。

**参数：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `date` | string | 是 | 日期，格式 `YYYY-MM-DD`，基于 `local_timestamp` |

**响应：** `list[dict]` — 与当前 `get_recent_memories()` 返回的字段完全一致。

**实现：** 在 `FramesStore` 新增 `get_frames_by_day(date: str) -> list[dict]`，WHERE 条件使用 `DATE(local_timestamp) = ?`。

### `GET /api/memories/dates`

返回指定月份有 captures 的日期列表。

**参数：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `month` | string | 是 | 月份，格式 `YYYY-MM` |

**响应：**
```json
{
  "dates": ["2026-04-01", "2026-04-02", "2026-04-05", "2026-04-28"]
}
```

**实现：** SQLite 查询 `SELECT DISTINCT DATE(local_timestamp) FROM frames WHERE DATE(local_timestamp) LIKE 'YYYY-MM%'`。

## UI 设计

### 顶部工具栏

```
┌─────────────────────────────────────────────────────────────┐
│  [Today]  [📅 2026-04-28 ▼]  ◀  ▶        [Start] [End]   │
└─────────────────────────────────────────────────────────────┘
```

- **Today 按钮**：跳回今天，禁用状态当已选中今天
- **日期按钮**：显示当前选中日期，点击弹出日历浮层
- **◀ ▶**：前一天 / 后一天快捷导航
- **Start/End**：保留现有时间范围筛选（作用于当天内部）

### 日历浮层

```
┌────────────────┐
│   ◀  2026年4月  ▶  │
│ 日 一 二 三 四 五 六 │
│                 1  │
│  2  3  4  5  6  7  8 │
│  9 10 11 12 13 14 15 │
│ 16 17 18 19 20 21 22 │
│ 23 24 25 26 27 ●28 │
│ 29 30              │
└────────────────┘
```

- 月份左右切换箭头
- 有 captures 的日期下方显示小圆点（●）
- 当前选中日期高亮背景
- 今天日期边框高亮
- 点击日期 → 关闭浮层 → 加载该天数据

### 日期标题栏

```
┌──────────────────────────────────────────────────────────────┐
│  2026年4月28日（星期一）              Completed 45  Pending 3  Failed 1 │
└──────────────────────────────────────────────────────────────┘
```

- 左侧：完整日期 + 星期
- 右侧：当天 Stats（completed / pending / failed）
- Stats 样式复用现有 `.stats-bar`，但放在标题行内紧凑排列

### Grid 区域

- 复用现有 `.memory-grid` CSS grid 布局
- 当天所有 frames 无 limit 全部展示
- 空状态：当天无 captures 时显示提示（如 "No captures on 2026-04-28"）
- 卡片内容和样式完全复用现有实现

## 数据加载策略

| 场景 | 行为 |
|------|------|
| 页面初始加载 | 加载今天全部 captures |
| 点击日期选择器选某天 | 加载该天全部 captures |
| 点击 ◀ / ▶ | 加载前一天 / 后一天 |
| 点击 Today | 加载今天 |
| 切换日历月份 | 获取该月有数据的日期列表（用于圆点标记） |
| 实时新 capture | 若当前查看的是今天，通过 `checkNew()` 插入到 entries 头部 |

## 前端状态（Alpine.js）

```javascript
{
  currentDate: '2026-04-28',     // 当前选中的日期
  entries: [],                    // 当前日期的所有 frames
  datesWithData: new Set(),       // 当月有数据的日期集合
  calendarOpen: false,            // 日历浮层是否打开
  calendarYear: 2026,             // 日历显示的年份
  calendarMonth: 4,               // 日历显示的月份（1-12）
  retrying: false,
  selectedIndex: null,
  modalTab: 'image',
  // ... 现有方法
}
```

## 性能考虑

1. **单日数据量大**：一天数千条 captures 时，所有卡片一次性渲染可能卡顿。若实测有性能问题，后续可引入虚拟滚动（只渲染可视区域内的卡片）。
2. **日历圆点查询**：切换月份时只查询该月有数据的日期，数据量小（最多 31 条）。
3. **图片懒加载**：复用现有 `loading="lazy"` 策略，只加载首屏图片。

## 错误处理

- API 失败：显示错误提示，保留当前数据不变
- 选中日期无数据：显示空状态提示
- 网络断开：实时更新 `checkNew()` 静默失败，不打扰用户

## 测试要点

- 切换日期后 grid 正确替换
- 日历圆点正确标记有数据的日期
- 今天有实时新 capture 时正确插入
- 前一天 / 后一天导航正确
- 空日期正确显示空状态
- Stats 数字计算正确
