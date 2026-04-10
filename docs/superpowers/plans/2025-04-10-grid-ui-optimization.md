# Grid UI 优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 优化 Grid 界面 UI，采用 Apple 风格设计：重构 Header 为两行精简布局，Footer 改为 2x2 网格状态系统，柔和化颜色方案

**Architecture:** 保持现有 Alpine.js + Jinja2 模板架构，仅修改样式和 HTML 结构，添加新的 CSS 类（`card-header-v3`, `card-footer-grid` 等），保留原有数据逻辑

**Tech Stack:** HTML, CSS, Alpine.js, Jinja2, Flask

---

## 文件映射

| 文件 | 责任 | 变更类型 |
|------|------|----------|
| `openrecall/client/web/templates/index.html` | Grid 页面模板，包含 HTML 结构、CSS 样式、Alpine.js 逻辑 | 修改 |

---

## Task 1: 添加 CSS 变量和基础样式

**文件:**
- 修改: `openrecall/client/web/templates/index.html:16-45`（`<style>` 块开始处）

- [ ] **Step 1: 添加柔和化颜色变量**

在现有的 `:root` 变量后添加新的颜色系统：

```css
:root {
  /* 保持现有变量... */

  /* 柔和化状态色 */
  --color-success: #5BC88C;
  --color-success-bg: rgba(91, 200, 140, 0.1);
  --color-success-border: rgba(91, 200, 140, 0.15);

  --color-primary: #4A9EFF;
  --color-primary-bg: rgba(74, 158, 255, 0.1);
  --color-primary-border: rgba(74, 158, 255, 0.15);

  --color-warning: #FFB84D;
  --color-warning-bg: rgba(255, 184, 77, 0.1);
  --color-warning-border: rgba(255, 184, 77, 0.15);

  --color-error: #FF6B6B;
  --color-error-bg: rgba(255, 107, 107, 0.1);
  --color-error-border: rgba(255, 107, 107, 0.15);

  --color-neutral: #8E8E93;
  --color-neutral-bg: rgba(142, 142, 147, 0.1);
  --color-neutral-border: rgba(142, 142, 147, 0.15);

  /* 文本层次 */
  --text-tertiary: #8E8E93;
  --bg-footer: #FAFAFA;
}
```

- [ ] **Step 2: 添加脉冲动画关键帧**

在样式块的 `@keyframes` 区域添加：

```css
@keyframes pulse-soft {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.7;
    transform: scale(0.95);
  }
}
```

- [ ] **Step 3: 更新 Grid 间距**

找到 `.memory-grid` 类（约第 64-69 行），修改为：

```css
.memory-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 28px;
  padding: 28px 0;
}
```

- [ ] **Step 4: 更新卡片悬停效果**

找到 `.memory-card:hover` 类（约第 82-85 行），修改为：

```css
.memory-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.1);
}
```

- [ ] **Step 5: 更新卡片状态边条**

找到 `/* P1-S3: Status-specific card styling */` 区域（约第 798-813 行），修改为更细的边条：

```css
/* P1-S3: Status-specific card styling - Apple style subtle */
.memory-card[data-frame-status="pending"] {
  border-left: 2px solid var(--color-warning);
}

.memory-card[data-frame-status="processing"] {
  border-left: 2px solid var(--color-primary);
}

.memory-card[data-frame-status="completed"] {
  border-left: 2px solid var(--color-success);
}

.memory-card[data-frame-status="failed"] {
  border-left: 2px solid var(--color-error);
}
```

- [ ] **Step 6: Commit**

```bash
git add openrecall/client/web/templates/index.html
git commit -m "style(grid): add soft color system and base layout adjustments"
```

---

## Task 2: 添加 Header V3 样式

**文件:**
- 修改: `openrecall/client/web/templates/index.html:855-997`（在 `card-header-v2` 样式后添加）

- [ ] **Step 1: 添加 Header V3 基础样式**

在 `card-header-v2` 样式块之后添加新的 Header V3 样式：

