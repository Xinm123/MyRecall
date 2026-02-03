# Phase 2: Ingestion Pipeline Refactoring Plan

We will switch the client-server communication from JSON-serialized arrays to standard Multipart Binary Streaming to reduce resource usage.

**Note**: The current server implementation uses **Flask**, not FastAPI. I will implement the multipart streaming logic using **Flask's native `request.files` and `request.form`** to ensure compatibility with the existing codebase, while achieving the same performance goals (streaming write, low RAM usage).

## 1. Client-Side Refactoring (`openrecall/client/uploader.py`)
- **Action**: Modify `HTTPUploader.upload_screenshot`.
- **Implementation**:
    - Convert NumPy image to PNG bytes using `cv2.imencode` (efficient) or `PIL`.
    - Serialize metadata (`timestamp`, `app_name`, `window_title`) to JSON string.
    - Switch `requests.post` to use `files` (image) and `data` (metadata).

## 2. Server-Side Refactoring (`openrecall/server/api.py`)
- **Action**: Rewrite `/api/upload` endpoint.
- **Implementation**:
    - Remove JSON payload parsing logic.
    - Access image stream via `request.files['file']`.
    - Access metadata via `request.form['metadata']`.
    - **Streaming Write**: Use `file.save(path)` (Flask's efficient save) or `shutil.copyfileobj` to write directly to `settings.screenshots_path` without loading the full file into RAM.
    - **Database**: Parse metadata and call `insert_pending_entry`.
    - Return `202 Accepted`.

## 3. Verification (`tests/test_phase2_ingestion.py`)
- **Action**: Create standalone integration test.
- **Implementation**:
    - Use `requests` to simulate the client.
    - Generate a dummy test image and metadata.
    - POST to the running server (or mock app context).
    - Verify:
        1.  HTTP 202 response.
        2.  File exists on disk (correct size/content).
        3.  SQLite entry exists with status `PENDING`.

## 4. Execution Order
1.  Refactor `openrecall/client/uploader.py`.
2.  Refactor `openrecall/server/api.py`.
3.  Create and run `tests/test_phase2_ingestion.py` (ensuring `conda activate MRv2` is used).
