# Update Project Analysis Document (Bilingual & Rich Content)

## Objective
Rewrite `docs/MyRecall_V2_Analysis.md` to be a comprehensive, bilingual (English/Chinese) technical reference with rich visualizations.

## Revised Structure Plan

### 1. System Architecture / 系统架构
- **Overview**: Client-Server decoupled architecture.
- **Visual**: High-level architecture Mermaid diagram.
- **Client Architecture**: Recorder (Capture), Buffer (Persistence), Uploader (Sync).
- **Server Architecture**: API Gateway, Async Worker, Hybrid Search Engine.

### 2. Client-Side Mechanics / 客户端机制 (New Detailed Section)
- **Capture Logic**: `mss` based capture, MSSIM similarity deduplication (saving space).
- **Buffering**: Atomic write operations (`.tmp` -> `.json`) ensuring data safety during crashes.
- **Visual**: Flowchart showing Capture -> Filter (MSSIM) -> Buffer -> Upload.

### 3. Server Processing Pipeline / 服务端处理流水线
- **Visual**: Sequence diagram of the "Ingest -> Process -> Index" lifecycle.
- **Ingestion**: Fire-and-forget API design for low latency.
- **Worker Logic**:
    - **Dynamic Queues**: LIFO (Priority for new) vs FIFO (Backlog clearing).
    - **AI Processing**: OCR -> VLM (Vision) -> Keyword Extraction -> Fusion.
    - **Dual-Write**: Consistency between Vector Store (LanceDB) and Metadata DB (SQLite).

### 4. Hybrid Search Engine / 混合搜索引擎 (Core Feature)
- **Visual**: 3-Stage Pipeline Diagram (Retrieval -> Fusion -> Rerank).
- **Stage 1 (Recall)**: Parallel Vector (Semantic) + FTS (Keyword) search.
- **Stage 2 (Fusion)**: RRF algorithm with "FTS Rescue" mechanism.
- **Stage 3 (Rerank)**: Cross-Encoder (Qwen) deep relevance scoring.

### 5. Data Schema / 数据结构
- **Relational**: SQLite tables (`entries`, `ocr_fts`).
- **Vector**: LanceDB `SemanticSnapshot` model.

### 6. Configuration / 配置说明
- Key environment variables table (Bilingual descriptions).

## Execution
I will rewrite `docs/MyRecall_V2_Analysis.md` using this structure, ensuring every section has clear English and Chinese explanations, and utilizing Mermaid diagrams extensively to meet the "图文并茂" (rich text and images) requirement.
