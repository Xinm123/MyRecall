# OpenRecall V2 Refactor - Phase 1: Data Foundation & Infrastructure

You are an expert Python Systems Engineer. We are beginning the refactoring of OpenRecall to V2.
The goal of V2 is a **"Caption-First" Architecture**, meaning we rely entirely on Text Embeddings (OCR + VLM Captions) and strictly **avoid Image Embeddings**.

**Environment**:
- OS: macOS (Local Development)
- Architecture: Client and Server run locally.
- Python: 3.10+

---

## 🎯 Objective: Phase 1 (Data Foundation)
Establish the storage layer using **LanceDB** (for vectors) and **SQLite FTS5** (for keyword search), and define the strict **Pydantic Schemas**.

---

## 📝 Task List

### 1. Dependency Management
- Update `requirements.txt` or `pyproject.toml`.
- Add: `lancedb`, `pydantic`.
- Mark `numpy` (if used only for old storage) as deprecated.

### 2. Schema Definition (Crucial)
Create `openrecall/server/schema.py`. Define the following Pydantic models to support the "Caption-First" logic:

1.  **`Context`**:
    - `app_name` (str)
    - `window_title` (str)
    - `timestamp` (float)
    - `time_bucket` (str) - e.g., "2024-01-24-10"

2.  **`Content`**:
    - `ocr_text` (str) - Full text for FTS.
    - `ocr_head` (str) - First 300 chars for embedding context.
    - `caption` (str) - Natural language description.
    - `keywords` (List[str]) - Extracted entities.
    - `scene_tag` (str) - e.g., "coding".
    - `action_tag` (str) - e.g., "debugging".

3.  **`SemanticSnapshot`** (The main entity):
    - `id` (str) - UUID.
    - `image_path` (str) - Local file path.
    - `context` (Context)
    - `content` (Content)
    - `embedding_vector` (Optional[List[float]]) - The fusion text embedding.
    - `embedding_model` (str) - Default to "qwen-text-v1".
    - `embedding_dim` (int) - Default to 1024.

### 3. LanceDB Implementation
Create `openrecall/server/database/vector_store.py`:
- Initialize a LanceDB connection locally (e.g., inside `./data/lancedb`).
- Implement a class `VectorStore`.
- Method `create_table()`: Define the table schema based on `SemanticSnapshot`. Ensure the vector column handles 1024 dimensions.
- Method `add_snapshot(snapshot: SemanticSnapshot)`: Flatten the Pydantic object if necessary to fit LanceDB's structure.
- Method `search(query_vec: List[float], limit: int)`: Basic ANN search.

