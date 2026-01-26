
I will complete Phase 5 of the OpenRecall V2 refactor by consolidating database logic into `SQLStore` and `VectorStore`, removing legacy code, and verifying the system end-to-end.

**Environment Note**: I will ensure `conda activate MRv2` is used (or simulated via prefix) for all execution commands.

### 1. Update Configuration (`openrecall/shared/config.py`)
- **Add**: `LANCEDB_PATH`, `FTS_PATH`, `KEYWORD_STRATEGY` (default "local"), `EMBEDDING_MODEL` (default "qwen-text-v1").
- **Update**: Ensure `db_path` is preserved for the Task Queue (SQLite), while `lancedb_path` and `fts_path` handle the new search architecture.
- **Verify**: Check environment variable overrides.

### 2. Implement `SQLStore` (`openrecall/server/database/sql.py`)
- **Refactor**: Rename `FTSStore` to `SQLStore` (or extend it).
- **Consolidate**: Move task queue and metadata management from `legacy.py` to `SQLStore`.
- **Implement Methods**: Port necessary methods from `legacy.py` to `SQLStore` to support `worker.py` and `api.py`:
    - `create_db` (initialize tables)
    - `insert_pending_entry`
    - `get_pending_count`
    - `get_next_task`
    - `update_task_status` (replaces `mark_task_*`)
    - `get_recent_memories` / `get_all_entries` (for UI compatibility)
- **Schema**: Maintain the `entries` table for task status and lightweight metadata.

### 3. Refactor Codebase Dependencies
- **Update `openrecall/server/database/__init__.py`**: Export `VectorStore` and `SQLStore`.
- **Refactor `app.py`**: Initialize `SQLStore` and replace legacy calls.
- **Refactor `worker.py`**: Replace `db.*` calls with `SQLStore` methods.
- **Refactor `api.py`**: Replace legacy query/insert calls with `SQLStore`.
- **Cleanup**: Remove `openrecall/server/database/legacy.py`.

### 4. Optimize Dependencies (`setup.py`)
- Review and ensure `lancedb`, `pydantic`, `fastapi`, `python-multipart` are listed.

### 5. Verification (E2E Test)
- **Create**: `tests/test_phase5_e2e.py`
- **Scenario**: Ingestion -> Processing (Worker) -> Validation (DB check) -> Retrieval (Search).
