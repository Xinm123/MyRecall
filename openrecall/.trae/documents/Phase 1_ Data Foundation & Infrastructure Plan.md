Refactor OpenRecall to V2 Phase 1: Data Foundation & Infrastructure.

## 1. Dependency Management
- **File**: `openrecall/setup.py`
- **Action**: Add `lancedb` to `install_requires`.
- **Note**: `pydantic` is present. `numpy` is kept.

## 2. Schema Definition
- **File**: `openrecall/server/schema.py`
- **Action**: Create new file.
- **Content**: Define Pydantic models:
    - `Context`: `app_name`, `window_title`, `timestamp`, `time_bucket`.
    - `Content`: `ocr_text`, `ocr_head`, `caption`, `keywords`, `scene_tag`, `action_tag`.
    - `SemanticSnapshot`: `id` (UUID), `image_path`, `context`, `content`, `embedding_vector`, `embedding_model`, `embedding_dim`.

## 3. Database Module Refactor (Backward Compatible)
- **Action**: Convert `openrecall/server/database.py` into a package `openrecall/server/database/`.
- **Steps**:
    1.  Create directory `openrecall/server/database/`.
    2.  Move existing `openrecall/server/database.py` to `openrecall/server/database/legacy.py`.
    3.  **CRITICAL**: Create `openrecall/server/database/__init__.py` and add `from .legacy import *`. This ensures existing imports like `from openrecall.server.database import create_db` continue to work without changes in the rest of the codebase.

## 4. LanceDB Implementation
- **File**: `openrecall/server/database/vector_store.py`
- **Action**: Create new file.
- **Content**:
    - Initialize LanceDB connection.
    - Implement `VectorStore` class.
    - `create_table()`: Use LanceDB's native Pydantic integration: `db.create_table(name, schema=SemanticSnapshot)`.
    - `add_snapshot()`: Insert `SemanticSnapshot` objects directly.
    - `search()`: ANN search implementation.

## 5. SQLite FTS5 Implementation
- **File**: `openrecall/server/database/sql.py`
- **Action**: Create new file.
- **Content**:
    - Setup SQLite connection for FTS.
    - Create virtual table `ocr_fts` using `fts5`.
    - Implement insert and search methods.

## 6. Verification
- **Environment**: Use `conda activate MyRecall`.
- **File**: `tests/test_phase1_infra.py`
- **Action**: Create standalone test script.
- **Steps**:
    1.  Initialize DBs.
    2.  Create mock `SemanticSnapshot`.
    3.  Insert and Verify (Vector Search & Keyword Search).
    4.  Cleanup.
