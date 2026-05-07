# BM25 Migration to LanceDB with jieba — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate BM25 search from SQLite FTS5 to LanceDB FTS with jieba tokenization. Consolidate vector and keyword search in a single LanceDB backend.

**Architecture:** Ingest pipeline adds jieba-tokenized text to LanceDB alongside vectors. Query path routes `mode=fts` and `mode=hybrid` through LanceDB FTS with BM25 scoring. SQLite FTS is preserved but excluded from all new data flows.

**Tech Stack:** Python, jieba, LanceDB 0.27, SQLite FTS5 (legacy, read-only)

**Fixes from review (v2):**
- API `mode=fts` routing now correctly goes through `HybridSearchEngine` (not direct `SearchEngine`)
- Metadata filters (start_time/end_time/app_name/window_name/focused/browser_url) preserved in LanceDB FTS path
- jieba warmup moved to module level (reliable on every startup)
- Embedding backfill step added for data loss recovery
- `full_text` stored in LanceDB to avoid JOIN in FTS-only hot path (documented trade-off)

---

## File Map

```
Created:
  openrecall/server/search/tokenizer.py         — jieba tokenization with warmup
  tests/unit/test_tokenizer.py                  — tokenizer unit tests

Modified:
  setup.py                                      — add jieba dependency
  openrecall/server/embedding/models.py         — + tokenized_text, full_text
  openrecall/server/database/embedding_store.py — schema, search_fts, _ensure_fts_index
  openrecall/server/embedding/service.py        — save_embedding signature
  openrecall/server/embedding/worker.py         — compute & pass tokenized_text
  openrecall/server/search/hybrid_engine.py     — LanceDB FTS paths + metadata filters + count_by_type delegation
  openrecall/server/search/engine.py            — mark deprecated
  openrecall/server/api_v1.py                   — _get_search_engine returns HybridSearchEngine
```

---

## CRITICAL: Data Loss Warning

**Task 4 (EmbeddingStore schema change) will delete ALL existing LanceDB embedding data.**
The `_init_table()` logic drops and recreates the table when the LanceDB schema changes. Adding `tokenized_text` and `full_text` fields triggers this.

**Before starting:** Back up LanceDB data if needed. After Task 4 completes, Task 9 will re-enqueue all frames for embedding backfill.

---

## Task 1: Add jieba dependency

**Files:**
- Modify: `setup.py`

- [ ] **Step 1: Add jieba to setup.py dependencies**

Run: `grep -n "jieba" setup.py`
Expected: no output (not yet present)

Edit `setup.py`, add `"jieba>=0.42"` to `install_requires`:

```python
install_requires = [
    # ... existing dependencies ...
    "jieba>=0.42",
]
```

- [ ] **Step 2: Verify jieba is installable**

Run: `pip install jieba>=0.42 && python3 -c "import jieba; print(jieba.__version__)"`
Expected: version number printed

- [ ] **Step 3: Commit**

```bash
git add setup.py
git commit -m "chore: add jieba dependency for BM25 tokenization"
```

---

## Task 2: Implement tokenizer module with warmup

**Files:**
- Create: `openrecall/server/search/tokenizer.py`
- Create: `tests/unit/test_tokenizer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_tokenizer.py`:

```python
"""Unit tests for jieba tokenizer."""
from openrecall.server.search.tokenizer import tokenize_text


def test_empty_string():
    assert tokenize_text("") == ""


def test_none_becomes_empty():
    assert tokenize_text(None) == ""


def test_whitespace_only():
    result = tokenize_text("   ")
    assert result == ""


def test_chinese_tokenization():
    result = tokenize_text("今天天气不错")
    assert result == "今天 天气 不错"


def test_english_preserved():
    result = tokenize_text("Python教程")
    assert result == "Python 教程"


def test_mixed_chinese_english():
    result = tokenize_text("我在学Python机器学习")
    tokens = result.split()
    assert "Python" in tokens
    assert "机器" in tokens
    assert "学习" in tokens


def test_numbers_preserved():
    result = tokenize_text("macOS Ventura 15.3")
    assert "macOS" in result
    assert "Ventura" in result
    assert "15.3" in result


def test_punctuation_handling():
    result = tokenize_text("你好，世界！")
    # jieba handles punctuation by including it as token
    assert len(result) > 0
```

