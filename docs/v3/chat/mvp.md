# MyRecall v3 Chat MVP

## Goal

This document defines the reduced MVP scope for MyRecall v3 chat.

The goal of this MVP is to build a usable, Host-side, grounded chat experience that can answer questions about recent screen activity using local tools and frame-backed evidence.

This MVP adopts a screenpipe-style architecture, but it does not aim for full screenpipe parity.

Older documents in `docs/v3/chat/` remain as reference only. This document is the implementation scope for the reduced MVP.

## Non-goals

This MVP does not include:

- independent tree walker
- input search
- public `/v1/elements`
- multi-skill chat architecture
- full browser URL coverage across browsers
- full screenpipe parity
- audio support beyond response-shape compatibility

This MVP also does not attempt to reproduce screenpipe's independent accessibility timeline semantics.

## Architecture

### Runtime

Chat runs in a Host-side agent runtime.

The runtime is responsible for:

- session management
- streaming output
- abort
- tool execution

### Skill

The MVP uses a single main skill:

- `myrecall-search`

This skill defines tool usage policy and keeps the agent constrained to the MVP tool surface.

### Tool Surface

The MVP exposes the following tools to chat:

- `GET /v1/activity-summary`
- `GET /v1/search`
- `GET /v1/frames/{id}/context`
- `GET /v1/frames/{id}`

### High-level Flow

```text
User
  -> Host Chat Runtime
    -> Agent
      -> myrecall-search
        -> /v1/activity-summary
        -> /v1/search
        -> /v1/frames/{id}/context
        -> /v1/frames/{id}
```

## Capture And Data Flow

The MVP keeps the paired capture direction.

- accessibility is captured at capture time
- accessibility acquisition happens on the client capture side, not on the server
- OCR remains on the existing MyRecall async server worker path
- accessibility is preferred when available
- OCR is used as fallback when accessibility is unavailable

### Paired Capture Rules

- if accessibility is available at capture time:
  - write `frames`
  - write `accessibility`
  - write `elements`
  - set `frames.text`
  - set `frames.text_source='accessibility'`
- if accessibility is unavailable at capture time:
  - write base `frames`
  - leave `frames.text=NULL`
  - leave `frames.text_source=NULL`
  - let the OCR worker complete the frame later

### Accessibility Acquisition

The MVP follows the screenpipe paired-capture model for accessibility acquisition, with narrower monitor binding rules.

#### Capture Location

- accessibility is acquired on the client at capture time
- the client uploads accessibility payload as part of capture metadata
- the server persists accessibility results but does not attempt to acquire accessibility data itself

Recommended client-side capture order:

- capture screenshot
- snapshot active context
- evaluate accessibility eligibility and adoption
- build base capture metadata
- merge accessibility payload when adopted
- enqueue the capture envelope

The client should keep activity-context lookup and accessibility walking as separate concerns:

- existing active-context logic continues to provide frontmost app metadata, active window title, and focused-monitor routing inputs
- the accessibility walker is responsible only for producing a focused-window accessibility snapshot

#### Focus Boundary

- the acquisition unit is the current focused window
- the MVP does not capture all windows of the frontmost app
- the MVP does not capture desktop-wide accessibility state

#### Multi-monitor Rule

- in multi-monitor mode, only the frame captured on the current focused monitor is AX-eligible
- non-focused monitor frames do not attempt accessibility acquisition
- non-focused monitor frames remain OCR-domain frames
- if a focused window spans multiple monitors, AX eligibility follows the existing focused-monitor routing decision used by capture routing

#### OCR-preferred App Exceptions

The MVP inherits screenpipe-style OCR-preferred exceptions for terminal-class apps.

These include app names matching:

- `wezterm`
- `iterm`
- `terminal`
- `alacritty`
- `kitty`
- `hyper`
- `warp`
- `ghostty`

For these apps:

- accessibility is not adopted into the canonical chat data plane
- no paired accessibility persistence is written
- no `frames.accessibility_tree_json` is written
- no `accessibility` row is written
- no `elements` rows are written
- the frame remains on the OCR-pending path until OCR completion

#### Accessibility Adoption Rule

For AX-eligible non-terminal focused-window captures:

- if the accessibility snapshot has non-empty `text_content`, it may be adopted as canonical accessibility text
- if the accessibility snapshot has empty `text_content`, the frame falls back to the OCR path
- truncation alone does not invalidate an accessibility snapshot

#### Upload Contract

When a frame is accessibility-canonical, the client must upload:

- top-level canonical frame fields:
  - `text`
  - `text_source='accessibility'`
  - `browser_url` when available (frame-level metadata, not accessibility-specific)
  - `content_hash`
  - `simhash`
- a nested `accessibility` payload containing:
  - `text_content`
  - `tree_json`
  - `node_count`
  - `truncated`
  - `truncation_reason`
  - `max_depth_reached`
  - `duration_ms`

> **Note on `browser_url`:** This is frame-level best-effort metadata, not accessibility-specific.
> It should be extracted during capture and saved to `frames.browser_url` regardless of the frame's
> final `text_source`. See the "Browser URL" section below for details.

For accessibility-canonical frames:

- `text` must equal `accessibility.text_content`
- `accessibility.tree_json` is required
- `accessibility.tree_json` must parse successfully on the server before the frame can take the accessibility-complete path

Example accessibility-canonical metadata payload:

```json
{
  "timestamp": "2026-03-19T10:21:35Z",
  "capture_trigger": "click",
  "device_name": "monitor_2",
  "event_ts": "2026-03-19T10:21:34Z",
  "app_name": "Safari",
  "window_name": "MyRecall v3 Chat MVP",
  "browser_url": "https://example.com",
  "focused": true,
  "text": "MyRecall v3 Chat MVP\nGoal\nArchitecture",
  "text_source": "accessibility",
  "content_hash": 123456789,
  "simhash": 987654321,
  "accessibility": {
    "text_content": "MyRecall v3 Chat MVP\nGoal\nArchitecture",
    "tree_json": "[{\"role\":\"AXHeading\",\"text\":\"MyRecall v3 Chat MVP\",\"depth\":1,\"bounds\":{\"left\":0.1,\"top\":0.08,\"width\":0.6,\"height\":0.04}}]",
    "node_count": 42,
    "truncated": false,
    "truncation_reason": null,
    "max_depth_reached": 8,
    "duration_ms": 47
  }
}
```

If accessibility data is unavailable or not adopted, the client should omit the accessibility-canonical fields and let the frame follow the OCR-pending path.

#### Tree Walker Bounds

The MVP uses bounded accessibility walks.

- `max_depth = 30`
- `max_nodes = 5000`
- `max_text_length = 50000`
- `walk_timeout = 250ms`

The first MVP should also use a best-effort per-element timeout target:

- `element_timeout = 200ms`

The walker is bounded to keep Python-based acquisition viable.

The preferred implementation order is:

- first try to use the platform AX messaging timeout for per-element reads
- treat per-element timeout and attribute read failures as local failures
- keep `walk_timeout` as the whole-walk budget
- if in-process AX calls still prove capable of hard-stalling capture, evaluate a subprocess walker boundary later instead of relying on complex thread-level interruption

### OCR Worker Rules

- OCR stays on the existing async server worker path
- OCR-only frames are completed later by the worker
- canonical OCR completion only applies to frames that are still pending and have no canonical `text_source`
- on canonical OCR success, the worker writes:
  - `ocr_text`
  - `frames.text`
  - `frames.text_source='ocr'`
- OCR may still be persisted for accessibility-canonical frames as auxiliary OCR data
- auxiliary OCR persistence must not overwrite `frames.text`
- auxiliary OCR persistence must not overwrite `frames.text_source`
- search visibility is always controlled by canonical `frames.text_source`

