# Frame Context Endpoint Simplification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify `GET /v1/frames/{id}/context` by removing `max_text_length`, `max_nodes`, `include_nodes` params and `nodes`, `nodes_truncated`, `description_status` from the response. Text capped at 5000 chars. Description moved before text in field order.

**Architecture:** Two-layer change: (1) `FramesStore.get_frame_context()` removes nodes logic and adds fixed 5000-char truncation, (2) API endpoint removes param parsing and reorders fields.

**Tech Stack:** Python, Flask, SQLite, pytest

---

## Files to Modify

| File | Change |
|------|--------|
| `openrecall/server/database/frames_store.py` | Simplify `get_frame_context()` — remove `include_nodes`, `max_nodes` params, remove nodes parsing, add 5000-char text truncation |
| `openrecall/server/api_v1.py` | Simplify `get_frame_context()` route — remove query param parsing, reorder fields, remove `description_status` |
| `tests/test_chat_mvp_frame_context.py` | Remove `TestGetFrameContextTruncation` (6 tests) and `TestGetFrameContextIncludeNodes` (8 tests); update `TestGetFrameContext` calls to remove `include_nodes` args |
| `tests/test_chat_mvp_frame_context_api.py` | Update API tests — remove param-related tests, update field expectations, remove `description_status` |
| `docs/v3/chat/api-fields-reference.md` | Update response fields table, examples, remove nodes/truncation |
| `docs/v3/chat/mvp.md` | Update Frame Context Contract |

---

## Task 1: Simplify `FramesStore.get_frame_context()`

**Files:**
- Modify: `openrecall/server/database/frames_store.py:1392-1520`

- [ ] **Step 1: Rewrite `get_frame_context()` method**

Replace the entire `get_frame_context` method in `openrecall/server/database/frames_store.py` (lines 1392-1520) with the new implementation shown below. Key changes: remove `include_nodes`/`max_nodes` params, remove nodes parsing, remove link-node URL extraction, add fixed 5000-char text truncation with "..." suffix.

```python
MAX_TEXT_LENGTH = 5000

def get_frame_context(
    self,
    frame_id: int,
) -> Optional[dict]:
    """Return frame context for chat grounding.

    Returns:
        - frame_id, timestamp, app_name, window_name: frame metadata
        - text: accessibility_text or ocr_text, truncated at MAX_TEXT_LENGTH chars
        - text_source: 'accessibility' | 'ocr' | 'hybrid' | None
        - urls: extracted from text via regex
        - browser_url, status: frame metadata

    Text is always truncated at MAX_TEXT_LENGTH (5000) chars with "..." suffix.
    """
    try:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT f.id, f.accessibility_text, f.ocr_text, f.text_source,
                       f.browser_url, f.status,
                       f.timestamp, f.app_name, f.window_name
                FROM frames f
                WHERE f.id = ?
                """,
                (frame_id,),
            ).fetchone()

            if row is None:
                return None

            frame_id_val = row["id"]
            # Use frames.ocr_text for OCR frames, frames.accessibility_text for accessibility frames
            if row["text_source"] == "ocr":
                text = row["ocr_text"] or ""
            else:
                text = row["accessibility_text"] or ""
            text_source = row["text_source"]
            browser_url = row["browser_url"]
            status = row["status"]
            timestamp = row["timestamp"]
            app_name = row["app_name"]
            window_name = row["window_name"]

            urls: list[str] = []

            # Extract URLs from text using regex (screenpipe-aligned)
            for url in self._extract_urls_from_text(text):
                if url not in urls:
                    urls.append(url)

            # Apply fixed text truncation at MAX_TEXT_LENGTH
            result_text = text
            if len(result_text) > MAX_TEXT_LENGTH:
                result_text = result_text[:MAX_TEXT_LENGTH] + "..."

            return {
                "frame_id": frame_id_val,
                "timestamp": timestamp,
                "app_name": app_name,
                "window_name": window_name,
                "text": result_text,
                "text_source": text_source,
                "urls": urls,
                "browser_url": browser_url,
                "status": status,
            }
    except Exception:
        logger.exception(f"Error getting frame context for frame_id={frame_id}")
        return None
```

