# MyRecall-v3 Grid UI/UX 设计规范

> **文档定位**: Frame 卡片视觉与交互设计的单一事实源（SSOT）  
> **适用范围**: Grid 视图 (`/`) 的 frame 卡片组件  
> **依赖文档**: [data-model.md](../data-model.md), [spec.md](../spec.md)  
> **状态**: 讨论草案（P1-S3 优化阶段）

---

## 目录

1. [设计原则](#1-设计原则)
2. [卡片整体结构](#2-卡片整体结构)
3. [Header 区域详解](#3-header-区域详解)
4. [Footer 区域详解](#4-footer-区域详解)
5. [状态系统设计](#5-状态系统设计)
6. [响应式与可访问性](#6-响应式与可访问性)
7. [实现参考](#7-实现参考)

---

## 1. 设计原则

### 1.1 信息层级（Information Hierarchy）

| 优先级 | 内容 | 视觉权重 | 用户目标 |
|--------|------|----------|----------|
| **P0** | 截图预览 | 最高（大图片） | 快速识别内容 |
| **P1** | 应用名称 + 时间 | 高 | 确认上下文 |
| **P2** | 窗口标题 | 中 | 精确识别 |
| **P3** | 处理状态 | 中 | 了解可用性 |
| **P4** | 触发类型 + 设备 | 低 | 调试/元信息 |
| **P5** | OCR 文本预览 | 低（展开后高） | 内容预览 |

### 1.2 设计约束

- **密度**: 单屏显示 8-12 张卡片（1080p）
- **一致性**: 所有卡片高度统一，宽度响应式
- **渐进披露**: 次要信息默认折叠，hover/点击展开
- **性能**: 支持 1000+ 卡片虚拟滚动（未来）

### 1.3 与 screenpipe 的差异

| 维度 | screenpipe | MyRecall-v3 |
|------|------------|-------------|
| 技术栈 | Tauri + React | Flask + Alpine.js |
| 主题 | 深色优先 | 浅色优先（可切换） |
| 布局 | 紧凑瀑布流 | 规则网格 |
| 状态 | 微妙指示 | 显式标签 |

---

## 2. 卡片整体结构

### 2.1 物理结构

```
┌─────────────────────────────────────────────────────┐
│ [Status Border]  ← 左侧 3px 状态色条                 │
│ ┌─────────────────────────────────────────────────┐ │
│ │ HEADER (64px)                                    │ │
│ │ ├─ 应用信息区                                    │ │
│ │ └─ 时间戳                                        │ │
│ ├─────────────────────────────────────────────────┤ │
│ │                                                  │ │
│ │ IMAGE (240px, 16:10)                             │ │
│ │                                                  │ │
│ ├─────────────────────────────────────────────────┤ │
│ │ FOOTER (自适应, min 60px)                        │ │
│ │ ├─ 状态指示区                                    │ │
│ │ ├─ 元信息区（OCR引擎/统计）                      │ │
│ │ └─ 文本预览区                                    │ │
│ └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

### 2.2 尺寸规范

| 元素 | 尺寸 | 说明 |
|------|------|------|
| 卡片宽度 | 320px | 网格 minmax(320px, 1fr) |
| 卡片间距 | 24px | gap: 24px |
| Header 高度 | 64px | 固定，防止跳动 |
| 图片高度 | 200px (固定) | 所有卡片统一高度，整齐对齐 |
| 图片填充 | object-fit: cover | 填满容器，超出部分裁剪 |
| 图片定位 | object-position: top | 优先显示截图顶部（标题栏/URL）|
| 交互 | hover scale 1.05x | 临时查看完整内容 |
| Footer 最小高度 | 60px | 随内容扩展 |
| 圆角 | 12px | 统一 border-radius |
| 阴影 | 0 1px 3px rgba(0,0,0,0.08) | 默认状态 |

---

## 3. Header 区域详解

### 3.1 Header 信息架构

#### 当前实现分析

```
当前 Header（index.html:477-487）:
┌──────────────────────────────────────────────────────┐
│ ┌────────────────────────────────┐  ┌─────────────┐  │
│ │ [AppName] [trigger-label]      │  │  Timestamp  │  │
│ │ WindowName                      │  │             │  │
│ │ DEVICE_NAME                     │  │             │  │
│ └────────────────────────────────┘  └─────────────┘  │
└──────────────────────────────────────────────────────┘
```

**问题识别**:
1. `device_name` 占据宝贵垂直空间，但用户关注度低
2. `trigger-label` 与 `app_name` 同行，导致拥挤
3. 时间戳使用等宽字体，视觉重量不均衡
4. 三行文字导致 Header 过高，压缩图片区域

### 3.2 Header 优化方案

#### 方案 A: 紧凑双行（备选）

```
┌──────────────────────────────────────────────────────┐
│ ┌─────────────────────────────┐  ┌────────────────┐  │
│ │ [icon] AppName             │  │  🕐 2分钟前    │  │
│ │      └─ WindowName    [trigger]│  │  2024-03-17    │  │
│ └─────────────────────────────┘  └────────────────┘  │
└──────────────────────────────────────────────────────┘
```

#### 方案 B: 三行信息分组（已定稿）

**设计意图**：按信息关联度分组，确保所有卡片高度一致
- **第一行**：上下文标识（应用 + 触发方式 + 设备名称）
- **第二行**：内容标识（窗口标题，始终显示保持对齐）
- **第三行**：时间标识（相对时间 + 绝对时间）

```
┌──────────────────────────────────────────────────────────┐
│ [AppName] [trigger] [last known]          2分钟前        │
│ WindowName                                               │
│ 2024-03-17 10:23:45                   MONITOR_2          │
└──────────────────────────────────────────────────────────┘
```

**结构定义**：

| 元素 | 位置 | 样式 | 说明 |
|------|------|------|------|
| **应用名称** | 第一行左侧 | font-weight 600, 14px | 主标识，最大宽度 200px |
| **触发标签** | 第一行，app_name 右侧 | 8px padding, 圆角 4px, 彩色 | 与 app 关联，表示触发场景 |
| **设备名称** | 第一行右侧 | 11px, monospace, uppercase | MONITOR_2 等 |
| **窗口标题** | 第二行 | font-size 12px, color secondary | 内容上下文，无内容时留空，支持 last_known_window |
| **相对时间** | 第一行右侧 | 11px, color tertiary | "2分钟前" |
| **绝对时间** | 第三行左侧 | 11px, monospace | 格式：YYYY-MM-DD HH:MM:SS |
| **设备名称** | 第三行右侧 | 11px, monospace, uppercase | MONITOR_2 等 |
| **[last known] 标签** | 第一行，trigger 右侧 | 灰色背景，斜体 | 表示 app/window 为回退数据 |

**优势**：
1. **逻辑分组清晰**：每行一类信息（上下文/内容/时间）
2. **时间戳突出**：独立一行，便于扫描时间序列
3. **设备图标化**：节省空间，保持可访问性
4. **trigger 与 app 关联**：同一行表示「什么应用在什么场景下」

#### 方案 B: 极简单行

```
┌──────────────────────────────────────────────────────┐
│ [icon] AppName · WindowName    [trigger]  🕐 2分钟前  │
└──────────────────────────────────────────────────────┘
```

**适用场景**: 小屏幕、高密度模式

#### 方案 C: 当前保持（基准）

```
┌──────────────────────────────────────────────────────┐
│ AppName [trigger]                            Time    │
│ WindowName                                           │
│ DEVICE_NAME                                          │
└──────────────────────────────────────────────────────┘
```

### 3.3 Header 布局技术规范（方案 B 实现）

#### HTML 结构（Alpine.js）

```html
<div class="card-header">
  <!-- 第一行：应用 + 触发器 + 设备 -->
  <div class="header-row context-row">
    <div class="context-left">
      <span class="app-name" 
            x-text="entry.app_name || 'Unknown'"
            :title="entry.app_name">
        Safari
      </span>
      <span class="trigger-label" 
            x-text="entry.capture_trigger"
            x-show="entry.capture_trigger"
            :data-trigger="entry.capture_trigger">
        app_switch
      </span>
    </div>
    <span class="device-icon" 
          x-text="getDeviceIcon(entry.device_name)"
          :title="entry.device_name">
      🖥️
    </span>
  </div>
  
  <!-- 第二行：窗口标题 -->
  <div class="header-row window-row" x-show="entry.window_title || entry.title">
    <span class="window-name" 
          x-text="entry.window_title || entry.title || ''">
      GitHub - MyRecall
    </span>
  </div>
  
  <!-- 第三行：时间戳 -->
  <div class="header-row time-row">
    <span class="timestamp" x-text="formatTime(entry.timestamp)">
      2024-03-17 10:23:45
    </span>
    <span class="time-icon" 
          :title="formatRelativeTime(entry.timestamp)"
          x-show="entry.timestamp">
      🕐
    </span>
  </div>
</div>
```

#### CSS 规范（定稿版）

```css
.card-header-v2 {
  display: flex;
  flex-direction: column;
  padding: 10px 14px;
  gap: 4px;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-card);
}

/* 通用行样式 */
.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 18px;
}

/* 第一行：上下文（应用 + 触发器 + 设备名称） */
.context-row {
  gap: 8px;
}

.context-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.app-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex-shrink: 1;
}

.trigger-label {
  font-size: 10px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: capitalize;
  flex-shrink: 0;
  white-space: nowrap;
  background: rgba(0, 0, 0, 0.05);
  color: var(--text-secondary);
}

/* Trigger 类型着色 */
.trigger-label[data-trigger="idle"] {
  background: rgba(255, 149, 0, 0.12);
  color: #FF9500;
}

.trigger-label[data-trigger="app_switch"] {
  background: rgba(0, 122, 255, 0.12);
  color: #007AFF;
}

.trigger-label[data-trigger="click"] {
  background: rgba(52, 199, 89, 0.12);
  color: #34C759;
}

.trigger-label[data-trigger="manual"] {
  background: rgba(175, 82, 222, 0.12);
  color: #AF52DE;
}

.trigger-label.fallback-label {
  background: rgba(120, 120, 128, 0.12);
  color: #8E8E93;
  font-style: italic;
}

.context-row .relative-time {
  font-size: 11px;
  color: var(--text-tertiary, #8E8E93);
  font-weight: 500;
  flex-shrink: 0;
}

.device-name {
  font-size: 11px;
  color: var(--text-tertiary, #8E8E93);
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
  flex-shrink: 0;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

/* 第二行：窗口标题（始终显示保持对齐） */
.window-row {
  justify-content: flex-start;
}

.window-name {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  line-height: 1.3;
  min-height: 16px; /* 无内容时保持占位 */
}

/* 第三行：绝对时间 + 设备名称 */
  .time-row {
    margin-top: 2px;
    padding-top: 4px;
    border-top: 1px dashed rgba(0, 0, 0, 0.06);
    justify-content: space-between;
    gap: 8px;
  }

  /* 第一行右侧：相对时间 */
  .context-row .relative-time {
    font-size: 11px;
    color: var(--text-tertiary, #8E8E93);
    font-weight: 500;
    flex-shrink: 0;
  }

  .timestamp {
    font-size: 11px;
    color: var(--text-tertiary, #8E8E93);
    font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
    letter-spacing: -0.3px;
  }

  /* Card Image - 智能统一高度方案（参考 screenpipe） */
  .card-image-wrapper {
    width: 100%;
    height: 200px;
    overflow: hidden;
    background: #1a1a1a;
    position: relative;
    display: flex;
    align-items: flex-start;
    justify-content: center;
  }

  .card-image {
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: top center;
    cursor: pointer;
    transition: transform 0.3s ease;
  }

  .card-image:hover {
    transform: scale(1.05);
  }
```

### 3.4 设备图标映射

```javascript
function getDeviceIcon(deviceName) {
  if (!deviceName) return '🖥️';
  const name = deviceName.toLowerCase();
  if (name.includes('laptop') || name.includes('macbook')) return '💻';
  if (name.includes('phone') || name.includes('mobile')) return '📱';
  if (name.includes('tablet') || name.includes('ipad')) return '📋';
  if (name.includes('tv') || name.includes('television')) return '📺';
  if (name.includes('watch')) return '⌚';
  return '🖥️';
}
```

### 3.5 触发器标签样式

```css
.trigger-label[data-trigger="idle"] {
  background: rgba(255, 149, 0, 0.12);
  color: #FF9500;
}

.trigger-label[data-trigger="app_switch"] {
  background: rgba(0, 122, 255, 0.12);
  color: #007AFF;
}

.trigger-label[data-trigger="click"] {
  background: rgba(52, 199, 89, 0.12);
  color: #34C759;
}

.trigger-label[data-trigger="manual"] {
  background: rgba(175, 82, 222, 0.12);
  color: #AF52DE;
}
```

### 3.6 设备图标映射

```javascript
function getDeviceIcon(deviceName) {
  if (!deviceName) return '🖥️';
  const name = deviceName.toLowerCase();
  if (name.includes('laptop') || name.includes('macbook')) return '💻';
  if (name.includes('phone') || name.includes('mobile')) return '📱';
  if (name.includes('tablet') || name.includes('ipad')) return '📋';
  if (name.includes('tv') || name.includes('television')) return '📺';
  if (name.includes('watch')) return '⌚';
  return '🖥️';
}
```

### 3.7 相对时间格式化

```javascript
formatRelativeTime(ts) {
  const date = this.parseTimestamp(ts);
  if (!date) return '';
  
  const now = new Date();
  const diffMs = now - date;
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);
  
  if (diffSec < 60) return '刚刚';
  if (diffMin < 60) return `${diffMin}分钟前`;
  if (diffHour < 24) return `${diffHour}小时前`;
  if (diffDay < 7) return `${diffDay}天前`;
  
  return this.formatTime(ts); // 显示完整日期
}
```

### 3.8 时间显示策略

#### 相对时间规则

| 时间差 | 显示格式 | 示例 |
|--------|----------|------|
| < 1分钟 | "刚刚" | 刚刚 |
| < 1小时 | "{n}分钟前" | 23分钟前 |
| < 24小时 | "{n}小时前" | 3小时前 |
| < 7天 | "{n}天前" | 2天前 |
| >= 7天 | 具体日期 | 03-10 |

#### 绝对时间 tooltip

Hover 时显示完整格式：`2024-03-17 10:23:45`

---

## 4. Footer 区域详解

（待讨论填充）

---

## 5. 状态系统设计

（待讨论填充）

---

## 6. 响应式与可访问性

（待讨论填充）

---

## 7. 实现参考

### 7.1 当前代码位置

| 组件 | 文件 | 行号 |
|------|------|------|
| Card 结构 | `openrecall/server/templates/index.html` | 476-537 |
| Card CSS | `openrecall/server/templates/index.html` | 63-430 |
| Grid 数据 API | `openrecall/server/database/frames_store.py` | 504+ |
| Alpine.js 逻辑 | `openrecall/server/templates/index.html` | 567-758 |

### 7.2 相关测试

> E2E 测试已取消。UI 验证通过代码审查完成。

---

## 附录

### A. 设计决策记录

| 日期 | 决策 | 理由 | 状态 |
|------|------|------|------|
| 2026-03-17 | ~~device_name 图标化~~ | ~~减少视觉噪音~~ | ❌ 已否决，改为文字显示 |
| 2026-03-17 | trigger-label 与 app_name 同行 | 表示「应用在什么场景下被捕获」| ✅ 已采纳 |
| 2026-03-17 | Header 三行信息分组布局 | 按信息类型分组（上下文/内容/时间） | ✅ 已采纳 |
| 2026-03-17 | ~~时间图标 hover 显示相对时间~~ | ~~兼顾精确时间~~ | ❌ 已否决，改为直接显示 |
| 2026-03-17 | ~~相对时间直接显示在第三行~~ | ~~人类更易理解~~ | ❌ 已否决，移到第一行右侧 |
| 2026-03-17 | device_name 文字显示（monospace） | 技术感更强，便于识别 | ✅ 已采纳 |
| 2026-03-17 | 窗口标题行始终显示 | 保持所有卡片高度一致 | ✅ 已采纳 |
| 2026-03-17 | 相对时间移到第一行右侧 | 快速识别时效性 | ✅ 已采纳 |
| 2026-03-17 | device_name 移到第三行右侧 | 低频信息放底部 | ✅ 已采纳 |
| 2026-03-17 | [last known] 标签标注回退数据 | 明确表达数据回退 | ✅ 已采纳 |
| 2026-03-17 | last_known_app/window 回退显示 | 提升数据完整性 | ✅ 已采纳 |
| 2026-03-17 | 图片固定高度 200px + cover | 对齐 screenpipe，grid 整齐 | ✅ 已采纳 |
| 2026-03-17 | object-position: top | 优先显示截图顶部重要信息 | ✅ 已采纳 |
| 2026-03-17 | hover scale 1.05x | 临时查看完整内容 | ✅ 已采纳 |
| 2026-03-17 | Modal 详情面板 | Tab 切换显示元数据，不显示完整 OCR | ✅ 已采纳 |

### B. 待讨论议题

- [x] Header 布局方案选择（A/B/C）→ **已确定方案 B（已定稿）**
- [x] Device 显示方式（图标 vs 文字）→ **已确定文字显示**
- [x] 时间显示策略 → **已确定相对时间 + 绝对时间同行**
- [ ] Footer 快捷操作设计
- [ ] 深色主题颜色映射
- [ ] 键盘导航规范
- [ ] 移动端适配策略

### C. 实现代码参考

#### C.1 Header HTML 替换（index.html:600-642）

**当前代码（已弃用）：**
```html
<div class="card-header">
  <div class="card-header-content">
    <div class="card-app-line">
      <span class="card-app" x-text="entry.app_name || entry.app || 'Unknown'" ...></span>
      <span class="trigger-label" x-text="entry.capture_trigger || ''" ...></span>
    </div>
    <span class="card-window" x-text="entry.window_title || entry.title || ''" ...></span>
    <span class="card-device" x-text="entry.device_name || ''" ...></span>
  </div>
  <span class="card-time" x-text="formatTime(entry.timestamp)"></span>
</div>
```

**新方案代码（已定稿）：**
```html
<!-- Header: 三行信息分组布局 -->
<div class="card-header-v2">
  <!-- 第一行：应用 + 触发器 + [last known] + 相对时间 -->
  <div class="header-row context-row">
    <div class="context-left">
      <span class="app-name" 
            :class="{ 'fallback': !entry.app_name && !entry.app && entry.last_known_app }"
            x-text="getAppDisplay(entry)" 
            :title="getAppNameTooltip(entry)"
      ></span>
      <span class="trigger-label" 
            x-text="entry.capture_trigger" 
            x-show="entry.capture_trigger"
            :data-trigger="entry.capture_trigger"
      ></span>
      <span class="trigger-label fallback-label"
            x-show="!entry.app_name && !entry.app && entry.last_known_app"
      >last known</span>
    </div>
    <span class="relative-time" x-text="formatRelativeTime(entry.timestamp)"
    ></span>
  </div>
  
  <!-- 第二行：窗口标题（始终显示，无内容时占位） -->
  <div class="header-row window-row">
    <span class="window-name" 
          x-text="entry.window_title || entry.title || entry.last_known_window || ''"
    ></span>
  </div>
  
  <!-- 第三行：绝对时间 + 设备名称 -->
  <div class="header-row time-row">
    <span class="timestamp" x-text="formatTime(entry.timestamp)"
    ></span>
    <span class="device-name" 
          x-text="entry.device_name"
          x-show="entry.device_name"
    ></span>
  </div>
</div>
```

**新方案代码：**
```html
<!-- Header: 三行信息分组布局 -->
<div class="card-header-v2">
  <!-- 第一行：上下文（应用 + 触发器 + 设备图标）-->
  <div class="header-row context-row">
    <div class="context-left">
      <span class="app-name" 
            x-text="entry.app_name || entry.app || 'Unknown'" 
            :title="entry.app_name || entry.app || ''"></span>
      <span class="trigger-label" 
            x-text="entry.capture_trigger" 
            x-show="entry.capture_trigger"
            :data-trigger="entry.capture_trigger"></span>
    </div>
    <span class="device-icon" 
          x-text="getDeviceIcon(entry.device_name)"
          :title="entry.device_name || 'Unknown device'"
          x-show="entry.device_name"></span>
  </div>
  
  <!-- 第二行：窗口标题 -->
  <div class="header-row window-row" x-show="entry.window_title || entry.title">
    <span class="window-name" 
          x-text="entry.window_title || entry.title || ''"></span>
  </div>
  
  <!-- 第三行：时间戳 -->
  <div class="header-row time-row">
    <span class="timestamp" x-text="formatTime(entry.timestamp)"></span>
    <span class="time-icon" 
          title="Click to view relative time"
          @mouseenter="$el.setAttribute('data-relative', formatRelativeTime(entry.timestamp))"
          x-data="{ showRelative: false }"
          @click="showRelative = !showRelative"
          x-text="showRelative ? formatRelativeTime(entry.timestamp) : '🕐'"></span>
  </div>
</div>
```

#### C.2 CSS 追加（index.html style 区块）

```css
/* =============================================
   Header V2 - 三行信息分组布局
   ============================================= */

.card-header-v2 {
  display: flex;
  flex-direction: column;
  padding: 10px 14px;
  gap: 4px;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-card);
}

/* 通用行样式 */
.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 18px;
}

/* 第一行：上下文（应用 + 触发器 + 设备） */
.context-row {
  gap: 8px;
}

.context-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.app-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex-shrink: 1;
}

.trigger-label {
  font-size: 10px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: capitalize;
  flex-shrink: 0;
  white-space: nowrap;
  background: rgba(0, 0, 0, 0.05);
  color: var(--text-secondary);
}

/* Trigger 类型着色 */
.trigger-label[data-trigger="idle"] {
  background: rgba(255, 149, 0, 0.12);
  color: #FF9500;
}

.trigger-label[data-trigger="app_switch"] {
  background: rgba(0, 122, 255, 0.12);
  color: #007AFF;
}

.trigger-label[data-trigger="click"] {
  background: rgba(52, 199, 89, 0.12);
  color: #34C759;
}

.trigger-label[data-trigger="manual"] {
  background: rgba(175, 82, 222, 0.12);
  color: #AF52DE;
}

.device-icon {
  font-size: 14px;
  opacity: 0.5;
  flex-shrink: 0;
  cursor: help;
  transition: opacity 0.2s;
  line-height: 1;
}

.device-icon:hover {
  opacity: 0.8;
}

/* 第二行：窗口标题 */
.window-row {
  justify-content: flex-start;
}

.window-name {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  line-height: 1.3;
}

/* 第三行：时间戳 */
.time-row {
  margin-top: 2px;
  padding-top: 4px;
  border-top: 1px dashed rgba(0, 0, 0, 0.06);
}

.timestamp {
  font-size: 11px;
  color: var(--text-tertiary, #8E8E93);
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
  letter-spacing: -0.3px;
}

.time-icon {
  font-size: 12px;
  opacity: 0.4;
  cursor: pointer;
  transition: opacity 0.2s;
  line-height: 1;
  user-select: none;
}

.time-icon:hover {
  opacity: 0.7;
}
```

#### C.3 JavaScript 辅助函数（memoryGrid 对象）

```javascript
function memoryGrid() {
  return {
    entries: window.initialEntries || [],
    config: window.initialConfig || { show_ai_description: false },
    lastCheckMs: 0,
    selectedIndex: null,

    // ... 现有方法保持不变 ...

    /**
     * 格式化相对时间
     * @param {number|string} ts - 时间戳
     * @returns {string} 相对时间描述
     */
    formatRelativeTime(ts) {
      const date = this.parseTimestamp(ts);
      if (!date) return '';

      const now = new Date();
      const diffMs = now - date;
      const diffSec = Math.floor(diffMs / 1000);
      const diffMin = Math.floor(diffSec / 60);
      const diffHour = Math.floor(diffMin / 60);
      const diffDay = Math.floor(diffHour / 24);

      if (diffSec < 60) return '刚刚';
      if (diffMin < 60) return `${diffMin}分钟前`;
      if (diffHour < 24) return `${diffHour}小时前`;
      if (diffDay < 7) return `${diffDay}天前`;

      return this.formatTime(ts);
    },

    /**
     * 获取应用显示名称（支持 last_known_app 回退）
     * @param {Object} entry - frame entry
     * @returns {string} 应用名称
     */
    getAppDisplay(entry) {
      if (!entry) return 'Unknown';
      return entry.app_name || entry.app || entry.last_known_app || 'Unknown';
    },

    /**
     * 获取应用名称 tooltip（说明是否为回退数据）
     * @param {Object} entry - frame entry
     * @returns {string} tooltip 文本
     */
    getAppNameTooltip(entry) {
      if (!entry) return '';
      if (entry.app_name || entry.app) {
        return entry.app_name || entry.app || '';
      }
      if (entry.last_known_app) {
        return `Current context unknown. Last known: ${entry.last_known_app}`;
      }
      return 'Unknown application';
    },

    // ... 其他现有方法 ...
  };
}
```

#### C.4 图片容器改造（index.html:124-145）

**原代码：**
```html
<img
  :src="imageSrc(entry)"
  alt="Screenshot"
  class="card-image"
  :loading="i < 8 ? 'eager' : 'lazy'"
  decoding="async"
  :fetchpriority="i < 2 ? 'high' : 'auto'"
  @click="openAt(i)"
>
```

**新方案代码：**
```html
<div class="card-image-wrapper">
  <img
    :src="imageSrc(entry)"
    alt="Screenshot"
    class="card-image"
    :loading="i < 8 ? 'eager' : 'lazy'"
    decoding="async"
    :fetchpriority="i < 2 ? 'high' : 'auto'"
    @click="openAt(i)"
  >
</div>
```

#### C.5 Modal 详情面板改造（index.html:719-890）

**功能说明**：
- 点击 frame 打开 Modal，支持 Tab 切换
- **图片 Tab**：大图预览 + 基础元信息 overlay
- **元数据 Tab**：完整技术信息，不显示 OCR 全文

**实现代码**：
```html
<div id="imageModal" class="modal" :class="{ 'active': isOpen() }" @click.self="closeModal()">
  <button class="modal-nav prev" type="button" @click="prev()">‹</button>
  <button class="modal-nav next" type="button" @click="next()">›</button>
  <span class="modal-close" role="button" @click="closeModal()">&times;</span>
  
  <div class="modal-container">
    <!-- Tab 导航 -->
    <div class="modal-tabs">
      <button type="button" class="modal-tab" 
              :class="{ 'active': modalTab === 'image' }"
              @click="modalTab = 'image'">图片</button>
      <button type="button" class="modal-tab" 
              :class="{ 'active': modalTab === 'metadata' }"
              @click="modalTab = 'metadata'">元数据</button>
    </div>
    
    <!-- Tab 内容 -->
    <div class="modal-tab-content">
      <!-- 图片预览 -->
      <div x-show="modalTab === 'image'" class="modal-image-panel">
        <div class="modal-meta-overlay">
          <div x-text="selectedIndex !== null ? `${selectedIndex + 1} / ${entries.length}` : ''"></div>
          <div x-text="selectedEntry?.app || 'Unknown'"></div>
          <div x-text="selectedEntry ? formatTime(selectedEntry.timestamp) : ''"></div>
        </div>
        <img :src="selectedEntry ? imageSrc(selectedEntry) : ''">
      </div>
      
      <!-- 元数据面板 -->
      <div x-show="modalTab === 'metadata'" class="modal-metadata-panel">
        <div class="metadata-section">
          <h3>基本信息</h3>
          <div class="metadata-grid">
            <div class="metadata-item">
              <span class="metadata-label">Frame ID</span>
              <span class="metadata-value" x-text="selectedEntry?.id || '-'"></span>
            </div>
            <div class="metadata-item">
              <span class="metadata-label">应用</span>
              <span class="metadata-value" x-text="selectedEntry?.app_name || 'Unknown'"></span>
            </div>
            <div class="metadata-item">
              <span class="metadata-label">窗口</span>
              <span class="metadata-value" x-text="selectedEntry?.window_title || '-'"></span>
            </div>
            <!-- ... 其他字段 ... -->
          </div>
        </div>
        
        <div class="metadata-section">
          <h3>技术信息</h3>
          <div class="metadata-grid">
            <div class="metadata-item">
              <span class="metadata-label">状态</span>
              <span class="metadata-value" x-text="selectedEntry?.status || 'pending'"></span>
            </div>
            <div class="metadata-item">
              <span class="metadata-label">文本来源</span>
              <span class="metadata-value" x-text="selectedEntry?.text_source || '-'"></span>
            </div>
            <div class="metadata-item">
              <span class="metadata-label">文本长度</span>
              <span class="metadata-value" x-text="(selectedEntry?.text_length || 0) + ' 字符'"></span>
            </div>
            <div class="metadata-item">
              <span class="metadata-label">文件大小</span>
              <span class="metadata-value" x-text="formatFileSize(selectedEntry?.image_size_bytes)"></span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
```

**关键特性**：
- **不显示完整 OCR 文本**：元数据面板只显示 `text_length`，不展示 `ocr_text`
- **分组展示**：基本信息、时间信息、技术信息、错误信息分区域
- **网格布局**：metadata-grid 使用 CSS Grid 响应式排列
- **Tab 切换记忆**：`modalTab` 状态由 Alpine.js 管理

#### C.6 JavaScript 辅助函数

```javascript
// 在 memoryGrid() 中添加
return {
  // ... 其他属性 ...
  modalTab: 'image',  // 默认显示图片 Tab

  /**
   * 计算处理耗时
   */
  getProcessingDuration(entry) {
    if (!entry || !entry.processed_at || !entry.ingested_at) return '-';
    const duration = new Date(entry.processed_at) - new Date(entry.ingested_at);
    if (duration < 1000) return `${duration}ms`;
    if (duration < 60000) return `${(duration / 1000).toFixed(1)}s`;
    return `${(duration / 60000).toFixed(1)}m`;
  },

  /**
   * 格式化文件大小
   */
  formatFileSize(bytes) {
    if (!bytes) return '-';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  }
};
```

#### C.7 迁移说明

1. **渐进式部署**：保留旧的 `.card-header` 类，新增 `.card-header-v2` 类
2. **兼容性**：旧代码继续工作，新布局通过类名切换启用
3. **回滚策略**：只需改回类名即可恢复旧布局
