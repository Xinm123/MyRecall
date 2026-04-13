# Web UI Embedding Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add embedding status display to Grid page cards and search mode selection to Search page

**Architecture:**
- Grid page: Redesign card footer as horizontal flow diagram showing Text Source → Parallel Processing (Desc/Embed) → Frame Status
- Search page: Add search mode pills (FTS/Vector/Hybrid) above content type filters, display mode-specific scores

**Tech Stack:** Python Flask (backend), Jinja2 templates, Alpine.js, vanilla CSS

---

## File Structure

| File | Responsibility |
|------|---------------|
| `openrecall/client/web/templates/index.html` | Grid page template - card footer redesign |
| `openrecall/client/web/templates/search.html` | Search page template - mode pills & score display |
| `openrecall/server/api_v1.py` | API endpoint - ensure embedding_status in frame data |

---

## Pre-Implementation: Check API Data

Before modifying UI, verify the API returns required fields.

### Task 0: Verify API Response Fields

**Files:**
- Check: `openrecall/server/api_v1.py`

- [ ] **Step 1: Check `/v1/frames` endpoint response**

Run server and test:
```bash
curl http://localhost:8083/v1/frames?limit=1 | jq '.[0] | {frame_id, text_source, accessibility_text_length, ocr_text_length, description_status, embedding_status, status}'
```

Expected fields:
- `text_source`: "accessibility" | "ocr" | "hybrid"
- `accessibility_text_length`: number
- `ocr_text_length`: number
- `description_status`: "completed" | "processing" | "pending" | "failed"
- `embedding_status`: "completed" | "processing" | "pending" | "failed" | "disabled"
- `status`: "completed" | "processing" | "pending" | "failed"

- [ ] **Step 2: If fields missing, check FramesStore**

Read: `openrecall/server/database/frames_store.py`

Look for `get_frames()` method - verify it returns embedding_status and text lengths.

- [ ] **Step 3: Check `/v1/search` endpoint response**

```bash
curl "http://localhost:8083/v1/search?q=test&mode=hybrid" | jq '.data[0].content | {frame_id, fts_rank, bm25_rank, cosine_score, cosine_rank, hybrid_score, hybrid_rank, embedding_status}'
```

Expected: All rank fields, scores, and embedding_status present.

---

## Part 1: Grid Page Card Footer Redesign

### Task 1: Create Card Footer CSS

**Files:**
- Modify: `openrecall/client/web/templates/index.html` (in `<style>` block, after line 966)

- [ ] **Step 1: Add footer layout styles**

Add after existing `.status-pending` CSS (around line 577):

