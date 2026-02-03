I will implement the `OCRPostProcessor` logic directly within `openrecall/server/ocr/rapid_backend.py` to handle the geometric merging and semantic joining of OCR results.

### 1. Implementation in `rapid_backend.py`

*   **Define `OCRPostProcessor` Class**:
    *   **`process(dt_boxes, rec_res)`**: 
        *   Calculates `y_center`, `height`, and `x1` for each box.
        *   Implements the **Running Mean Algorithm** for line merging:
            *   Initial sort by `y_center`.
            *   Groups blocks into lines if `abs(y_center - current_line_mean_y) < 0.5 * current_line_mean_height`.
            *   Updates running mean `y` and `height` for each line.
        *   Sorts blocks within each line by `x1`.
        *   Applies `smart_join` to each line.
    *   **`_is_cjk(char)`**: Static method for Unicode range check (`0x4E00`-`0x9FFF`).
    *   **`_smart_join(text_list)`**: 
        *   Inserts a space between two text segments if both the end of the first and start of the second are non-CJK.
        *   Joins without space if either side is CJK.

*   **Refactor `RapidOCRBackend.extract_text`**:
    *   Extracts `dt_boxes` and `rec_res` from the raw `self.engine` result.
    *   Passes them to `OCRPostProcessor().process()`.
    *   Returns the final text joined by newlines.

*   **Add Mock Data Test**:
    *   Appends a `if __name__ == "__main__":` block with the "DeepSeek 3B" mock data to verify the logic.

### 2. Verification
*   I will run the verification using `python openrecall/server/ocr/rapid_backend.py` in the terminal.
*   I will ensure the output matches the expected "DeepSeek 3B params" with correct spacing and "深度求索" without spaces.
