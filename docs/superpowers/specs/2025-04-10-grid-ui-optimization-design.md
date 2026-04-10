# Grid UI 优化设计文档

**日期**: 2025-04-10
**方案**: 精致信息卡片（方案 A）
**风格**: Apple Design Language

---

## 1. 设计目标

- **美观**: 采用 Apple 风格设计语言，柔和色调，精致排版
- **简洁**: 优化信息密度，通过视觉层次让信息更易消化
- **清晰**: 重构 Header 和 Footer 结构，增强信息层次
- **标识准确**: 柔和化状态指示颜色，保持辨识度

---

## 2. 整体布局调整

### 2.1 Grid 间距优化

```css
.memory-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 28px;  /* 从 24px 增加 */
  padding: 28px 0;
}
```

### 2.2 卡片基础样式

```css
.memory-card {
  background: var(--bg-card, #FFFFFF);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1),
              box-shadow 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.memory-card:hover {
  transform: translateY(-4px);  /* 从 -2px 增加 */
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);  /* 更深阴影 */
}
```

---

## 3. Header 重构（两行精简布局）

### 3.1 结构变化

**当前（三行）**:
```
应用名 + 触发器                    Frame ID
窗口标题
时间 · 相对时间 · 设备
```

**优化后（三行精简版）**:
```
[图标] 应用名          [触发器微标]  [Frame ID]
窗口标题（主视觉，加粗）
时间 · 相对时间 · 设备（颜色减淡）
```

### 3.2 HTML 结构

```html
<div class="card-header-v3">
  <!-- 第一行：上下文信息 -->
  <div class="header-row context-row">
    <div class="context-left">
      <span class="app-icon" x-html="getAppIcon(entry)"></span>
      <span class="app-name" x-text="getAppDisplay(entry)"></span>
      <span class="trigger-badge" :data-trigger="entry.capture_trigger" x-text="entry.capture_trigger"></span>
    </div>
    <span class="frame-id" x-text="'No.' + entry.frame_id"></span>
  </div>

  <!-- 第二行：窗口标题（主视觉） -->
  <div class="header-row window-row">
    <span class="window-name" x-text="entry.window_title || entry.title || entry.last_known_window || ''"></span>
  </div>

  <!-- 第三行：时间信息 -->
  <div class="header-row meta-row">
    <span class="timestamp" x-text="formatTime(entry.timestamp)"></span>
    <span class="separator">·</span>
    <span class="relative-time" x-text="formatRelativeTime(entry.timestamp)"></span>
    <span class="separator">·</span>
    <span class="device-name" x-text="entry.device_name"></span>
  </div>
</div>
```

### 3.3 CSS 样式

```css
.card-header-v3 {
  display: flex;
  flex-direction: column;
  padding: 12px 16px;
  gap: 6px;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-card);
}

/* 第一行：上下文 */
.context-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 22px;
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
  background: rgba(255, 149, 0, 0.1);
  color: #D4840D;
}

.trigger-badge[data-trigger="app_switch"] {
  background: rgba(0, 122, 255, 0.1);
  color: #0A6ED6;
}

.trigger-badge[data-trigger="click"] {
  background: rgba(52, 199, 89, 0.1);
  color: #2A9D4A;
}

.trigger-badge[data-trigger="manual"] {
  background: rgba(175, 82, 222, 0.1);
  color: #8E4DB0;
}

.frame-id {
  font-size: 11px;
  color: var(--text-tertiary, #8E8E93);
  font-weight: 500;
  font-family: 'SF Mono', monospace;
  flex-shrink: 0;
}

/* 第二行：窗口标题（主视觉） */
.window-row {
  min-height: 20px;
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
  color: var(--text-tertiary, #8E8E93);
  white-space: nowrap;
}

.meta-row .timestamp {
  font-family: 'SF Mono', monospace;
  letter-spacing: -0.2px;
}

.meta-row .separator {
  font-size: 11px;
  color: var(--text-tertiary, #8E8E93);
  opacity: 0.6;
}
```

### 3.4 应用图标映射

```javascript
const appIcons = {
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

function getAppIcon(entry) {
  const appName = entry.app_name || entry.app || '';
  return appIcons[appName] || appIcons['default'];
}
```

---

## 4. Footer 流程优化（2x2 网格微标系统）

### 4.1 布局变化

**当前（横向流程）**:
```
[AX] 1349字 → [Desc] ○ → [Frame Status]
[OCR] 0字     [Embed] ●
```