```css
/* =============================================
   Card Footer Flow Layout
   ============================================= */

.card-footer-flow {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  min-height: 80px;
}

/* Text Source Section */
.flow-text-source {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 90px;
}

.flow-source-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.flow-source-row .icon {
  font-size: 14px;
  width: 18px;
  text-align: center;
}

.flow-source-row .label {
  font-weight: 500;
  min-width: 28px;
}

.flow-source-row .status-icon {
  font-size: 11px;
  width: 14px;
  text-align: center;
}

.flow-source-row .char-count {
  font-size: 11px;
  color: var(--text-secondary);
  font-family: 'SF Mono', monospace;
}

/* Status colors for text source */
.flow-source-row.active {
  color: var(--text-primary);
}

.flow-source-row.inactive {
  color: var(--text-secondary);
  opacity: 0.6;
}

.flow-source-row.status-completed {
  color: #34C759;
}

.flow-source-row.status-failed {
  color: #FF3B30;
}

/* Parallel Processing Section */
.flow-parallel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 14px;
  background: rgba(0, 0, 0, 0.02);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  min-width: 100px;
}

.flow-parallel-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.flow-parallel-row .icon {
  font-size: 13px;
  width: 18px;
  text-align: center;
}

.flow-parallel-row .label {
  font-weight: 500;
  min-width: 36px;
}

.flow-parallel-row .status-icon {
  font-size: 11px;
  margin-left: auto;
}

/* Status badge colors */
.status-badge-pending {
  color: #FF9500;
}

.status-badge-processing {
  color: #007AFF;
}

.status-badge-completed {
  color: #34C759;
}

.status-badge-failed {
  color: #FF3B30;
}

.status-badge-disabled {
  color: #8E8E93;
  opacity: 0.5;
}

.spinner-inline {
  display: inline-block;
  width: 10px;
  height: 10px;
  border: 1.5px solid rgba(0, 122, 255, 0.2);
  border-top-color: #007AFF;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

/* Frame Status Section */
.flow-frame-status {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-width: 70px;
  gap: 4px;
}

.flow-frame-status .status-icon-large {
  font-size: 20px;
  line-height: 1;
}

.flow-frame-status .status-text {
  font-size: 11px;
  font-weight: 500;
  text-transform: lowercase;
}

.flow-frame-status.status-completed {
  color: #34C759;
}

.flow-frame-status.status-processing {
  color: #007AFF;
}

.flow-frame-status.status-pending {
  color: #FF9500;
}

.flow-frame-status.status-failed {
  color: #FF3B30;
}

/* Connector lines */
.flow-connector {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--border-color);
  font-size: 14px;
  padding: 0 2px;
}

/* Responsive: Mobile stack */
@media (max-width: 480px) {
  .card-footer-flow {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }

  .flow-connector {
    transform: rotate(90deg);
    padding: 4px 0;
  }

  .flow-text-source,
  .flow-parallel,
  .flow-frame-status {
    width: 100%;
  }

  .flow-frame-status {
    flex-direction: row;
    justify-content: flex-start;
    gap: 8px;
  }
}
```

- [ ] **Step 2: Commit CSS changes**

```bash
git add openrecall/client/web/templates/index.html
git commit -m "feat(grid): add card footer flow layout styles"
```

### Task 2: Create Alpine.js Helper Methods

**Files:**
- Modify: `openrecall/client/web/templates/index.html` (in `<script>` section)

- [ ] **Step 1: Add helper methods to memoryGrid()**

Find the `memoryGrid()` function and add these methods (before `init()`):

```javascript
// Text source display helpers
getTextSourceClass(entry, sourceType) {
  const actualSource = (entry.text_source || 'ocr').toLowerCase();
  if (actualSource === 'hybrid') return 'active';
  if (actualSource === sourceType) return 'active';
  return 'inactive';
},

getTextSourceStatusIcon(entry, sourceType) {
  const actualSource = (entry.text_source || 'ocr').toLowerCase();
  const isActive = actualSource === sourceType || actualSource === 'hybrid';

  if (!isActive) return '—';

  // For active source, show based on processing status
  const status = (entry.status || 'pending').toLowerCase();
  if (status === 'completed') return '✓';
  if (status === 'processing') return '<span class="spinner-inline"></span>';
  if (status === 'failed') return '✗';
  return '○';
},

getTextSourceStatusClass(entry, sourceType) {
  const actualSource = (entry.text_source || 'ocr').toLowerCase();
  const isActive = actualSource === sourceType || actualSource === 'hybrid';

  if (!isActive) return 'inactive';

  const status = (entry.status || 'pending').toLowerCase();
  return `status-${status}`;
},

getAccessibilityCharCount(entry) {
  return entry.accessibility_text_length || entry.accessibility_text?.length || 0;
},

getOcrCharCount(entry) {
  return entry.ocr_text_length || entry.ocr_text?.length || 0;
},

// Parallel processing helpers
getDescriptionStatusIcon(entry) {
  const status = (entry.description_status || 'pending').toLowerCase();
  if (status === 'completed') return '✓';
  if (status === 'processing') return '<span class="spinner-inline"></span>';
  if (status === 'failed') return '✗';
  if (status === 'disabled') return '⊘';
  return '○';
},

getDescriptionStatusClass(entry) {
  const status = (entry.description_status || 'pending').toLowerCase();
  return `status-badge-${status}`;
},

getEmbeddingStatusIcon(entry) {
  const status = (entry.embedding_status || 'pending').toLowerCase();
  if (status === 'completed') return '✓';
  if (status === 'processing') return '<span class="spinner-inline"></span>';
  if (status === 'failed') return '✗';
  if (status === 'disabled') return '⊘';
  return '○';
},

getEmbeddingStatusClass(entry) {
  const status = (entry.embedding_status || 'pending').toLowerCase();
  return `status-badge-${status}`;
},

// Frame status helpers
getFrameStatusIcon(entry) {
  const status = (entry.status || 'pending').toLowerCase();
  if (status === 'completed') return '✓';
  if (status === 'processing') return '<span class="spinner-inline"></span>';
  if (status === 'failed') return '✗';
  return '○';
},

getFrameStatusClass(entry) {
  const status = (entry.status || 'pending').toLowerCase();
  return `status-${status}`;
},

getFrameStatusText(entry) {
  return (entry.status || 'pending').toLowerCase();
},
```