Run: `pytest tests/unit/test_tokenizer.py -v`
Expected: FAIL — module `openrecall` not yet importable (since it was just created)

- [ ] **Step 2: Write implementation with module-level warmup**

Create `openrecall/server/search/tokenizer.py`:

```python
"""jieba-based text tokenizer for BM25 search."""
from __future__ import annotations

import jieba

# Warmup jieba dictionary at module load time (~100ms).
# This ensures no latency spike on the first tokenization call,
# regardless of whether LanceDB's FTS index already exists.
jieba.initialize()


def tokenize_text(text: str | None) -> str:
    """Tokenize text with jieba for BM25 indexing and querying.

    jieba automatically preserves English words as-is (e.g. "Python" is not split).
    Chinese text is segmented by meaning (e.g. "机器学习" → "机器 学习").

    Args:
        text: Input text, or None/empty string.

    Returns:
        Space-separated tokens.
    """
    if not text:
        return ""
    tokens = jieba.cut(text.strip(), cut_all=False)
    return " ".join(tokens)
```

> **Note:** `jieba.initialize()` runs once at module import time. This warmup is reliable — it fires on every server startup, not just when the LanceDB FTS index is created.

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/unit/test_tokenizer.py -v`
Expected: PASS (all 8 tests)

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_tokenizer.py openrecall/server/search/tokenizer.py
git commit -m "feat(search): add jieba tokenizer for Chinese BM25 support"
```

---

## Task 3: Extend LanceDB schema with tokenized_text and full_text

> **Prerequisite for Task 4.** Task 4 mirrors the same fields in `FrameEmbeddingSchema`. Execute Task 3 first.

**Files:**
- Modify: `openrecall/server/embedding/models.py`

- [ ] **Step 1: Read current models.py**

Run: `cat openrecall/server/embedding/models.py`

- [ ] **Step 2: Add new fields to FrameEmbedding model**

Edit `openrecall/server/embedding/models.py`, add to `FrameEmbedding` class:

```python
    tokenized_text: str = Field(
        default="",
        description="jieba-tokenized text for BM25 FTS",
    )
    full_text: str = Field(
        default="",
        description="Original full text for reference",
    )
```

Also update `to_storage_dict()` to include new fields:

```python
    def to_storage_dict(self) -> dict:
        return {
            "frame_id": self.frame_id,
            "embedding_vector": self.embedding_vector,
            "embedding_model": self.embedding_model,
            "timestamp": self.timestamp,
            "app_name": self.app_name,
            "window_name": self.window_name,
            "tokenized_text": self.tokenized_text,
            "full_text": self.full_text,
        }
```

- [ ] **Step 3: Run existing tests to verify no regression**

Run: `pytest tests/ -k "embedding" -v --ignore=tests/integration -x`
Expected: PASS (or pre-existing failures only)

- [ ] **Step 4: Commit**

```bash
git add openrecall/server/embedding/models.py
git commit -m "feat(embedding): add tokenized_text and full_text fields to FrameEmbedding"
```

---

## Task 4: Add search_fts and _ensure_fts_index to EmbeddingStore

> **WARNING: This task deletes all existing LanceDB embedding data.** The `_init_table()` schema-mismatch logic drops and recreates the table. Existing vectors will be lost; Task 9 re-generates them via backfill.

**Files:**
- Modify: `openrecall/server/database/embedding_store.py`

- [ ] **Step 1: Read current embedding_store.py**

Run: `cat openrecall/server/database/embedding_store.py`

- [ ] **Step 2: Update FrameEmbeddingSchema with new fields**

In `FrameEmbeddingSchema`, add two new fields:

```python
    tokenized_text: str = Field(default="", description="jieba-tokenized text for BM25")
    full_text: str = Field(default="", description="Original full text")
```

- [ ] **Step 3: Add _ensure_fts_index method**

After `_init_table()`, add:

```python
    def _ensure_fts_index(self) -> None:
        """Ensure FTS index exists on tokenized_text column."""
        table = self.db.open_table(self.table_name)
        try:
            table.create_fts_index("tokenized_text")
            logger.info("Created FTS index on tokenized_text")
        except Exception as e:
            if "already exists" in str(e):
                logger.debug("FTS index on tokenized_text already exists")
            else:
                raise
```

