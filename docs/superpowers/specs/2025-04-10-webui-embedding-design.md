# Web UI Embedding Integration Design

**Date**: 2025-04-10
**Status**: Approved
**Scope**: Grid and Search page UI modifications for embedding support

## Overview

This document describes the Web UI modifications needed to support the new frame embedding functionality. The embedding system enables semantic search capabilities, and the UI needs to:

1. Allow users to select search modes (FTS / Vector / Hybrid)
2. Display embedding processing status on frames
3. Show technical scores for different search modes

## Current State

### Grid Page (`/`)
- Displays frames in a responsive grid layout
- Each card shows: app name, window title, timestamp, screenshot
- Footer shows: text source (AX/OCR), description status
- Uses `data-frame-status` for border coloring (pending/processing/completed/failed)

### Search Page (`/search`)
- Search form with filters: query, time range, app, window, focused
- Content type pills: All | OCR | AX
- Results show: frame info, FTS rank, type badge
- Modal for full image view with navigation

### API Support
- `GET /v1/search?mode=fts|vector|hybrid` - Three search modes
- `GET /v1/frames/<id>/similar` - Find similar frames (not used in UI)
- `GET /v1/embedding/tasks/status` - Queue statistics

## Design Decisions

### 1. Grid Page: Card Footer Redesign

#### Layout: Horizontal Flow Diagram

The footer is redesigned as a horizontal process flow showing:

