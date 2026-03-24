# Search Content Type Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use @superpowers:subagent-driven-development (recommended) or @superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add content type filter (OCR/AX/All) with pill UI and lazy-loaded counts to the client web search page.

**Architecture:** Extend existing SearchEngine with a lightweight `count_by_type()` method that runs two COUNT queries. Add new API endpoint `/v1/search/counts`. Frontend adds inline pill filters that update `content_type` param, fetches counts after search completes.

**Tech Stack:** Python (Flask/SQLite), JavaScript (vanilla), Jinja2 templates

---

## File Structure

| File | Purpose |
|---|---|
| `openrecall/server/search/engine.py` | Add `count_by_type()` method to SearchEngine |
| `openrecall/server/api_v1.py` | Add `GET /v1/search/counts` endpoint |
| `openrecall/client/web/templates/search.html` | Add pill filters, type badges, counts fetch logic |

---

## Task 1: Add `count_by_type()` to SearchEngine

**Files:**
- Modify: `openrecall/server/search/engine.py:850+`
- Test: `tests/test_search_engine.py`

- [ ] **Step 1.1: Write the failing test**

```python
def test_count_by_type_returns_ocr_and_accessibility_counts(test_db):
    """Test count_by_type returns counts for both content types."""
    engine = SearchEngine(db_path=test_db)

    # Insert test data
    # One OCR frame
    # One accessibility frame
    # Search with matching query

    counts = engine.count_by_type(
        q="test",
        start_time=None,
        end_time=None,
        app_name=None,
        window_name=None,
        focused=None,
        min_length=None,
        max_length=None,
        browser_url=None,
    )

    assert "ocr" in counts
    assert "accessibility" in counts
    assert isinstance(counts["ocr"], int)
    assert isinstance(counts["accessibility"], int)
```

- [ ] **Step 1.2: Run test to verify it fails**

Run: `pytest tests/test_search_engine.py::test_count_by_type_returns_ocr_and_accessibility_counts -v`

Expected: FAIL with `AttributeError: 'SearchEngine' object has no attribute 'count_by_type'`

- [ ] **Step 1.3: Implement `count_by_type()` method**

Add to `openrecall/server/search/engine.py` after the `count()` method (around line 891):

```python
def count_by_type(
    self,
    q: str = "",
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    app_name: Optional[str] = None,
    window_name: Optional[str] = None,
    focused: Optional[bool] = None,
    min_length: Optional[int] = None,
    max_length: Optional[int] = None,
    browser_url: Optional[str] = None,
) -> dict[str, int]:
    """Count matching frames by content type without returning results.

    Args:
        Same as search() except limit/offset/content_type

    Returns:
        Dict with "ocr" and "accessibility" counts
    """
    params = SearchParams(
        q=q,
        start_time=start_time,
        end_time=end_time,
        app_name=app_name,
        window_name=window_name,
        focused=focused,
        min_length=min_length,
        max_length=max_length,
        browser_url=browser_url,
    )

    try:
        with self._connect() as conn:
            # Get OCR count
            ocr_sql, ocr_params = self._build_ocr_query(params, is_count=True)
            ocr_row = conn.execute(ocr_sql, ocr_params).fetchone()
            ocr_count = ocr_row["total"] if ocr_row else 0

            # Get accessibility count
            ax_sql, ax_params = self._build_accessibility_query(params, is_count=True)
            ax_row = conn.execute(ax_sql, ax_params).fetchone()
            ax_count = ax_row["total"] if ax_row else 0

            return {"ocr": ocr_count, "accessibility": ax_count}
    except sqlite3.Error as e:
        logger.error("Count by type failed: %s", e)
        return {"ocr": 0, "accessibility": 0}
```

- [ ] **Step 1.4: Run test to verify it passes**

Run: `pytest tests/test_search_engine.py::test_count_by_type_returns_ocr_and_accessibility_counts -v`

Expected: PASS

- [ ] **Step 1.5: Write edge case test**

```python
def test_count_by_type_returns_zeros_on_empty_database(test_db):
    """Test count_by_type returns zeros for empty database."""
    engine = SearchEngine(db_path=test_db)

    counts = engine.count_by_type(q="nonexistent")

    assert counts["ocr"] == 0
    assert counts["accessibility"] == 0
```