- [ ] **Step 4: Call _ensure_fts_index from __init__**

In `__init__`, after `self._init_table()`, add:

```python
        self._ensure_fts_index()
```

- [ ] **Step 5: Add search_fts method**

Add after `search_with_distance`:

```python
    def search_fts(
        self,
        query: str,
        limit: int = 20,
    ) -> List[dict]:
        """BM25 FTS search via LanceDB.

        Args:
            query: Pre-tokenized (jieba) query string
            limit: Maximum number of results

        Returns:
            List of matching records with frame_id and _score (BM25)
        """
        table = self.db.open_table(self.table_name)
        result = (
            table.search(query, query_type="fts")
            .limit(limit)
            .to_list()
        )
        return result
```

- [ ] **Step 6: Update FrameEmbedding constructors in existing read methods**

Update `search()`, `get_by_frame_id()`, and `search_with_distance()` to include the new fields when constructing `FrameEmbedding` objects. For example, in `search()` (around line 137) and `search_with_distance()` (around line 221):

```python
            emb = FrameEmbedding(
                frame_id=r["frame_id"],
                embedding_vector=r["embedding_vector"],
                embedding_model=r.get("embedding_model", "qwen3-vl-embedding"),
                timestamp=r["timestamp"],
                app_name=r.get("app_name", ""),
                window_name=r.get("window_name", ""),
                tokenized_text=r.get("tokenized_text", ""),
                full_text=r.get("full_text", ""),
            )
```

And in `get_by_frame_id()` (around line 166):

```python
        return FrameEmbedding(
            frame_id=r["frame_id"],
            embedding_vector=r["embedding_vector"],
            embedding_model=r.get("embedding_model", "qwen3-vl-embedding"),
            timestamp=r["timestamp"],
            app_name=r.get("app_name", ""),
            window_name=r.get("window_name", ""),
            tokenized_text=r.get("tokenized_text", ""),
            full_text=r.get("full_text", ""),
        )
```

- [ ] **Step 7: Verify LanceDB integration tests pass**

Run: `pytest tests/ -k "embedding" -v --ignore=tests/integration -x`
Expected: PASS

> **Note:** Since this task recreates the LanceDB table (schema change), existing embedding data is lost. Task 9 handles backfill.

- [ ] **Step 8: Commit**

```bash
git add openrecall/server/database/embedding_store.py
git commit -m "feat(lancedb): add FTS index and search_fts method"
```

---

## Task 5: Update EmbeddingService.save_embedding signature

**Files:**
- Modify: `openrecall/server/embedding/service.py`

- [ ] **Step 1: Read current save_embedding method**

Run: `grep -n "def save_embedding" openrecall/server/embedding/service.py`

- [ ] **Step 2: Update save_embedding signature**

Edit `save_embedding` in `openrecall/server/embedding/service.py` (around line 87), add two new parameters and set them on the embedding object:

```python
    def save_embedding(
        self,
        conn,
        frame_id: int,
        embedding: FrameEmbedding,
        timestamp: str,
        app_name: str = "",
        window_name: str = "",
        tokenized_text: str = "",
        full_text: str = "",
    ) -> None:
        embedding.frame_id = frame_id
        embedding.timestamp = timestamp
        embedding.app_name = app_name
        embedding.window_name = window_name
        embedding.tokenized_text = tokenized_text
        embedding.full_text = full_text
        self.embedding_store.save_embedding(embedding)
```

- [ ] **Step 3: Verify tests still pass**

Run: `pytest tests/ -k "embedding" -v --ignore=tests/integration -x`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add openrecall/server/embedding/service.py
git commit -m "feat(embedding): extend save_embedding with tokenized_text and full_text"
```

---

## Task 6: Update EmbeddingWorker to compute and pass tokenized_text

**Files:**
- Modify: `openrecall/server/embedding/worker.py`

- [ ] **Step 1: Read current _process_batch method**

Run: `grep -n "_process_batch\|save_embedding" openrecall/server/embedding/worker.py`

- [ ] **Step 2: Add tokenizer import at module top**

Edit the top of `openrecall/server/embedding/worker.py`, after existing imports:

```python
from openrecall.server.search.tokenizer import tokenize_text
```

- [ ] **Step 3: Update save_embedding call in _process_batch**

In `_process_batch` (around line 103), update the `save_embedding` call:

```python
        raw_text = frame.get("full_text") or ""
        tokenized = tokenize_text(raw_text)

        self.service.save_embedding(
            conn,
            frame_id,
            embedding,
            timestamp=frame.get("timestamp") or "",
            app_name=frame.get("app_name") or "",
            window_name=frame.get("window_name") or "",
            tokenized_text=tokenized,
            full_text=raw_text,
        )