### Data Flow

```text
paired_capture
  -> frames
     - text
     - text_source
     - accessibility_tree_json
  -> accessibility
  -> elements

ocr_worker
  -> ocr_text
  -> frames.text
  -> frames.text_source='ocr'
```

### Accessibility Snapshot Contract

The client-side accessibility collector should return a focused-window snapshot shaped like a screenpipe-style `TreeSnapshot`.

#### macOS Platform API Boundary

The first MVP macOS implementation should use a narrow platform boundary:

- existing client active-context logic remains the source of:
  - frontmost app metadata for policy and logging
  - active window title for policy and logging
  - focused-monitor routing
- the macOS accessibility walker is responsible for:
  - resolving the frontmost app AX application element
  - resolving the focused window AX root
  - extracting a bounded focused-window snapshot

The walker should not own:

- monitor eligibility decisions
- terminal OCR-preference decisions
- metadata merge logic
- persistence decisions

#### `walk_focused_window(config)` Internal Order

The first MVP walker should follow this order:

1. initialize walk state
2. resolve the frontmost app and PID
3. resolve the focused window AX root
4. read window-level context such as `window_name`
5. best-effort browser URL extraction
6. perform bounded depth-first `walk_element(...)`
7. finalize `text_content`, hashes, timing, and truncation state
8. return `TreeSnapshot` or `None`

The walker should return `None` when no focused window can be found or the walk itself fails.
An empty-text snapshot is still a valid `TreeSnapshot` and will be mapped to `empty_text` by the service.
This design preserves debug visibility when a window exists but contains no text-bearing nodes.

#### `collect_for_capture(...)` Decision Mapping

The accessibility service should map policy and walker outcomes into a stable `AccessibilityDecision`.

Recommended mapping:

- `target_device_name != focused_device_name`
  - `eligible=false`
  - `adopted=false`
  - `reason='non_focused_monitor'`
  - `snapshot=None`
- `app_prefers_ocr(app_name)`
  - `eligible=false`
  - `adopted=false`
  - `reason='app_prefers_ocr'`
  - `snapshot=None`
- walker returns `None`
  - `eligible=true`
  - `adopted=false`
  - `reason='no_focused_window'`
  - `snapshot=None`
  > Note: The walker returns `None` for both "no focused window found" and "walk failed" cases.
  > The specific reason is logged internally by the walker for debugging.
- walker returns a snapshot with empty `text_content`
  - `eligible=true`
  - `adopted=false`
  - `reason='empty_text'`
  - `snapshot=TreeSnapshot`
- walker returns a snapshot with non-empty `text_content`
  - `eligible=true`
  - `adopted=true`
  - `reason='adopted_accessibility'`
  - `snapshot=TreeSnapshot`

Minimum fields:

- `app_name`
- `window_name`
- `browser_url`
- `text_content`
- `nodes`
- `node_count`
- `truncated`
- `truncation_reason`
- `max_depth_reached`
- `content_hash`
- `simhash`
- `captured_at`
- `duration_ms`

This snapshot is the single source for all paired accessibility persistence.

### Ingest Split

`/v1/ingest` supports two frame-completion paths.

#### Accessibility-complete path

If the uploaded metadata contains a valid accessibility-canonical payload, ingest should:

- finalize the claimed frame image
- synchronously complete the frame in one DB transaction
- write:
  - `frames.text`
  - `frames.text_source='accessibility'`
  - `frames.accessibility_tree_json`
  - `frames.browser_url`
  - `frames.content_hash`
  - `frames.simhash`
  - `accessibility`
  - `elements`
  - `status='completed'`
- return a success payload whose `status` reflects completed ingestion

#### OCR-pending path

If no valid accessibility-canonical payload is present, ingest should:

- finalize the claimed frame image
- keep the frame on the pending OCR path
- leave canonical text fields unset until worker completion
- return a success payload whose `status` reflects queued OCR work