Notable changes: removed `accessibility_tree_json` from SELECT, removed all `include_nodes`/`max_nodes` params, removed link-node URL extraction, added `MAX_TEXT_LENGTH = 5000` constant, uses `logger.exception` (same pattern as other store methods).

- [ ] **Step 2: Run tests to see failures**

Run: `pytest tests/test_chat_mvp_frame_context.py -v`
Expected: ~14 tests FAIL (tests pass old `include_nodes` args and/or expect `nodes`/`nodes_truncated`). This is expected — we'll fix in Task 2.

- [ ] **Step 3: Commit**

```bash
git add openrecall/server/database/frames_store.py
git commit -m "refactor: simplify get_frame_context — remove nodes, cap text at 5000"
```

---

## Task 2: Update unit tests for store layer

**Files:**
- Modify: `tests/test_chat_mvp_frame_context.py`

- [ ] **Step 1: Remove `TestGetFrameContextTruncation` class**

Delete the entire `TestGetFrameContextTruncation` class (lines 459-546). These tests cover the old `max_text_length` and `max_nodes` parameters which are removed.

- [ ] **Step 2: Remove `TestGetFrameContextIncludeNodes` class**

Delete the entire `TestGetFrameContextIncludeNodes` class (lines 548-739). These tests cover the old `include_nodes` parameter and `nodes`/`nodes_truncated` response fields which are removed.

- [ ] **Step 3: Remove two tests whose assertions are entirely about nodes**

After removing the above classes, delete these two tests from `TestGetFrameContext`:

- `test_get_frame_context_parses_accessibility_tree_json` (original line 95): Tests node parsing. After removing `include_nodes`, it has no meaningful assertions left.
- `test_get_frame_context_extracts_urls_from_link_nodes` (original line 125): Tests URL extraction from AX link/hyperlink nodes. Link-node URL extraction is removed. Text-based URL extraction is covered by `test_get_frame_context_extracts_urls_from_text`.

- [ ] **Step 4: Update `TestGetFrameContext` — remove `include_nodes` args from all remaining calls**

In the `TestGetFrameContext` class (after removals above), update every `store.get_frame_context()` call. Some tests need `include_nodes=True` REMOVED, and six tests need `include_nodes=True` ADDED:

**REMOVE `include_nodes=True` (no longer a valid kwarg):**
- Line 108: `store.get_frame_context(frame_id, include_nodes=True)` → `store.get_frame_context(frame_id)`
- Line 140: `store.get_frame_context(frame_id, include_nodes=True)` → `store.get_frame_context(frame_id)`
- Line 194: `store.get_frame_context(frame_id, include_nodes=True)` → `store.get_frame_context(frame_id)`
- Line 224: `store.get_frame_context(frame_id, include_nodes=True)` → `store.get_frame_context(frame_id)`
- Line 259: `store.get_frame_context(frame_id, include_nodes=True)` → `store.get_frame_context(frame_id)`
- Line 277: `store.get_frame_context(frame_id, include_nodes=True)` → `store.get_frame_context(frame_id)`
- Line 295: `store.get_frame_context(frame_id, include_nodes=True)` → `store.get_frame_context(frame_id)`
- Line 317: `store.get_frame_context(frame_id, include_nodes=True)` → `store.get_frame_context(frame_id)`
- Line 383: `store.get_frame_context(frame_id, include_nodes=True)` → `store.get_frame_context(frame_id)`

Note: Tests without `include_nodes` argument (lines 88, 160, 208, 246, 335, 361) are already correct — no change needed. The new API takes no optional args.

- [ ] **Step 5: Update `test_get_frame_context_handles_ocr_fallback`**

Remove the assertion `assert context["nodes"] == []` (around line 200 in original file). The `nodes` key is no longer in the response.

- [ ] **Step 6: Update `test_get_frame_context_returns_empty_for_pending_frame`**

Remove the assertion `assert context["nodes"] == []`. Keep `assert context["urls"] == []`.

- [ ] **Step 7: Update `test_get_frame_context_handles_empty_accessibility_tree`**

Remove the assertion `assert context["nodes"] == []`.

- [ ] **Step 8: Rewrite `test_get_frame_context_filters_empty_text_nodes`**

Replace the test body (original line 303) with a test that verifies text still contains content from non-empty nodes:

