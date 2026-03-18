# Chat 功能前置需求分析

- 版本：v2.0
- 日期：2026-03-19
- 状态：**Final**
- 目标：明确在进入 Chat 功能开发前需要补齐的能力，与 screenpipe（accessibility 有，audio 无）**完全对齐**

---

## 1. 概述

MyRecall-v3 的 Chat 功能需要**完全对齐** screenpipe（无 audio）的 Chat 能力。screenpipe 的 Chat 通过 Pi agent + Search API 实现数据检索，依赖以下数据源：

1. **OCR 文本** — 屏幕截图文字（已实现）
2. **UI Events** — 用户交互事件（click、text、app_switch、clipboard）
3. **Accessibility 文本** — AX tree 文本内容
4. **Elements** — 结构化 UI 元素

**对齐状态：完全对齐 screenpipe（vision-only）**

本文档记录需要补齐的能力及实现优先级。

---

## 2. 能力差距总览

| 能力 | screenpipe | MyRecall-v3 当前 | Chat 依赖 | 优先级 |
|------|-----------|-----------------|----------|-------|
| OCR 文本搜索 | ✅ | ✅ 已实现 | 必须 | — |
| UI Events: click | ✅ | ❌ 未实现 | 必须 | **P0** |
| UI Events: element context | ✅ | ❌ 未实现 | 必须 | **P0** |
| UI Events: text (聚合输入) | ✅ | ❌ 未实现 | 高 | P0 |
| UI Events: app_switch | ✅ | ⚠️ 部分（capture_trigger） | 高 | P0 |
| UI Events: clipboard | ✅ | ❌ 未实现 | 中 | P0 |
| UI Events: scroll | ✅ (默认关闭) | ❌ | 低 | 可舍弃 |
| UI Events: move | ✅ (默认关闭) | ❌ | 低 | 可舍弃 |
| UI Events: key (单按键) | ✅ (默认关闭) | ❌ | 低 | 可舍弃 |
| Accessibility 表写入 | ✅ | ❌ (v4 seam) | 高 | **P0** |
| `content_type=accessibility` 搜索 | ✅ | ❌ | 高 | **P0** |
| `content_type=input` 搜索 | ✅ | ❌ | 必须 | P0 |
| Elements 表 + `/v1/elements` API | ✅ | ❌ | 中 | **P0** |
| Browser URL 提取 | ✅ | ❌ (reserved NULL) | 中 | P2 |

---

## 3. 双系统架构设计

### 3.1 对齐 screenpipe 的双系统模式

screenpipe 有两套并行的采集系统：

| 系统 | 职责 | 数据存储 |
|------|------|---------|
| **Event-Driven Capture** | 检测用户行为 → 触发截图 | frames + ocr_text + elements |
| **UI Events Recording** | 记录交互事件详情 | ui_events |
| **Tree Walker** | 独立采集 AX tree | accessibility |

**同一个用户操作会产生多条记录**：

```
用户点击按钮 "Submit"
    ↓
    ├─→ Event-Driven Capture: 触发截图
    │       → frames 表 (capture_trigger='click')
    │       + paired_capture 获取 AX tree → elements 表
    │
    ├─→ UI Events Recording: 记录 click 事件
    │       → ui_events 表 (element_role='AXButton', element_name='Submit')
    │
    └─→ Tree Walker: 独立采集（~3s 间隔）
            → accessibility 表（无 frame_id）
```

**MyRecall 采用相同的三系统模式。**

### 3.2 系统 1: Event-Driven Capture（截图触发）

| 触发条件 | screenpipe 默认 | MyRecall 当前 | 需要新增 |
|---------|----------------|--------------|---------|
| `idle` | ✅ 30s 无活动 | ✅ 已有 | — |
| `app_switch` | ✅ 应用切换 | ✅ 已有 | — |
| `manual` | ✅ 手动触发 | ✅ 已有 | — |
| `click` | ✅ 鼠标点击 | ❌ | **P0** |
| `clipboard` | ✅ 剪贴板操作 | ❌ | **P0** |
| `typing_pause` | ✅ 500ms 无输入 | ❌ | P1 |
| `scroll_stop` | ✅ 300ms 无滚动 | ❌ | P1 |
| `visual_change` | ✅ 帧差异检测 | ❌ | P2 |

### 3.3 系统 2: UI Events Recording（事件记录）

| 事件类型 | screenpipe 默认 | MyRecall 选择 | 说明 |
|---------|----------------|--------------|------|
| `click` | ✅ 启用 | ✅ 实现 | 记录坐标 + element context |
| `text` | ✅ 启用 | ✅ 实现 | 聚合文本输入 |
| `app_switch` | ✅ 启用 | ✅ 实现 | 记录应用切换 |
| `clipboard` | ✅ 启用 | ✅ 实现 | 记录复制粘贴 |
| `element context` | ✅ 启用 | ✅ 实现 | 点击时捕获 AX 元素信息 |
| `scroll` | ❌ 禁用 | ❌ 舍弃 | 数据量过大 |
| `move` | ❌ 禁用 | ❌ 舍弃 | 数据量过大 |
| `key` (单按键) | ❌ 禁用 | ❌ 舍弃 | 隐私风险 |

### 3.4 系统 3: Tree Walker（独立 AX 采集）

| 配置项 | screenpipe | MyRecall | 说明 |
|--------|-----------|----------|------|
| 采集间隔 | 3s | 3s | 定时采集 |
| 立即唤醒触发 | AppSwitch | AppSwitch | 切换应用时立即采集 |
| 唤醒后等待 | 300ms | 300ms | 让新窗口 UI 稳定 |
| 最小冷却时间 | 500ms | 500ms | 两次采集最小间隔 |
| 写入表 | accessibility | accessibility | 无 frame_id |
| 写入 elements | ❌ | ❌ | 无 frame_id，无法写入 |