#### Validation And Degradation

If uploaded accessibility payload is malformed or inconsistent, ingest should not reject the frame solely for that reason.

Instead, ingest should:

- log the accessibility payload failure
- degrade the frame to the OCR-pending path
- preserve the frame image and base metadata

## Data Model

### Frames

`frames` is the frame context truth source.

It stores:

- `id`
- `capture_id`
- `timestamp`
- `app_name`
- `window_name`
- `browser_url`
- `focused`
- `device_name`
- `snapshot_path`
- `capture_trigger`
- `text`
- `text_source`
- `accessibility_tree_json`
- `content_hash`
- `simhash`
- `image_size_bytes`
- `ingested_at`
- `status`
- `error_message`
- `retry_count`
- `processed_at`

Notes:

- `frames.text` is the canonical text for the frame
- `frames.text_source` is one of `accessibility | ocr | NULL`
- `frames.accessibility_tree_json` stores the serialized flat accessibility node list from the focused-window snapshot and is used by frame context
- `frames_fts` should be metadata-only

### Accessibility

`accessibility` is the frame-backed accessibility search plane.

It stores:

- `id`
- `frame_id`
- `timestamp`
- `app_name`
- `window_name`
- `browser_url`
- `text_content`
- `text_length`

Notes:

- `frame_id` is required
- this table stores aggregated accessibility text only
- this table does not store structured node data
- this table is the truth source for `content_type=accessibility`

### Elements

`elements` is an internal structured projection of the paired accessibility tree.

Its shape should stay close to screenpipe:

- `id`
- `frame_id`
- `source`
- `role`
- `text`
- `parent_id`
- `depth`
- `left_bound`
- `top_bound`
- `width_bound`
- `height_bound`
- `sort_order`

MVP constraints:

- only `source='accessibility'` is written in MVP
- `/v1/elements` is not exposed in MVP
- `elements` exists mainly to support `activity-summary.recent_texts`
- `elements.parent_id` and `elements.sort_order` are reconstructed on the server from node `depth` ordering

### OCR Text

`ocr_text` remains the OCR text plane.

- OCR text is still persisted even if a frame's canonical source is accessibility
- OCR search visibility is still controlled by `frames.text_source`

### Accessibility Nodes

The accessibility snapshot stores a flat list of text-bearing nodes, not a full raw tree.

Node shape aligns with screenpipe's capture-layer shape:

- `role`
- `text`
- `depth`
- `bounds` (optional)

The snapshot does not need client-side `node_id`, `parent_id`, or nested `children` fields.

The flat node list must preserve depth-first traversal order because server-side `elements` reconstruction depends on ordered `depth` transitions.

#### Node Extraction Strategy

- the walker traverses the focused window tree within configured bounds
- decorative and irrelevant roles are skipped
- text-bearing roles are retained
- the retained nodes form a light filtered node list
- unknown roles recurse by default but do not extract text by default
- child enumeration/read failure should be treated as a local branch failure, not a whole-walk failure

This is a full walk with filtered text-node persistence, not a full raw-tree serialization.

#### Text-bearing Roles

At acquisition time, the walker should use a wider text-bearing role set, similar to screenpipe.

The first MVP role table should be:

##### `skip_roles`

- `AXScrollBar`
- `AXImage`
- `AXSplitter`
- `AXGrowArea`
- `AXMenuBar`
- `AXMenu`
- `AXToolbar`
- `AXSecureTextField`
- `AXRuler`
- `AXRulerMarker`
- `AXBusyIndicator`
- `AXProgressIndicator`

Nodes in `skip_roles` are skipped entirely.

##### `text_bearing_roles`

- `AXStaticText`
- `AXTextField`
- `AXTextArea`
- `AXButton`
- `AXMenuItem`
- `AXCell`
- `AXHeading`
- `AXLink`
- `AXMenuButton`
- `AXPopUpButton`
- `AXComboBox`
- `AXCheckBox`
- `AXRadioButton`
- `AXDisclosureTriangle`
- `AXTab`