**优化后（2x2 网格 + 底部状态）**:
```
┌──────────────┐ ┌──────────────┐
│ 📱 AX        │ │ ✨ Desc      │
│   1,349字    │ │   ○ pending  │
├──────────────┤ ├──────────────┤
│ 📝 OCR       │ │ 🧠 Embed     │
│   0字        │ │   ● done     │
└──────────────┘ └──────────────┘
       [● Completed]
```

### 4.2 HTML 结构

```html
<div class="card-footer-grid" role="region" aria-label="处理状态">
  <!-- 2x2 网格 -->
  <div class="status-grid">
    <!-- AX -->
    <div class="status-cell" :class="getTextSourceClass(entry, 'accessibility')">
      <div class="cell-header">
        <span class="cell-icon">📱</span>
        <span class="cell-label">AX</span>
      </div>
      <div class="cell-value" x-text="formatCharCount(getAccessibilityCharCount(entry))"></div>
    </div>

    <!-- Desc -->
    <div class="status-cell" :class="getDescriptionStatusClass(entry)">
      <div class="cell-header">
        <span class="cell-icon">✨</span>
        <span class="cell-label">Desc</span>
      </div>
      <div class="cell-value" x-html="getDescriptionStatusText(entry)"></div>
    </div>

    <!-- OCR -->
    <div class="status-cell" :class="getTextSourceClass(entry, 'ocr')">
      <div class="cell-header">
        <span class="cell-icon">📝</span>
        <span class="cell-label">OCR</span>
      </div>
      <div class="cell-value" x-text="formatCharCount(getOcrCharCount(entry))"></div>
    </div>

    <!-- Embed -->
    <div class="status-cell" :class="getEmbeddingStatusClass(entry)">
      <div class="cell-header">
        <span class="cell-icon">🧠</span>
        <span class="cell-label">Embed</span>
      </div>
      <div class="cell-value" x-html="getEmbeddingStatusText(entry)"></div>
    </div>
  </div>

  <!-- Frame 状态（底部居中） -->
  <div class="frame-status-bar" :class="getFrameStatusClass(entry)">
    <span class="status-dot"></span>
    <span class="status-label" x-text="getFrameStatusText(entry)"></span>
  </div>
</div>
```

### 4.3 CSS 样式

```css
.card-footer-grid {
  padding: 12px 14px;
  background: #FAFAFA;
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
  font-family: 'SF Mono', monospace;
}

/* 状态特定样式 */
.status-cell.active {
  background: rgba(52, 199, 89, 0.06);
  border-color: rgba(52, 199, 89, 0.12);
}

.status-cell.active .cell-label {
  color: #2A9D4A;
}

.status-cell.inactive {
  opacity: 0.6;
}

.status-cell.status-completed {
  background: rgba(52, 199, 89, 0.06);
  border-color: rgba(52, 199, 89, 0.12);
}

.status-cell.status-completed .cell-label {
  color: #2A9D4A;
}

.status-cell.status-processing {
  background: rgba(0, 122, 255, 0.06);
  border-color: rgba(0, 122, 255, 0.12);
}

.status-cell.status-processing .cell-label {
  color: #0A6ED6;
}

.status-cell.status-pending {
  background: rgba(142, 142, 147, 0.06);
  border-color: rgba(142, 142, 147, 0.12);
}

.status-cell.status-pending .cell-label {
  color: #8E8E93;
}

.status-cell.status-failed {
  background: rgba(255, 59, 48, 0.06);
  border-color: rgba(255, 59, 48, 0.12);
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
  background: rgba(52, 199, 89, 0.1);
  color: #2A9D4A;
}

.frame-status-bar.status-processing {
  background: rgba(0, 122, 255, 0.1);
  color: #0A6ED6;
}

.frame-status-bar.status-pending {
  background: rgba(255, 149, 0, 0.1);
  color: #D4840D;
}

.frame-status-bar.status-failed {
  background: rgba(255, 59, 48, 0.1);
  color: #D63126;
}
```

---

## 5. 柔和化颜色系统

### 5.1 颜色变量

