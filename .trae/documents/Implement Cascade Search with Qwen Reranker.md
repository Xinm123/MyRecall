I will implement the "Retrieve-then-Rerank" pipeline as requested, including the UI and debug enhancements.

### 1. Configuration (`openrecall/shared/config.py`)
I will add the following fields to the `Settings` class:
- `reranker_mode`: `api` (default) or `local`.
- `reranker_url`: `http://localhost:8080/rerank`.
- `reranker_model`: `Qwen/Qwen3-Reranker-0.6B`.

### 2. Service Implementation (`openrecall/server/services/reranker.py`)
I will create a new module `openrecall/server/services/reranker.py` implementing the Strategy Pattern:
- **`BaseReranker`**: Abstract base class.
- **`APIReranker`**: Uses `requests` to call the external API. Handles timeouts and returns 0.0 scores on failure.
- **`LocalReranker`**: Uses `transformers` to run the model locally. Implements lazy loading (model loads on first use).
- **`get_reranker()`**: Factory function to instantiate the correct reranker based on config.

### 3. Engine Update (`openrecall/server/search/engine.py`)
I will modify `engine.py` to:
- **Add Helper**: `construct_rerank_context(item: dict) -> str` with the specified "Inverted Pyramid" structure.
- **Update `SearchEngine`**:
    - Initialize `self.reranker` in `__init__`.
    - **Refactor `_search_impl`**:
        - Keep existing Vector + FTS retrieval and RRF fusion.
        - **New Stage 3**:
            - Slice to Top 30 candidates.
            - Construct context strings.
            - **Debug Log**: When `settings.debug` is True, log the full input text sent to the reranker.
            - Call `reranker.compute_score`.
            - Update scores and re-sort.
            - Return top results.
    - **Update `search_debug`**: Include `rerank_score` and `rerank_rank` in the returned dictionary for UI display.
    - Ensure fallback mechanism: if reranking fails, preserve original RRF order.

### 4. UI Update (`openrecall/server/templates/search.html`)
I will modify the search results template to display the Rerank score and rank:
- Add a "Rerank" row in the `similarity-info` section, displaying `#{rank} · {score}`.

**Note**: I will ensure any verification commands run using the `MRv2` conda environment.