- [ ] **Step 2: Commit helper methods**

```bash
git add openrecall/client/web/templates/index.html
git commit -m "feat(grid): add card footer flow helper methods"
```

### Task 3: Replace Card Footer Template

**Files:**
- Modify: `openrecall/client/web/templates/index.html` (card-footer section, around line 1064)

- [ ] **Step 1: Replace existing card-footer**

Find and replace the entire `<div class="card-footer">` section (lines ~1064-1130):

```html
<div class="card-footer-flow" role="region" aria-label="处理流程状态">
  <!-- Text Source Section -->
  <div class="flow-text-source" role="group" aria-label="文本来源">
    <!-- AX Row -->
    <div class="flow-source-row"
         :class="[getTextSourceClass(entry, 'accessibility'), getTextSourceStatusClass(entry, 'accessibility')]"
         :aria-label="'无障碍文本: ' + getAccessibilityCharCount(entry) + '字符, 状态: ' + (getTextSourceClass(entry, 'accessibility') === 'active' ? '已使用' : '未使用')">
      <span class="icon" aria-hidden="true">📱</span>
      <span class="label">AX</span>
      <span class="status-icon" x-html="getTextSourceStatusIcon(entry, 'accessibility')" aria-hidden="true"></span>
      <span class="char-count" x-text="getAccessibilityCharCount(entry) + '字'"></span>
    </div>

    <!-- OCR Row -->
    <div class="flow-source-row"
         :class="[getTextSourceClass(entry, 'ocr'), getTextSourceStatusClass(entry, 'ocr')]"
         :aria-label="'OCR文本: ' + getOcrCharCount(entry) + '字符, 状态: ' + (getTextSourceClass(entry, 'ocr') === 'active' ? '已使用' : '未使用')">
      <span class="icon" aria-hidden="true">📝</span>
      <span class="label">OCR</span>
      <span class="status-icon" x-html="getTextSourceStatusIcon(entry, 'ocr')" aria-hidden="true"></span>
      <span class="char-count" x-text="getOcrCharCount(entry) + '字'"></span>
    </div>
  </div>

  <!-- Connector -->
  <div class="flow-connector" aria-hidden="true">→</div>

  <!-- Parallel Processing Section -->
  <div class="flow-parallel" role="group" aria-label="并行处理">
    <!-- Description Row -->
    <div class="flow-parallel-row" :aria-label="'描述生成: ' + (entry.description_status || 'pending')">
      <span class="icon" aria-hidden="true">✨</span>
      <span class="label">Desc</span>
      <span class="status-icon" :class="getDescriptionStatusClass(entry)" x-html="getDescriptionStatusIcon(entry)" aria-hidden="true"></span>
    </div>

    <!-- Embedding Row -->
    <div class="flow-parallel-row" :aria-label="'向量嵌入: ' + (entry.embedding_status || 'pending')">
      <span class="icon" aria-hidden="true">🧠</span>
      <span class="label">Embed</span>
      <span class="status-icon" :class="getEmbeddingStatusClass(entry)" x-html="getEmbeddingStatusIcon(entry)" aria-hidden="true"></span>
    </div>
  </div>

  <!-- Connector -->
  <div class="flow-connector" aria-hidden="true">→</div>

  <!-- Frame Status Section -->
  <div class="flow-frame-status" :class="getFrameStatusClass(entry)" role="status" :aria-label="'帧状态: ' + getFrameStatusText(entry)">
    <span class="status-icon-large" x-html="getFrameStatusIcon(entry)" aria-hidden="true"></span>
    <span class="status-text" x-text="getFrameStatusText(entry)"></span>
  </div>
</div>
```

