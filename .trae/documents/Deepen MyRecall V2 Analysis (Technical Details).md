# Deep Dive Expansion based on Codebase Verification

## Objective
Update Sections 3 and 4 of `docs/MyRecall_V2_Analysis.md` based *strictly* on the verified implementation details in `worker.py`, `engine.py`, and `providers.py`.

## Expansion Plan

### Section 3: Server Processing Pipeline / 服务端处理流水线 (Strictly Verified)

#### 3.1 Task Queue & Flow Control (任务队列与流控)
- **Source**: `worker.py`
- **Dynamic Queue Logic**:
    - **LIFO (Burst Mode)**: Triggered when `queue_size > lifo_threshold`. Prioritizes recent tasks to ensure instant searchability.
    - **FIFO (Catch-up Mode)**: Standard processing for backlog.
- **Concurrency**: SQLite lock via `mark_task_processing` prevents duplicate processing.

#### 3.2 AI Processing Implementation (AI 处理链实现)
- **Source**: `providers.py` & `worker.py`
- **OCR Strategy**:
    - **Local**: Wraps `openrecall.server.ocr` (likely Tesseract/Paddle/EasyOCR wrapper).
    - **Cloud**: Uses VLM with a specific prompt ("Extract all visible text...") effectively turning VLM into a high-context OCR.
- **VLM (Vision Analysis)**:
    - **Local (Qwen-VL)**: Includes specific image resizing logic (max dimension constraint) for CPU optimization.
    - **Prompt Engineering**: Enforces strict JSON output (`caption`, `scene`, `action`) and includes markdown stripping logic for robustness.
- **Data Fusion**:
    - **Source**: `worker.py` -> `build_fusion_text`
    - **Format**: Explicitly combines Metadata, AI Caption, and OCR text into a single block for the Embedding model.

### Section 4: Hybrid Search Engine / 混合搜索引擎 (Strictly Verified)

#### 4.1 Search Architecture (搜索架构)
- **Source**: `engine.py`
- **Parallel Retrieval**:
    - **Vector**: LanceDB search with time-range filtering.
    - **FTS**: SQLite BM25 search on keywords extracted from user query.

#### 4.2 Fusion Algorithm: Weighted Boosting (融合算法：加权提升)
- **Source**: `engine.py`
- **Correction**: Explicitly state **"Not RRF"**.
- **The Formula**:
    - **Base Score**: Vector Similarity (or `0.2` for FTS-only rescue).
    - **Boost**: `0.3 * (1.0 - (rank / total_fts))`
    - **Final**: `Base + Boost`
- **Rationale**: A semantic match (high vector score) gets a "bonus" if it also matches keywords exactly (high FTS rank).

#### 4.3 Deep Reranking (深度重排)
- **Source**: `engine.py` & `reranker.py`
- **Context Construction**:
    - Builds a structured string: `[Metadata]... [Visual Context]... [OCR Content]...`.
    - Priorities: Metadata > Visual > OCR.
- **Scoring**:
    - Cross-Encoder model computes relevance (0-1).
    - This score **overwrites** the previous fusion score for the top candidates.

## Execution
I will rewrite Sections 3 and 4 with these verified details, ensuring no "hallucinated" features (like RRF) are present.