### 3.5 两系统的关系

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Host 端                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   CGEventTap 监听用户输入                                               │
│         │                                                               │
│         ├─→ 检测到 click                                                │
│         │       │                                                       │
│         │       ├─→ 系统 1: 发送 capture_trigger='click'                │
│         │       │         → 截图 → POST /v1/ingest → frames 表          │
│         │       │         → paired_capture AX tree → elements 表        │
│         │       │                                                       │
│         │       └─→ 系统 2: 获取 element context                        │
│         │                 → POST /v1/events → ui_events 表              │
│         │                                                               │
│         ├─→ 检测到 app_switch                                           │
│         │       │                                                       │
│         │       ├─→ 系统 1: 发送 capture_trigger='app_switch'            │
│         │       │                                                       │
│         │       └─→ 系统 2: 记录事件 → POST /v1/events                   │
│         │                                                               │
│         ├─→ 检测到 Cmd+C/V (clipboard)                                  │
│         │       │                                                       │
│         │       ├─→ 系统 1: 发送 capture_trigger='clipboard'             │
│         │       │                                                       │
│         │       └─→ 系统 2: 记录事件 → POST /v1/events                   │
│         │                                                               │
│         └─→ 检测到文本输入 (聚合)                                        │
│                 │                                                       │
│                 └─→ 系统 2: 300ms 超时后 → POST /v1/events               │
│                     (text 事件不触发截图)                                │
│                                                                         │
│   Tree Walker（独立线程）                                               │
│         │                                                               │
│         ├─→ 定时采集（~3s 间隔）                                        │
│         │       → POST /v1/accessibility → accessibility 表             │
│         │                                                               │
│         └─→ AppSwitch 立即唤醒                                          │
│                 → POST /v1/accessibility → accessibility 表             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. UI Events 详细设计

### 4.1 选定的事件类型

基于 screenpipe 默认配置和 Chat 价值分析，选定以下事件类型：

| 事件类型 | screenpipe 默认 | MyRecall 选择 | 理由 |
|---------|----------------|--------------|------|
| **click** | ✅ 启用 | ✅ 实现 | Chat 最核心：回答"点了什么" |
| **text** | ✅ 启用 | ✅ 实现 | 回答"输入了什么"，聚合文本非单按键 |
| **app_switch** | ✅ 启用 | ✅ 实现 | 应用切换追踪，与现有 capture_trigger 部分重叠 |
| **clipboard** | ✅ 启用 | ✅ 实现 | 复制粘贴追踪，内容预览（可选） |
| **element context** | ✅ 启用 | ✅ 实现 | 点击时捕获 AX 元素信息，Chat 价值最高 |

### 4.2 舍弃的事件类型

| 事件类型 | screenpipe 默认 | 舍弃原因 |
|---------|----------------|---------|
| scroll | ❌ 禁用 | 数据量极大，Chat 价值低 |
| move | ❌ 禁用 | 数据量极大，Chat 价值低 |
| key (单按键) | ❌ 禁用 | 隐私风险，screenpipe 默认也禁用 |
| window_focus | ❌ 禁用 | 数据量较大，可用 app_switch 替代 |

### 4.3 数据表设计

#### ui_events 表

```sql
CREATE TABLE ui_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,              -- UTC ISO8601
    session_id TEXT,                      -- Session identifier (UUID per Host process)
    relative_ms INTEGER DEFAULT 0,        -- Milliseconds since session start
    event_type TEXT NOT NULL,             -- 'click' | 'text' | 'app_switch' | 'clipboard'

    -- 位置信息（click 专用）
    x INTEGER DEFAULT NULL,
    y INTEGER DEFAULT NULL,
    button INTEGER DEFAULT NULL,          -- 0=left, 1=right, 2=middle
    click_count INTEGER DEFAULT NULL,     -- 单击/双击/三击

    -- 文本内容（text/clipboard 专用）
    text_content TEXT DEFAULT NULL,
    text_length INTEGER DEFAULT NULL,

    -- 剪贴板操作类型
    clipboard_op TEXT DEFAULT NULL,       -- 'copy' | 'cut' | 'paste'

    -- 元素上下文（click 时通过 AX API 获取）
    element_role TEXT DEFAULT NULL,       -- 'AXButton', 'AXTextField', 'AXStaticText', etc.
    element_name TEXT DEFAULT NULL,       -- 按钮文本/标签
    element_value TEXT DEFAULT NULL,      -- 输入框当前值
    element_bounds TEXT DEFAULT NULL,     -- JSON: {"x":0,"y":0,"width":100,"height":50}

    -- 应用上下文
    app_name TEXT DEFAULT NULL,
    window_title TEXT DEFAULT NULL,
    browser_url TEXT DEFAULT NULL,        -- 可选，浏览器 URL

    -- 帧关联
    frame_id INTEGER DEFAULT NULL,        -- 关联到 frames.id（用于截图回溯）

    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- 索引
CREATE INDEX idx_ui_events_timestamp ON ui_events(timestamp);
CREATE INDEX idx_ui_events_event_type ON ui_events(event_type);
CREATE INDEX idx_ui_events_app_name ON ui_events(app_name);
CREATE INDEX idx_ui_events_frame_id ON ui_events(frame_id);
CREATE INDEX idx_ui_events_session_id ON ui_events(session_id);
```

#### ui_events_fts 表（FTS5 全文索引）