- [ ] **Step 1.6: Run edge case test**

Run: `pytest tests/test_search_engine.py::test_count_by_type_returns_zeros_on_empty_database -v`

Expected: PASS

- [ ] **Step 1.7: Commit**

```bash
git add openrecall/server/search/engine.py tests/test_search_engine.py
git commit -m "feat(search): add count_by_type method to SearchEngine

Adds count_by_type() to return OCR and accessibility frame counts
without fetching result data. Returns {ocr: N, accessibility: M}
for any given search filters."
```

---

## Task 2: Add API Endpoint `GET /v1/search/counts`

**Files:**
- Modify: `openrecall/server/api_v1.py:850+`
- Test: `tests/test_search_api.py`

- [ ] **Step 2.1: Write the failing test**

```python
def test_search_counts_endpoint_returns_type_counts(client):
    """Test /v1/search/counts returns ocr and accessibility counts."""
    response = client.get('/v1/search/counts?q=test')

    assert response.status_code == 200
    data = response.get_json()
    assert "counts" in data
    assert "ocr" in data["counts"]
    assert "accessibility" in data["counts"]
    assert isinstance(data["counts"]["ocr"], int)
    assert isinstance(data["counts"]["accessibility"], int)
```

- [ ] **Step 2.2: Run test to verify it fails**

Run: `pytest tests/test_search_api.py::test_search_counts_endpoint_returns_type_counts -v`

