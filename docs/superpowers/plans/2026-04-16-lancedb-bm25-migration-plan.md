# BM25 Migration to LanceDB with jieba — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate BM25 search from SQLite FTS5 to LanceDB FTS with jieba tokenization. Consolidate vector and keyword search in a single LanceDB backend.

**Architecture:** Ingest pipeline adds jieba-tokenized text to LanceDB alongside vectors. Query path routes `mode=fts` and `mode=hybrid` through LanceDB FTS with BM25 scoring. SQLite FTS is preserved but excluded from all new data flows.

**Tech Stack:** Python, jieba, LanceDB 0.27, SQLite FTS5 (legacy, read-only)

---

## File Map

```
Created:
  openrecall/server/search/tokenizer.py         — jieba tokenization
  tests/unit/test_tokenizer.py                  — tokenizer unit tests

Modified:
  pyproject.toml                                — add jieba dependency
  openrecall/server/embedding/models.py         — + tokenized_text, full_text
  openrecall/server/database/embedding_store.py — schema, search_fts, _ensure_fts_index
  openrecall/server/embedding/service.py        — save_embedding signature
  openrecall/server/embedding/worker.py         — compute & pass tokenized_text
  openrecall/server/search/hybrid_engine.py     — LanceDB FTS paths
  openrecall/server/search/engine.py            — mark deprecated
```

---

## Task 1: Add jieba dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add jieba to pyproject.toml dependencies**

Run: `grep -n "jieba" pyproject.toml`
Expected: no output (not yet present)

Edit `pyproject.toml`, add to `[project.dependencies]`:

```toml
jieba = ">=0.42"
```

- [ ] **Step 2: Verify jieba is installable**

Run: `uv pip install jieba>=0.42 && python3 -c "import jieba; print(jieba.__version__)"`
Expected: version number printed

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add jieba dependency for BM25 tokenization"
```

---

## Task 2: Implement tokenizer module

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
Expected: FAIL with "No module named 'openrecall'"

- [ ] **Step 2: Write minimal implementation**

Create `openrecall/server/search/tokenizer.py`:

```python
"""jieba-based text tokenizer for BM25 search."""
from __future__ import annotations

import jieba


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

**Files:**
- Modify: `openrecall/server/database/embedding_store.py`

- [ ] **Step 1: Read current embedding_store.py**

Note the `FrameEmbeddingSchema` class at the top and `save_embedding` method.

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

- [ ] **Step 6: Verify LanceDB integration tests pass**

Run: `pytest tests/ -k "embedding" -v --ignore=tests/integration -x`
Expected: PASS

- [ ] **Step 7: Commit**

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

Run: `grep -n "save_embedding\|from openrecall" openrecall/server/embedding/worker.py`

- [ ] **Step 2: Add tokenizer import and compute tokenized_text**

Edit the imports at the top of `_process_batch` method (line ~1, after existing imports):

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

## Task 7: Rewrite HybridSearchEngine to use LanceDB FTS

**Files:**
- Modify: `openrecall/server/search/hybrid_engine.py`

- [ ] **Step 1: Read current HybridSearchEngine class**

Run: `grep -n "def _fts_only_search\|def _hybrid_search\|self._fts_engine\|self._embedding_store" openrecall/server/search/hybrid_engine.py`

Note: `_fts_only_search` delegates to `self._fts_engine.search()`, which uses SQLite FTS. This is the key method to rewrite.

- [ ] **Step 2: Rewrite _fts_only_search**

Replace the entire `_fts_only_search` method body (lines 99-103) with:

```python
    def _fts_only_search(
        self, q: str, limit: int, offset: int, **kwargs
    ) -> Tuple[List[Dict[str, Any]], int]:
        """FTS-only search via LanceDB with jieba tokenizer."""
        from openrecall.server.search.tokenizer import tokenize_text
        from openrecall.server.database.frames_store import FramesStore

        frames_store = FramesStore()

        # Browse mode (no query): return recent queryable frames
        if not q or q.isspace():
            return self._get_recent_queryable_frames(frames_store, limit, offset)

        # Tokenize query with jieba
        tokenized_q = tokenize_text(q)

        # Search LanceDB FTS
        lance_results = self._embedding_store.search_fts(tokenized_q, limit=limit + offset)

        # Fetch full frame data from SQLite
        frame_ids = [r["frame_id"] for r in lance_results]
        frame_data_map = frames_store.get_frames_by_ids(frame_ids)

        results = []
        for r in lance_results[offset:offset + limit]:
            frame = frame_data_map.get(r["frame_id"], {})
            results.append({
                "frame_id": r["frame_id"],
                "score": r.get("_score"),
                "fts_score": r.get("_score"),
                "timestamp": frame.get("timestamp", r.get("timestamp", "")),
                "text": r.get("full_text", "")[:200] if r.get("full_text") else "",
                "text_source": frame.get("text_source", ""),
                "app_name": frame.get("app_name", r.get("app_name", "")),
                "window_name": frame.get("window_name", r.get("window_name", "")),
                "browser_url": frame.get("browser_url"),
                "focused": frame.get("focused"),
                "device_name": frame.get("device_name", "monitor_0"),
                "frame_url": f"/v1/frames/{r['frame_id']}",
                "embedding_status": frame.get("embedding_status", ""),
            })

        return results, len(lance_results)
```

- [ ] **Step 3: Update _hybrid_search to use new _fts_only_search**

In `_hybrid_search` (around line 231), replace the FTS search line:

Old:
```python
        fts_results, _ = self._fts_engine.search(q=q, limit=limit * 2, **kwargs)
```

New:
```python
        fts_results, _ = self._fts_only_search(q=q, limit=limit * 2, offset=0, **kwargs)
```

The `_fts_only_search` now calls LanceDB FTS with jieba, so `_hybrid_search` automatically benefits.

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

## Task 9: Integration verification

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

- [ ] **Step 3: Test mode=fts search**

```bash
curl "http://localhost:8083/v1/search?mode=fts&q=Python"
curl "http://localhost:8083/v1/search?mode=fts&q=机器学习"
```

- [ ] **Step 4: Test mode=hybrid search**

```bash
curl "http://localhost:8083/v1/search?q=Python教程"
```

- [ ] **Step 5: Run all tests**

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

Confirm all 8 task commits are present. The implementation is complete.