Nodes in `text_bearing_roles` should attempt text extraction and should be added to the flat node list when non-empty text is found.

For `AXTextField`, `AXTextArea`, `AXComboBox`, and `AXStaticText`, a successful text extraction may short-circuit recursion into children.

##### `light_container_roles`

- `AXGroup`
- `AXWebArea`

Nodes in `light_container_roles` may contribute direct value text to `text_content`, but they do not need to be emitted as persisted text-bearing nodes and should continue recursing into children.

This acquisition-time role set is intentionally wider than the summary-time role set used by `recent_texts`.

#### Text Extraction Priority

The MVP should align with screenpipe-style extraction priority:

- for text-entry-like roles (`AXTextField`, `AXTextArea`, `AXComboBox`), prefer `value`
- for `AXStaticText`, prefer `value`
- otherwise use `title`
- then fall back to `description`

In short, extraction priority is generally `value -> title -> description`, with text-entry roles explicitly preferring `value`.

More specifically:

- `AXTextField`, `AXTextArea`, `AXComboBox`
  - read `value`
  - if non-empty, use it and stop
- `AXStaticText`
  - read `value`
  - if non-empty, use it and stop
- other `text_bearing_roles`
  - read `title`
  - if empty, fall back to `description`
- `light_container_roles`
  - may read direct `value` only for contribution to `text_content`
  - do not need to be emitted as persisted text-bearing nodes

Single-attribute read failure should be treated as local and should fall back to the next allowed extraction step instead of failing the entire walk.

#### Bounds

- node bounds are best-effort
- bounds should only be attempted for nodes that are already being persisted into the flat node list
- when available, bounds should be normalized relative to the focused window
- missing bounds do not invalidate a node or the overall snapshot
- bounds are an enrichment field, not a canonical adoption requirement

#### Browser URL Matching

The first MVP browser URL path should follow a narrow browser-candidate rule.

- lower-case the app name
- treat the app as a browser candidate only when the name contains:
  - `safari`
  - `chrome`

For browser candidates, the first MVP should attempt a single extraction strategy:

- read `AXDocument` from the focused window

No fallback strategy is required in the first MVP. If `AXDocument` is absent or not an `http(s)` URL, `browser_url` should be `None`.

#### Size Control Strategy

The first MVP should prefer simple bounded collection over complex payload compression or multi-stage degradation.

Priority order:

- `text_content` is the primary payload
- `tree_json` is a required structural payload for accessibility-canonical frames
- debug dumps are development-only artifacts

Rules:

- enforce `max_text_length = 50000`
- enforce `max_nodes = 5000`
- use role filtering and text-bearing-node filtering as the primary size controls
- do not add a second complex `tree_json` trimming system in the first MVP
- do not introduce a special accessibility-canonical-without-`tree_json` state in the first MVP

Observability should include:

- `text_length`
- `node_count`
- serialized `tree_json` byte size
- truncation flags and reasons

Debug dumps may retain the full flat node list, but they should be controlled by debug-only retention rather than by changing canonical payload semantics.

### Accessibility Debugging

Accessibility acquisition must be observable during MVP development.

#### Goals

The debugging path should make it easy to answer:

- whether AX acquisition was attempted
- whether AX was adopted or rejected
- why adoption was rejected
- what text-bearing nodes were actually captured
- whether server persistence matched the client snapshot

#### Client-side Structured Logging

When accessibility collection is evaluated, the client should emit a concise structured log including:

- `capture_id`
- `device_name`
- `eligible`
- `adopted`
- `reason`
- `app_name`
- `window_name`
- `duration_ms`
- `node_count`
- `truncated`
- `text_preview`

Recommended reason vocabulary:

- `non_focused_monitor`
- `app_prefers_ocr`
- `no_focused_window`
- `empty_text`
- `adopted_accessibility`

#### Client-side Debug Dumps