```sql
CREATE VIRTUAL TABLE ui_events_fts USING fts5(
    text_content,
    app_name,
    window_title,
    element_name,
    content='ui_events',
    content_rowid='id',
    tokenize='unicode61'
);

-- 触发器（INSERT/UPDATE/DELETE 同步到 FTS）
CREATE TRIGGER ui_events_ai AFTER INSERT ON ui_events
WHEN NEW.text_content IS NOT NULL OR NEW.element_name IS NOT NULL
BEGIN
    INSERT INTO ui_events_fts(rowid, text_content, app_name, window_title, element_name)
    VALUES (NEW.id, NEW.text_content, NEW.app_name, NEW.window_title, NEW.element_name);
END;

CREATE TRIGGER ui_events_ad AFTER DELETE ON ui_events BEGIN
    INSERT INTO ui_events_fts(ui_events_fts, rowid, text_content, app_name, window_title, element_name)
    VALUES('delete', OLD.id, OLD.text_content, OLD.app_name, OLD.window_title, OLD.element_name);
END;
```

### 4.4 事件结构定义

#### click 事件

```python
{
    "event_type": "click",
    "timestamp": "2026-03-18T10:30:00.123Z",
    "x": 500,
    "y": 300,
    "button": 0,           # 0=left, 1=right, 2=middle
    "click_count": 1,      # 1=single, 2=double, 3=triple
    "element_role": "AXButton",
    "element_name": "Submit",
    "element_bounds": {"x": 480, "y": 290, "width": 80, "height": 30},
    "app_name": "Google Chrome",
    "window_title": "GitHub - Chrome",
    "frame_id": 12345
}
```

**Chat 用例**：
```
用户: "我今天在 Chrome 里点了什么按钮？"
Chat → GET /v1/search?content_type=input&app_name=Chrome&q=click
     → 返回 element_role="AXButton" 的点击记录
     → 回答: "您在 Chrome 中点击了 'Submit' 按钮、'Sign in' 按钮等..."
```

#### text 事件（聚合文本输入）

```python
{
    "event_type": "text",
    "timestamp": "2026-03-18T10:30:05.456Z",
    "text_content": "hello world",
    "text_length": 11,
    "app_name": "Slack",
    "window_title": "#general - Slack",
    "frame_id": 12346
}
```

**聚合逻辑**：
- 用户连续输入时，聚合到缓冲区
- 300ms 无新输入后，刷新为一条 text 事件
- 退格键处理：从缓冲区删除字符

#### app_switch 事件

```python
{
    "event_type": "app_switch",
    "timestamp": "2026-03-18T10:30:10.789Z",
    "app_name": "VS Code",
    "window_title": "main.py - MyRecall",
    "frame_id": null       # 可选关联
}
```

**与现有 capture_trigger=app_switch 的关系**：
- 现有：触发截图，记录在 frames.capture_trigger
- 新增：独立事件记录，支持搜索和统计

#### clipboard 事件

```python
{
    "event_type": "clipboard",
    "timestamp": "2026-03-18T10:30:15.012Z",
    "clipboard_op": "copy",    # 'copy' | 'cut' | 'paste'
    "text_content": "selected text...",  # 可选，截断到 1000 字符
    "app_name": "Google Chrome",
    "window_title": "GitHub - Chrome"
}
```

### 4.5 Element Context 捕获逻辑

**触发时机**：click 事件发生时

**捕获流程（Split Pattern - 对齐 screenpipe）**：

两个独立事件，不合并：
1. **主 click 事件**：立即发送，包含坐标、按钮、点击次数
2. **context 事件**：后台异步获取 element 信息，使用 `click_count=0` 作为 marker

> 详细实现见 `docs/superpowers/specs/2026-03-18-ui-events-capture-design.md` Section 4.6.1

**AX API 调用**：
```rust
// 获取点击位置的 AX 元素
fn get_element_at_position(x: f64, y: f64) -> Option<ElementContext> {
    let system_wide = ax::UIElement::system_wide();
    let element = system_wide.element_at_position(x, y)?;
    Some(ElementContext {
        role: element.role(),
        name: element.attribute(ax::attributes::TITLE),
        value: element.attribute(ax::attributes::VALUE),
        bounds: element.attribute(ax::attributes::FRAME),
    })
}
```

### 4.6 配置项

```bash
# Master toggle
export OPENRECALL_CAPTURE_UI_EVENTS=false      # Disable all UI event capture

# Individual event type toggles
export OPENRECALL_CAPTURE_CLICKS=true           # Click events
export OPENRECALL_CAPTURE_TEXT=true             # Text input events
export OPENRECALL_CAPTURE_APP_SWITCH=true       # App switch events
export OPENRECALL_CAPTURE_CLIPBOARD=true        # Clipboard events
```

**No fine-grained content toggles**: 不提供类似 `capture_text_content` 的细粒度控制。如果用户需要隐私保护，应禁用整个事件类型。

---

## 5. Elements 表设计（P0）

### 4.1 表结构（完全对齐 screenpipe）

