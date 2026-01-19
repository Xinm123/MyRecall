# Role: Python Refactoring Expert
# Phase: 1 - Configuration Refactoring (In-Place + Storage Migration)

# Context
We are modifying the **OpenRecall** project directly (`openrecall/` directory).
The current `openrecall/config.py` relies on `argparse` parsing at the module level and storing paths in global variables. This is fragile and causes crashes because subdirectories are not automatically created.
We want to upgrade this to use `pydantic-settings` and **change the default storage location** to isolate it from previous OpenRecall data.

# Task 1: Refactor `openrecall/config.py`
1.  **Install Dependencies**: Ensure `pydantic` and `pydantic-settings` are installed.
2.  **Rewrite `openrecall/config.py`**:
    -   Clear the existing content and import `pydantic_settings.BaseSettings` and `pathlib.Path`.
    -   Create a `Settings` class inheriting from `BaseSettings`.
    -   **Configuration Fields**:
        -   `port`: `int`, default to **8083** 
        -   `base_path`: `Path`, **CHANGE DEFAULT** to `Path.home() / ".myrecall_data"`. Allow overriding via env var `OPENRECALL_DATA_DIR`.
    -   **Computed Properties**:
        -   `screenshots_path`: returns `base_path / "screenshots"`.
        -   `db_path`: returns `base_path / "recall.db"` (Note: this is a file path).
        -   `buffer_path`: returns `base_path / "buffer"` (New directory for local buffering).
    -   **Critical Logic (Bug Fix)**: Implement an `ensure_directories()` method (or `model_post_init` hook). It **MUST** recursively create:
        -   `base_path`
        -   `screenshots_path`
        -   `buffer_path`
        -   The parent directory of `db_path`
    -   **Singleton**: Expose a global instance: `settings = Settings()`, and immediately call `settings.ensure_directories()`.

# Task 2: Update References (Fix Breaking Changes)
You need to fix all imports that relied on the old global variables (like `screenshots_path`, `appdata_folder`).
1.  **`openrecall/app.py`**:
    -   Change `from .config import screenshots_path` (and others) to `from .config import settings`.
    -   Replace usages with `settings.screenshots_path`, `settings.port`, etc.
2.  **`openrecall/screenshot.py`**:
    -   Update imports to use `settings`.
    -   Replace usage of global path variables with `settings.screenshots_path` and `settings.db_path`.
3.  **`openrecall/database.py`**:
    -   Update to use `settings.db_path` for the SQLite connection.
4.  **`openrecall/nlp.py`**:
    -   Update model cache path to use `settings.base_path / "models"`.

# Task 3: Test
Create `tests/test_config_refactor.py` to verify the robustness of the new config:
1.  **Default Path Test**: Verify that if no env vars are set, `settings.base_path` points to `~/.myrecall_data`.
2.  **Auto-Creation Test**:
    -   Use `tempfile` to generate a temporary path string.
    -   Override `OPENRECALL_DATA_DIR` with this path.
    -   Initialize `Settings` and verify that `screenshots/`, `buffer/`, and `db/` folders are actually created on the disk.

# Constraints
-   **Backward Compatibility**: The application must still be launchable via `python -m openrecall.app`.
-   **Cleanliness**: Remove the old `argparse` logic from `config.py` entirely; do not mix the two approaches.

# Role: Python Backend Engineer

# Phase: 2 - Database Hardening & Type Safety

# Context
We are continuing the in-place refactoring of **OpenRecall**.
**Current State**: The `openrecall/database.py` module suffers from inconsistent return types. `get_all_entries()` returns deserialized arrays, but `get_entries_by_time_range()` returns raw SQLite `BLOBs` (bytes). This inconsistency causes fragile code in the consumers (UI/API) and requires manual deserialization in multiple places.

**Goal**: Enforce a strict data contract using **Pydantic**. The database layer must **always** return strongly-typed objects where the `embedding` field is a valid numpy array, never raw bytes.