```css
/* =============================================
   Header V3 - Apple Style Refined Layout
   ============================================= */

.card-header-v3 {
  display: flex;
  flex-direction: column;
  padding: 12px 16px;
  gap: 6px;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-card);
}

/* 第一行：上下文 */
.header-row {
  display: flex;
  align-items: center;
  min-height: 20px;
}

.context-row {
  justify-content: space-between;
}

.context-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.app-icon {
  font-size: 14px;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.app-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.app-name.fallback {
  font-style: italic;
  color: var(--text-secondary);
}

.trigger-badge {
  font-size: 10px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 10px;
  text-transform: capitalize;
  flex-shrink: 0;
  white-space: nowrap;
  background: rgba(0, 0, 0, 0.05);
  color: var(--text-secondary);
}

.trigger-badge[data-trigger="idle"] {
  background: var(--color-warning-bg);
  color: #D4840D;
}

.trigger-badge[data-trigger="app_switch"] {
  background: var(--color-primary-bg);
  color: #0A6ED6;
}

.trigger-badge[data-trigger="click"] {
  background: var(--color-success-bg);
  color: #2A9D4A;
}

.trigger-badge[data-trigger="manual"] {
  background: rgba(175, 82, 222, 0.1);
  color: #8E4DB0;
}

.frame-id {
  font-size: 11px;
  color: var(--text-tertiary);
  font-weight: 500;
  font-family: 'SF Mono', Monaco, Consolas, monospace;
  flex-shrink: 0;
}

/* 第二行：窗口标题 */
.window-row {
  min-height: 18px;
  display: flex;
  align-items: center;
}

.window-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.4;
}

/* 第三行：元信息 */
.meta-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 16px;
  margin-top: 2px;
  padding-top: 6px;
  border-top: 1px solid rgba(0, 0, 0, 0.04);
}

.meta-row .timestamp,
.meta-row .relative-time,
.meta-row .device-name {
  font-size: 11px;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.meta-row .timestamp {
  font-family: 'SF Mono', Monaco, Consolas, monospace;
  letter-spacing: -0.2px;
}

.meta-row .separator {
  font-size: 11px;
  color: var(--text-tertiary);
  opacity: 0.6;
}
```

- [ ] **Step 2: Commit**

```bash
git add openrecall/client/web/templates/index.html
git commit -m "style(grid): add header v3 styles"
```

---

## Task 3: 添加 Footer Grid 样式

**文件:**
- 修改: `openrecall/client/web/templates/index.html:797-814`（在状态边条样式后添加）

- [ ] **Step 1: 添加 Footer Grid 样式**

```css
/* =============================================
   Card Footer Grid Layout
   ============================================= */

.card-footer-grid {
  padding: 12px 14px;
  background: var(--bg-footer);
  border-top: 1px solid var(--border-color);
}

/* 2x2 网格 */
.status-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 10px;
}

.status-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  background: rgba(255, 255, 255, 0.8);
  border-radius: 8px;
  border: 1px solid rgba(0, 0, 0, 0.04);
  transition: all 0.2s ease;
}

.status-cell:hover {
  background: rgba(255, 255, 255, 1);
  border-color: rgba(0, 0, 0, 0.08);
}

.cell-header {
  display: flex;
  align-items: center;
  gap: 6px;
}

.cell-icon {
  font-size: 13px;
}

.cell-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.cell-value {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
  font-family: 'SF Mono', Monaco, Consolas, monospace;
}

/* 状态特定样式 */
.status-cell.active {
  background: var(--color-success-bg);
  border-color: var(--color-success-border);
}

.status-cell.active .cell-label {
  color: #2A9D4A;
}

.status-cell.inactive {
  opacity: 0.6;
}

.status-cell.status-completed {
  background: var(--color-success-bg);
  border-color: var(--color-success-border);
}

.status-cell.status-completed .cell-label {
  color: #2A9D4A;
}

.status-cell.status-processing {
  background: var(--color-primary-bg);
  border-color: var(--color-primary-border);
}

.status-cell.status-processing .cell-label {
  color: #0A6ED6;
}

.status-cell.status-pending {
  background: var(--color-neutral-bg);
  border-color: var(--color-neutral-border);
}

.status-cell.status-pending .cell-label {
  color: var(--color-neutral);
}

.status-cell.status-failed {
  background: var(--color-error-bg);
  border-color: var(--color-error-border);
}

.status-cell.status-failed .cell-label {
  color: #D63126;
}

/* Frame 状态条 */
.frame-status-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  text-transform: capitalize;
  transition: all 0.2s ease;
}

.frame-status-bar .status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.frame-status-bar.status-completed {
  background: var(--color-success-bg);
  color: #2A9D4A;
}

.frame-status-bar.status-processing {
  background: var(--color-primary-bg);
  color: #0A6ED6;
}

.frame-status-bar.status-processing .status-dot {
  animation: pulse-soft 1.5s ease-in-out infinite;
}

.frame-status-bar.status-pending {
  background: var(--color-warning-bg);
  color: #D4840D;
}

.frame-status-bar.status-failed {
  background: var(--color-error-bg);
  color: #D63126;
}

/* 脉冲点 */
.pulse-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse-soft 1.5s ease-in-out infinite;
}
```