Expected: FAIL with 404 Not Found (route doesn't exist)

- [ ] **Step 2.3: Implement the endpoint**

Add to `openrecall/server/api_v1.py` after the `search()` endpoint (around line 1015, after the search endpoint returns):

```python

# ---------------------------------------------------------------------------
# GET /v1/search/counts
# ---------------------------------------------------------------------------

@v1_bp.route("/search/counts", methods=["GET"])
def search_counts():
    """Return per-type result counts without frame data.

    Query Parameters:
        q: Text query
        start_time: ISO8601 UTC start timestamp
        end_time: ISO8601 UTC end timestamp
        app_name: Filter by app name
        window_name: Filter by window name
        browser_url: Filter by browser URL
        focused: Filter by focused state
        min_length: Minimum text length
        max_length: Maximum text length

    Returns:
        {"counts": {"ocr": 142, "accessibility": 23}}
    """
    # Parse query parameters (same as search endpoint)
    q = request.args.get("q", "").strip()

    # Parse time range
    start_time = request.args.get("start_time")
    if start_time:
        start_time = start_time.strip() or None

    end_time = request.args.get("end_time")
    if end_time:
        end_time = end_time.strip() or None

    # Parse metadata filters
    app_name = request.args.get("app_name")
    if app_name:
        app_name = app_name.strip() or None

    window_name = request.args.get("window_name")
    if window_name:
        window_name = window_name.strip() or None

    browser_url = request.args.get("browser_url")
    if browser_url:
        browser_url = browser_url.strip() or None

    # Parse focused
    focused_str = request.args.get("focused")
    focused = None
    if focused_str:
        focused_lower = focused_str.strip().lower()
        if focused_lower in ("true", "1", "yes"):
            focused = True
        elif focused_lower in ("false", "0", "no"):
            focused = False

    # Parse text length
    min_length = None
    max_length = None
    try:
        min_length = int(request.args.get("min_length", 0)) or None
    except (ValueError, TypeError):
        pass
    try:
        max_length = int(request.args.get("max_length", 0)) or None
    except (ValueError, TypeError):
        pass

    # Execute counts
    engine = _get_search_engine()
    counts = engine.count_by_type(
        q=q,
        start_time=start_time,
        end_time=end_time,
        app_name=app_name,
        window_name=window_name,
        browser_url=browser_url,
        focused=focused,
        min_length=min_length,
        max_length=max_length,
    )

    return jsonify({"counts": counts})
```

- [ ] **Step 2.4: Run test to verify it passes**

Run: `pytest tests/test_search_api.py::test_search_counts_endpoint_returns_type_counts -v`

Expected: PASS

- [ ] **Step 2.5: Write edge case test**

```python
def test_search_counts_endpoint_handles_invalid_params(client):
    """Test /v1/search/counts handles invalid params gracefully."""
    response = client.get('/v1/search/counts?min_length=invalid')

    assert response.status_code == 200
    data = response.get_json()
    assert "counts" in data
    assert "ocr" in data["counts"]
    assert "accessibility" in data["counts"]
```

- [ ] **Step 2.6: Run edge case test**

Run: `pytest tests/test_search_api.py::test_search_counts_endpoint_handles_invalid_params -v`

Expected: PASS

- [ ] **Step 2.7: Commit**

```bash
git add openrecall/server/api_v1.py tests/test_search_api.py
git commit -m "feat(api): add GET /v1/search/counts endpoint

New endpoint returns per-type frame counts for any search query.
Returns {counts: {ocr: N, accessibility: M}}. Same filters as
/v1/search but without pagination."
```

---

## Task 3: Add Pill Filter UI to Search Template

**Files:**
- Modify: `openrecall/client/web/templates/search.html`

### 3.1: Add CSS Styles

- [ ] **Step 3.1.1: Add pill filter styles**

Add to `<style>` section (around line 100, before spinner animation):

```css
  /* Content type pill filters */
  .content-type-pills {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .pill {
    padding: 6px 14px;
    border: 1px solid var(--border-color);
    border-radius: 16px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    background: var(--bg-body);
    color: var(--text-secondary);
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .pill:hover {
    border-color: var(--accent-color);
    color: var(--accent-color);
  }

  .pill.active {
    background: var(--accent-color);
    color: white;
    border-color: var(--accent-color);
  }

  .pill .count {
    font-size: 11px;
    font-weight: 400;
    opacity: 0.7;
    min-width: 16px;
    text-align: center;
  }

  /* Type badge on result cards */
  .type-badge {
    font-size: 10px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 10px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .type-badge.type-ocr {
    background: rgba(0, 122, 255, 0.1);
    color: #007AFF;
  }

  .type-badge.type-ax,
  .type-badge.type-accessibility {
    background: rgba(175, 82, 222, 0.1);
    color: #AF52DE;
  }
```

- [ ] **Step 3.1.2: Commit**

```bash
git add openrecall/client/web/templates/search.html
git commit -m "feat(search): add pill filter and type badge CSS styles

Add content-type-pills container styles with pill buttons.
Add type-badge styles for OCR (blue) and AX (purple) badges."
```

### 3.2: Add Pill Filter HTML

- [ ] **Step 3.2.1: Add pill filter HTML**

Add after the search form (around line 441, after `</form>`), before results grid:

```html

<div class="content-type-pills">
  <button type="button" class="pill active" data-type="all">All</button>
  <button type="button" class="pill" data-type="ocr">OCR <span class="count">—</span></button>
  <button type="button" class="pill" data-type="accessibility">AX <span class="count">—</span></button>
</div>
```

- [ ] **Step 3.2.2: Commit**

```bash
git add openrecall/client/web/templates/search.html
git commit -m "feat(search): add content type pill filter HTML

Add three pill buttons: All (default active), OCR, AX with count spans."
```

### 3.3: Add JavaScript State and Event Handlers

- [ ] **Step 3.3.1: Add selectedContentType state**

Add to JavaScript state section (around line 474, after `let currentPagination`):

```javascript
  // Content type filter state
  let selectedContentType = 'all';
```

- [ ] **Step 3.3.2: Add pill elements and event handlers**

Add after pill state declaration (around line 476):

```javascript
  // Content type pills
  const contentTypePills = document.querySelectorAll('.content-type-pills .pill');
  const ocrCountSpan = document.querySelector('.pill[data-type="ocr"] .count');
  const axCountSpan = document.querySelector('.pill[data-type="accessibility"] .count');

  // Initialize content type from URL
  function initContentTypeFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const urlContentType = params.get('content_type');
    if (urlContentType && ['ocr', 'accessibility', 'all'].includes(urlContentType)) {
      selectedContentType = urlContentType;
      updatePillActiveState();
    }
  }

  // Update pill active state
  function updatePillActiveState() {
    contentTypePills.forEach(pill => {
      const type = pill.dataset.type;
      if (type === selectedContentType) {
        pill.classList.add('active');
      } else {
        pill.classList.remove('active');
      }
    });
  }

  // Handle pill click
  contentTypePills.forEach(pill => {
    pill.addEventListener('click', () => {
      const newType = pill.dataset.type;
      if (newType !== selectedContentType) {
        selectedContentType = newType;
        updatePillActiveState();
        performSearch(0);
      }
    });
  });
```

- [ ] **Step 3.3.3: Update buildQueryString to include content_type**

Modify `buildQueryString()` function (around line 553):

```javascript
  // Build query string from form
  function buildQueryString(offset = 0) {
    const params = new URLSearchParams();
    const q = document.getElementById('q').value.trim();
    const startTime = document.getElementById('start_time').value;
    const endTime = document.getElementById('end_time').value;
    const appName = document.getElementById('app_name').value.trim();
    const windowName = document.getElementById('window_name').value.trim();
    const focused = document.getElementById('focused').value;
    const minLength = document.getElementById('min_length').value;
    const maxLength = document.getElementById('max_length').value;

    if (q) params.set('q', q);
    if (startTime) params.set('start_time', startTime + ':00');
    if (endTime) params.set('end_time', endTime + ':00');
    if (appName) params.set('app_name', appName);
    if (windowName) params.set('window_name', windowName);
    if (focused) params.set('focused', focused);
    if (minLength) params.set('min_length', minLength);
    if (maxLength) params.set('max_length', maxLength);

    // Add content type filter (default 'all' is omitted)
    if (selectedContentType !== 'all') {
      params.set('content_type', selectedContentType);
    }

    params.set('limit', '20');
    params.set('offset', offset.toString());

    return params.toString();
  }
```

- [ ] **Step 3.3.4: Add fetchCounts function**

Add after `buildQueryString()` function (around line 580):

```javascript
  // Fetch type counts for current filters
  async function fetchCounts() {
    const params = new URLSearchParams();
    const q = document.getElementById('q').value.trim();
    const startTime = document.getElementById('start_time').value;
    const endTime = document.getElementById('end_time').value;
    const appName = document.getElementById('app_name').value.trim();
    const windowName = document.getElementById('window_name').value.trim();
    const focused = document.getElementById('focused').value;
    const minLength = document.getElementById('min_length').value;
    const maxLength = document.getElementById('max_length').value;

    if (q) params.set('q', q);
    if (startTime) params.set('start_time', startTime + ':00');
    if (endTime) params.set('end_time', endTime + ':00');
    if (appName) params.set('app_name', appName);
    if (windowName) params.set('window_name', windowName);
    if (focused) params.set('focused', focused);
    if (minLength) params.set('min_length', minLength);
    if (maxLength) params.set('max_length', maxLength);

    const url = `${EDGE_BASE_URL}/v1/search/counts?${params.toString()}`;

    try {
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Counts fetch failed: ${response.status}`);
      }
      const data = await response.json();

      // Update count spans
      if (ocrCountSpan) {
        ocrCountSpan.textContent = data.counts.ocr;
      }
      if (axCountSpan) {
        axCountSpan.textContent = data.counts.accessibility;
      }
    } catch (error) {
      console.error('Counts fetch error:', error);
      // Silently leave as '—' on error
      if (ocrCountSpan) ocrCountSpan.textContent = '—';
      if (axCountSpan) axCountSpan.textContent = '—';
    }
  }
