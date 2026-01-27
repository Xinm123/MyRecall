# Add Input Length to Reranker Debug Log

## Implementation Plan
I will modify `openrecall/server/search/engine.py` to calculate and log the combined length of the query and the document context for each candidate in the reranking results.

### Steps:
1.  **Calculate Pair Length**: inside the loop that logs the Top Reranked Results (approx line 363), I will re-construct the context for the current candidate (`c['snapshot']`) to get its exact length.
2.  **Append to Log**: I will update the `logger.debug` statement to include `Pair_len={len(query) + len(doc_context)}` after `Cap_len`.

### Verification
-   I will verify the code changes by running `pytest tests/v2/test_search_rerank.py` to ensure no syntax errors or regressions.
-   (Optional) If you wish, I can create a new test case to assert this specific log format, but usually manual verification via the existing test suite is sufficient for debug logging changes.

### Expected Output
The log line will change from:
`... | OCR_len=1988 Cap_len=541 | ...`
to:
`... | OCR_len=1988 Cap_len=541 Pair_len=2544 | ...`