- [ ] **Step 2: Commit**

```bash
git add openrecall/client/web/templates/index.html
git commit -m "style(grid): add footer grid layout styles"
```

---

## Task 4: 更新 Stats Bar 样式

**文件:**
- 修改: `openrecall/client/web/templates/index.html:538-567`（Stats Bar 样式区域）

- [ ] **Step 1: 更新 Stats Bar 样式**

找到 `.stats-bar` 和相关样式，替换为：

```css
/* Stats Bar - Refined */
.stats-bar {
  display: flex;
  gap: 24px;
  margin-bottom: 24px;
  padding: 14px 24px;
  background: var(--bg-card);
  border-radius: 12px;
  border: 1px solid var(--border-color);
  width: fit-content;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--text-secondary);
}

.stat-value {
  font-weight: 600;
  color: var(--text-primary);
  background: rgba(0, 0, 0, 0.04);
  padding: 3px 10px;
  border-radius: 8px;
  font-size: 13px;
  font-family: 'SF Mono', Monaco, Consolas, monospace;
  min-width: 24px;
  text-align: center;
}

/* Stats 状态颜色 */
.stat-item[data-status="completed"] .stat-value {
  background: var(--color-success-bg);
  color: #2A9D4A;
}

.stat-item[data-status="processing"] .stat-value {
  background: var(--color-primary-bg);
  color: #0A6ED6;
}

.stat-item[data-status="pending"] .stat-value {
  background: var(--color-warning-bg);
  color: #D4840D;
}
```

- [ ] **Step 2: Commit**

```bash
git add openrecall/client/web/templates/index.html
git commit -m "style(grid): update stats bar styling"
```

---

## Task 5: 添加响应式适配

**文件:**
- 修改: `openrecall/client/web/templates/index.html`（在样式块末尾添加）

- [ ] **Step 1: 添加响应式样式**

在样式块末尾（`[x-cloak]` 样式后）添加：

```css
/* =============================================
   Responsive Adaptations
   ============================================= */

@media (max-width: 768px) {
  .memory-grid {
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 20px;
    padding: 20px 0;
  }

  .card-header-v3 {
    padding: 10px 12px;
  }

  .app-name {
    font-size: 13px;
  }

  .window-name {
    font-size: 12px;
  }

  .status-grid {
    gap: 6px;
  }

  .status-cell {
    padding: 6px 8px;
  }

  .cell-label {
    font-size: 10px;
  }

  .cell-value {
    font-size: 11px;
  }

  .stats-bar {
    gap: 16px;
    padding: 12px 18px;
  }

  .stat-item {
    font-size: 13px;
  }
}

@media (max-width: 480px) {
  .memory-grid {
    grid-template-columns: 1fr;
    gap: 16px;
  }

  .stats-bar {
    flex-wrap: wrap;
    gap: 12px;
    padding: 12px 16px;
    width: auto;
  }

  .card-footer-grid {
    padding: 10px 12px;
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add openrecall/client/web/templates/index.html
git commit -m "style(grid): add responsive styles"
```

---

## Task 6: 更新 HTML Header 结构

**文件:**
- 修改: `openrecall/client/web/templates/index.html:1230-1269`（`card-header-v2` HTML 部分）

- [ ] **Step 1: 替换 Header 结构**

找到 `<div class="card-header-v2">` 部分（约第 1230-1269 行），替换为新的 V3 结构：

```html
<div class="card-header-v3">
  <!-- 第一行：应用 + 触发器 + Frame ID -->
  <div class="header-row context-row">
    <div class="context-left">
      <span class="app-icon" x-html="getAppIcon(entry)"></span>
      <span class="app-name"
            :class="{ 'fallback': !entry.app_name && !entry.app && entry.last_known_app }"
            x-text="getAppDisplay(entry)"
            :title="getAppNameTooltip(entry)"
      ></span>
      <span class="trigger-badge"
            x-text="entry.capture_trigger"
            x-show="entry.capture_trigger"
            :data-trigger="entry.capture_trigger"
      ></span>
      <span class="trigger-badge fallback-label"
            x-show="!entry.app_name && !entry.app && entry.last_known_app"
      >last known</span>
    </div>
    <span class="frame-id" x-text="'No.' + entry.frame_id"></span>
  </div>

  <!-- 第二行：窗口标题 -->
  <div class="header-row window-row">
    <span class="window-name"
          x-text="entry.window_title || entry.title || entry.last_known_window || ''"
          :title="entry.window_title || entry.title || entry.last_known_window || ''"
    ></span>
  </div>

  <!-- 第三行：时间信息 -->
  <div class="header-row meta-row">
    <span class="timestamp" x-text="formatTime(entry.timestamp)"></span>
    <span class="separator">·</span>
    <span class="relative-time" x-text="formatRelativeTime(entry.timestamp)"></span>
    <span class="separator" x-show="entry.device_name">·</span>
    <span class="device-name"
          x-text="entry.device_name"
          x-show="entry.device_name"
    ></span>
  </div>
</div>
```

