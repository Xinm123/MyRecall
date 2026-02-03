I will implement the **Phase 4 Hybrid Search Engine** in the `MRv2` environment.

### 1. Database Layer Refactoring
*   **Modify `openrecall/server/database/vector_store.py`**:
    *   Update `search()` to accept a `where` filter string (for time filtering).
    *   Update `search()` to return `List[Tuple[SemanticSnapshot, float]]` (Snapshot + Distance/Score) instead of just the model, so we can rank results.

### 2. Query Parser Implementation
*   **Create `openrecall/server/utils/query_parser.py`**:
    *   Implement `QueryParser` class to extract:
        *   **Time Filters**: "today", "yesterday" (using `datetime` logic).
        *   **Keywords**: Quoted text (e.g., `"error code"`) as mandatory terms.
    *   Define `ParsedQuery` output model.

### 3. Hybrid Search Engine Core
*   **Create `openrecall/server/search/engine.py`**:
    *   **Class**: `SearchEngine`.
    *   **Logic**:
        1.  **Parse**: Convert user query to `ParsedQuery`.
        2.  **Vector Search**: Query LanceDB with embedding + time filter.
        3.  **Keyword Search**: Query SQLite FTS5 with text.
        4.  **Hybrid Merge**:
            *   Convert Vector Distance to Similarity Score.
            *   Apply **Boost** if a record appears in Keyword Search results.
            *   Rank and return combined results.

### 4. API Integration
*   **Update `openrecall/server/app.py`**:
    *   Replace the current "Legacy Search" (in-memory cosine similarity) with the new `SearchEngine`.
    *   Update `/search` endpoint to return the rich `SemanticSnapshot` data.

### 5. Verification (MRv2)
*   **Create `tests/test_phase4_search.py`**:
    *   Standalone test using temporary databases.
    *   Verify **Time Filtering** (Today vs Yesterday).
    *   Verify **Hybrid Boosting** (Keyword match ranks higher).
*   **Execution**: Run the test using the `MRv2` environment (e.g., `/opt/homebrew/Caskroom/miniconda/base/envs/MRv2/bin/python3.11`).
