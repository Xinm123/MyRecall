# Screenpipe: Accessibility → OCR Fallback → Persistence Architecture

## Executive Summary

Screenpipe uses a **three-layer architecture** for text extraction and persistence:

1. **S1: Raw AX Tree Extraction** — Accessibility tree walk computes `content_hash` and `simhash` WITHOUT any labeling decision
2. **S2: AX-First Decision + OCR Fallback** — `paired_capture` evaluates raw AX output, decides whether to run OCR, and computes `text_source`
3. **S3: DB Persistence** — Frame is inserted with separate columns for AX text, OCR text, and metadata (`text_source`, `content_hash`, `simhash`)

**Key insight**: `text_source` is **NOT** computed during AX tree walk. Instead, it is determined **post-AX** in `paired_capture` based on:
- Whether AX tree returned non-empty text
- Whether structured nodes (tree_json) are present
- App-level rules (terminal emulator preference for OCR)

---

## Layer 1: Raw Accessibility Tree Extraction (S1)

### File: [`screenpipe-accessibility/src/tree/macos.rs`](https://github.com/screenpipe/screenpipe/blob/main/crates/screenpipe-accessibility/src/tree/macos.rs)

**Purpose**: Walk the macOS accessibility tree and **extract raw text WITHOUT deciding if it's usable**.

#### Pre-extraction Validation (Early-Exit Gates)

These are evaluated **before** tree walk:

```rust
// Line 232-244: Skip excluded apps (password managers, 1Password, Bitwarden, etc.)
const EXCLUDED_APPS: &[&str] = &[
    "1password", "bitwarden", "lastpass", "dashlane", "keepassxc", 
    "keychain access", "screenpipe", "loginwindow",
];
if EXCLUDED_APPS.iter().any(|ex| app_lower.contains(ex)) {
    return Ok(None);
}

// Line 247-252: Apply user-configured ignored windows
if self.config.ignored_windows.iter().any(|pattern| {
    let p = pattern.to_lowercase();
    app_lower.contains(&p)
}) {
    return Ok(None);
}

// Line 268-275: Get AX focused window — if failed, return None (not empty text)
let window_val = match ax_app.attr_value(ax::attr::focused_window()) {
    Ok(v) => v,
    Err(_) => return Ok(None),
};
```

#### Core Tree Walk (No Success/Failure Decision)

```rust
// Line 324-325: Walk the tree — this is "pure extraction", no labeling
walk_element(window, 0, &mut state);

let text_content = state.text_buffer;
// Line 328-330: IMPORTANT: Don't bail on empty text
// "Some apps may return empty text on the first walk after 
// AXEnhancedUserInterface is set (Chromium builds the tree async)."
```

#### Compute Hashes (Pre-Processing for S2)

```rust
// Line 343-344: Compute content_hash and simhash DURING tree walk, not after
let content_hash = TreeSnapshot::compute_hash(&text_content);
let simhash = TreeSnapshot::compute_simhash(&text_content);
```

**Where hashes are defined**:

