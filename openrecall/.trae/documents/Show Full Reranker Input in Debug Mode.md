I will modify `openrecall/server/search/engine.py` to output the full reranker input context for all candidates when in debug mode.

1.  **Modify `openrecall/server/search/engine.py`**:
    *   Locate the debug logging section in `_search_impl` before `self.reranker.compute_score` (around line 304).
    *   Replace the current truncated preview (`[:1000]`) with a loop that logs the **full** constructed context string for every candidate document being sent to the reranker.
    *   Add clear separators (e.g., `--- Doc X ---`) to distinguish between documents in the log output.

This will allow you to see exactly what text is being fed into the Reranker for every candidate, ensuring full transparency for debugging.