```

- [ ] **Step 3.3.5: Update performSearch to call fetchCounts**

Modify `performSearch()` function (around line 691), add `fetchCounts()` call after successful search:

```javascript
  // Perform search
  async function performSearch(offset = 0) {
    const queryString = buildQueryString(offset);
    const url = `${EDGE_BASE_URL}/v1/search?${queryString}`;

    // Update URL without reloading
    const newUrl = `${window.location.pathname}?${queryString}`;
    window.history.replaceState({}, '', newUrl);

    const searchBtn = searchForm.querySelector('.btn-search');
    searchBtn.disabled = true;
    searchBtn.textContent = 'Searching...';

    try {
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Search failed: ${response.status}`);
      }
      const result = await response.json();
      renderResults(result.data, result.pagination);

      // Fetch counts after successful search
      fetchCounts();
    } catch (error) {
      console.error('Search error:', error);
      resultsGrid.innerHTML = `
        <div class="empty-state">
          Error performing search. Please try again.
        </div>
      `;
      paginationDiv.style.display = 'none';
    } finally {
      searchBtn.disabled = false;
      searchBtn.textContent = 'Search';
    }
  }
```

- [ ] **Step 3.3.6: Update renderResults to add type badges**

Modify card footer in `renderResults()` (around line 658), add type badge:

```javascript
          <div class="card-footer">
            <div class="rank-info">
              <span class="rank-label">Rank</span>
              <span class="rank-value">${content.fts_rank !== null && content.fts_rank !== undefined ? Number(content.fts_rank).toFixed(4) : '—'}</span>
            </div>
            <span class="type-badge type-${item.type.toLowerCase()}">${item.type === 'Accessibility' ? 'AX' : item.type}</span>
            <div class="result-position">#${idx + 1} / ${pagination.total}</div>
          </div>
```

- [ ] **Step 3.3.7: Add initContentTypeFromUrl call to page load**

Add before the existing page load check (around line 746), before `if (window.location.search)`:

```javascript
  // Initialize content type from URL
  initContentTypeFromUrl();
```

- [ ] **Step 3.3.8: Commit**

```bash
git add openrecall/client/web/templates/search.html
git commit -m "feat(search): add content type filter JavaScript

- Add selectedContentType state with URL sync
- Add pill click handlers to update filter
- Add fetchCounts() to lazy-load type counts
- Update renderResults() to show type badges
- Initialize content type from URL on page load"
```

---

## Task 4: Manual Testing

**Files:**
- All modified files

- [ ] **Step 4.1: Start the server and verify endpoint**

```bash
# Terminal 1: Start server
./run_server.sh --debug

# Terminal 2: Test endpoint
curl "http://localhost:8883/v1/search/counts?q=test"
```

Expected: `{"counts":{"ocr":0,"accessibility":0}}` (or actual counts)

- [ ] **Step 4.2: Verify search page loads with pills**

Open browser: http://localhost:8083/search

Expected:
- Three pills visible: "All" (active), "OCR —", "AX —"
- "All" pill has accent background

- [ ] **Step 4.3: Test OCR filter**

1. Click "OCR" pill
2. Verify pill becomes active (accent background)
3. "All" pill becomes inactive
4. Search executes
5. URL updates with `content_type=ocr`

- [ ] **Step 4.4: Test AX filter**

1. Click "AX" pill
2. Verify URL updates with `content_type=accessibility`
3. Results update

- [ ] **Step 4.5: Test type badges on cards**

Verify each result card shows:
- "OCR" badge for OCR frames
- "AX" badge for accessibility frames

- [ ] **Step 4.6: Test counts appear after search**

1. Perform a search
2. Wait briefly
3. Verify OCR and AX pills show numbers (not "—")

- [ ] **Step 4.7: Test URL sharing**

1. Filter to "OCR" and search
2. Copy URL with `content_type=ocr`
3. Open in new tab
4. Verify "OCR" pill is active on page load

- [ ] **Step 4.8: Test pagination with filters**

1. Search with OCR filter
2. Click Next page
3. Verify filter persists (OCR pill still active, URL still has content_type)

- [ ] **Step 4.9: Commit**

```bash
git add -A
git commit -m "test: verify content type filter feature works end-to-end

Manual testing confirms:
- /v1/search/counts endpoint returns correct counts
- Pill filters switch correctly
- Type badges render on cards
- URL sync works for sharing
- Pagination preserves filter state"
```

---

## Summary

This plan implements:

1. **Backend:** `SearchEngine.count_by_type()` method + `/v1/search/counts` API endpoint
2. **Frontend:** Three pill filters (All/OCR/AX) with lazy-loaded counts
3. **UI:** Type badges on result cards (OCR/AX)
4. **UX:** URL sync for shareable filtered searches

All changes follow existing patterns in the codebase and use the same query parameter parsing as the existing search endpoint.