When accessibility debug mode is enabled, the client should be able to dump raw accessibility decisions and snapshots to local JSON files.

Recommended dump content:

- capture metadata
- decision metadata (`eligible`, `adopted`, `reason`)
- snapshot summary (`duration_ms`, `node_count`, `truncated`, `truncation_reason`)
- `text_content`
- full flat `nodes` list

Recommended properties:

- debug-only
- disabled by default
- bounded retention

#### Server-side Verification

The server should make it easy to inspect the persisted result for a frame, including:

- `frames.text`
- `frames.text_source`
- `frames.browser_url`
- `frames.accessibility_tree_json`
- `accessibility.text_content`
- `elements` rows for the frame

This verification path may initially be implemented via store helpers or internal debugging utilities instead of a public API.

#### Snapshot-vs-Persistence Comparison

Accessibility debugging should support comparison between:

- the raw client-side accessibility snapshot
- the persisted server-side frame/accessibility/elements state

This comparison is the primary way to distinguish acquisition bugs from persistence bugs.

### Accessibility Performance Observability

The accessibility hot path should be instrumented before optimization work is considered.

#### Hot-path Timing Breakdown

At minimum, the client should measure these segments:

- `capture_ms`
- `active_context_ms`
- `ax_policy_ms`
- `ax_walk_ms`
- `metadata_merge_ms`
- `spool_enqueue_ms`
- `total_ms`

This breakdown is required to distinguish AX-walk cost from screenshot cost and spool cost.

#### Accessibility-specific Metrics

Recommended AX-specific metrics include:

- `ax_eligible_count`
- `ax_adopted_count`
- `ax_rejected_count`
- `ax_reason_counts`
- `ax_node_count`
- `ax_text_length`
- `ax_truncated_count`
- `ax_timeout_count`
- `ax_duration_ms`

#### Per-capture Performance Logging

When debug logging is enabled, each capture should be able to emit a concise performance summary including:

- trigger
- target device
- app name
- eligibility/adoption decision
- reason
- `capture_ms`
- `ax_walk_ms`
- `spool_enqueue_ms`
- `total_ms`
- `node_count`
- `truncated`

#### Periodic Summaries

The client should also support periodic aggregated summaries, for example every 60 seconds, including:

- capture count
- AX-eligible count
- AX-adopted count
- `total_ms` p50/p95
- `ax_walk_ms` p50/p95
- `spool_enqueue_ms` p50/p95
- timeout count
- truncation count
- top slow apps

#### Optimization Gate

The MVP should not optimize for concurrency or native reimplementation before the above observability exists.

Optimization decisions should be based on measured evidence, especially around:

- `ax_walk_ms`
- timeout frequency
- truncation frequency
- multi-monitor capture cost

## Search Contract

### Endpoint

- `GET /v1/search`

### Query Parameters

- `q`
- `content_type = ocr | accessibility | all`
- `limit`
- `offset`
- `start_time`
- `end_time`
- `app_name`
- `window_name`
- `browser_url`
- `focused`

### Return Shape

The endpoint returns a typed union.

```json
{
  "data": [
    {
      "type": "OCR",
      "content": {
        "frame_id": 1,
        "text": "...",
        "timestamp": "...",
        "app_name": "...",
        "window_name": "...",
        "browser_url": "...",
        "text_source": "ocr"
      }
    },
    {
      "type": "Accessibility",
      "content": {
        "frame_id": 2,
        "text": "...",
        "timestamp": "...",
        "app_name": "...",
        "window_name": "...",
        "browser_url": "...",
        "text_source": "accessibility"
      }
    }
  ],
  "pagination": {
    "limit": 10,
    "offset": 0,
    "total": 42
  }
}
```

### Search Semantics

- `content_type=ocr`
  - searches the OCR text plane
  - only returns frames where `frames.text_source='ocr'`
- `content_type=accessibility`
  - searches `accessibility_fts`
  - only returns frames where `frames.text_source='accessibility'`
