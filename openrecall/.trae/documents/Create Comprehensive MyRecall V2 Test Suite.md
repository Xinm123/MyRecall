I will create a comprehensive, isolated test suite in `tests/v2` to verify the MyRecall V2 architecture.

### 1. Test Structure & Strategy

We will implement a layered testing strategy covering Unit, Integration, and End-to-End scenarios.

| Layer | File | Focus Areas |
| :--- | :--- | :--- |
| **Foundation** | `tests/v2/conftest.py` | **Test Fixtures**: Setup isolated temp environments (`MRS`/`MRC`) and Mock AI Providers to ensure tests run fast and deterministically. |
| **Unit** | `tests/v2/test_utils.py` | **Core Logic**: Verify Keyword Extraction (stopword removal), Fusion Text formatting (`[APP]...`), and Query Parsing (time filters). |
| **Config** | `tests/v2/test_config.py` | **Environment**: Verify Path Expansion (`~/MRS` -> `/Users/...`), Environment Variable overrides, and Permission handling. |
| **Algorithm** | `tests/v2/test_search.py` | **Hybrid Search**: Verify RRF Logic (Boosting formula), Rescue Mechanism (FTS-only results), and Time Filtering accuracy. |
| **Integration** | `tests/v2/test_pipeline.py` | **Full Lifecycle**: <br>1. **Ingestion**: API returns 202 + Task is `PENDING`.<br>2. **Processing**: Worker picks up task -> Runs Mock AI -> Updates DB.<br>3. **Consistency**: Verify data exists in BOTH SQLite and LanceDB.<br>4. **Queue**: Verify **LIFO** priority (Newest First) when queue is full. |

### 2. Execution Plan

1.  **Setup**: Create `tests/v2` directory.
2.  **Infrastructure**: Implement `tests/v2/conftest.py` with `mock_settings` and `mock_ai_provider`.
3.  **Implementation**:
    *   Create `test_config.py` to lock down path handling.
    *   Create `test_utils.py` to verify helper logic.
    *   Create `test_search.py` to validate the ranking math.
    *   Create `test_pipeline.py` for the "Grand Finale" integration test.
4.  **Verification**: Run `pytest tests/v2 -v` to confirm all systems go.