```python
def test_get_frame_context_text_captures_node_content(self, store: FramesStore):
    """Frame context text should include content from non-empty AX nodes."""
    elements = [
        {"role": "AXStaticText", "text": "Visible text", "depth": 0},
        {"role": "AXGroup", "text": "", "depth": 0},  # Empty text - filtered from tree
        {"role": "AXButton", "text": None, "depth": 0},  # None text - filtered from tree
        {"role": "AXStaticText", "text": "More text", "depth": 0},
    ]
    frame_id = _create_completed_frame_with_accessibility(
        store, "cap-1", "2026-03-20T10:00:00Z", "Safari", "Visible text More text", elements
    )
    context = store.get_frame_context(frame_id)
    assert context is not None
    # Text should contain both non-empty texts (concatenated by the recorder)
    assert "Visible text" in context["text"]
    assert "More text" in context["text"]
```

- [ ] **Step 9: Rename `test_get_frame_context_link_text_url_extraction` to `test_get_frame_context_url_extraction_from_text`**

Update the docstring and remove the link-node assertion (the AXLink text doesn't start with http, so it wasn't extracted even before):

```python
def test_get_frame_context_url_extraction_from_text(self, store: FramesStore):
    """URLs are extracted from text via regex (link-node extraction removed)."""
    elements = [
        {"role": "AXStaticText", "text": "Check https://direct-url.com for details", "depth": 0},
    ]
    frame_id = _create_completed_frame_with_accessibility(
        store, "cap-1", "2026-03-20T10:00:00Z", "Safari",
        "Check https://direct-url.com for details", elements
    )
    context = store.get_frame_context(frame_id)
    assert context is not None
    assert "https://direct-url.com" in context["urls"]
```

- [ ] **Step 10: Add truncation boundary test**

Add the following test to `TestGetFrameContext`:

```python
def test_get_frame_context_truncates_text_at_5000_chars(self, store: FramesStore):
    """Text should be truncated at 5000 chars with '...' suffix."""
    # Exactly 5000 chars — no truncation
    text_5000 = "X" * 5000
    elements = [{"role": "AXStaticText", "text": text_5000, "depth": 0}]
    frame_id = _create_completed_frame_with_accessibility(
        store, "cap-t5000", "2026-03-20T10:00:00Z", "Safari", text_5000, elements
    )
    context = store.get_frame_context(frame_id)
    assert context is not None
    assert len(context["text"]) == 5000
    assert not context["text"].endswith("...")

    # 5001 chars — truncated to 5000 + "..."
    text_5001 = "Y" * 5001
    elements2 = [{"role": "AXStaticText", "text": text_5001, "depth": 0}]
    frame_id2 = _create_completed_frame_with_accessibility(
        store, "cap-t5001", "2026-03-20T10:00:00Z", "Safari", text_5001, elements2
    )
    context2 = store.get_frame_context(frame_id2)
    assert context2 is not None
    assert len(context2["text"]) == 5003  # 5000 + "..."
    assert context2["text"].endswith("...")
```

- [ ] **Step 11: Run tests to verify all pass**

Run: `pytest tests/test_chat_mvp_frame_context.py -v`
Expected: PASS (all remaining tests)

- [ ] **Step 12: Commit**

```bash
git add tests/test_chat_mvp_frame_context.py
git commit -m "test: update frame context tests — remove nodes/truncation tests, update remaining tests"
```

---

## Task 3: Simplify API endpoint

**Files:**
- Modify: `openrecall/server/api_v1.py:639-719`

- [ ] **Step 1: Rewrite the `get_frame_context` route handler**

Replace the entire route function (lines 639-719) with:

```python
@v1_bp.route("/frames/<int:frame_id>/context", methods=["GET"])
def get_frame_context(frame_id: int):
    """Return frame context for chat grounding.

    Returns:
        200 JSON — frame context (always includes description, text, urls, text_source)
        404 NOT_FOUND — frame_id not in DB
    """
    request_id = str(uuid.uuid4())

    store = _get_frames_store()

    context = store.get_frame_context(frame_id)

    if context is None:
        return make_error_response(
            "frame not found",
            "NOT_FOUND",
            404,
            request_id=request_id,
        )

    # Add description if completed
    description = None
    try:
        with store._connect() as conn:
            row = conn.execute(
                "SELECT description_status FROM frames WHERE id = ?",
                (frame_id,),
            ).fetchone()
            if row and row["description_status"] == "completed":
                desc_row = store.get_frame_description(conn, frame_id)
                if desc_row:
                    description = {
                        "narrative": desc_row["narrative"],
                        "summary": desc_row["summary"],
                        "tags": desc_row["tags"],
                    }
    except Exception as e:
        logger.warning(f"Failed to get description for frame {frame_id}: {e}")

    # Insert description at the correct field position (after window_name, before text)
    # Build ordered result dict
    result = {
        "frame_id": context["frame_id"],
        "timestamp": context["timestamp"],
        "app_name": context["app_name"],
        "window_name": context["window_name"],
        "description": description,
        "text": context["text"],
        "text_source": context["text_source"],
        "urls": context["urls"],
        "browser_url": context["browser_url"],
        "status": context["status"],
    }

    return jsonify(result)
```

Note: Removed all query param parsing (`include_nodes`, `max_text_length`, `max_nodes`). Removed `description_status` from response. Reordered fields to put `description` before `text`.

- [ ] **Step 2: Run the API tests to see failures**

Run: `pytest tests/test_chat_mvp_frame_context_api.py -v`
Expected: Multiple tests FAIL (expecting old params, nodes, description_status, field order)

- [ ] **Step 3: Commit**

```bash
git add openrecall/server/api_v1.py
git commit -m "refactor: simplify /frames/{id}/context endpoint — remove params, reorder fields"
```

---

## Task 4: Update API tests

**Files:**
- Modify: `tests/test_chat_mvp_frame_context_api.py`

- [ ] **Step 1: Rewrite test fixture — `_seed_accessibility_context()`**

Update the fixture at the top of the file to match the new response shape (after imports, before class):

```python
def _seed_accessibility_context():
    """Return sample frame context for accessibility frame."""
    return {
        "frame_id": 1,
        "timestamp": "2026-03-26T10:00:00Z",
        "app_name": "Claude Code",
        "window_name": "Claude Code — ~/chat",
        "description": None,
        "text": "Hello World",
        "text_source": "accessibility",
        "urls": [],
        "browser_url": "https://example.com",
        "status": "completed",
    }
```

- [ ] **Step 2: Remove `test_frame_context_supports_max_text_length`**

Delete the test (lines 93-114). Parameter no longer exists.

- [ ] **Step 3: Remove `test_frame_context_supports_max_nodes`**

Delete the test (lines 116-141). Parameter and field no longer exist.

- [ ] **Step 4: Remove `test_frame_context_passes_params_to_store`**

Delete the test (lines 142-152). Parameter parsing no longer exists.

- [ ] **Step 5: Remove `test_frame_context_handles_invalid_max_text_length`**

Delete the test (lines 154-164). Parameter no longer exists.

- [ ] **Step 6: Remove `test_frame_context_handles_invalid_max_nodes`**

Delete the test (lines 166-176). Parameter no longer exists.

- [ ] **Step 7: Update `test_frame_context_returns_valid_response`**

Update to remove `nodes` from expected fields and add `description`:

```python
def test_frame_context_returns_valid_response(self, app_with_context_route, mock_store):
    """Endpoint returns frame_id, description, text, urls, text_source."""
    mock_store.get_frame_context.return_value = {
        "frame_id": 1,
        "timestamp": "2026-03-26T10:00:00Z",
        "app_name": "Claude Code",
        "window_name": "Claude Code — ~/chat",
        "text": "Hello World",
        "text_source": "accessibility",
        "urls": [],
        "browser_url": "https://example.com",
        "status": "completed",
    }

    with patch("openrecall.server.api_v1._get_frames_store", return_value=mock_store):
        client = app_with_context_route.test_client()
        response = client.get("/v1/frames/1/context")

        assert response.status_code == 200
        body = json.loads(response.data)
        assert body["frame_id"] == 1
        assert body["text"] == "Hello World"
        assert body["text_source"] == "accessibility"
        assert body["timestamp"] == "2026-03-26T10:00:00Z"
        assert body["app_name"] == "Claude Code"
        assert body["window_name"] == "Claude Code — ~/chat"
        # nodes and description_status are removed
        assert "nodes" not in body
        assert "description_status" not in body
```

