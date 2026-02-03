I will generate a detailed project analysis report in Markdown format at `docs/MyRecall_V2_Analysis.md`.

## Report Content & Visuals

I will use **Mermaid.js** code blocks to create visual diagrams directly within the Markdown file.

1.  **System Architecture & Data Flow**
    -   **Visual**: A high-level **Flowchart** (Mermaid `graph TD`) showing the movement of data from the Client $\to$ API $\to$ Worker $\to$ Databases (SQLite + LanceDB).
    -   **Analysis**: Explanation of the client-server separation (`MRS`/`MRC`) and component responsibilities.

2.  **Pipeline Analysis (Deep Dive)**
    -   **Ingestion**:
        -   **Visual**: A **Sequence Diagram** (Mermaid `sequenceDiagram`) showing the async `POST /upload` flow.
        -   **Text**: Analysis of the "Fire-and-Forget" mechanism.
    -   **Processing**:
        -   **Visual**: A **State Diagram** (Mermaid `stateDiagram`) for the Task Lifecycle (`Pending` $\to$ `OCR` $\to$ `Vision` $\to$ `Embedding` $\to$ `Completed`).
        -   **Text**: Detailed steps of the worker loop, queue priority (LIFO/FIFO), and model interactions.
    -   **Search**:
        -   **Visual**: A **Flowchart** illustrating the Hybrid RRF logic (Parallel Vector/Keyword Search $\to$ Fusion).
        -   **Text**: Mathematical explanation of the ranking and boosting algorithms.

3.  **Data Schema & Models**
    -   **Visual**: An **Entity Relationship (ER) Diagram** (Mermaid `erDiagram`) for SQLite tables (`entries`, `ocr_fts`) and LanceDB structure.
    -   **Text**: Detailed field definitions, data types, and model configurations (Qwen, Embedding Dimensions).

4.  **Configuration & Environment**
    -   Summary of key settings in `config.py` and environment variable overrides.