```sql
CREATE TABLE elements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    frame_id INTEGER NOT NULL,
    source TEXT NOT NULL,              -- 'ocr' | 'accessibility'
    role TEXT NOT NULL,                -- OCR: 'page','block','paragraph','line','word'
                                      -- AX: 'AXButton','AXTextField','AXStaticText', etc.
    text TEXT,                         -- 元素文本内容
    parent_id INTEGER,                 -- 自引用 FK，树形结构
    depth INTEGER NOT NULL DEFAULT 0,  -- 树深度
    left_bound REAL,                   -- 归一化边界框 (0-1)
    top_bound REAL,
    width_bound REAL,
    height_bound REAL,
    confidence REAL,                   -- OCR 置信度 (0-100)
    sort_order INTEGER NOT NULL DEFAULT 0,  -- 兄弟节点排序
    FOREIGN KEY (frame_id) REFERENCES frames(id),
    FOREIGN KEY (parent_id) REFERENCES elements(id)
);

-- 索引
CREATE INDEX idx_elements_frame_id ON elements(frame_id);
CREATE INDEX idx_elements_parent_id ON elements(parent_id);
CREATE INDEX idx_elements_source ON elements(source);

-- FTS5 索引
CREATE VIRTUAL TABLE elements_fts USING fts5(
    text, role, frame_id UNINDEXED,
    content='elements', content_rowid='id',
    tokenize='unicode61'
);

-- 触发器
CREATE TRIGGER elements_ai AFTER INSERT ON elements
WHEN NEW.text IS NOT NULL AND NEW.text != ''
BEGIN
    INSERT INTO elements_fts(rowid, text, role, frame_id)
    VALUES (NEW.id, NEW.text, NEW.role, NEW.frame_id);
END;

CREATE TRIGGER elements_ad AFTER DELETE ON elements BEGIN
    DELETE FROM elements_fts WHERE id = OLD.id;
END;
```

### 4.2 写入策略（二选一，对齐 screenpipe）

| 场景 | OCR 写入 elements | Accessibility 写入 elements |
|------|-------------------|----------------------------|
| 普通应用（有 AX tree） | ❌ 不执行 OCR | ✅ 写入 |
| 普通应用（无 AX tree） | ✅ 写入（fallback） | ❌ 无 tree_json |
| Terminal 应用（iTerm 等） | ✅ 写入 | ❌ tree_json = None |

**逻辑**：有 accessibility 文本时使用 accessibility，无 accessibility 时 OCR fallback。

### 4.3 写入位置

| 步骤 | 执行位置 |
|------|---------|
| 采集 AX tree / 执行 OCR | Host 端 |
| 序列化为 JSON | Host 端 |
| 解析 JSON 写入 elements 表 | Edge 端 |

### 4.4 API 端点

```
GET /v1/elements?q=Submit&role=AXButton&start_time=...&limit=10
GET /v1/frames/{frame_id}/elements
```

---

## 5. Accessibility 表设计（P0）

### 5.1 表结构

```sql
CREATE TABLE accessibility (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    app_name TEXT NOT NULL,
    window_name TEXT NOT NULL,
    text_content TEXT NOT NULL,
    browser_url TEXT
);

CREATE INDEX idx_accessibility_timestamp ON accessibility(timestamp);
CREATE INDEX idx_accessibility_app_name ON accessibility(app_name);

-- FTS5
CREATE VIRTUAL TABLE accessibility_fts USING fts5(
    text_content, app_name, window_name,
    content='accessibility', content_rowid='id',
    tokenize='unicode61'
);
```

### 5.2 数据来源

| 来源 | 写入 accessibility 表 | 写入 elements 表 |
|------|---------------------|-----------------|
| paired_capture | ❌ | ✅（有 frame_id） |
| tree_walker | ✅ | ❌（无 frame_id） |

### 5.3 Tree Walker 唤醒机制

```
方式 1: 定时唤醒（每 3s）
   sleep(walk_interval = 3s)
   → 醒来 → walk_accessibility_tree()

方式 2: 立即唤醒（AppSwitch 事件）
   UI 事件监听检测到 AppSwitch
   → 设置 wake_signal = true
   → tree_walker 被唤醒
   → 等待 300ms（让新窗口稳定）
   → walk_accessibility_tree()

冷却保护：两次 walk 之间至少间隔 500ms
```

---

## 6. Search API 扩展

### 6.1 content_type 参数扩展

| 值 | screenpipe | MyRecall | 说明 |
|---|-----------|----------|------|
| `ocr` | ✅ | ✅ 已有 | OCR 文本搜索 |
| `input` | ✅ | P0 实现 | UI 事件搜索 |
| `accessibility` | ✅ | P0 实现 | AX 文本搜索 |
| `all` | ✅ | P0 实现 | 并行合并所有类型 |
| `audio` | ✅ | ❌ 不实现 | vision-only 范围 |

### 6.2 搜索路由

```
content_type=ocr          → search_ocr()          [已实现]
content_type=input        → search_input()        [P0 待实现]
content_type=accessibility → search_accessibility() [P0 待实现]
content_type=all          → 并行搜索 + 合并        [P0 待实现]
```

### 6.3 search_input() 查询示例

```sql
-- 搜索 UI 事件
SELECT e.*, f.timestamp as frame_timestamp, f.snapshot_path
FROM ui_events e
LEFT JOIN frames f ON e.frame_id = f.id
JOIN ui_events_fts fts ON e.id = fts.id
WHERE ui_events_fts MATCH ?
  AND (? IS NULL OR e.app_name = ?)
  AND (? IS NULL OR e.event_type = ?)
  AND e.timestamp >= ? AND e.timestamp <= ?
ORDER BY ui_events_fts.rank, e.timestamp DESC
LIMIT ? OFFSET ?
```

---

## 7. Accessibility 文本采集（P0）

### 7.1 当前状态

- `accessibility` 表已存在于 schema（v4 reserved seam）
- v3 OCR-only 主线不写入、不读取该表
- 需要：从 v4 seam 升级为 v3 active 能力

### 7.2 screenpipe 实现方式

screenpipe 有两条 AX 文本采集路径：

| 路径 | 说明 | 数据量 |
|------|------|-------|
| `paired_capture` | 截图时同步获取 AX 文本，写入 frames.accessibility_text + elements 表 | 与 frames 1:1 |
| `ui_recorder` tree walker | 独立线程，每 ~3s 遍历 AX tree，写入 accessibility 表 | 高频 |

