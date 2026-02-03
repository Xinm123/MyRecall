🎉 OpenRecall V2 Refactor Completed Successfully!

I have completed the Phase 5 cleanup and optimization. The codebase has been refactored to remove legacy database logic and consolidate storage operations into SQLStore (Metadata + FTS) and VectorStore (LanceDB).

### 📝 Key Changes
- Configuration : Updated openrecall/shared/config.py with new paths ( ~/.openrecall/data/lancedb , ~/.openrecall/data/fts.db ), added KEYWORD_STRATEGY="local" , and set default EMBEDDING_MODEL="qwen-text-v1" .
- Database :
  - Renamed and expanded FTSStore to SQLStore in openrecall/server/database/sql.py . It now manages both the Task Queue (SQLite) and FTS Index.
  - Deleted openrecall/server/database/legacy.py .
  - Updated openrecall/server/database/__init__.py to export only VectorStore and SQLStore .
- Refactoring :
  - Updated app.py , worker.py , and api.py to use SQLStore instead of legacy database functions.
  - Fixed search/engine.py to use SQLStore .
  - Cleaned up main.py and server/__main__.py initialization logic.
- Dependencies : Added fastapi and python-multipart to setup.py .
### ✅ Verification (E2E Test)
I created and ran tests/test_phase5_e2e.py simulating the full lifecycle:

1. Ingestion : API accepted upload (Task ID: 1).
2. Processing : Worker successfully processed the task (Mocked AI/OCR).
3. Validation : Verified data integrity in SQLite (Status: COMPLETED), FTS, and Vector Store.
4. Retrieval : SearchEngine successfully returned the record for query "Safari".