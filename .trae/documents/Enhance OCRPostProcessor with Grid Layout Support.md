I will update `openrecall/server/ocr/rapid_backend.py` with the improved `OCRPostProcessor` class that supports grid layouts, column detection, and language-aware spacing.

### 1. Update `OCRPostProcessor` Class in `rapid_backend.py`

*   **Logic Refinements**:
    *   **Step 1 (Data Standardization)**: Update `_get_box_metrics` to also compute `x_end` (max x) for gap calculation.
    *   **Step 2 (Row Clustering)**: Keep the Running Mean Algorithm for merging items into rows based on Y-coordinates.
    *   **Step 3 (Column Detection & Smart Joining)**:
        *   Implement `_smart_join_line(line_items)` method.
        *   Iterate through sorted items in a row.
        *   Calculate `gap = current_x_start - previous_x_end`.
        *   **Condition**: If `gap > 2.0 * previous_height`, treat as a column break and insert `\t`.
        *   **Condition**: Else, check CJK status. If both Non-CJK, insert space. Else, join tightly.

*   **Helper Methods**:
    *   `_is_cjk(char)`: Remains the same.

*   **Mock Data Update**:
    *   Replace the `if __name__ == "__main__":` block with the new "ModelScope Grid Layout" mock data provided by the user (GLM-4, Minimind, Qwen columns).
    *   Update assertions to verify `\t` separation for wide gaps and correct spacing for mixed languages.

### 2. Verification
*   Run `conda activate MRv2 && python openrecall/server/ocr/rapid_backend.py` to confirm the new logic passes the updated tests.