### 7.3 MyRecall 选择

**采用两种模式并存（Q4 决定：C）**：

| 模式 | 说明 | 数据量 | 用途 |
|------|------|-------|------|
| `paired_capture` | 截图时同步获取 AX 文本 | 与 frames 1:1 | 精确关联截图时刻的 AX 状态 |
| `tree walker` | 独立线程，~3s 间隔遍历 AX tree | 高频（~3s/次） | 捕获截图间隙的 UI 变化 |

**实现优先级**：
- P0：paired_capture + tree_walker 都实现

**tree walker 的价值**：
- 捕获截图间隙的内容变化（如滚动、动态加载）
- 用户在某个应用停留期间的 UI 状态变化
- Chat 可回答"我在那个页面看到了什么"更完整

**数据量预估**：
- paired_capture：假设 1fps 截图 → ~86400 条/天
- tree walker：~3s 间隔 → ~28800 条/天
- 总计：~115000 条/天（可控）

---

## 8. Elements 表详细设计（P0）

### 8.1 表结构（完全对齐 screenpipe）

```sql
CREATE TABLE elements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    frame_id INTEGER NOT NULL,
    source TEXT NOT NULL,              -- 'ocr' | 'accessibility'
    role TEXT NOT NULL,                -- OCR: 'page','block','paragraph','line','word'
                                      -- AX: 'AXButton','AXTextField','AXStaticText', etc.
    text TEXT,                         -- 元素文本内容
    parent_id INTEGER,                 -- 自引用 FK，树形结构
    depth INTEGER NOT NULL DEFAULT 0,  -- 树深度
    left_bound REAL,                   -- 归一化边界框 (0-1)
    top_bound REAL,
    width_bound REAL,
    height_bound REAL,
    confidence REAL,                   -- OCR 置信度 (0-100)
    sort_order INTEGER NOT NULL DEFAULT 0,  -- 兄弟节点排序
    FOREIGN KEY (frame_id) REFERENCES frames(id),
    FOREIGN KEY (parent_id) REFERENCES elements(id)
);

-- 索引
CREATE INDEX idx_elements_frame_id ON elements(frame_id);
CREATE INDEX idx_elements_parent_id ON elements(parent_id);
CREATE INDEX idx_elements_source ON elements(source);

-- FTS5 索引
CREATE VIRTUAL TABLE elements_fts USING fts5(
    text, role, frame_id UNINDEXED,
    content='elements', content_rowid='id',
    tokenize='unicode61'
);

-- 触发器
CREATE TRIGGER elements_ai AFTER INSERT ON elements
WHEN NEW.text IS NOT NULL AND NEW.text != ''
BEGIN
    INSERT INTO elements_fts(rowid, text, role, frame_id)
    VALUES (NEW.id, NEW.text, NEW.role, NEW.frame_id);
END;

CREATE TRIGGER elements_ad AFTER DELETE ON elements BEGIN
    DELETE FROM elements_fts WHERE id = OLD.id;
END;
```

### 8.2 Chat 价值

- 元素级精确定位："这个按钮在屏幕哪个位置？"
- 层次结构查询："这个窗口有哪些按钮？"
- `/v1/elements` API：按 role 过滤元素

### 8.3 写入策略（二选一，对齐 screenpipe）

| 场景 | OCR 写入 elements | Accessibility 写入 elements |
|------|-------------------|----------------------------|
| 普通应用（有 AX tree） | ❌ 不执行 OCR | ✅ 写入 |
| 普通应用（无 AX tree） | ✅ 写入（fallback） | ❌ 无 tree_json |
| Terminal 应用（iTerm 等） | ✅ 写入 | ❌ tree_json = None |

**逻辑**：有 accessibility 文本时使用 accessibility，无 accessibility 时 OCR fallback。

### 8.4 写入位置

| 步骤 | 执行位置 |
|------|---------|
| 采集 AX tree / 执行 OCR | Host 端 |
| 序列化为 JSON | Host 端 |
| 解析 JSON 写入 elements 表 | Edge 端 |

### 8.5 API 端点

```
GET /v1/elements?q=Submit&role=AXButton&start_time=...&limit=10
GET /v1/frames/{frame_id}/elements
```

---

## 9. Accessibility 表设计（P0）

### 9.1 表结构

```sql
CREATE TABLE accessibility (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    app_name TEXT NOT NULL,
    window_name TEXT NOT NULL,
    text_content TEXT NOT NULL,
    browser_url TEXT
);

CREATE INDEX idx_accessibility_timestamp ON accessibility(timestamp);
CREATE INDEX idx_accessibility_app_name ON accessibility(app_name);

-- FTS5
CREATE VIRTUAL TABLE accessibility_fts USING fts5(
    text_content, app_name, window_name,
    content='accessibility', content_rowid='id',
    tokenize='unicode61'
);
```

### 9.2 数据来源

| 来源 | 写入 accessibility 表 | 写入 elements 表 |
|------|---------------------|-----------------|
| paired_capture | ❌ | ✅（有 frame_id） |
| tree_walker | ✅ | ❌（无 frame_id） |

### 9.3 Tree Walker 唤醒机制

```
方式 1: 定时唤醒（每 3s）
   sleep(walk_interval = 3s)
   → 醒来 → walk_accessibility_tree()

方式 2: 立即唤醒（AppSwitch 事件）
   UI 事件监听检测到 AppSwitch
   → 设置 wake_signal = true
   → tree_walker 被唤醒
   → 等待 300ms（让新窗口稳定）
   → walk_accessibility_tree()

冷却保护：两次 walk 之间至少间隔 500ms
```