- [ ] **Step 2: Commit**

```bash
git add openrecall/client/web/templates/index.html
git commit -m "refactor(grid): update header to v3 layout"
```

---

## Task 7: 更新 HTML Footer 结构

**文件:**
- 修改: `openrecall/client/web/templates/index.html:1283-1335`（`card-footer-flow` HTML 部分）

- [ ] **Step 1: 替换 Footer 结构**

找到 `<div class="card-footer-flow"` 部分（约第 1283-1335 行），替换为新的 Grid 结构：

```html
<div class="card-footer-grid" role="region" aria-label="处理状态">
  <!-- 2x2 网格 -->
  <div class="status-grid">
    <!-- AX -->
    <div class="status-cell" :class="[getTextSourceClass(entry, 'accessibility'), getTextSourceStatusClass(entry, 'accessibility')]">
      <div class="cell-header">
        <span class="cell-icon">📱</span>
        <span class="cell-label">AX</span>
      </div>
      <div class="cell-value" x-text="formatCharCount(getAccessibilityCharCount(entry))"></div>
    </div>

    <!-- Description -->
    <div class="status-cell" :class="getDescriptionStatusClass(entry)">
      <div class="cell-header">
        <span class="cell-icon">✨</span>
        <span class="cell-label">Desc</span>
      </div>
      <div class="cell-value" x-html="getDescriptionStatusText(entry)"></div>
    </div>

    <!-- OCR -->
    <div class="status-cell" :class="[getTextSourceClass(entry, 'ocr'), getTextSourceStatusClass(entry, 'ocr')]">
      <div class="cell-header">
        <span class="cell-icon">📝</span>
        <span class="cell-label">OCR</span>
      </div>
      <div class="cell-value" x-text="formatCharCount(getOcrCharCount(entry))"></div>
    </div>

    <!-- Embedding -->
    <div class="status-cell" :class="getEmbeddingStatusClass(entry)">
      <div class="cell-header">
        <span class="cell-icon">🧠</span>
        <span class="cell-label">Embed</span>
      </div>
      <div class="cell-value" x-html="getEmbeddingStatusText(entry)"></div>
    </div>
  </div>

  <!-- Frame 状态条 -->
  <div class="frame-status-bar" :class="getFrameStatusClass(entry)">
    <span class="status-dot"></span>
    <span class="status-label" x-text="getFrameStatusText(entry)"></span>
  </div>
</div>
```

- [ ] **Step 2: Commit**

```bash
git add openrecall/client/web/templates/index.html
git commit -m "refactor(grid): update footer to grid layout"
```

---

## Task 8: 添加 Alpine.js 辅助函数

**文件:**
- 修改: `openrecall/client/web/templates/index.html:1190-1250`（Alpine.js `memoryGrid()` 函数区域）

- [ ] **Step 1: 添加新函数到 Alpine.js 组件**

找到 Alpine.js 的 `memoryGrid()` 函数，在现有方法后添加新函数：

```javascript
// 格式化字符数（添加千位分隔符）
formatCharCount(count) {
  const num = parseInt(count) || 0;
  if (num === 0) return '0';
  return num.toLocaleString('en-US') + '字';
},

// 获取应用图标
getAppIcon(entry) {
  const appName = entry.app_name || entry.app || '';
  const iconMap = {
    'Code': '💻',
    'code': '💻',
    'cursor': '💻',
    'Google Chrome': '🌐',
    'chrome': '🌐',
    'Safari': '🌐',
    'Firefox': '🌐',
    'cmux': '📱',
    'Terminal': '⌨️',
    'terminal': '⌨️',
    'iTerm': '⌨️',
    'default': '📱'
  };
  return iconMap[appName] || iconMap['default'];
},

// 获取描述状态文本
getDescriptionStatusText(entry) {
  const status = entry.description_status || 'pending';
  const labels = {
    pending: '○ pending',
    processing: '<span class="pulse-dot"></span> processing',
    completed: '● done',
    failed: '✕ failed'
  };
  return labels[status] || labels.pending;
},

// 获取嵌入状态文本
getEmbeddingStatusText(entry) {
  const status = entry.embedding_status || 'pending';
  const labels = {
    pending: '○ pending',
    processing: '<span class="pulse-dot"></span> processing',
    completed: '● done',
    failed: '✕ failed'
  };
  return labels[status] || labels.pending;
}
```