```

- [ ] **Step 4: Verify worker tests pass**

Run: `pytest tests/ -k "worker" -v --ignore=tests/integration -x`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/embedding/worker.py
git commit -m "feat(worker): compute and persist jieba tokenized text"
```

---

## Task 7: Rewrite HybridSearchEngine with LanceDB FTS + metadata filters

**Files:**
- Modify: `openrecall/server/search/hybrid_engine.py`

- [ ] **Step 1: Remove `_fts_engine` from `__init__` and rewrite `_fts_only_search`**

Read current `HybridSearchEngine.__init__`:

```bash
grep -n "self._fts_engine\|self._embedding_store\|def __init__" openrecall/server/search/hybrid_engine.py
```

**Edit `__init__`** — remove the `SearchEngine` singleton since it will no longer be used:

```python
class HybridSearchEngine:
    def __init__(self):
        from openrecall.server.database.embedding_store import EmbeddingStore

        self._embedding_store = EmbeddingStore()
        # Note: self._fts_engine removed — FTS now goes through LanceDB
```

Then replace the entire `_fts_only_search` method body with:

```python
    def _fts_only_search(
        self, q: str, limit: int, offset: int, **kwargs
    ) -> Tuple[List[Dict[str, Any]], int]:
        """FTS-only search via LanceDB with jieba tokenizer.

        Metadata filters (start_time, end_time, app_name, window_name,
        focused, browser_url) are applied in the Python layer after
        LanceDB returns results, via FramesStore.get_frames_by_ids.
        """
        from openrecall.server.search.tokenizer import tokenize_text
        from openrecall.server.database.frames_store import FramesStore

        frames_store = FramesStore()

        # Browse mode (no query): return recent queryable frames
        if not q or q.isspace():
            return self._get_recent_embedded_frames(frames_store.db_path, limit, offset)

        # Tokenize query with jieba
        tokenized_q = tokenize_text(q)

        # Fetch ALL potential results from LanceDB FTS (no limit applied yet —
        # we need all to apply filters before pagination)
        lance_results = self._embedding_store.search_fts(tokenized_q, limit=1000)

        # Fetch full frame data from SQLite for metadata filtering
        frame_ids = [r["frame_id"] for r in lance_results]
        frame_data_map = frames_store.get_frames_by_ids(frame_ids)

        # Apply metadata filters in Python layer
        start_time = kwargs.get("start_time")
        end_time = kwargs.get("end_time")
        filter_app_name = kwargs.get("app_name")
        filter_window_name = kwargs.get("window_name")
        filter_focused = kwargs.get("focused")
        filter_browser_url = kwargs.get("browser_url")

        filtered_results = []
        for r in lance_results:
            frame = frame_data_map.get(r["frame_id"], {})
            if frame:
                # Apply time range filter
                if start_time and (frame.get("timestamp") or "") < start_time:
                    continue
                if end_time and (frame.get("timestamp") or "") > end_time:
                    continue
                # Apply app_name filter (case-insensitive substring)
                if filter_app_name:
                    frame_app = (frame.get("app_name") or "").lower()
                    if filter_app_name.lower() not in frame_app:
                        continue
                # Apply window_name filter (case-insensitive substring)
                if filter_window_name:
                    frame_window = (frame.get("window_name") or "").lower()
                    if filter_window_name.lower() not in frame_window:
                        continue
                # Apply focused filter
                if filter_focused is not None:
                    frame_focused = bool(frame.get("focused"))
                    if frame_focused != filter_focused:
                        continue
                # Apply browser_url filter (case-insensitive substring)
                if filter_browser_url:
                    frame_url = (frame.get("browser_url") or "").lower()
                    if filter_browser_url.lower() not in frame_url:
                        continue
                filtered_results.append(r)

        # Apply offset and limit
        total = len(filtered_results)
        paginated = filtered_results[offset:offset + limit]

        results = []
        for r in paginated:
            frame = frame_data_map.get(r["frame_id"], {})
            ts = frame.get("timestamp") if frame.get("timestamp") else (r.get("timestamp") or "")
            results.append({
                "frame_id": r["frame_id"],
                "score": r.get("_score"),
                "fts_score": r.get("_score"),
                "cosine_score": None,        # FTS-only has no vector score
                "vector_rank": None,         # FTS-only has no vector rank
                "timestamp": ts,
                "text": (r.get("full_text") or frame.get("full_text", ""))[:200],
                "text_source": frame.get("text_source", ""),
                "app_name": frame.get("app_name") or r.get("app_name", ""),
                "window_name": frame.get("window_name") or r.get("window_name", ""),
                "browser_url": frame.get("browser_url"),
                "focused": frame.get("focused"),
                "device_name": frame.get("device_name") or "monitor_0",
                "frame_url": f"/v1/frames/{r['frame_id']}",
                "embedding_status": frame.get("embedding_status", ""),
            })

        return results, total
```