---

## 10. Frames 表扩展（P0）

### 10.1 新增字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `accessibility_tree_json` | TEXT | AX tree 原始 JSON |

### 10.2 字段状态变更

| 字段 | 原状态 | 新状态 |
|------|--------|--------|
| `accessibility_text` | v4 seam | v3 active |
| `text_source` | 固定 'ocr' | 动态（'accessibility'/'ocr'） |

### 10.3 content_hash 字段

- 字段保留
- P0 不实现去重逻辑

---

## 11. Browser URL 提取（P2）

### 11.1 screenpipe 实现

| 浏览器 | 提取方式 |
|-------|---------|
| Safari / Chrome | AXDocument 属性 |
| Arc | AppleScript |
| 其他 | 浅层 AX tree 遍历 |

### 11.2 MyRecall 当前状态

- `frames.browser_url` 字段存在但固定为 NULL
- P1 阶段保留为 reserved 字段

### 11.3 Chat 价值

- "我在哪个网页上？"
- "我打开过 GitHub 吗？"
- 可通过 `frames_fts.browser_url MATCH ?` 搜索

---

## 12. 实现优先级总结

### P0（Chat 功能前置必须）

| 序号 | 能力 | 工作量估算 |
|------|------|-----------|
| 1 | ui_events 表 + FTS | 0.5 周 |
| 2 | Host 端 click 捕获 + element context | 1 周 |
| 3 | Host 端 text 聚合输入捕获 | 0.5 周 |
| 4 | Host 端 app_switch 捕获 | 0.5 周 |
| 5 | Host 端 clipboard 捕获 | 0.5 周 |
| 6 | Edge 端 POST /v1/events | 0.5 周 |
| 7 | search_input() 路径实现 | 0.5 周 |
| 8 | elements 表 + FTS | 0.5 周 |
| 9 | paired_capture AX 采集 + elements 写入 | 2 周 |
| 10 | tree_walker 实现（3s + 立即唤醒） | 1.5 周 |
| 11 | accessibility 表 + FTS | 0.5 周 |
| 12 | search_accessibility() 路径实现 | 0.5 周 |
| 13 | /v1/elements API | 0.5 周 |
| 14 | frames 表新增 accessibility_tree_json 字段 | 0.5 周 |
| 15 | /v1/activity-summary 端点 | 1 周 |
| 16 | /v1/raw_sql 端点 | 0.5 周 |

**P0 总计：~10-12 周**

### P1（增强）

| 序号 | 能力 | 工作量估算 |
|------|------|-----------|
| 1 | content_type=all 并行搜索 + 合并 | 0.5 周 |
| 2 | /v1/activity-summary 增加 ui_events 统计 | 0.5 周 |

**P1 总计：~1 周**

### P2（完善体验）

| 序号 | 能力 | 工作量估算 |
|------|------|-----------|
| 1 | Browser URL 提取 | 0.5-1 周 |
| 2 | typing_pause / scroll_stop 触发器 | 1 周 |

**P2 总计：~1.5-2 周**

---

## 13. 待决问题

| ID | 问题 | 选项 | 建议 | 状态 |
|----|------|------|------|------|
| Q1 | ui_events 的 API 端点设计 | A 独立端点 `POST /v1/events` / B 扩展 `/v1/ingest` | **A 已决定** | ✅ 已关闭 |
| Q2 | text 事件聚合超时时间 | 300ms / 500ms / 1000ms | **300ms 已决定** | ✅ 已关闭 |
| Q3 | clipboard 事件是否捕获剪贴板内容？ | A 捕获（截断 1000 字符）/ B 仅记录操作 | **A 已决定** | ✅ 已关闭 |
| Q4 | accessibility 表采用哪种采集模式？ | A paired_capture / B tree walker / C 两者都有 | **C 已决定** | ✅ 已关闭 |
| Q5 | 这些能力是放在 P1-S5 之前还是之后？ | A Chat 前必须完成 / B 与 Chat 并行 | **A 已决定** | ✅ 已关闭 |

---

## 14. 隐私与安全决策

| ID | 问题 | 选项 | 决定 | 状态 |
|----|------|------|------|------|
| A1 | clipboard PII 脱敏策略 | A 复用 screenpipe 模式 / B 简化版 / C 可配置 / D 完全不处理 | **D 已决定** | ✅ 已关闭 |
| A2 | text 事件密码字段处理 | A 跳过密码字段 / B 完全不跳过 | **B 已决定** | ✅ 已关闭 |
| A3 | 应用级隐私黑名单 | A P0实现 / B P1实现 / C 不实现 | **C 已决定** | ✅ 已关闭 |
| A4 | element_value 敏感字段 | A 检测密码字段 / B 不捕获 / C 捕获所有 | **C 已决定** | ✅ 已关闭 |

### A1 结论：完全不处理 PII 脱敏

**选择 D**：clipboard 内容原样存储，不进行 PII 检测或脱敏。

**理由**：
1. **用户自主**：MyRecall 是本地优先应用，数据不上传云端，用户对自己的数据有完全控制
2. **透明性**：不擅自修改用户剪贴板内容，保持数据原始性
3. **实现简洁**：避免引入复杂的正则匹配逻辑和潜在误判
4. **与 screenpipe 差异**：screenpipe 有云同步功能需要 PII 脱敏，MyRecall 纯本地不需要

**风险评估**：
- clipboard 内容可能包含敏感信息（密码、API Key 等）
- 用户需自行判断是否启用 clipboard 捕获
- 可在未来提供应用级隐私黑名单作为补充（A3）