# Task 1: Define Data Model (`openrecall/models.py`)
1.  **Create File**: Create a new file `openrecall/models.py`.
2.  **Define `RecallEntry`**:
    -   Inherit from `pydantic.BaseModel`.
    -   **Fields**:
        -   `id`: `int | None = None`
        -   `timestamp`: `float` (or `str`, match existing DB schema)
        -   `app`: `str`
        -   `title`: `str | None`
        -   `text`: `str`
        -   `embedding`: `Any` (We need to allow `np.ndarray`).
    -   **Config**: Set `model_config = ConfigDict(arbitrary_types_allowed=True)` to allow numpy arrays.
    -   **Validator (Crucial)**: Implement a `field_validator('embedding', mode='before')`.
        -   Logic: If the input value is `bytes`, use `np.frombuffer(v, dtype=np.float32)` to convert it to a numpy array immediately.
        -   This ensures that no matter what comes out of SQLite, the model always holds a usable array.

# Task 2: Refactor Database Layer (`openrecall/database.py`)
Refactor the read operations to return `RecallEntry` objects instead of raw tuples/rows.
1.  **Imports**: Import `RecallEntry` from `.models` and `settings` from `.config`.
2.  **Refactor `get_all_entries()`**:
    -   Execute the query.
    -   Iterate over the cursor/rows.
    -   Convert each row into a `RecallEntry` object (e.g., `RecallEntry(**dict(row))`).
    -   Return: `List[RecallEntry]`.

3.  **Refactor `get_entries_by_time_range()`**:
    -   Apply the exact same logic: ensure it returns `List[RecallEntry]`.
    -   *Note*: This fixes the bug where this specific function was returning raw BLOBs.

4.  **Update `insert_entry()`**:
    -   Ensure it uses `settings.db_path`.
    -   No major logic change needed here if it already handles numpy array serialization to bytes correctly during `execute()`.

# Task 3: Fix Consumers (Minimal Changes)
Update `openrecall/app.py` to handle the new `RecallEntry` objects.
1.  **Access Attribute vs. Dict**:
    -   The `RecallEntry` object is accessed via attributes (e.g., `entry.timestamp`), whereas `sqlite3.Row` supports dict-style access (`entry['timestamp']`).
    -   Scan `app.py` (especially inside `render_template` context or loops) and switch usage to attribute access if necessary.
2.  **Remove Redundant Deserialization**:
    -   Locate the `search()` function in `app.py`.
    -   It likely contains manual code like `np.frombuffer(entry['embedding'], ...)` or similar.
    -   **Delete this manual conversion**. The `RecallEntry` from the database is now guaranteed to already contain a numpy array.

# Task 4: Verification Test
Create a new test file `tests/test_database_strict.py`:
1.  **Setup**: Initialize the DB using `settings`.
2.  **Test Write**: Insert a dummy entry with a random 384-dim numpy array as the embedding.
3.  **Test Read Consistency**:
    -   Call `get_all_entries()`.
    -   Call `get_entries_by_time_range()` for that timestamp.
    -   **Assert**:
        -   Both return `RecallEntry` objects.
        -   `type(result.embedding)` is `np.ndarray` for **BOTH** cases.
        -   The embedding values match the inserted values.

# Constraints
-   **Minimal Changes**: Only touch `models.py`, `database.py`, and `app.py` (where broken). Do not rewrite the NLP or OCR logic.
-   **Dependencies**: Rely on `numpy` and `pydantic`.
-   **Performance**: Do not iterate unnecessarily. Convert rows to models efficiently.
-   **Backward Compatibility**: The application must still be launchable via `python -m openrecall.app`.
-   **避免过度设计和重构整个 codebase**：Think carefully and only action the specific task I have given you with the most concise and elegant solution that changes as little code as possible. 