> **Important:** If LanceDB returns an unexpected score column name (not `"_score"`), adjust `r.get("_score")` to match. Verify by inspecting `lance_results[0].keys()` after running.

- [ ] **Step 2: Update `_hybrid_search` to use the new `_fts_only_search`**

In `_hybrid_search` (find the FTS search line), replace:

Old:
```python
        fts_results, _ = self._fts_engine.search(q=q, limit=limit * 2, **kwargs)
```

New:
```python
        fts_results, _ = self._fts_only_search(q=q, limit=limit * 2, offset=0, **kwargs)
```

The `_fts_only_search` now calls LanceDB FTS with jieba, so `_hybrid_search` automatically benefits.

- [ ] **Step 3: Add temporary `count_by_type` delegation to HybridSearchEngine**

> Add: this is backward-compat for `/v1/search/counts` until Phase 3 cleanup.

Add this method to `HybridSearchEngine` (after `_hybrid_search` or near the end of the class):

```python
    def count_by_type(self, **kwargs):
        """Temporary backward-compat delegation to SearchEngine."""
        from openrecall.server.search.engine import SearchEngine
        return SearchEngine().count_by_type(**kwargs)
```

- [ ] **Step 4: Verify search tests pass**

Run: `pytest tests/ -k "search" -v --ignore=tests/integration -x`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/search/hybrid_engine.py
git commit -m "feat(search): route FTS through LanceDB with jieba tokenizer"
```

---

## Task 8: Mark SearchEngine as deprecated

**Files:**
- Modify: `openrecall/server/search/engine.py`

- [ ] **Step 1: Update SearchEngine class docstring**

Add `@deprecated` notice to the `SearchEngine` class docstring (around line 73):

```python
class SearchEngine:
    """Unified FTS5 search engine using frames_fts with full_text.

    .. deprecated::
        As of 2026-04-16, FTS search is handled by LanceDB FTS in
        HybridSearchEngine. This class is retained for backward
        compatibility and will be removed in a future release.

    After FTS unification:
    ...
```

- [ ] **Step 2: Commit**

```bash
git add openrecall/server/search/engine.py
git commit -m "docs(search): mark SearchEngine as deprecated"
```

---

## Task 9: Update API routing + Embedding backfill

**Files:**
- Modify: `openrecall/server/api_v1.py`
- Modify: `tests/test_search_api_optimized.py`

### Sub-task 9a: Update `_get_search_engine` to return HybridSearchEngine

- [ ] **Step 1: Find `_get_search_engine` in api_v1.py**

Run: `grep -n "def _get_search_engine" openrecall/server/api_v1.py`

- [ ] **Step 2: Replace SearchEngine with HybridSearchEngine in `_get_search_engine`**

Find the function around line 917:

```python
def _get_search_engine():
    """Lazily initialize the SearchEngine singleton."""
    global _search_engine
    if _search_engine is None:
        from openrecall.server.search.engine import SearchEngine

        _search_engine = SearchEngine()
    return _search_engine
```

Replace with:

```python
def _get_search_engine():
    """Lazily initialize the search engine singleton."""
    global _search_engine
    if _search_engine is None:
        from openrecall.server.search.hybrid_engine import HybridSearchEngine

        _search_engine = HybridSearchEngine()
    return _search_engine
```

> **Why this approach?** `mode=fts`, `mode=vector`, `mode=hybrid`, and `/v1/search/counts` all call `_get_search_engine()`. Updating the singleton avoids changing every call site and preserves ~76 existing test mocks that patch `_get_search_engine`.

- [ ] **Step 3: Verify api_v1 tests pass**

Run: `pytest tests/ -k "api" -v --ignore=tests/integration -x`
Expected: PASS

### Sub-task 9b: Trigger embedding backfill (recover lost LanceDB data)

- [ ] **Step 4: Trigger embedding backfill**

After the server starts with the new schema, trigger a backfill to regenerate all LanceDB embeddings:

```bash
curl -X POST "http://localhost:8083/v1/admin/embedding/backfill"
```

Or via Python:

```python
import requests
resp = requests.post("http://localhost:8083/v1/admin/embedding/backfill")
print(resp.json())
```

Expected: `{"enqueued": <N>}` where N is the number of frames without embeddings.

- [ ] **Step 5: Commit api_v1 change**

```bash
git add openrecall/server/api_v1.py
git commit -m "feat(api): _get_search_engine now returns HybridSearchEngine"
```

### Sub-task 9c: Update test name for clarity

- [ ] **Step 6: Rename `test_fts_mode_uses_fts_engine` for accuracy**

The test body still works (it patches `_get_search_engine`, which now returns `HybridSearchEngine`), but the name is misleading. Update around line 324:

Old:
```python
    def test_fts_mode_uses_fts_engine(self, app_with_search_route):
        """Test that mode=fts still uses the FTS engine (not hybrid)."""
```

New:
```python
    def test_fts_mode_uses_search_engine(self, app_with_search_route):
        """Test that mode=fts routes through the search engine singleton."""
```

Leave the test body unchanged — it correctly verifies that `mode=fts` calls `engine.search()` on the object returned by `_get_search_engine()`.

- [ ] **Step 7: Run updated test**

Run: `pytest tests/test_search_api_optimized.py::TestSearchAPIOptimized::test_fts_mode_uses_search_engine -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add tests/test_search_api_optimized.py
git commit -m "test(search): rename fts mode test for accuracy after routing change"
```

---

## Task 10: Integration verification

- [ ] **Step 1: Start server and run ingest pipeline**

Run: `./run_server.sh --mode local --debug`

In another terminal, run client to generate frames.

- [ ] **Step 2: Verify LanceDB has tokenized_text**

Run: Python snippet to check LanceDB:

```python
import lancedb
db = lancedb.connect("~/.myrecall/server/lancedb")
tbl = db.open_table("frame_embeddings")
print(tbl.schema)
# Should show tokenized_text and full_text fields
```

- [ ] **Step 3: Test mode=fts search with Chinese query**

```bash
curl "http://localhost:8083/v1/search?mode=fts&q=Python"
curl "http://localhost:8083/v1/search?mode=fts&q=机器学习"
```

- [ ] **Step 4: Test mode=fts with metadata filters**

```bash
curl "http://localhost:8083/v1/search?mode=fts&q=Python&app_name=Chrome"
curl "http://localhost:8083/v1/search?mode=fts&q=学习&start_time=2026-04-01"
```

- [ ] **Step 5: Test mode=hybrid search**

```bash
curl "http://localhost:8083/v1/search?q=Python教程"
```

- [ ] **Step 6: Run all tests**

```bash
pytest tests/ -v --ignore=tests/integration -x
```

---

## Rollup

When all tasks pass, commit everything:

```bash
git status
git log --oneline -10
```

Confirm all 10 task commits are present. The implementation is complete.

---

## Post-Implementation: Phase 3 Cleanup (future PR)

After verifying everything works:
- Delete SQLite FTS triggers (migration SQL)
- Delete `SearchEngine` class and `openrecall/server/search/engine.py`
- Update `count_by_type` endpoint to route through `HybridSearchEngine`