```css
:root {
  /* 柔和化系统色 */
  --color-success: #5BC88C;      /* 原 #34C759，增加亮度降低饱和度 */
  --color-success-bg: rgba(91, 200, 140, 0.1);
  --color-success-border: rgba(91, 200, 140, 0.15);

  --color-primary: #4A9EFF;      /* 原 #007AFF */
  --color-primary-bg: rgba(74, 158, 255, 0.1);
  --color-primary-border: rgba(74, 158, 255, 0.15);

  --color-warning: #FFB84D;      /* 原 #FF9500 */
  --color-warning-bg: rgba(255, 184, 77, 0.1);
  --color-warning-border: rgba(255, 184, 77, 0.15);

  --color-error: #FF6B6B;        /* 原 #FF3B30 */
  --color-error-bg: rgba(255, 107, 107, 0.1);
  --color-error-border: rgba(255, 107, 107, 0.15);

  --color-neutral: #8E8E93;
  --color-neutral-bg: rgba(142, 142, 147, 0.1);
  --color-neutral-border: rgba(142, 142, 147, 0.15);

  /* 文本色 */
  --text-primary: #1D1D1F;
  --text-secondary: #636366;
  --text-tertiary: #8E8E93;

  /* 背景色 */
  --bg-body: #F5F5F7;
  --bg-card: #FFFFFF;
  --bg-footer: #FAFAFA;
}
```

### 5.2 卡片状态边条优化

```css
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

---

## 6. Stats Bar 优化

### 6.1 样式调整

```css
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
  font-family: 'SF Mono', monospace;
  min-width: 24px;
  text-align: center;
}

/* 状态颜色 */
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

---

## 7. 交互优化

### 7.1 悬停效果

```css
/* 卡片悬停 */
.memory-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.1);
}

/* 窗口标题悬停显示完整 */
.window-name {
  position: relative;
}

.memory-card:hover .window-name {
  white-space: normal;
  overflow: visible;
}

/* 图片悬停 */
.card-image {
  transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.card-image:hover {
  transform: scale(1.03);
}
```

### 7.2 加载动画（脉冲效果）

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

.status-processing .status-dot {
  animation: pulse-soft 1.5s ease-in-out infinite;
}
```

---

## 8. 辅助函数

### 8.1 JavaScript 工具函数

```javascript
// 格式化字符数（添加千位分隔符）
function formatCharCount(count) {
  const num = parseInt(count) || 0;
  if (num === 0) return '0';
  return num.toLocaleString('en-US') + '字';
}

// 获取状态文本
function getDescriptionStatusText(entry) {
  const status = entry.description_status || 'pending';
  const icons = {
    pending: '○',
    processing: '<span class="pulse-dot"></span>',
    completed: '●',
    failed: '✕'
  };
  return `${icons[status]} ${status}`;
}

function getEmbeddingStatusText(entry) {
  const status = entry.embedding_status || 'pending';
  const icons = {
    pending: '○',
    processing: '<span class="pulse-dot"></span>',
    completed: '●',
    failed: '✕'
  };
  return `${icons[status]} ${status}`;
}

// 应用图标映射
const appIconMap = {
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

function getAppIcon(entry) {
  const appName = entry.app_name || entry.app || '';
  return appIconMap[appName] || appIconMap['default'];
}
```

---

## 9. 响应式适配

### 9.1 移动端优化

```css
@media (max-width: 768px) {
  .memory-grid {
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 20px;
  }

  .card-header-v3 {
    padding: 10px 12px;
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
}

@media (max-width: 480px) {
  .memory-grid {
    grid-template-columns: 1fr;
  }

  .stats-bar {
    flex-wrap: wrap;
    gap: 12px;
    padding: 12px 16px;
  }
}
```

---

## 10. 实施检查清单

- [ ] 更新 `index.html` 中的 Header 结构（`card-header-v2` → `card-header-v3`）
- [ ] 更新 Footer 结构（`card-footer-flow` → `card-footer-grid`）
- [ ] 添加新的 CSS 样式到 `<style>` 块
- [ ] 更新 Alpine.js 数据函数（`getAppIcon`, `formatCharCount` 等）
- [ ] 更新 Stats Bar 样式
- [ ] 更新柔和化颜色变量
- [ ] 测试所有状态显示（completed/processing/pending/failed）
- [ ] 测试响应式布局（桌面/平板/手机）
- [ ] 验证悬停效果
- [ ] 检查无障碍访问性（ARIA 标签）

---

## 11. 设计原则参考

1. **层次清晰**：通过字体大小、颜色深浅、间距建立视觉层次
2. **柔和色彩**：降低饱和度，使用半透明背景营造轻盈感
3. **充足留白**：增加间距让界面呼吸
4. **渐进披露**：悬停时显示额外信息，保持默认状态简洁
5. **一致圆角**：统一使用 8px/12px 圆角，符合 Apple 设计语言