- [ ] **Step 2: Remove old footer styles (optional cleanup)**

Old CSS classes to potentially remove (check if used elsewhere):
- `.card-footer` (original)
- `.status-processing`
- `.status-pending`
- `.ai-description`
- `.ai-icon`
- `.description-status-badge`
- `.status-badge`

Keep them if used by other pages, only remove if unused.

- [ ] **Step 3: Test Grid page**

```bash
# Start server
./run_server.sh --mode local --debug

# Open browser
curl http://localhost:8889/
```

Verify:
- Cards show new footer layout
- AX/OCR display correctly based on text_source
- Description and Embedding status show correctly
- Frame status shows correctly
- Connector lines visible
- Responsive layout works (resize window)

- [ ] **Step 4: Commit footer template**

```bash
git add openrecall/client/web/templates/index.html
git commit -m "feat(grid): implement card footer flow layout"
```

---

## Part 2: Search Page Enhancements

### Task 4: Add Search Mode Pills

**Files:**
- Modify: `openrecall/client/web/templates/search.html`

- [ ] **Step 1: Add search mode pills HTML**

After the search form (after `</form>` around line 503), before content-type-pills:

```html
<!-- Search Mode Pills -->
<div class="search-mode-pills" role="radiogroup" aria-label="搜索模式">
  <span class="pills-label">搜索模式:</span>
  <button type="button"
          class="pill"
          :class="{ active: searchMode === 'fts' }"
          @click="setSearchMode('fts')"
          @keydown="handleModeKeydown($event, 'fts')"
          role="radio"
          :aria-checked="searchMode === 'fts'"
          aria-label="全文搜索 - 基于关键词匹配"
          tabindex="0">全文搜索</button>
  <button type="button"
          class="pill"
          :class="{ active: searchMode === 'vector' }"
          @click="setSearchMode('vector')"
          @keydown="handleModeKeydown($event, 'vector')"
          role="radio"
          :aria-checked="searchMode === 'vector'"
          aria-label="语义搜索 - 基于语义理解"
          tabindex="0">语义搜索</button>
  <button type="button"
          class="pill"
          :class="{ active: searchMode === 'hybrid' }"
          @click="setSearchMode('hybrid')"
          @keydown="handleModeKeydown($event, 'hybrid')"
          role="radio"
          :aria-checked="searchMode === 'hybrid'"
          aria-label="混合搜索 - 结合全文和语义"
          tabindex="0">混合搜索</button>
</div>
```

- [ ] **Step 2: Add search mode pills CSS**

Add to `<style>` block (after `.content-type-pills` styles):

```css
/* Search Mode Pills */
.search-mode-pills {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.search-mode-pills .pills-label {
  font-size: 13px;
  color: var(--text-secondary);
  margin-right: 4px;
}

/* Reuse existing .pill styles from content-type-pills */
.search-mode-pills .pill {
  padding: 6px 14px;
  border: 1px solid var(--border-color);
  border-radius: 16px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  background: var(--bg-body);
  color: var(--text-secondary);
  transition: all 0.2s ease;
}

.search-mode-pills .pill:hover {
  border-color: var(--accent-color);
  color: var(--accent-color);
}

.search-mode-pills .pill.active {
  background: var(--accent-color);
  color: white;
  border-color: var(--accent-color);
}
```

- [ ] **Step 3: Add search mode state and methods**

In `<script>` section, add to search state (after `selectedContentType`):

```javascript
// Search mode state
let searchMode = 'fts';
```