File: [`screenpipe-accessibility/src/tree/mod.rs`](https://github.com/screenpipe/screenpipe/blob/main/crates/screenpipe-accessibility/src/tree/mod.rs)

```rust
// Line 81-85: content_hash = SHA256-like hash on full text
impl TreeSnapshot {
    pub fn compute_hash(text: &str) -> u64 {
        let mut hasher = DefaultHasher::new();
        text.hash(&mut hasher);
        hasher.finish()
    }

    // Line 89-124: simhash = locality-sensitive hash for fuzzy dedup
    pub fn compute_simhash(text: &str) -> u64 {
        // Word-level 3-shingles: similar texts → small Hamming distance
        let words: Vec<&str> = text.split_whitespace().collect();
        // ... accumulate bit vectors for each 3-shingle ...
        result
    }
}
```

#### Return TreeSnapshot (WITH Hashes, NO text_source)

```rust
// Line 364-378: Return raw snapshot with hashes computed
Ok(Some(TreeSnapshot {
    app_name,
    window_name,
    text_content,
    nodes: state.nodes,
    browser_url,
    timestamp: Utc::now(),
    node_count: state.node_count,
    walk_duration,
    content_hash,           // ← Computed but NOT labeled as "accessibility" yet
    simhash,                // ← Computed but NOT labeled as "accessibility" yet
    truncated: state.truncated,
    truncation_reason: state.truncation_reason,
    max_depth_reached: state.max_depth_reached,
}))
```

**Note**: `TreeSnapshot` struct does NOT have a `text_source` field. It only has:
- `text_content` (raw string)
- `nodes` (structured tree)
- `content_hash`, `simhash` (dedup hashes)
- `node_count`, `walk_duration`, `truncation_reason` (metadata)

---

## Layer 2: AX-First Decision + OCR Fallback (S2)

### File: [`screenpipe-server/src/paired_capture.rs`](https://github.com/screenpipe/screenpipe/blob/main/crates/screenpipe-server/src/paired_capture.rs)

**Purpose**: Evaluate AX output and decide OCR fallback + final `text_source` label.

### Step 1: Determine if AX Text is Usable

```rust
// Line 100-116: Check if app prefers OCR (terminal emulators)
let app_prefers_ocr = ctx.app_name.is_some_and(|name| {
    let n = name.to_lowercase();
    n.contains("wezterm") || n.contains("iterm") || n.contains("terminal") 
        || n.contains("alacritty") || n.contains("kitty") || n.contains("hyper") 
        || n.contains("warp") || n.contains("ghostty")
});

let has_accessibility_text = !app_prefers_ocr
    && tree_snapshot
        .map(|s| !s.text_content.is_empty())
        .unwrap_or(false);
```

**Key gate**: `has_accessibility_text = tree_snapshot exists AND text_content not empty AND app doesn't prefer OCR`

### Step 2: Conditionally Run OCR

```rust
// Line 119-155: Only run OCR when accessibility tree returned no text
let (ocr_text, ocr_text_json) = if !has_accessibility_text {
    #[cfg(target_os = "macos")]
    {
        let image_for_ocr = ctx.image.clone();
        let ocr_result = tokio::task::spawn_blocking(move || {
            let (text, json, _confidence) = 
                screenpipe_vision::perform_ocr_apple(&image_for_ocr, &[]);
            (text, json)
        }).await?;
        ocr_result
    }
    // ... Windows native OCR (async), Tesseract (Linux) ...
} else {
    (String::new(), "[]".to_string())
};
```

**Optimization**: If `has_accessibility_text=true`, OCR is **skipped entirely**. This saves 50-200ms per capture and avoids cloning the Arc<DynamicImage>.

### Step 3: Extract Data and Decide Between AX vs OCR Text

```rust
// Line 161-190: Merge AX and OCR fallback
let (accessibility_text, tree_json, content_hash, simhash) = if app_prefers_ocr {
    // Terminal: OCR is only useful source, AX tree returns window chrome only
    if !ocr_text.is_empty() {
        (Some(ocr_text.clone()), None, None, None)  // ← OCR text, NO nodes
    } else {
        (None, None, None, None)  // ← Neither worked
    }
} else {
    match tree_snapshot {
        Some(snap) if !snap.text_content.is_empty() => {
            let json = serde_json::to_string(&snap.nodes).ok();
            (
                Some(snap.text_content.clone()),
                json,  // ← Nodes present: AX succeeded
                Some(snap.content_hash as i64),
                Some(snap.simhash as i64),
            )
        }
        _ => {
            // OCR fallback: accessibility returned no text
            if ocr_text.is_empty() {
                (None, None, None, None)  // ← Neither worked
            } else {
                (Some(ocr_text.clone()), None, None, None)  // ← OCR text, NO nodes
            }
        }
    }
};
```

### Step 4: Assign `text_source` Label

```rust
// Line 192-204: FINAL DECISION on text_source
let (final_text, text_source) = if let Some(ref text) = accessibility_text {
    if text.is_empty() {
        (None, None)
    } else if tree_json.is_some() {
        // tree_json is ONLY present if AX succeeded
        (Some(text.as_str()), Some("accessibility"))  // ← AX source
    } else {
        // Text came from OCR fallback (no tree_json means no accessibility nodes)
        (Some(text.as_str()), Some("ocr"))  // ← OCR source
    }
} else {
    (None, None)
};
```

**Key insight**: `text_source` is determined by **presence of `tree_json`**, not by which source produced the text:
- `text_source = "accessibility"` ⟺ `tree_json.is_some()` (structured nodes from AX)
- `text_source = "ocr"` ⟺ `tree_json.is_none()` (OCR fallback used)

### Step 5: Persist to Database

```rust
// Line 243-261: Insert frame with both AX and OCR data
let frame_id = ctx.db.insert_snapshot_frame_with_ocr(
    ctx.device_name,
    ctx.captured_at,
    &snapshot_path_str,
    ctx.app_name,
    ctx.window_name,
    ctx.browser_url,
    ctx.focused,
    Some(ctx.capture_trigger),
    sanitized_text.as_deref(),        // ← Final text (AX or OCR)
    text_source,                       // ← "accessibility" or "ocr"
    tree_json.as_deref(),              // ← Structured nodes if AX succeeded
    content_hash,
    simhash,
    ocr_data,                          // ← OCR positions if OCR ran
).await?;
```

---

## Layer 3: DB Persistence Schema (S3)

### File: [`screenpipe-db/src/migrations/20260220000000_event_driven_capture.sql`](https://github.com/screenpipe/screenpipe/blob/main/crates/screenpipe-db/src/migrations/20260220000000_event_driven_capture.sql)

**Frames table schema** (NEW columns):

```sql
CREATE TABLE frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_chunk_id INTEGER DEFAULT NULL,
    offset_index INTEGER NOT NULL DEFAULT 0,
    timestamp TIMESTAMP NOT NULL,
    name TEXT,
    app_name TEXT DEFAULT NULL,
    window_name TEXT DEFAULT NULL,
    focused BOOLEAN DEFAULT NULL,
    browser_url TEXT DEFAULT NULL,
    device_name TEXT NOT NULL DEFAULT '',
    
    -- Event-driven snapshot columns (new in S2a)
    snapshot_path TEXT DEFAULT NULL,
    accessibility_text TEXT DEFAULT NULL,
    accessibility_tree_json TEXT DEFAULT NULL,
    content_hash INTEGER DEFAULT NULL,
    simhash INTEGER DEFAULT NULL,
    capture_trigger TEXT DEFAULT NULL,
    text_source TEXT DEFAULT NULL,  -- ← "accessibility" or "ocr"
    
    FOREIGN KEY (video_chunk_id) REFERENCES video_chunks(id)
);
```

### DB Insertion Function

File: [`screenpipe-db/src/db.rs:1487`](https://github.com/screenpipe/screenpipe/blob/main/crates/screenpipe-db/src/db.rs#L1487)

```rust
pub async fn insert_snapshot_frame_with_ocr(
    &self,
    device_name: &str,
    timestamp: DateTime<Utc>,
    snapshot_path: &str,
    app_name: Option<&str>,
    window_name: Option<&str>,
    browser_url: Option<&str>,
    focused: bool,
    capture_trigger: Option<&str>,
    accessibility_text: Option<&str>,        // ← From AX or OCR
    text_source: Option<&str>,               // ← "accessibility" or "ocr"
    accessibility_tree_json: Option<&str>,   // ← Nodes (if AX)
    content_hash: Option<i64>,               // ← From AX
    simhash: Option<i64>,                    // ← From AX
    ocr_data: Option<(&str, &str, &str)>,   // ← (text, json, engine) if OCR
) -> Result<i64, sqlx::Error> {
    let mut tx = self.begin_immediate_with_retry().await?;
    
    // Insert frame
    let id = sqlx::query(
        r#"INSERT INTO frames (
            ..., accessibility_text, text_source,
            accessibility_tree_json, content_hash, simhash
        ) VALUES (
            ..., ?10, ?11, ?12, ?13, ?14
        )"#,
    )
    .bind(accessibility_text)
    .bind(text_source)               // ← Persisted here
    .bind(accessibility_tree_json)
    .bind(content_hash)
    .bind(simhash)
    .execute(&mut **tx.conn())
    .await?
    .last_insert_rowid();
    
    // Dual-write: insert OCR elements if present
    if let Some((text, text_json, ocr_engine)) = ocr_data {
        sqlx::query(
            "INSERT INTO ocr_text (frame_id, text, text_json, ocr_engine) VALUES (?1, ?2, ?3, ?4)",
        )
        .bind(id)
        .bind(text)
        .bind(text_json)
        .bind(ocr_engine)
        .execute(&mut **tx.conn())
        .await?;
    }
    
    // Dual-write: insert AX elements if present
    if let Some(tree_json) = accessibility_tree_json {
        if !tree_json.is_empty() {
            Self::insert_accessibility_elements(tx.conn(), id, tree_json).await;
        }
    }
    
    tx.commit().await?;
    Ok(id)
}
```

---

## Content Deduplication Pre-Gate (Before S3)

### File: [`screenpipe-server/src/event_driven_capture.rs:560-586`](https://github.com/screenpipe/screenpipe/blob/main/crates/screenpipe-server/src/event_driven_capture.rs#L560)

Screenpipe uses `content_hash` **before** persisting to decide if a frame should be skipped entirely:

```rust
// Step 1: Walk AX tree (compute content_hash)
let tree_snapshot = tokio::task::spawn_blocking(move || {
    crate::paired_capture::walk_accessibility_tree(&config)
}).await?;

// Step 2: Check if content matches previous capture
let dedup_eligible = !matches!(trigger, CaptureTrigger::Idle | CaptureTrigger::Manual)
    && last_db_write.elapsed() < Duration::from_secs(30);
if dedup_eligible {
    if let Some(ref snap) = tree_snapshot {
        if !snap.text_content.is_empty() {
            let new_hash = snap.content_hash as i64;  // ← From AX
            if let Some(prev) = previous_content_hash {
                if prev == new_hash && new_hash != 0 {
                    debug!("content dedup: skipping capture for monitor {}", monitor_id);
                    return Ok(CaptureOutput {
                        result: None,  // ← Frame NOT inserted
                        image,
                    });
                }
            }
        }
    }
}
```

**Key flow**:
1. AX tree walk computes `content_hash`
2. **Before** calling `paired_capture`, event-driven loop checks if hash matches previous
3. If dedup triggered, DB insertion is skipped entirely
4. If not deduped, frame proceeds to `paired_capture` → DB insertion

This is an **S2b gate**: validates AX success (non-empty text + matching hash) **before** S3 (DB persistence).

---

## MyRecall S2b Gate Proposal

Based on screenpipe's architecture, a MyRecall S2b gate should:

### Input to S2b
- Raw AX tree result (text_content, nodes, hashes)
- App name/window metadata
- Screenshot image

### Validation Criteria
1. **AX tree walk succeeded** (tree_snapshot is Some)
2. **Text content is non-empty** (text_content.len() > 0)
3. **Content hash is valid** (content_hash != 0)
4. **Not excluded app** (not password manager, screensaver, etc.)
5. **Nodes present** (nodes.len() > 0 for structured AX)

### Output to S3
- **Persist?** (yes/no decision)
- **text_source** ("accessibility" | "ocr" | None)
- **Hash metadata** (content_hash, simhash)
- **Structured nodes** (tree_json, if AX succeeded)

### Implementation Pattern from Screenpipe

```rust
// Pseudocode for MyRecall S2b gate
fn validate_ax_capture(tree_snapshot: Option<&TreeSnapshot>) -> (bool, Option<&str>) {
    match tree_snapshot {
        Some(snap) => {
            if snap.text_content.is_empty() {
                // Empty text: AX walk succeeded but returned nothing
                // Decision: Don't persist (unless fallback to OCR)
                return (false, None);
            }
            if snap.content_hash == 0 {
                // Invalid hash (should rarely happen)
                return (false, None);
            }
            if snap.nodes.is_empty() {
                // No structured nodes: might be OCR-only
                return (true, Some("ocr"));
            }
            // AX tree succeeded with content and structure
            (true, Some("accessibility"))
        }
        None => {
            // AX walk failed entirely (accessibility unavailable, app blocked, etc.)
            (false, None)
        }
    }
}
```

---

## Summary Table

| Layer | Component | Decision | Output | Evidence |
|-------|-----------|----------|--------|----------|
| **S1: AX Extract** | `tree/macos.rs` | Walk AX tree, compute hashes | `TreeSnapshot` (text, nodes, hash) | [macos.rs:343-378](https://github.com/screenpipe/screenpipe/blob/main/crates/screenpipe-accessibility/src/tree/macos.rs#L343) |
| **S2: Fallback** | `paired_capture.rs` | Decide if OCR needed | `text_source` label | [paired_capture.rs:192-204](https://github.com/screenpipe/screenpipe/blob/main/crates/screenpipe-server/src/paired_capture.rs#L192) |
| **S2b: Dedup Gate** | `event_driven_capture.rs` | Check hash vs previous | Persist? (skip if dedup) | [event_driven_capture.rs:566-586](https://github.com/screenpipe/screenpipe/blob/main/crates/screenpipe-server/src/event_driven_capture.rs#L566) |
| **S3: Persist** | `db.rs` | Insert frame + OCR + AX | Frame in `frames` table | [db.rs:1487-1570](https://github.com/screenpipe/screenpipe/blob/main/crates/screenpipe-db/src/db.rs#L1487) |