### 4. SQLite FTS5 Implementation
Modify/Update `openrecall/server/database/sql.py`:
- Ensure the connection enables extension loading if needed (usually standard in Python's sqlite3 on Mac).
- Create a virtual table `ocr_fts` using `fts5`.
- Columns: `snapshot_id` (UNINDEXED), `ocr_text`, `caption`, `keywords`.
- This is purely for keyword-based inverted index search.

---

## ✅ Verification Plan (The Test Script)

Create a standalone test script `tests/test_phase1_infra.py` to verify the infrastructure on my Mac without running the full server.

**The script must:**
1.  **Initialize**: Setup temporary LanceDB and SQLite databases.
2.  **Mock Data**: Create a dummy `SemanticSnapshot` object:
    - App: "VSCode"
    - Caption: "User is writing Python code"
    - OCR: "def hello_world(): print('hi')"
    - Vector: A random list of 1024 floats.
3.  **Insert**: Save this snapshot to both LanceDB and SQLite FTS.
4.  **Query Verification**:
    - **Vector Search**: Query LanceDB with the same random vector to see if it returns the record.
    - **Keyword Search**: Query SQLite FTS for "hello_world" to see if it hits.
5.  **Cleanup**: Clean up temporary DB files.

---

## 🚀 Execution Instructions

1.  Analyze the existing codebase structure.
2.  Implement the dependencies and Schema first.
3.  Implement the Database wrappers.
4.  Write and **run** the `test_phase1_infra.py` script.
5.  Output the full content of the test script and its execution result (simulated or real).


# Refactor OpenRecall to V2 - Phase 2: High-Performance Ingestion Pipeline

**Context**:
We have completed Phase 1 (Infrastructure). The database layer is ready.
Now we must refactor the **Ingestion Pipeline** (Client Capture -> Server Upload).
The current implementation serializes images to JSON arrays, which is inefficient. We will switch to standard **Binary Streaming (Multipart)**.

**Environment**:
- Local macOS (Client and Server on same machine).
- Framework: FastAPI (Server), Requests (Client).

---

## 🎯 Objective
Refactor `uploader.py` (Client) and `api.py` (Server) to use `multipart/form-data`.
The image should be streamed directly to the disk on the server side to minimize RAM usage.

---

## 📝 Task List

### 1. Client-Side Refactoring
- **File**: `openrecall/client/uploader.py`
- **Current Logic**: Converts MSSIM-checked NumPy array -> List -> JSON Payload.
- **New Logic**:
    1.  Keep the MSSIM deduplication logic (it works well).
    2.  Once a frame is selected for upload:
        - Convert the NumPy array (image) to **PNG bytes** in memory (use `io.BytesIO` and `PIL` or `cv2.imencode`).
        - Prepare metadata (`timestamp`, `app_name`, `window_title`) as a JSON string.
    3.  **Action**: Update the `requests.post` call to use `multipart/form-data`:
        - `files`: The PNG byte stream.
        - `data`: The metadata JSON string (key: `metadata`).
- **Constraint**: Ensure the upload is still synchronous or handled in a way that doesn't block capture (maintain existing threading model if present).

### 2. Server-Side Refactoring
- **File**: `openrecall/server/api.py`
- **Current Logic**: Receives JSON payload -> Parses huge array -> Reconstructs Image -> Saves.
- **New Logic**:
    1.  Update the `/api/upload` endpoint signature to accept:
        - `file`: `UploadFile` (FastAPI).
        - `metadata`: `str` (Form field).
    2.  **Streaming Write (Critical)**:
        - Do NOT read the entire file into RAM (`await file.read()`).
        - Generate a unique filename (using the timestamp from metadata).
        - Use `shutil.copyfileobj` or standard file I/O to stream the `file.file` directly to `settings.screenshots_path`.
    3.  **Metadata Handling**:
        - Parse the `metadata` string back to a dictionary.
    4.  **Database Entry**:
        - Call the legacy database function (or new `sql.py`) to insert the record.
        - Status: `PENDING`.
        - Fields: `filename`, `timestamp`, `app`, `window`.
        - **Note**: Return `202 Accepted` immediately.

### 3. Cleanup Legacy Code
- **Action**: Check if there are any utility functions used solely for "NumPy Array to JSON" conversion (e.g., in `openrecall/shared/utils.py`) and mark them as deprecated or remove them if safe.

---

## ✅ Verification Plan (Integration Test)

Create a standalone integration test script `tests/test_phase2_ingestion.py`.
**Do not use the real client recorder.** We want to test the API contract.

**Script Requirements**:
1.  **Setup**:
    - Use `fastapi.testclient.TestClient` to wrap the Server App.
    - Create a dummy 100x100 random RGB image (using PIL or numpy).
    - Convert it to PNG bytes in a `BytesIO` buffer.
2.  **Execution**:
    - Mock metadata: `{"app_name": "TestApp", "window_title": "TestWindow", "timestamp": 123456.789}`.
    - Send POST request to `/api/upload` with `files={'file': ...}` and `data={'metadata': ...}`.
3.  **Assertions**:
    - **Response**: Assert status code is `202`.
    - **Disk**: Assert the file was actually created in the `screenshots` directory (check `settings.screenshots_path`).
    - **Database**: Check SQLite (via `legacy.py` or `sql.py`) to see if a `PENDING` record exists with the correct metadata.
4.  **Cleanup**: Remove the test image and DB entry after test.

---

## 🚀 Execution Instructions

1.  Modify `openrecall/client/uploader.py` first.
2.  Modify `openrecall/server/api.py` next.
3.  Create and run `tests/test_phase2_ingestion.py`.
4.  If the test passes, print "**Phase 2 Ingestion Pipeline Refactor Complete**".


这是 **Phase 3: The Processing Brain (智能处理核心)** 的完整提示词。

这一阶段是重构中最复杂的环节，涉及将原始图像转化为结构化的语义数据。Prompt 重点强调了 **“Caption-First” (文本优先)** 的处理逻辑和 **“Structured Fusion” (结构化融合)** 的文本构建策略。

请将以下 Prompt 复制给 Code Agent。

---

### 📋 Copy to Code Agent

```markdown
# Refactor OpenRecall to V2 - Phase 3: The Processing Brain (AI Pipeline)

**Context**:
We have the Infrastructure (Phase 1) and Ingestion Pipeline (Phase 2).
Now we build the core processing logic.
**Architecture Constraint**: We are using a **"Caption-First" approach**. We do NOT use Image Embeddings. We rely on OCR + VLM Captions -> Text Fusion -> Text Embedding.

**Environment**:
- Local macOS.
- Existing files: `server/schema.py`, `server/database/*`.

---

## 🎯 Objective
Implement the processing pipeline that converts a raw screenshot into a `SemanticSnapshot` and saves it to LanceDB and SQLite FTS.
Key components: Keyword Extraction, VLM JSON Output, Structured Text Fusion, and the Worker Orchestrator.

---

## 📝 Task List

### 1. Implement Keyword Extractor
- **File**: `openrecall/server/utils/keywords.py`
- **Action**: Create new file.
- **Class**: `KeywordExtractor`
- **Logic**:
    - Initialize with a strategy (default "local").
    - Implement `extract(text: str) -> List[str]`.
    - **Algorithm**:
        1.  Tokenize text (regex `\w+`).
        2.  Filter out common English stopwords (hardcode a small set like 'the', 'is', 'and', 'def', 'class' etc. or use a library if available).
        3.  Filter out short words (< 3 chars).
        4.  Count frequency (`collections.Counter`).
        5.  Return Top-10 most frequent words.

### 2. Update Vision Provider (JSON Output)
- **File**: `openrecall/server/ai/vision.py`
- **Action**: Update `analyze_image` method.
- **Logic**:
    - Change the System Prompt to force JSON output.
    - **Prompt**:
      > "Analyze this screenshot. Output a strictly valid JSON object with these keys:
      > - 'caption': A detailed natural language description of the screen content and user intent.
      > - 'scene': A single tag describing the scene (e.g., coding, browsing, meeting, chat).
      > - 'action': A single tag describing the action (e.g., debugging, reading, typing).
      > Do not include markdown formatting."
    - **Parsing**: Add error handling to parse the response. If JSON parsing fails, fall back to a raw string in 'caption' and empty tags.

### 3. Implement Structured Fusion (Critical)
- **File**: `openrecall/server/utils/fusion.py`
- **Action**: Create new file.
- **Function**: `build_fusion_text(snapshot: SemanticSnapshot) -> str`
- **Logic**: Construct the single text string used for embedding. Use strict tagging.
- **Format**:
  ```text
  [APP] {app_name}
  [TITLE] {window_title}
  [SCENE] {scene_tag}
  [ACTION] {action_tag}
  [CAPTION] {caption}
  [KEYWORDS] {comma_separated_keywords}
  [OCR_HEAD] {first_300_chars_of_ocr}
  ```

### 4. Refactor Worker Orchestrator
- **File**: `openrecall/server/worker.py`
- **Action**: Rewrite `process_task` (or the main processing loop).
- **New Workflow**:
    1.  **Load**: Load image from disk based on `PENDING` task.
    2.  **OCR**: `ocr_text = ocr_provider.extract_text(image)`.
    3.  **Vision**: `vision_data = vision_provider.analyze_image(image)` (returns caption, scene, action).
    4.  **Keywords**: `keywords = keyword_extractor.extract(ocr_text)`.
    5.  **Construct Object**: Create `SemanticSnapshot` object (Pydantic model from `schema.py`).
        - Populate `Context` (from metadata).
        - Populate `Content` (ocr_head, caption, tags, etc.).
    6.  **Fusion**: `dense_text = build_fusion_text(snapshot)`.
    7.  **Embedding**: `vector = embedding_provider.embed_text(dense_text)` (Ensure this uses the Text model, not Vision model).
    8.  **Save**:
        - `vector_store.add_snapshot(snapshot_with_vector)` (LanceDB).
        - `sql_store.add_record(snapshot)` (SQLite FTS).
        - Update Task Status to `COMPLETED`.

---

## ✅ Verification Plan (Mocked Pipeline)

Create `tests/test_phase3_brain.py`.
**Crucial**: To make this test fast and reliable, **MOCK the AI Providers**. We want to test the *Pipeline Logic* (Fusion -> Storage), not the AI models themselves.

**Steps**:
1.  **Setup**: Init temp databases (LanceDB/SQLite).
2.  **Mocks**:
    - Mock `ocr_provider.extract_text` returns "def hello(): print('world')".
    - Mock `vision_provider.analyze_image` returns `{"caption": "User coding", "scene": "coding", "action": "typing"}`.
    - Mock `embedding_provider.embed_text` returns a list of 1024 floats.
3.  **Execution**:
    - Manually trigger `process_task` with a dummy image path.
4.  **Assertions**:
    - Check LanceDB: Query by vector (mock vector) -> Should find the record.
    - Check LanceDB Payload: Ensure `scene_tag` is "coding".
    - Check SQLite FTS: Search for "hello" -> Should find the record.
    - Check Fusion Logic: Verify the text passed to the embedding mock contained `[APP]` and `[SCENE]`.

---

## 🚀 Execution Instructions

1.  Create `utils/keywords.py` and `utils/fusion.py`.
2.  Update `ai/vision.py` (Focus on the prompt and JSON parsing).
3.  Rewrite `worker.py` to orchestrate the new flow using `SemanticSnapshot`.
4.  Run `tests/test_phase3_brain.py`.
5.  If passed, output "**Phase 3 Brain Logic Refactor Complete**".
```

---


这是 **Phase 3: The Processing Brain (智能处理核心)** 的完整提示词。

这一阶段是重构中最复杂的环节，涉及将原始图像转化为结构化的语义数据。Prompt 重点强调了 **“Caption-First” (文本优先)** 的处理逻辑和 **“Structured Fusion” (结构化融合)** 的文本构建策略。

请将以下 Prompt 复制给 Code Agent。

---

### 📋 Copy to Code Agent

```markdown
# Refactor OpenRecall to V2 - Phase 3: The Processing Brain (AI Pipeline)

**Context**:
We have the Infrastructure (Phase 1) and Ingestion Pipeline (Phase 2).
Now we build the core processing logic.
**Architecture Constraint**: We are using a **"Caption-First" approach**. We do NOT use Image Embeddings. We rely on OCR + VLM Captions -> Text Fusion -> Text Embedding.

**Environment**:
- Local macOS.
- Existing files: `server/schema.py`, `server/database/*`.

---

## 🎯 Objective
Implement the processing pipeline that converts a raw screenshot into a `SemanticSnapshot` and saves it to LanceDB and SQLite FTS.
Key components: Keyword Extraction, VLM JSON Output, Structured Text Fusion, and the Worker Orchestrator.

---

## 📝 Task List

### 1. Implement Keyword Extractor
- **File**: `openrecall/server/utils/keywords.py`
- **Action**: Create new file.
- **Class**: `KeywordExtractor`
- **Logic**:
    - Initialize with a strategy (default "local").
    - Implement `extract(text: str) -> List[str]`.
    - **Algorithm**:
        1.  Tokenize text (regex `\w+`).
        2.  Filter out common English stopwords (hardcode a small set like 'the', 'is', 'and', 'def', 'class' etc. or use a library if available).
        3.  Filter out short words (< 3 chars).
        4.  Count frequency (`collections.Counter`).
        5.  Return Top-10 most frequent words.

### 2. Update Vision Provider (JSON Output)
- **File**: `openrecall/server/ai/vision.py`
- **Action**: Update `analyze_image` method.
- **Logic**:
    - Change the System Prompt to force JSON output.
    - **Prompt**:
      > "Analyze this screenshot. Output a strictly valid JSON object with these keys:
      > - 'caption': A detailed natural language description of the screen content and user intent.
      > - 'scene': A single tag describing the scene (e.g., coding, browsing, meeting, chat).
      > - 'action': A single tag describing the action (e.g., debugging, reading, typing).
      > Do not include markdown formatting."
    - **Parsing**: Add error handling to parse the response. If JSON parsing fails, fall back to a raw string in 'caption' and empty tags.

### 3. Implement Structured Fusion (Critical)
- **File**: `openrecall/server/utils/fusion.py`
- **Action**: Create new file.
- **Function**: `build_fusion_text(snapshot: SemanticSnapshot) -> str`
- **Logic**: Construct the single text string used for embedding. Use strict tagging.
- **Format**:
  ```text
  [APP] {app_name}
  [TITLE] {window_title}
  [SCENE] {scene_tag}
  [ACTION] {action_tag}
  [CAPTION] {caption}
  [KEYWORDS] {comma_separated_keywords}
  [OCR_HEAD] {first_300_chars_of_ocr}
  ```

### 4. Refactor Worker Orchestrator
- **File**: `openrecall/server/worker.py`
- **Action**: Rewrite `process_task` (or the main processing loop).
- **New Workflow**:
    1.  **Load**: Load image from disk based on `PENDING` task.
    2.  **OCR**: `ocr_text = ocr_provider.extract_text(image)`.
    3.  **Vision**: `vision_data = vision_provider.analyze_image(image)` (returns caption, scene, action).
    4.  **Keywords**: `keywords = keyword_extractor.extract(ocr_text)`.
    5.  **Construct Object**: Create `SemanticSnapshot` object (Pydantic model from `schema.py`).
        - Populate `Context` (from metadata).
        - Populate `Content` (ocr_head, caption, tags, etc.).
    6.  **Fusion**: `dense_text = build_fusion_text(snapshot)`.
    7.  **Embedding**: `vector = embedding_provider.embed_text(dense_text)` (Ensure this uses the Text model, not Vision model).
    8.  **Save**:
        - `vector_store.add_snapshot(snapshot_with_vector)` (LanceDB).
        - `sql_store.add_record(snapshot)` (SQLite FTS).
        - Update Task Status to `COMPLETED`.

---

## ✅ Verification Plan (Mocked Pipeline)

Create `tests/test_phase3_brain.py`.
**Crucial**: To make this test fast and reliable, **MOCK the AI Providers**. We want to test the *Pipeline Logic* (Fusion -> Storage), not the AI models themselves.

**Steps**:
1.  **Setup**: Init temp databases (LanceDB/SQLite).
2.  **Mocks**:
    - Mock `ocr_provider.extract_text` returns "def hello(): print('world')".
    - Mock `vision_provider.analyze_image` returns `{"caption": "User coding", "scene": "coding", "action": "typing"}`.
    - Mock `embedding_provider.embed_text` returns a list of 1024 floats.
3.  **Execution**:
    - Manually trigger `process_task` with a dummy image path.
4.  **Assertions**:
    - Check LanceDB: Query by vector (mock vector) -> Should find the record.
    - Check LanceDB Payload: Ensure `scene_tag` is "coding".
    - Check SQLite FTS: Search for "hello" -> Should find the record.
    - Check Fusion Logic: Verify the text passed to the embedding mock contained `[APP]` and `[SCENE]`.

---

## 🚀 Execution Instructions

1.  Create `utils/keywords.py` and `utils/fusion.py`.
2.  Update `ai/vision.py` (Focus on the prompt and JSON parsing).
3.  Rewrite `worker.py` to orchestrate the new flow using `SemanticSnapshot`.
4.  Run `tests/test_phase3_brain.py`.
5.  If passed, output "**Phase 3 Brain Logic Refactor Complete**".
```

---


# Refactor OpenRecall to V2 - Phase 4: Hybrid Search Engine

**Context**:
- Phase 1-3 are complete. We have:
    - **LanceDB**: Stores `SemanticSnapshot` with a text-based `embedding_vector`.
    - **SQLite FTS**: Stores `ocr_fts` table for keyword search.
    - **Data Structure**: `SemanticSnapshot` (Pydantic model).
- **Goal**: Implement the search logic that combines Vector Semantic Search with Keyword Match, including Time Filtering.

**Environment**:
- Local macOS.
- Python 3.10+.

---

## 🎯 Objective
Build the `SearchEngine` that parses natural language queries, executes parallel searches (Vector + FTS), and merges the results into a ranked list of `SemanticSnapshot` objects.

---

## 📝 Task List

### 1. Implement Query Parser (NLP Lite)
- **File**: `openrecall/server/utils/query_parser.py`
- **Action**: Create new file.
- **Class**: `QueryParser`
- **Logic**:
    - Method `parse(query: str) -> ParsedQuery`.
    - **Time Extraction**:
        - Detect simple time phrases: "today", "yesterday", "last week".
        - Calculate `start_time` and `end_time` timestamps based on current time.
        - *Tip*: You can use `dateparser` library if available, or simple regex/delta logic for the MVP.
    - **Keyword Extraction**:
        - If the user uses quotes (e.g., `"error code"`), treat it as a mandatory keyword for FTS.
        - Otherwise, the whole query string is used for vector search.
    - **Output DTO**:
        ```python
        class ParsedQuery(BaseModel):
            text: str
            start_time: Optional[float]
            end_time: Optional[float]
            mandatory_keywords: List[str]
        ```

### 2. Implement Hybrid Search Engine
- **File**: `openrecall/server/search/engine.py`
- **Action**: Create new file.
- **Class**: `SearchEngine`
- **Dependencies**: `VectorStore` (LanceDB), `SQLStore` (SQLite), `EmbeddingProvider` (Text Model), `QueryParser`.
- **Logic**: `search(user_query: str, limit: int = 50)`
    1.  **Parse**: `parsed = query_parser.parse(user_query)`.
    2.  **Vector Branch**:
        - Embed `parsed.text` -> `query_vec`.
        - Search LanceDB: `vector_store.search(query_vec)`.
        - **Filter**: Apply SQL filter `timestamp >= {start} AND timestamp <= {end}` if time is present.
        - Get Top-100 candidates.
    3.  **Keyword Branch (FTS)**:
        - Search SQLite: `sql_store.search_fts(parsed.text)`.
        - Get Top-50 candidates.
    4.  **Merge & Rank (The Hybrid Logic)**:
        - Create a dictionary `results: Dict[str, SnapshotWithScore]`. Key is `id`.
        - **Vector Base**: Add all vector results with `score = vector_distance_score` (normalized 0-1).
        - **Keyword Boost**: If a record ID exists in FTS results, **boost its score** (e.g., `final_score = vector_score * 1.0 + fts_boost * 0.3`).
        - If a record is ONLY in FTS (not in Vector), add it with a lower base score.
    5.  **Sort**: Return Top-`limit` sorted by `final_score`.

### 3. Update API Endpoint
- **File**: `openrecall/server/api.py` (or `app.py`)
- **Action**: Update `/api/search` GET endpoint.
- **Logic**:
    - Input: `q` (query string), `limit` (optional).
    - Call `search_engine.search(q, limit)`.
    - **Response Format**:
        - Return a rich JSON list.
        - Important: Include `caption`, `scene_tag`, `app_name`, `timestamp`, and `image_path` in the response so the UI can verify the result.

---

## ✅ Verification Plan (Search Logic Test)

Create `tests/test_phase4_search.py`.
**Requirement**: Use `tempfile` for DBs. Do not touch production data.

**Scenario**:
1.  **Setup**:
    - Insert Record A: App="VSCode", Text="Python Error", Timestamp=Today.
    - Insert Record B: App="Chrome", Text="News about Python", Timestamp=Yesterday.
2.  **Test 1: Time Filter**:
    - Query: "Python today".
    - Assert: Only Record A is returned (because Record B is yesterday).
3.  **Test 2: Hybrid Boosting**:
    - Assume Vector Search finds both A and B (semantics).
    - Assume FTS finds A (exact keyword match "Error").
    - Assert: Record A should have a higher score than Record B.
4.  **Output**: Print the ranked list to console for visual verification.

---

## 🚀 Execution Instructions

1.  Create `utils/query_parser.py`.
2.  Create `search/engine.py` and implement the Hybrid Merge logic.
3.  Update the API endpoint.
4.  Run `tests/test_phase4_search.py`.
5.  If successful, output "**Phase 4 Hybrid Search Refactor Complete**".




x# Refactor OpenRecall to V2 - Phase 5: Cleanup & Optimization (Final)

**Context**:
- Phases 1-4 are complete. The new "Caption-First" architecture (Ingestion -> Processing -> Hybrid Search) is implemented.
- The codebase currently contains a mix of new modules (`vector_store.py`, `sql.py`) and legacy modules (`legacy.py`) kept for backward compatibility during refactoring.
- **Goal**: Remove technical debt, finalize configuration, and verify the entire system E2E.

**Environment**:
- Local macOS.

---

## 🎯 Objective
Clean up the codebase by removing legacy database logic, updating the configuration system, and running a final End-to-End integration test.

---

## 📝 Task List

### 1. Update Configuration
- **File**: `openrecall/shared/config.py`
- **Action**: Update `Settings` class.
- **Changes**:
    - **Add**:
        - `LANCEDB_PATH`: Default to `~/.openrecall/data/lancedb`.
        - `FTS_PATH`: Default to `~/.openrecall/data/fts.db`.
        - `KEYWORD_STRATEGY`: Default to `"local"`.
        - `EMBEDDING_MODEL`: Default to `"qwen-text-v1"` (or whatever model logic you implemented).
    - **Remove**:
        - Any deprecated paths strictly related to the old BLOB storage if they exist.
    - **Verify**: Ensure environment variable overrides work (e.g., `os.getenv("OPENRECALL_LANCEDB_PATH")`).

### 2. Remove Legacy Database Code
- **File**: `openrecall/server/database/legacy.py`
- **Action**: **Delete this file.** We no longer support the V1 architecture.
- **File**: `openrecall/server/database/__init__.py`
- **Action**: Update exports.
    - **Remove**: `from .legacy import *`
    - **Add**: Explicit exports for the new system.
      ```python
      from .vector_store import VectorStore
      from .sql import SQLStore
      ```

### 3. Scan and Fix Imports
- **Action**: Scan the codebase (especially `app.py`, `worker.py`, `api.py`) for any lingering imports from the old database interface.
- **Logic**:
    - If `api.py` calls `create_db()` (old function), remove it or replace it with `SQLStore().setup_fts()` and `VectorStore().create_table()`.
    - Ensure `app.py` initializes the new stores on startup if necessary.

### 4. Optimize Dependencies
- **File**: `openrecall/setup.py` (or `pyproject.toml`)
- **Action**: Review dependencies.
    - Ensure `lancedb`, `pydantic`, `fastapi`, `python-multipart` are listed.
    - If `numpy` is ONLY used for the old manual vector math (which we replaced with LanceDB), and NOT used by OCR/Vision providers, consider removing it. *However, typically OCR libraries need numpy, so keep it if unsure, but remove any direct `numpy.save` calls in our code.*

---

## ✅ Verification Plan (The Grand Finale: E2E Test)

Create `tests/test_phase5_e2e.py`.
**Requirement**: This test simulates the **entire lifecycle** of a screenshot. Use `tempfile` for data directories.

**Scenario**:
1.  **Setup**: Initialize fresh LanceDB and SQLite FTS in temp dirs.
2.  **Step 1: Ingestion (API)**
    - Send a POST request to `/api/upload` with a test image (blue square) and metadata (App="Safari").
    - Assert Response is `202 Accepted`.
3.  **Step 2: Processing (Worker)**
    - Manually trigger the `process_task` function (simulating the worker picking up the job).
    - *Mocking*: You may mock the slow AI parts (VLM/OCR) to make the test fast, BUT use the **real** database logic.
    - Assert: Task status becomes `COMPLETED` in SQLite.
    - Assert: Data exists in LanceDB (Vector) and SQLite (FTS).
4.  **Step 3: Retrieval (Search Engine)**
    - Call `search_engine.search("Safari")`.
    - Assert: The record uploaded in Step 1 is returned in the results.
    - Assert: Result contains `caption`, `app_name`, and `image_path`.

---

## 🚀 Execution Instructions

1.  Update `config.py`.
2.  Delete `legacy.py` and fix `database/__init__.py`.
3.  Run `grep` or search to ensure no old DB calls remain.
4.  Run `tests/test_phase5_e2e.py`.
5.  If passed, output:
    ```text
    🎉 OpenRecall V2 Refactor Completed Successfully!
    - Architecture: Caption-First (Text Only)
    - Storage: LanceDB + SQLite FTS5
    - Search: Hybrid RRF
    ```


这是为您准备的**最终完整版提示词**。

这份提示词已经包含了我们刚才讨论的所有细节：**三阶段漏斗架构**、**API 优先设计**、**32k 长文本策略**以及**带明确 Header 的输入结构**。

请直接复制以下内容发送给您的 Code Agent（Cursor / Windsurf / Copilot）：

---

# Prompt: Implement Cascade Search with Qwen Reranker for MyRecall V2

**Role:** Senior Python Backend Engineer & Search Architect
**Project:** MyRecall V2 (Personal Memory System)
**Context:**
*   **Server Root:** `~/MRS`
*   **Tech Stack:** FastAPI, Python 3.10+, LanceDB (Vector), SQLite (FTS & Metadata).
*   **Current Search Pipeline:** Parallel Retrieval (Vector + FTS) $\rightarrow$ RRF Fusion $\rightarrow$ Return Results.

**Objective:**
Upgrade the search engine to a **"Retrieve-then-Rerank" (Cascade) Pipeline** by integrating the `Qwen/Qwen3-Reranker-0.6B` model. The goal is to maximize search precision using a 3-stage funnel strategy.

---

## 1. Architectural Strategy (The 3-Stage Funnel)

Refactor the search logic in `engine.py` to follow this strict pipeline:

*   **Stage 1: Broad Recall (Top 100)**
    *   Retrieve Top 100 from Vector Search (LanceDB).
    *   Retrieve Top 100 from Keyword Search (SQLite FTS).
*   **Stage 2: Coarse Fusion (Top 30)**
    *   Apply RRF (Reciprocal Rank Fusion) to merge the lists.
    *   **Action:** Slice the combined list to the **Top 30** candidates. These are the "Rerank Candidates".
*   **Stage 3: Deep Reranking (Top 10)**
    *   Construct a detailed "Document Context" string for each of the 30 candidates (utilizing the model's 32k context).
    *   Pass `(Query, Document)` pairs to the Reranker.
    *   Re-sort based on the new similarity scores.
    *   Return the final Top 10-20 to the user.

---

## 2. Technical Specifications

### A. Configuration (`config.py`)
Add the following environment variables with defaults:
*   `OPENRECALL_RERANKER_MODE`: `api` (default) or `local`.
*   `OPENRECALL_RERANKER_URL`: Default `http://localhost:8080/rerank` (Compatible with TEI/BGE API).
*   `OPENRECALL_RERANKER_MODEL`: Default `Qwen/Qwen3-Reranker-0.6B`.

### B. New Service: `services/reranker.py`
Implement a Strategy Pattern.

1.  **`BaseReranker` (Interface)**:
    *   Method: `compute_score(query: str, documents: list[str]) -> list[float]`

2.  **`APIReranker` (Production/Default)**:
    *   Use `requests` to hit the `OPENRECALL_RERANKER_URL`.
    *   **Payload**: `{"query": "...", "texts": [...]}`.
    *   **Resilience**: If the API fails (timeout/connection error), catch the exception, log it, and return a list of `0.0` scores to ensure the search doesn't crash.

3.  **`LocalReranker` (Development/Fallback)**:
    *   Use `transformers` (`AutoModelForSequenceClassification`).
    *   **Lazy Loading**: Do NOT load the model on import. Initialize it only on the first `compute_score` call.
    *   **Device**: Auto-detect `cuda`, `mps` (Apple Silicon), or `cpu`.
    *   **Model**: Load `Qwen/Qwen3-Reranker-0.6B`.

4.  **Factory**: `get_reranker()` returns the correct instance based on config.

### C. Input Context Construction (Critical)
We must construct a structured prompt that leverages the **32k context window** without confusing the model. We will use an **"Inverted Pyramid"** structure with **Explicit Section Headers**.

Create a helper function in `engine.py` (or a utility module): `construct_rerank_context(item: dict) -> str`.

**Requirements:**
1.  **Time Parsing**: Convert Unix timestamp to a human-readable string (e.g., "Monday, 2026-01-26 14:00").
2.  **Explicit Headers**: Use `[Metadata]`, `[Visual Context]`, and `[OCR Content]` to guide the model's attention.
3.  **No Truncation**: Do not truncate OCR text unless it is absurdly large (e.g., > 20k chars).
4.  **Safety**: Use `.get()` for all dictionary accesses.

**Required Code Pattern for Context Builder:**
```python
import datetime

def construct_rerank_context(item: dict) -> str:
    # 1. Human-readable Time
    ts = item.get('timestamp', 0)
    time_str = datetime.datetime.fromtimestamp(ts).strftime("%A, %Y-%m-%d %H:%M")

    # 2. Build Parts with Explicit Headers and Double Newlines
    parts = [
        # --- Section 1: Metadata (High Priority) ---
        "[Metadata]",
        f"App: {item.get('app', 'Unknown App')}",
        f"Title: {item.get('title', 'No Title')}",
        f"Time: {time_str}",
        
        # --- Section 2: Visual Context (Medium Priority) ---
        "", # Empty string creates \n\n for paragraph separation
        "[Visual Context]",
        f"Scene: {item.get('scene', 'general')}",
        f"Summary: {item.get('caption', '')}",
        
        # --- Section 3: OCR Content (Low Priority, High Volume) ---
        "", 
        "[OCR Content]",
        item.get('text', '') # Full text, leveraging 32k context
    ]
    
    return "\n".join(parts)
```

### D. Search Logic Integration (`engine.py`)
Update the `search()` method:
1.  **Step 1 & 2**: Keep existing Vector/FTS/RRF logic.
2.  **Step 3 (New)**:
    *   Take the Top 30 results from RRF: `candidates = fused_results[:30]`.
    *   **Guard Clause**: If `candidates` is empty, return empty list.
    *   **Build Docs**: `doc_texts = [construct_rerank_context(c) for c in candidates]`.
    *   **Rerank**: `scores = self.reranker.compute_score(query, doc_texts)`.
    *   **Update**: Assign the new scores to the candidates.
    *   **Sort**: Sort candidates by the *new Reranker score* (descending).
    *   **Return**: The re-sorted list (Top 10-20).

---

## 3. Implementation Plan

Please modify/create the following files in this order:
1.  `config.py`: Add env vars.
2.  `services/reranker.py`: Create the module with API and Local implementations.
3.  `engine.py`: Integrate the context builder and the 3-stage logic.

**Note:** Ensure the code handles the case where `reranker.compute_score` returns all zeros (API failure) by preserving the original RRF sort order as a fallback.