### A2 结论：不跳过密码字段

**选择 B**：text 事件捕获所有输入，不检测或跳过密码字段。

**理由**：
1. **与 A1 一致**：保持"用户自主、不干预"的设计原则
2. **避免误判**：字段名检测可能误杀（如 "Password hint" 字段）
3. **实现简洁**：无需在 Host 端实现 AXSecureTextField 检测逻辑
4. **用户可控**：用户可通过 A3（应用黑名单）排除敏感应用

**screenpipe 差异**：
- screenpipe 默认 `skip_password_fields: true`
- MyRecall 选择不跳过，依赖用户自行控制

**风险评估**：
- 密码可能在 text 事件中以明文形式存储
- 用户应避免在不可信环境启用 text 事件捕获
- 数据库本地存储，不上传云端

### A3 结论：不实现应用级隐私黑名单

**选择 C**：不提供应用级隐私黑名单功能。

**理由**：
1. **设计一致性**：与 A1/A2 保持一致，遵循"用户自主、不干预"原则
2. **简化实现**：无需在 Host 端维护黑名单、无需配置 UI
3. **用户替代方案**：
   - 关闭 MyRecall 应用
   - 系统级权限控制（macOS 辅助功能权限）
   - 物理隔离（不使用敏感应用时运行 MyRecall）

**screenpipe 差异**：
- screenpipe 默认排除密码管理器（1Password 等）
- MyRecall 不提供此功能，由用户自行控制

**隐私保护总结**：
MyRecall 采用"透明捕获 + 本地存储 + 用户自主"模式，不主动过滤或脱敏任何内容。用户对数据有完全控制权，可通过关闭应用来保护隐私。

### A4 结论：捕获所有 element_value

**选择 C**：element_value 捕获所有输入框的当前值，不检测或过滤敏感字段。

**理由**：
1. **设计一致性**：与 A1-A3 保持一致的"不干预"原则
2. **Chat 价值**：element_value 可帮助回答"当时输入框里填了什么"
3. **避免误判**：密码字段检测逻辑可能误杀正常字段
4. **实现简洁**：无需额外的敏感字段检测逻辑

**screenpipe 差异**：
- screenpipe 对密码字段返回 `value: None` + `name: "[password field]"`
- MyRecall 捕获完整 element_value，不做过滤

---

### 隐私决策总结

| 决策项 | MyRecall | screenpipe | 差异原因 |
|--------|----------|-----------|----------|
| PII 脱敏 | 不处理 | 正则脱敏 | 本地存储无需云同步保护 |
| 密码字段跳过 | 不跳过 | 跳过 | 用户自主原则 |
| 应用黑名单 | 不实现 | 内置 + 可配置 | 简化实现 |
| element_value 过滤 | 不过滤 | 密码字段过滤 | 设计一致性 |

**核心原则**：MyRecall 是本地优先应用，数据不上传云端，采用"透明捕获 + 用户自主"模式，不主动干预或过滤捕获内容。

---

## 15. Host 端技术实现决策

| ID | 问题 | 选项 | 决定 | 状态 |
|----|------|------|------|------|
| B1 | click 事件的 frame_id 关联策略 | A 松耦合(字段存在但NULL) / B 无字段 / C 强耦合 | **A 已决定** | ✅ 已关闭 |
| B2 | AX API 调用失败处理 | A 分离事件 / B 合并等待 / C 仅发送成功 | **A 已决定** | ✅ 已关闭 |
| B3 | CGEventTap 线程模型 | A 与screenpipe对齐 / B 简化版 / C async/await | **A 已决定** | ✅ 已关闭 |
| B4 | 事件缓冲与批量上传 | A 实时上传 / B 内存批量 / C spool复用 | **B 已决定** | ✅ 已关闭 |

### B1 结论：frame_id 松耦合

**选择 A**：ui_events 表有 frame_id 字段，但采集时默认 NULL，不主动关联。

**screenpipe 对齐**：
- screenpipe 表结构有 `frame_id INTEGER` 字段和索引
- 采集时代码设置 `frame_id: None`
- 搜索 `search_ui_events()` 只查 ui_events 表，不 JOIN frames
- Chat 通过时间戳间接关联事件与截图

**设计理由**：
1. **时序解耦**：click 事件和截图是并行操作，无需等待截图完成
2. **实现简洁**：Host 端无需协调两个系统的时序
3. **预留扩展**：frame_id 字段保留，未来可用于 Edge 端时间窗口关联

**时间戳关联策略**：
- Chat 查询时，可通过事件 timestamp 查找 ±1s 范围内的 frame
- 类似 screenpipe 的 `search_accessibility()` 中 frames 与 accessibility 的关联方式

### B2 结论：分离事件模式

**选择 A**：click 事件立即发送，element context 异步获取（可能丢失）。

**screenpipe 实现**：
```rust
// 1. 主 click 事件 — 立即发送，不受 AX API 影响
let ui_event = UiEvent::click(timestamp, x, y, btn, clicks, mods);
let _ = state.tx.try_send(ui_event);  // 必定发送

// 2. element context 事件 — 后台异步，失败静默丢弃
std::thread::spawn(move || {
    if let Some(element) = get_element_at_position(x, y, &config) {
        let ctx_event = UiEvent { click_count: 0, element: Some(element), ... };
        let _ = tx.try_send(ctx_event);
    }
    // AX API 失败时静默丢弃，不影响主事件
});
```

