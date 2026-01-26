I will provide a detailed technical explanation of the FTS behavior.

### Explanation Summary
1.  **Implicit AND Operator**: SQLite FTS5 (the underlying engine) treats spaces between words as an implicit **AND** operator.
    *   Query: `mermaid` $\to$ Finds documents containing "mermaid".
    *   Query: `mermaid show` $\to$ Finds documents containing "mermaid" **AND** "show".
2.  **Data Mismatch**: The reason `mermaid show` returns no FTS matches is that the target document likely contains the word "mermaid" (in OCR/Caption) but does **not** contain the word "show".
3.  **Hybrid Strategy**: This "strictness" is by design.
    *   **FTS (Keyword)** is used for **High Precision** (exact matches boost the score).
    *   **Vector (Semantic)** is used for **High Recall** (fuzzy matches).
    *   If you search `mermaid show`, the **Vector Search** *should* still find the document (because "mermaid" is semantically dominant), but it won't get the "FTS Boost" because it's not an exact keyword match for *both* terms.

I will not modify code unless you explicitly ask to change this behavior (e.g., to support `OR` or lenient matching), as the current logic aligns with the Hybrid RRF design (Vector for fuzzy, FTS for exact boosting).