Add methods after `initContentTypeFromUrl()`:

```javascript
// Initialize search mode from URL
function initSearchModeFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const urlMode = params.get('mode');
  if (urlMode && ['fts', 'vector', 'hybrid'].includes(urlMode)) {
    searchMode = urlMode;
  }
}

// Set search mode
function setSearchMode(mode) {
  if (mode !== searchMode) {
    searchMode = mode;
    performSearch(0);
  }
}

// Keyboard navigation for mode pills
function handleModeKeydown(event, currentMode) {
  const modes = ['fts', 'vector', 'hybrid'];
  const currentIndex = modes.indexOf(currentMode);

  switch(event.key) {
    case 'ArrowLeft':
      event.preventDefault();
      if (currentIndex > 0) {
        const prevMode = modes[currentIndex - 1];
        setSearchMode(prevMode);
        // Focus the previous button
        event.target.previousElementSibling?.focus();
      }
      break;
    case 'ArrowRight':
      event.preventDefault();
      if (currentIndex < modes.length - 1) {
        const nextMode = modes[currentIndex + 1];
        setSearchMode(nextMode);
        // Focus the next button
        event.target.nextElementSibling?.focus();
      }
      break;
    case 'Home':
      event.preventDefault();
      setSearchMode(modes[0]);
      event.target.parentElement?.firstElementChild?.nextElementSibling?.focus();
      break;
    case 'End':
      event.preventDefault();
      setSearchMode(modes[modes.length - 1]);
      event.target.parentElement?.lastElementChild?.focus();
      break;
  }
}
```

Update `buildQueryString()` to include mode:

```javascript
function buildQueryString(offset = 0) {
  const params = getFormFilterParams();

  // Add search mode (default 'fts' is omitted)
  if (searchMode !== 'fts') {
    params.set('mode', searchMode);
  }

  // Add content type filter (default 'all' is omitted)
  if (selectedContentType !== 'all') {
    params.set('content_type', selectedContentType);
  }

  params.set('limit', '20');
  params.set('offset', offset.toString());

  return params.toString();
}
```

Call `initSearchModeFromUrl()` in initialization:

```javascript
// Initialize
initContentTypeFromUrl();
initSearchModeFromUrl();
```

- [ ] **Step 4: Test search mode switching**

```bash
# Start server and test
./run_server.sh --mode local --debug
```

Open http://localhost:8889/search
- Click different mode pills
- Verify URL updates with `mode=` parameter
- Verify search results update

- [ ] **Step 5: Commit**

```bash
git add openrecall/client/web/templates/search.html
git commit -m "feat(search): add search mode pills (fts/vector/hybrid)"
```

### Task 5: Add Score Display

**Files:**
- Modify: `openrecall/client/web/templates/search.html`

- [ ] **Step 1: Update renderResults to show scores**

In the `renderResults` function, update the rank-info section (around line 808):

Replace:
```javascript
<div class="rank-info">
  <span class="rank-label">Rank</span>
  <span class="rank-value">${content.fts_rank !== null && content.fts_rank !== undefined ? Number(content.fts_rank).toFixed(4) : '—'}</span>
</div>
```

With:
```javascript
<div class="score-display">
  ${renderScoreInfo(content, idx, pagination)}
</div>
```

Add the `renderScoreInfo` function:

```javascript
// Render score information based on search mode
function renderScoreInfo(content, index, pagination) {
  const mode = searchMode;
  const globalRank = pagination.offset + index + 1;

  if (mode === 'fts') {
    const rank = content.fts_rank;
    const score = rank !== null && rank !== undefined ? Number(rank).toFixed(2) : '—';
    // Format: BM25: 12.34 | Rank: #3
    return `
      <span class="score-item">BM25: ${score}</span>
      <span class="score-separator">|</span>
      <span class="score-item">Rank: #${globalRank}</span>
    `;
  }

  if (mode === 'vector') {
    // Format: Cosine: 0.87 | Rank: #3
    const cosine = content.cosine_score;
    const score = cosine !== null && cosine !== undefined ? Number(cosine).toFixed(2) : '—';
    return `
      <span class="score-item">Cosine: ${score}</span>
      <span class="score-separator">|</span>
      <span class="score-item">Rank: #${globalRank}</span>
    `;
  }

  if (mode === 'hybrid') {
    // Format: BM25: 12.34 (#5) | Cosine: 0.87 (#2) | Hybrid: 0.91 (#3)
    const bm25 = content.fts_rank;
    const cosine = content.cosine_score;
    const hybrid = content.hybrid_score;
    const bm25Rank = content.bm25_rank || '—';
    const cosineRank = content.cosine_rank || '—';
    const hybridRank = globalRank;

    return `
      <span class="score-item" title="BM25 rank">BM25: ${bm25 !== null && bm25 !== undefined ? Number(bm25).toFixed(2) : '—'} (#${bm25Rank})</span>
      <span class="score-separator">|</span>
      <span class="score-item" title="Cosine rank">Cosine: ${cosine !== null && cosine !== undefined ? Number(cosine).toFixed(2) : '—'} (#${cosineRank})</span>
      <span class="score-separator">|</span>
      <span class="score-item" title="Hybrid rank">Hybrid: ${hybrid !== null && hybrid !== undefined ? Number(hybrid).toFixed(2) : '—'} (#${hybridRank})</span>
    `;
  }

  return '';
}
```

Update the call in `renderResults`:
```javascript
<div class="score-display">
  ${renderScoreInfo(content, idx, pagination)}
</div>
```

- [ ] **Step 2: Add score display CSS**

Add to `<style>` block:

```css
/* Score Display */
.score-display {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.score-item {
  font-size: 11px;
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
  color: var(--text-secondary);
  background: rgba(0, 0, 0, 0.03);
  padding: 2px 6px;
  border-radius: 4px;
  white-space: nowrap;
}

.score-separator {
  color: var(--border-color);
  font-size: 11px;
}

.score-display:hover .score-item {
  background: rgba(0, 0, 0, 0.06);
}
```

- [ ] **Step 3: Test score display**

Test each search mode:
- FTS: Should show BM25 score
- Vector: Should show Cosine similarity
- Hybrid: Should show all three scores with ranks

- [ ] **Step 4: Commit**

```bash
git add openrecall/client/web/templates/search.html
git commit -m "feat(search): add mode-specific score display"
```

### Task 6: Add Embedding Status Badge and Warning

**Files:**
- Modify: `openrecall/client/web/templates/search.html`

- [ ] **Step 1: Add embedding status to result cards**

In `renderResults`, update the type-badge line (around line 812):

Replace:
```javascript
<span class="type-badge type-${item.type.toLowerCase()}">${item.type === 'Accessibility' ? 'AX' : item.type}</span>
```

With:
```javascript
<span class="type-badge type-${item.type.toLowerCase()}">${item.type === 'Accessibility' ? 'AX' : item.type}</span>
${renderEmbeddingBadge(content)}
```

Add the function:

```javascript
// Render embedding status badge
function renderEmbeddingBadge(content) {
  const status = content.embedding_status;
  if (status === 'completed') {
    return '<span class="embedding-badge indexed" title="已生成向量索引">🔵</span>';
  }
  if (status === 'pending' || status === 'processing') {
    return '<span class="embedding-badge pending" title="等待向量索引">⚪</span>';
  }
  return '';
}
```

Add CSS:

```css
/* Embedding Status Badge */
.embedding-badge {
  font-size: 12px;
  margin-left: 6px;
  cursor: help;
  opacity: 0.8;
  transition: opacity 0.2s;
}

.embedding-badge:hover {
  opacity: 1;
}

.embedding-badge.indexed {
  filter: drop-shadow(0 0 2px rgba(0, 122, 255, 0.3));
}
```

- [ ] **Step 2: Add semantic search warning banner**

Add HTML after search-mode-pills (only show for vector/hybrid modes):

```html
<!-- Semantic Search Warning -->
<div class="semantic-warning" x-show="(searchMode === 'vector' || searchMode === 'hybrid') && pendingEmbeddingCount > 0">
  <span class="warning-icon">⚠️</span>
  <span x-text="pendingEmbeddingCount + ' 个结果尚未生成向量索引，语义搜索可能不完整'"></span>
</div>
```

Add to data:

```javascript
let pendingEmbeddingCount = 0;
```

Update `renderResults` to count pending:

```javascript
function renderResults(data, pagination) {
  currentResults = data;
  currentPagination = pagination;

  // Count pending embeddings for vector/hybrid modes
  if (searchMode === 'vector' || searchMode === 'hybrid') {
    pendingEmbeddingCount = data.filter(item =>
      item.content.embedding_status !== 'completed'
    ).length;
  }

  // ... rest of render logic
}
```

Add CSS:

```css
/* Semantic Search Warning */
.semantic-warning {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: rgba(0, 122, 255, 0.08);
  border: 1px solid rgba(0, 122, 255, 0.2);
  border-radius: 8px;
  margin-bottom: 16px;
  font-size: 13px;
  color: var(--accent-color);
}

.warning-icon {
  font-size: 14px;
}
```

- [ ] **Step 3: Test**

- Verify embedding badges appear on result cards
- Verify warning shows when pending > 0 in vector/hybrid mode
- Verify warning hides in FTS mode

- [ ] **Step 4: Commit**

```bash
git add openrecall/client/web/templates/search.html
git commit -m "feat(search): add embedding status badge and semantic warning"
```

---

## Part 3: API Updates

### Task 7: Add cosine_score to Search API Response

**Files:**
- Modify: `openrecall/server/search/hybrid_engine.py` or `openrecall/server/api_v1.py`

- [ ] **Step 1: Find where search results are built**

In `openrecall/server/api_v1.py`, find the `search()` function around line 1084 where `hybrid_score` is added to the response.

- [ ] **Step 2: Add cosine_score field**

When mode is "vector" or "hybrid", include the cosine similarity score:

```python
# In search() function, around line 1084
# Add hybrid_score for hybrid/vector mode results
if "hybrid_score" in r:
    item["content"]["hybrid_score"] = r["hybrid_score"]

# Add cosine_score for vector/hybrid modes
if mode in ("vector", "hybrid"):
    # cosine_score is the raw vector similarity before fusion
    if "cosine_score" in r:
        item["content"]["cosine_score"] = r["cosine_score"]
    elif "hybrid_score" in r and mode == "vector":
        # For pure vector search, hybrid_score is the cosine score
        item["content"]["cosine_score"] = r["hybrid_score"]
```

If `cosine_score` is not available in results `r`, check `HybridSearchEngine` to add it:

```python
# In openrecall/server/search/hybrid_engine.py
# In search() method, when building results
result = {
    "frame_id": frame_id,
    "cosine_score": float(similarities[idx]),  # Add this
    "bm25_score": bm25_scores.get(frame_id, 0),
    "hybrid_score": final_score,
}
```

- [ ] **Step 3: Verify API response**

```bash
curl "http://localhost:8083/v1/search?q=test&mode=vector" | jq '.data[0].content | {frame_id, cosine_score, hybrid_score}'

curl "http://localhost:8083/v1/search?q=test&mode=hybrid" | jq '.data[0].content | {frame_id, fts_rank, bm25_rank, cosine_score, cosine_rank, hybrid_score}'
```

Expected response:
```json
{
  "frame_id": "uuid",
  "cosine_score": 0.87,
  "hybrid_score": 0.91
}
```

- [ ] **Step 4: Commit**

```bash
git add openrecall/server/api_v1.py openrecall/server/search/hybrid_engine.py
git commit -m "feat(api): add cosine_score to search response for vector/hybrid modes"
```

---

### Task 8: Ensure Grid API Returns Required Fields

**Files:**
- Modify: `openrecall/server/database/frames_store.py`

- [ ] **Step 1: Check FramesStore.get_frames()**

Find the SQL query and ensure it selects:
- `text_source`
- `accessibility_text_length` (or calculate from `accessibility_text`)
- `ocr_text_length` (or calculate from `ocr_text`)
- `description_status`
- `embedding_status`

- [ ] **Step 2: Add missing fields if needed**

Example modification:

```python
# In get_frames() method
query = """
SELECT
    f.frame_id,
    f.text_source,
    LENGTH(f.accessibility_text) as accessibility_text_length,
    LENGTH(f.ocr_text) as ocr_text_length,
    f.description_status,
    f.embedding_status,
    f.status,
    ...
FROM frames f
...
"""
```

- [ ] **Step 3: Test API response**

```bash
curl http://localhost:8083/v1/frames?limit=1 | jq '.[0] | {frame_id, text_source, accessibility_text_length, ocr_text_length, description_status, embedding_status, status}'
```

- [ ] **Step 4: Commit**

```bash
git add openrecall/server/database/frames_store.py
git commit -m "fix(api): add embedding_status and text lengths to frame response"
```

---

## Final Verification

### Task 9: End-to-End Testing

- [ ] **Step 1: Full test of Grid page**

```bash
./run_server.sh --mode local --debug &
./run_client.sh --mode local --debug &
```

Open http://localhost:8889/ and verify:
- [ ] Cards show new footer layout
- [ ] AX/OCR rows show correct colors based on text_source
- [ ] Description and Embedding status display correctly
- [ ] Frame status shows correctly
- [ ] Responsive layout works

- [ ] **Step 2: Full test of Search page**

Open http://localhost:8889/search and verify:
- [ ] Search mode pills visible and clickable
- [ ] Mode switching updates URL and results
- [ ] Score display shows correct values for each mode
- [ ] Embedding badges appear on cards
- [ ] Semantic warning shows when appropriate

- [ ] **Step 3: Final commit**

```bash
git log --oneline -5
```

Ensure all commits are clean and descriptive.

---

## Summary

| Task | Description | Files Modified |
|------|-------------|----------------|
| 0 | Verify API fields | - |
| 1 | Card footer CSS | index.html |
| 2 | Alpine.js helpers | index.html |
| 3 | Card footer template | index.html |
| 4 | Search mode pills | search.html |
| 5 | Score display | search.html |
| 6 | Embedding badge & warning | search.html |
| 7 | API: Add cosine_score | api_v1.py, hybrid_engine.py |
| 8 | API: Grid fields | frames_store.py |
| 9 | E2E testing | - |

---

## Changes Made to Fix Review Issues

### 1. API: Added cosine_score field (Task 7)
- New task to add `cosine_score` to search API response for vector/hybrid modes
- Updated Score Display (Task 5) to use `cosine_score` field
- Score format now matches Spec exactly:
  - FTS: `BM25: 12.34 | Rank: #3`
  - Vector: `Cosine: 0.87 | Rank: #3`
  - Hybrid: `BM25: 12.34 (#5) | Cosine: 0.87 (#2) | Hybrid: 0.91 (#3)`

### 2. Accessibility: Added ARIA labels and keyboard navigation
- Search mode pills: Added `role="radiogroup"`, `role="radio"`, `aria-checked`, `aria-label`
- Added keyboard navigation: ArrowLeft/ArrowRight/Home/End keys
- Grid card footer: Added `role="region"`, `role="group"`, `role="status"`, `aria-label` attributes

### 3. Connector Design Clarification
- Simple `→` character used for connectors (sufficient for the design)
- Hidden from screen readers with `aria-hidden="true"`

---

## Self-Review Checklist

- [ ] Spec coverage: All requirements from design doc are implemented
- [ ] No placeholders: All code is complete
- [ ] Type consistency: Method names match throughout
- [ ] Test commands provided for each task
- [ ] Commit commands included
- [ ] API fields: cosine_score added for vector search
- [ ] Accessibility: ARIA labels and keyboard navigation added
- [ ] Score format: Matches spec (BM25 | Cosine | Hybrid with ranks)