```
┌─────────────────────────────────────────────────────────────┐
│  TEXT SOURCE  →  PARALLEL PROCESSING  →  FRAME STATUS       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌─────────────────┐    ┌─────────────┐ │
│  │ 📱 AX       │    │   ┌─────────┐   │    │             │ │
│  │ [✓] 2,341字 │───┐│   │ ✨ Desc │   │    │   [✓]       │ │
│  │             │   ││   │ [✓]     │   │    │  completed  │ │
│  ├─────────────┤   └┤   ├─────────┤   ├───▶│             │ │
│  │ 📝 OCR      │    │   │ 🧠 Embed│   │    │             │ │
│  │ [—] 0字     │────┤   │ [✓]     │   │    │             │ │
│  │  (gray)     │    │   └─────────┘   │    │             │ │
│  └─────────────┘    └─────────────────┘    └─────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### Text Source Section (Left)

**Layout**: Two rows - AX on top, OCR below

**AX Row**:
- Icon: 📱
- Label: "AX"
- Status icon: [✓] / [⋯] / [✗] / [—]
- Char count: e.g., "2,341字"

**OCR Row**:
- Icon: 📝
- Label: "OCR"
- Status icon: [✓] / [⋯] / [✗] / [—]
- Char count: e.g., "1,234字"

**Color Rules**:
| text_source | AX Color | OCR Color |
|-------------|----------|-----------|
| accessibility | Green ✓ | Gray — |
| ocr | Gray ✗ | Green ✓ |
| hybrid | Green ✓ | Green ✓ |

**Status Icons**:
- ✓ (completed) - Green
- ⋯ (processing) - Blue spinning
- ○ (pending) - Orange
- ✗ (failed) - Red
- — (not used/gray) - Gray

#### Parallel Processing Section (Middle)

**Layout**: Bordered container with two stacked rows

**Description Row**:
- Icon: ✨
- Label: "Desc"
- Status: [✓] / [⋯] / [○] / [✗] / [⊘]
- States: completed / processing / pending / failed / disabled

**Embedding Row**:
- Icon: 🧠
- Label: "Embed"
- Status: [✓] / [⋯] / [○] / [✗] / [⊘]
- States: same as above

**Visual Design**:
- Light background (rgba(0,0,0,0.02))
- 1px border (var(--border-color))
- 8px border-radius
- 8px padding

#### Frame Status Section (Right)

**Layout**: Centered status display

**Content**:
- Large status icon (✓ / ⋯ / ○ / ✗)
- Status text: "completed" / "processing" / "pending" / "failed"

**Colors**:
- completed: Green (#34C759)
- processing: Blue (#007AFF)
- pending: Orange (#FF9500)
- failed: Red (#FF3B30)

#### Connector Lines

**Style**:
- 2px solid lines
- Color: var(--border-color)
- Dashed for optional/indirect connections

**Connections**:
1. Active text source → Parallel section (solid)
2. Parallel section → Frame status (solid)

### 2. Search Page: Search Mode Selection

#### Search Mode Pills

**Position**: Below search form, above content type pills

**Options**: [全文搜索] [语义搜索] [混合搜索]

**Styling**:
- Same as existing `content-type-pills`
- Active state: filled background (var(--accent-color))
- Inactive state: outlined

**Default**: 全文搜索 (FTS)

#### Embedding Status in Results

**Card Footer Badge**:
- Position: Next to type badge (OCR/AX)
- Icon: 🔵 (indexed) / ⚪ (pending)
- Hover tooltip: "已生成向量索引" / "等待向量索引"

**Semantic Search Warning**:
- Position: Above results grid
- Style: Info banner (blue background)
- Content: "XX 个结果尚未生成向量索引，语义搜索可能不完整"
- Show only when: mode is "vector" or "hybrid" AND pending count > 0

#### Score Display

**Full-Text Search**:
```
BM25: 12.34 | Rank: #3
```

**Vector Search**:
```
Cosine: 0.87 | Rank: #3
```

**Hybrid Search**:
```
BM25: 12.34 (#5) | Cosine: 0.87 (#2) | Hybrid: 0.91 (#3)
```

**Layout**: Small text below card footer, monospace font

### 3. Control Center: No Changes

Embedding status NOT added to Control Center per decision to keep it focused on recording controls only.

## API Requirements

### Grid Page Data Requirements

Current `/v1/frames` endpoint needs to include:
```json
{
  "frame_id": "uuid",
  "text_source": "accessibility|ocr|hybrid",
  "accessibility_text_length": 2341,
  "ocr_text_length": 0,
  "description_status": "completed|processing|pending|failed",
  "embedding_status": "completed|processing|pending|failed|disabled",
  "status": "completed|processing|pending|failed"
}
```

### Search Page Data Requirements

Updated `/v1/search` response needs:
```json
{
  "content": {
    "frame_id": "uuid",
    "fts_rank": 12.34,
    "bm25_rank": 5,
    "cosine_score": 0.87,
    "cosine_rank": 2,
    "hybrid_score": 0.91,
    "hybrid_rank": 3,
    "embedding_status": "completed|pending"
  }
}
```

**Fields:**
- `fts_rank`: BM25 score for FTS mode
- `bm25_rank`: Rank in BM25-only results (for hybrid mode)
- `cosine_score`: Raw cosine similarity for vector/hybrid modes
- `cosine_rank`: Rank in cosine-only results (for hybrid mode)
- `hybrid_score`: Fused score for hybrid mode
- `hybrid_rank`: Final rank in hybrid results
- `embedding_status`: Whether embedding is indexed

## Responsive Behavior

### Grid Card Footer

**Desktop (>768px)**:
- Full horizontal layout as designed
- All elements visible

**Tablet (480-768px)**:
- Maintain horizontal layout
- Reduce padding
- Smaller fonts (0.75rem)

**Mobile (<480px)**:
- Stack to vertical layout
- Text Source | Parallel | Frame in rows
- Hide connector lines

### Search Mode Pills

- Always horizontal
- Scrollable on very small screens
- Equal width distribution

## Accessibility

- Status icons have aria-labels
- Color is not the only indicator (icons + text)
- Hover states for interactive elements
- Keyboard navigation for pills

## Implementation Notes

1. **CSS Grid/Flexbox** for footer layout
2. **CSS Variables** for colors to support theming
3. **Alpine.js** for state management (consistent with existing code)
4. **CSS Transitions** for status changes
5. **Intersection Observer** for lazy loading status updates

## Testing Checklist

- [ ] All text_source combinations display correctly
- [ ] Status colors match specification
- [ ] Responsive layouts work at all breakpoints
- [ ] Search mode switching updates results
- [ ] Embedding status badges appear correctly
- [ ] Score displays match search mode
- [ ] Hover tooltips work
- [ ] Keyboard navigation works

## Future Considerations

- Real-time status updates via WebSocket
- Batch operations on selected frames
- Embedding status filtering
- Performance metrics display