- [ ] **Step 2: Commit**

```bash
git add openrecall/client/web/templates/index.html
git commit -m "feat(grid): add helper functions for new layout"
```

---

## Task 9: 更新 Stats Bar HTML

**文件:**
- 修改: `openrecall/client/web/templates/index.html:1212-1225`（Stats Bar HTML 部分）

- [ ] **Step 1: 添加 data-status 属性**

找到 Stats Bar 的 HTML（约第 1212-1225 行），修改为：

```html
<div class="stats-bar">
  <div class="stat-item" data-status="completed">
    <span>Completed</span>
    <span class="stat-value" x-text="stats().completed"></span>
  </div>
  <div class="stat-item" data-status="processing">
    <span>Processing</span>
    <span class="stat-value" x-text="stats().processing"></span>
  </div>
  <div class="stat-item" data-status="pending">
    <span>Pending</span>
    <span class="stat-value" x-text="stats().pending"></span>
  </div>
</div>
```

- [ ] **Step 2: Commit**

```bash
git add openrecall/client/web/templates/index.html
git commit -m "refactor(grid): update stats bar with status attributes"
```

---

## Task 10: 清理旧样式

**文件:**
- 修改: `openrecall/client/web/templates/index.html`（删除旧的 card-header-v2 和 card-footer-flow 样式）

- [ ] **Step 1: 删除旧 Header V2 样式**

找到 `/* =============================================
     Header V2 - 三行信息分组布局
     ============================================= */` 区域（约第 853-997 行），删除整个样式块。

- [ ] **Step 2: 删除旧 Footer Flow 样式**

找到 `/* =============================================
   Card Footer Flow Layout
   ============================================= */` 区域（约第 579-796 行），删除整个样式块。

- [ ] **Step 3: Commit**

```bash
git add openrecall/client/web/templates/index.html
git commit -m "cleanup(grid): remove old header v2 and footer flow styles"
```

---

## Task 11: 验证和测试

- [ ] **Step 1: 启动开发服务器**

```bash
# Terminal 1: 启动 Edge Server
./run_server.sh --mode local --debug

# Terminal 2: 启动 Client
./run_client.sh --mode local --debug
```

- [ ] **Step 2: 验证视觉检查清单**

打开 http://localhost:8889 检查：

- [ ] Header 显示应用图标 + 应用名 + 触发器微标
- [ ] Header 窗口标题清晰可见
- [ ] Header 时间/设备信息颜色较淡
- [ ] Footer 显示 2x2 网格（AX/OCR/Desc/Embed）
- [ ] Footer 底部显示 Frame Status 条
- [ ] 卡片悬停有上浮效果
- [ ] 颜色柔和不刺眼
- [ ] 不同状态（completed/processing/pending）颜色正确

- [ ] **Step 3: 验证响应式**

- [ ] 缩小浏览器窗口到 768px 以下，检查布局适应
- [ ] 缩小到 480px 以下，检查单列布局

- [ ] **Step 4: Commit 最终版本**

```bash
git add openrecall/client/web/templates/index.html
git commit -m "style(grid): Apple-style subtle design for card header and footer"
```

---

## 实施注意事项

1. **保留现有函数**: `getTextSourceClass`, `getTextSourceStatusClass`, `getAccessibilityCharCount`, `getOcrCharCount`, `getDescriptionStatusClass`, `getEmbeddingStatusClass`, `getFrameStatusClass`, `getFrameStatusText`, `getAppDisplay`, `getAppNameTooltip`, `formatTime`, `formatRelativeTime` 等现有函数保持不变

2. **渐进式实施**: 如果希望分阶段实施，可以先做 Header V3，确认无误后再做 Footer Grid

3. **回滚准备**: 修改前建议备份当前 `index.html`，或确保可以通过 git 回滚

4. **浏览器兼容性**: 使用现代 CSS 特性（backdrop-filter, grid 等），确保在目标浏览器中测试