# Role: Python Refactoring Expert
# Phase: 3 - Physical Separation (Modular Monolith)

# Context
We are refactoring **OpenRecall** to prepare for a Client-Server architecture.
**Current State**: The project is a flat directory (`openrecall/*.py`). All logic is mixed.
**Goal**: Restructure the codebase into three distinct domains: `client/` (Capture), `server/` (Storage & UI), and `shared/` (Config & Models).
**Constraint**: This is a structural refactor only. The application must still run as a single process (Modular Monolith).

# Task 1: Restructure Directories & Move Files
1.  **Create Domain Directories** inside `openrecall/` (ensure each has an empty `__init__.py`):
    -   `openrecall/client/`
    -   `openrecall/server/`
    -   `openrecall/shared/`

2.  **Move & Rename Files**:
    * **Shared Domain** (Pure Logic, No Dependencies on Client/Server):
        -   `config.py` -> `openrecall/shared/config.py`
        -   `models.py` -> `openrecall/shared/models.py`
        -   `utils.py`  -> `openrecall/shared/utils.py`
    * **Client Domain** (Capture Logic):
        -   `screenshot.py` -> `openrecall/client/recorder.py` (**Note Rename**)
    * **Server Domain** (Storage & UI Logic):
        -   `database.py` -> `openrecall/server/database.py`
        -   `nlp.py`      -> `openrecall/server/nlp.py`
        -   `ocr.py`      -> `openrecall/server/ocr.py`
        -   `app.py`      -> `openrecall/server/app.py`
        -   `templates/` folder -> `openrecall/server/templates/`

# Task 2: Fix Imports & Paths (Crucial)
Update all import statements to reflect the new structure.
1.  **Update `shared/*.py`**: Ensure `config.py` and `models.py` do NOT import from client or server.
2.  **Update `server/*.py`**:
    -   `server/database.py`: Fix imports from `openrecall.shared`.
    -   `server/app.py`:
        -   Fix imports for `database`, `nlp`, and `settings`.
        -   **CRITICAL**: Since `app.py` moved, you MUST update the `Flask` app initialization to point to the correct template folder location.
        -   *Example*: `app = Flask(__name__, template_folder='templates')` (Relative path works because it's inside `server/`).
3.  **Update `client/recorder.py`**:
    -   Fix imports from `openrecall.shared`.
    -   **Temporary Coupling**: It is acceptable for `client` to import `openrecall.server.database` directly for now. Add a comment: `# TODO: Phase 4 - Replace with API call`.

# Task 3: Create Unified Entry Point
Create a new file `openrecall/main.py` to act as the new entry point.
-   **Responsibilities**:
    1.  Import `app` (Flask) from `openrecall.server.app`.
    2.  Import the recording logic from `openrecall.client.recorder`.
    3.  Start the recorder thread (Producer).
    4.  Start the Flask server (Consumer/UI) on the main thread.
-   **Note**: This logic replaces the `if __name__ == "__main__":` block from the old `app.py`.

# Task 4: Cleanup & Verification Plan
1.  **Cleanup**: Delete the original files (`app.py`, `database.py`, etc.) from the root `openrecall/` directory after moving them.
2.  **Verification Steps** (Include these in your response):
    -   **New Launch Command**: `python -m openrecall.main`
    -   Check 1: Does the UI load at the configured port?
    -   Check 2: Does the screenshot loop start without `ModuleNotFoundError`?
    -   Check 3: Are new entries appearing in the database?

# Constraints
-   **No HTTP API yet**: Keep using direct function calls between modules.
-   **No Circular Imports**: Ensure `Shared` never imports from `Client` or `Server`.
-   **Launch Command**: The new standard launch command is `python -m openrecall.main`. You do NOT need to maintain backward compatibility for `openrecall.app`.
-   **避免过度设计和重构整个 codebase**：Think carefully and only action the specific task I have given you with the most concise and elegant solution that changes as little code as possible. 