- `content_type=all`
  - merges OCR and accessibility results
  - never returns the same frame twice

### Ordering

- for `ocr` and `accessibility`
  - when `q` is present: content-type-specific FTS rank, then `timestamp DESC`
  - when `q` is empty: `timestamp DESC`
- for `all`
  - each sub-search fetches enough rows for the global window
  - merged results are sorted globally by `timestamp DESC`
  - pagination is applied after merge

## Activity Summary Contract

### Endpoint

- `GET /v1/activity-summary`

### Query Parameters

- `start_time`
- `end_time`
- `app_name` (optional)

### Return Shape

```json
{
  "apps": [
    {
      "name": "Google Chrome",
      "frame_count": 128,
      "minutes": 4.3
    }
  ],
  "recent_texts": [
    {
      "frame_id": 123,
      "text": "Chat Capability Alignment",
      "app_name": "Cursor",
      "timestamp": "2026-03-19T10:21:35Z"
    }
  ],
  "audio_summary": {
    "segment_count": 0,
    "speakers": []
  },
  "total_frames": 204,
  "time_range": {
    "start": "2026-03-19T09:30:00Z",
    "end": "2026-03-19T10:30:00Z"
  }
}
```

### Semantics

- `apps` is aggregated from completed frames in the time range
- `apps.minutes` is an approximate value derived from frame density and is not a precise active-time metric
- `recent_texts` aligns with current screenpipe behavior
- `recent_texts` comes from `elements(source='accessibility')`
- `recent_texts` only includes text-like accessibility roles in MVP: `AXStaticText`, `line`, `paragraph`
- `recent_texts` returns recent text-like accessibility nodes, sorted by frame timestamp descending
- `audio_summary` is preserved as a shape-compatible empty shell in vision-only MVP

## Frame Context Contract

### Endpoint

- `GET /v1/frames/{id}/context`

### Return Shape

- `frame_id`
- `text`
- `nodes`
- `urls`
- `text_source`

### Semantics

- `text` comes from `frames.text`
- if accessibility data is available:
  - `text_source='accessibility'`
  - `nodes` are derived from `accessibility_tree_json`
  - `urls` are extracted from link-like nodes first, then from text
- otherwise:
  - fallback to OCR-derived frame text and URLs
  - `text_source='ocr'`

### Node Filtering (aligns with screenpipe)

Nodes with empty `text` are filtered out. This matches screenpipe behavior:

```rust
// screenpipe: if !text.is_empty() { nodes.push(...) }
```

Only nodes with non-empty text content are included in the response.

### URL Extraction (aligns with screenpipe)

**Link-like node extraction:**

- Matches roles containing "link" or "hyperlink" (case-insensitive)
- Extracts URL only if node text starts with `http://` or `https://`

**Full text extraction:**

- Word-based scan for `http://` or `https://` prefixes
- Length check: URL must be > 10 characters
- Punctuation trimming: removes trailing `, ) ] > " '`

**Deduplication:**

- URLs are deduplicated while preserving order
- Link node URLs are added first, then text URLs

### Node Shape

MVP node entries should include:

- `role`
- `text`
- `depth`
- `bounds` when available

### Truncation Policy (aligns with screenpipe)

The API returns complete data by default. Truncation is applied at the Chat/MCP layer, not the API layer.

**Default limits for Chat/MCP consumption:**

| Field | Default Limit | Behavior |
|-------|---------------|----------|
| `text` | 2000 chars | Truncate with `...` suffix |
| `nodes` | 50 items | Include `nodes_truncated` count if exceeded |
| `depth` indentation | 5 levels | Deeper nodes use max indent |

**API query parameters (optional):**

```
GET /v1/frames/{id}/context?max_text=2000&max_nodes=50
```

**Rationale:**