- [ ] **Step 8: Update `test_frame_context_returns_ocr_fallback`**

Update mock return value to match new shape:

```python
def test_frame_context_returns_ocr_fallback(self, app_with_context_route, mock_store):
    """Endpoint returns OCR data when accessibility unavailable."""
    mock_store.get_frame_context.return_value = {
        "frame_id": 3,
        "timestamp": "2026-03-26T10:00:00Z",
        "app_name": "Terminal",
        "window_name": "zsh — 120×40",
        "text": "OCR extracted text with https://ocr-url.com link",
        "text_source": "ocr",
        "urls": ["https://ocr-url.com"],
        "browser_url": None,
        "status": "completed",
    }
```

- [ ] **Step 9: Update `test_frame_context_includes_browser_url`**

Update mock return value:

```python
def test_frame_context_includes_browser_url(self, app_with_context_route, mock_store):
    """Endpoint includes browser_url when available."""
    mock_store.get_frame_context.return_value = {
        "frame_id": 1,
        "timestamp": "2026-03-26T10:00:00Z",
        "app_name": "Chrome",
        "window_name": "GitHub — MyRecall",
        "text": "Page content",
        "text_source": "accessibility",
        "urls": [],
        "browser_url": "https://example.com/page",
        "status": "completed",
    }
```

- [ ] **Step 10: Remove `test_frame_context_include_nodes_false_omits_nodes`**

Delete the test (lines 224-250). `include_nodes` param no longer exists.

- [ ] **Step 11: Remove `test_frame_context_include_nodes_false_passes_to_store`**

Delete the test (lines 251-269). `include_nodes` param no longer exists.

- [ ] **Step 12: Remove `test_frame_context_include_nodes_true_passes_to_store`**

Delete the test (lines 271-291). `include_nodes` param no longer exists.

- [ ] **Step 13: Add test for description inclusion when completed**

Add new test at end of `TestFrameContextAPI`:

```python
def test_frame_context_includes_description_when_completed(self, app_with_context_route, mock_store):
    """Endpoint includes description object when description_status=completed."""
    mock_store.get_frame_context.return_value = {
        "frame_id": 1,
        "timestamp": "2026-03-26T10:00:00Z",
        "app_name": "Claude Code",
        "window_name": "Claude Code Window",
        "text": "Test",
        "text_source": "accessibility",
        "urls": [],
        "browser_url": None,
        "status": "completed",
    }

    # Configure mock to return description_status=completed
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = {"description_status": "completed"}
    mock_store._connect.return_value = mock_conn
    mock_store.get_frame_description.return_value = {
        "narrative": "User is coding in Claude Code.",
        "summary": "Coding session",
        "tags": ["coding", "claude-code"],
    }

    with patch("openrecall.server.api_v1._get_frames_store", return_value=mock_store):
        client = app_with_context_route.test_client()
        response = client.get("/v1/frames/1/context")

        assert response.status_code == 200
        body = json.loads(response.data)
        assert body["description"] is not None
        assert body["description"]["narrative"] == "User is coding in Claude Code."
        assert body["description"]["summary"] == "Coding session"
        assert body["description"]["tags"] == ["coding", "claude-code"]
        # description_status should NOT be in response
        assert "description_status" not in body

def test_frame_context_omits_description_when_not_completed(self, app_with_context_route, mock_store):
    """Endpoint returns description=null when no description generated."""
    mock_store.get_frame_context.return_value = {
        "frame_id": 1,
        "timestamp": "2026-03-26T10:00:00Z",
        "app_name": "Safari",
        "window_name": "Safari Window",
        "text": "Test",
        "text_source": "accessibility",
        "urls": [],
        "browser_url": None,
        "status": "completed",
    }

    # Configure mock to return description_status != completed
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = {"description_status": "pending"}
    mock_store._connect.return_value = mock_conn
    mock_store.get_frame_description.return_value = None

    with patch("openrecall.server.api_v1._get_frames_store", return_value=mock_store):
        client = app_with_context_route.test_client()
        response = client.get("/v1/frames/1/context")

        assert response.status_code == 200
        body = json.loads(response.data)
        assert body["description"] is None
        assert "description_status" not in body
```

