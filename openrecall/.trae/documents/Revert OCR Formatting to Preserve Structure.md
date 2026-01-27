I will proceed with the following plan, ensuring to use the `MRv2` environment for any execution.

### 1. OCR Text Formatting (Revert to Newlines)
*   **Action**: Modify `openrecall/server/ocr/rapid_backend.py`.
    *   Change the text joining logic back to `\n` (newline) instead of space.
    *   **Preserve Sorting**: Keep the logic that sorts text blocks by vertical and horizontal position, as this ensures correct reading order.
*   **Rationale**: While spaces reduce "fragmentation", they destroy the structure of code blocks and UI menus (as seen in your log). Newlines are the standard practice for preserving visual structure in OCR.

### 2. Update Tests
*   **Action**: Update `tests/v2/test_ocr_rapid.py` to assert that output contains newlines (`Hello\nWorld`) instead of spaces.

### 3. Explanation regarding Title
*   I will provide a detailed explanation that the "Translated Title" (`维多雷/...`) is caused by a browser translation plugin modifying the window title, which OpenRecall faithfully records.

### 4. Verification
*   Run tests using `conda activate MRv2` (implied by environment context) to confirm the fix.