- API layer returns full data for flexibility (matches screenpipe behavior)
- Chat/MCP layer applies truncation to protect LLM context window
- Each frame context is ~1000-2000 tokens when sent to LLM
- Agents should fetch no more than 2-3 frames per query

## Image Fetch

### Endpoint

- `GET /v1/frames/{id}`

### Policy

- image fetch is enabled in MVP
- image fetch is not the default first step
- image fetch should be used when:
  - text grounding is insufficient, or
  - the user explicitly asks to inspect the visual frame
- the agent should prefer a small number of key frames

## Agent Policy

The MVP skill should align with screenpipe-search strategy while using the reduced MyRecall tool surface.

### Core Rules

- always include a time range for summary and search calls
- start with a narrow time window and expand only when needed
- use low-cost text tools first
- use image fetch only when necessary
- treat activity summary as overview, not final evidence
- use frame context as the main evidence layer
- protect context window: use default truncation limits for frame context
- fetch no more than 2-3 frames per query (each frame ~1000-2000 tokens)

### Default Tool Strategy

```text
broad question
  -> /v1/activity-summary
  -> /v1/search
  -> /v1/frames/{id}/context
  -> /v1/frames/{id} if needed

specific question
  -> /v1/search
  -> /v1/frames/{id}/context
  -> /v1/frames/{id} if needed
```

## Browser URL

`browser_url` is **frame-level best-effort metadata**.

### Key Semantic

- `browser_url` belongs to the frame, not to the accessibility subsystem
- It should be persisted to `frames.browser_url` whenever available, regardless of the frame's final `text_source`
- It does not influence or determine the canonical text source
- Search APIs can filter by `browser_url` for any frame (accessibility or OCR)

### Extraction Rules

MVP browser URL extraction rules:

- attempt retrieval only for focused browser windows
- first implementation treats app names containing `safari` or `chrome` as browser candidates
- first implementation uses `AXDocument` only
- no fallback is required in MVP
- retrieval failure should produce `None`
- absence of `browser_url` is expected and non-fatal

### Browser URL Availability

`browser_url` availability depends on whether the walker produced a snapshot:

| Decision Reason | browser_url | Explanation |
|-----------------|-------------|-------------|
| `adopted_accessibility` | ✅ Available | Snapshot produced with text |
| `empty_text` | ✅ Available | Snapshot produced (browser_url extracted before text aggregation) |
| `no_focused_window` | ❌ Unavailable | No snapshot produced, no window to extract from |

> Note: The walker extracts `browser_url` via `AXDocument` before aggregating text content.
> This means `empty_text` frames can still have `browser_url` populated.

### Search Implications

- `browser_url` filter works for both accessibility-canonical and OCR frames
- Accessibility-canonical frames have higher `browser_url` coverage
- OCR frames from `empty_text` may have `browser_url` (useful for browser history queries)
- OCR frames from `no_focused_window` cannot have `browser_url`

## Screenpipe Alignment

### Aligned

- Host-side agent runtime
- single-skill policy-driven chat
- progressive disclosure search strategy
- frame context contract direction
- image fetch as a secondary path
- paired accessibility-at-capture direction

### Intentional Deviations

- no independent tree walker
- accessibility is a frame-backed search plane
- no public `/v1/elements`
- no input or audio parity
- weaker browser URL support in MVP
- `frames.text` is the canonical frame text field
- `frames_fts` is metadata-only

## Deferred

The following items are explicitly deferred beyond MVP:

- independent tree walker
- screenpipe-style independent accessibility timeline semantics
- public `/v1/elements`
- input search
- OCR elements
- richer browser URL support across browsers
- multi-skill architecture
- broader parity work

## Success Criteria

The MVP is successful when:

- the user can ask about recent activity and receive grounded answers
- the agent can use summary -> search -> context as the primary workflow
- frame-backed accessibility search works
- frame context returns `text`, `nodes`, `urls`, and `text_source`
- image fetch works as a secondary tool
- search results can reliably drive follow-up retrieval with `frame_id`