- [ ] **Step 14: Add test for field order**

```python
def test_frame_context_field_order(self, app_with_context_route, mock_store):
    """Fields appear in the correct order per spec."""
    mock_store.get_frame_context.return_value = {
        "frame_id": 1,
        "timestamp": "2026-03-26T10:00:00Z",
        "app_name": "App",
        "window_name": "Window",
        "text": "Text",
        "text_source": "accessibility",
        "urls": [],
        "browser_url": None,
        "status": "completed",
    }
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = {"description_status": "pending"}
    mock_store._connect.return_value = mock_conn
    mock_store.get_frame_description.return_value = None

    with patch("openrecall.server.api_v1._get_frames_store", return_value=mock_store):
        client = app_with_context_route.test_client()
        response = client.get("/v1/frames/1/context")

        assert response.status_code == 200
        body = json.loads(response.data)
        keys = list(body.keys())
        expected_order = [
            "frame_id", "timestamp", "app_name", "window_name",
            "description", "text", "text_source", "urls", "browser_url", "status"
        ]
        assert keys == expected_order, f"Field order mismatch: {keys}"
```

- [ ] **Step 15: Run API tests to verify all pass**

Run: `pytest tests/test_chat_mvp_frame_context_api.py -v`
Expected: PASS

- [ ] **Step 16: Commit**

```bash
git add tests/test_chat_mvp_frame_context_api.py
git commit -m "test: update context API tests — remove param tests, update field expectations"
```

---

## Task 5: Update documentation

**Files:**
- Modify: `docs/v3/chat/api-fields-reference.md`
- Modify: `docs/v3/chat/mvp.md`

- [ ] **Step 1: Update `api-fields-reference.md`**

In the `GET /v1/frames/{id}/context` section:

1. **Response Fields table:** Remove `nodes`, `nodes_truncated`, `description_status` rows. Add/update `description` row: "AI-generated frame description. Returns `null` when no description has been generated."
2. **Query Parameters table:** Remove all rows (no more query parameters).
3. **Nodes Array section:** Remove entirely. The `nodes[]` shape is no longer returned.
4. **Description Object section:** Update it — the description object still exists (`description` field in response). Update the field list to `narrative`, `summary`, `tags` only (remove `entities` and `intent` which were never in the implementation).
5. **Example Response JSON:** Remove `nodes`, `nodes_truncated`, `description_status` from examples. Move `description` before `text`. Update Description Object in examples to `{"narrative": "...", "summary": "...", "tags": []}` (no entities/intent).
6. **Known Gaps table:** Remove `nodes[].properties` row.

- [ ] **Step 2: Update `mvp.md`**

In the "Frame Context Contract" section:

1. Remove `nodes`, `nodes_truncated`, `nodes_truncated_count` from Return Shape bullet list
2. Remove "Truncation Policy" subsection entirely (lines ~1020-1050)
3. Remove query parameter table (or mark as removed)
4. Update the example GET URL to remove query params: `GET /v1/frames/{id}/context` (no query params)

- [ ] **Step 3: Run all tests to verify everything passes**

Run: `pytest tests/test_chat_mvp_frame_context.py tests/test_chat_mvp_frame_context_api.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit docs**

```bash
git add docs/v3/chat/api-fields-reference.md docs/v3/chat/mvp.md
git commit -m "docs: update frame context docs — remove nodes/truncation, simplify field reference"
```

---

## Verification Checklist

After all tasks complete, verify:

- [ ] `pytest tests/test_chat_mvp_frame_context.py tests/test_chat_mvp_frame_context_api.py -v` — ALL PASS
- [ ] `GET /v1/frames/{id}/context?max_text_length=100` returns 200 with truncated text (params ignored, text still truncated at 5000)
- [ ] `GET /v1/frames/{id}/context` response has no `nodes`, no `nodes_truncated`, no `description_status`
- [ ] `GET /v1/frames/{id}/context` field order matches spec: frame_id, timestamp, app_name, window_name, description, text, text_source, urls, browser_url, status
- [ ] `description` field is `null` when no description, populated object when description completed
- [ ] Text is truncated at 5000 chars with `...` suffix