**事件流示例**：
```
用户点击按钮 "Submit"
    ↓
t0: click 事件立即发送
    { event_type: "click", x: 500, y: 300, element: None }
    ↓
t1: 后台 AX API 调用
    ↓
    ├─→ 成功: 发送 context 事件
    │   { event_type: "click", click_count: 0, element: { role: "AXButton", name: "Submit" } }
    │
    └─→ 失败: 静默丢弃（无 context 事件）
```

**设计理由**：
1. **可靠性**：主事件不受 AX API 影响，必定记录
2. **性能**：不阻塞事件流，AX API 在后台执行
3. **灵活性**：element context 是可选增强，丢失可接受

**Chat 消费逻辑**：
- 搜索 `content_type=input` 时，两个事件独立返回
- 可通过 timestamp + 坐标匹配关联主事件与 context 事件

### B3 结论：与 screenpipe 线程模型对齐

**选择 A**：采用与 screenpipe 一致的线程架构原则。

**screenpipe 线程模型**：
```
Thread 1: CGEventTap (专用 CFRunLoop 线程)
    - 高优先级，回调快速返回
    - 耗时操作 spawn 临时线程（AX API、clipboard 读取）
    - 事件通过 crossbeam channel 发送
    ↓ channel
Thread 2: 事件处理 (tokio::spawn)
    - 批量写入本地 DB
    - 同时发送 capture_trigger 触发截图
```

**MyRecall 对齐实现**：
```
Thread 1: CGEventTap (专用 CFRunLoop 线程)
    - 复用现有 MacOSEventTap 架构
    - 事件通过 TriggerEventChannel 发送
    ↓ channel
Thread 2: 事件消费者
    - 批量 POST /v1/events 到 Edge
    - 可复用现有 SpoolUploader 模式或独立队列
```

**架构原则一致性**：
| 原则 | screenpipe | MyRecall |
|------|-----------|----------|
| CGEventTap 快速返回 | ✅ | ✅ |
| channel 解耦捕获与处理 | ✅ | ✅ |
| 后台批量写入 | ✅ (本地DB) | ✅ (POST Edge) |
| 耗时操作临时线程 | ✅ | ✅ |

### B4 结论：内存批量上传

**选择 B**：事件在内存缓冲，定时/定量批量 POST 到 Edge。

**screenpipe 批量策略**：
```rust
// 配置
batch_size: 100,           // 满 100 条 flush
batch_timeout_ms: 1000,    // 超时 1s flush

// 风暴保护
if consecutive_failures > 3 && batch.len() > batch_size * 2 {
    batch.drain(..drain_count);  // 丢弃旧事件，保留最新的
}
```

**MyRecall 实现建议**：
```python
class UIEventsUploader:
    def __init__(self, batch_size=100, batch_timeout_ms=1000):
        self._buffer: list[dict] = []
        self._batch_size = batch_size
        self._batch_timeout = batch_timeout_ms / 1000.0
        self._last_flush = time.time()

    def enqueue(self, event: dict):
        self._buffer.append(event)
        if len(self._buffer) >= self._batch_size:
            self._flush()

    def _flush(self):
        if not self._buffer:
            return
        events = self._buffer
        self._buffer = []
        # POST /v1/events with {"events": events}
        ...
```

**设计理由**：
1. **网络效率**：批量 POST 减少 HTTP 开销
2. **与 screenpipe 一致**：相同的批量模式
3. **丢失风险可接受**：ui_events 是纯 JSON，崩溃丢失可接受
4. **风暴保护**：可复用 screenpipe 的丢弃策略

---

## 16. 新增决策记录

### 16.1 Elements 表决策

| ID | 问题 | 决定 |
|----|------|------|
| E1 | 表结构 | 完全对齐 screenpipe |
| E2 | OCR/Accessibility 写入策略 | 二选一（有 AX 用 AX，无 AX 用 OCR） |
| E3 | 写入位置 | Edge 端解析写入 |
| E4 | source 字段 | 保留（为 OCR 预留） |
| E5 | API 端点命名 | `/v1/elements`, `/v1/frames/{frame_id}/elements` |

### 16.2 Accessibility 采集决策

| ID | 问题 | 决定 |
|----|------|------|
| AC1 | 采集模式 | paired_capture + tree_walker 都实现 |
| AC2 | tree_walker 间隔 | 3s |
| AC3 | tree_walker 立即唤醒 | 实现（AppSwitch 触发） |
| AC4 | 唤醒后等待 | 300ms |
| AC5 | 最小冷却时间 | 500ms |

### 16.3 Frames 表决策

| ID | 问题 | 决定 |
|----|------|------|
| F1 | 新增 accessibility_tree_json | 是 |
| F2 | accessibility_text 字段 | v3 active |
| F3 | text_source 字段 | 动态 |
| F4 | content_hash 使用 | 字段保留，P0 不实现去重 |

### 16.4 其他决策

| ID | 问题 | 决定 |
|----|------|------|
| D1 | /v1/activity-summary | P0 实现，包含 ui_events 统计 |
| D2 | /v1/raw_sql | P0 实现（Chat 统计查询必需） |
| D3 | 与 screenpipe 对齐状态 | 完全对齐（vision-only） |

---

## 17. 版本记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-03-18 | 初始文档，确定 UI Events 选型（click/text/app_switch/clipboard/element context） |
| v1.1 | 2026-03-18 | 关闭所有待决问题：Q1(独立端点)、Q2(300ms)、Q3(捕获内容)、Q4(双模式)、Q5(Chat前完成) |
| v2.0 | 2026-03-19 | 重大更新：accessibility 和 elements 升级为 P0；完全对齐 screenpipe；新增 elements 表设计、tree_walker 唤醒机制、frames 表扩展；新增 /v1/activity-summary 和 /v1/raw_sql 端点决策；恢复所有被删除的详细设计内容 |
