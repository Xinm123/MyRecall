# Implement Cascade Search with Qwen Reranker

## 1. Configuration Changes
**File:** `openrecall/shared/config.py`
- Add environment variables for Reranker configuration:
  - `OPENRECALL_RERANKER_MODE`: "api" (default) or "local"
  - `OPENRECALL_RERANKER_URL`: Default "http://localhost:8080/rerank"
  - `OPENRECALL_RERANKER_MODEL`: Default "Qwen/Qwen3-Reranker-0.6B"

## 2. New Reranker Service
**File:** `openrecall/server/services/reranker.py`
- Create `BaseReranker` abstract base class.
- Create `APIReranker` implementation using `requests`.
  - Handle timeouts and connection errors gracefully (fallback to original order).
- Create `LocalReranker` implementation using `transformers`.
  - Lazy loading of the model.
  - Device auto-detection (cuda, mps, cpu).
- Create `get_reranker()` factory function.

## 3. Search Engine Logic Update
**File:** `openrecall/server/search/engine.py`
- **Helper Function:** Implement `construct_rerank_context(item: dict) -> str` as specified (Metadata, Visual Context, OCR Content).
- **Search Flow Refactor:**
  - Increase initial retrieval limit to 100 (for both Vector and FTS).
  - Perform RRF Fusion.
  - Slice Top 30 candidates.
  - Construct context for candidates.
  - Call `reranker.compute_score()`.
  - Re-sort based on new scores.
  - Return Top 10-20.

## 4. Verification & Testing
**File:** `tests/v2/test_reranker.py`
- Test context construction logic.
- Test API Reranker fallback behavior.
- Test Search Engine integration (mocking the actual Reranker to avoid model loading during tests).
