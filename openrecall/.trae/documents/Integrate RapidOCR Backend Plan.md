I have updated the plan to strictly ensure existing OCR methods are preserved and environment settings are handled correctly.

### 1. Dependencies & Environment
- **Modify `setup.py`**: Add `rapidocr_onnxruntime` to `install_requires`.
- **Create `requirements.txt`**: Add `rapidocr_onnxruntime`.
- **Update `openrecall/shared/config.py`**: Add `ocr_rapid_use_local` and `ocr_rapid_model_dir` to `Settings` class to support `.env` configuration.

### 2. Safe Refactoring of OCR Module
- **Convert `openrecall/server/ocr.py` to a Package**:
  - Create directory `openrecall/server/ocr/`.
  - **Preserve Existing Logic**: Move the current content of `ocr.py` to `openrecall/server/ocr/doctr_backend.py` without changes.
  - **Maintain Compatibility**: Create `openrecall/server/ocr/__init__.py` that explicitly re-exports `extract_text_from_image` from `doctr_backend`. This ensures all existing imports continue to work unchanged.

### 3. Implement RapidOCR Backend
- **Create `openrecall/server/ocr/rapid_backend.py`**:
  - Implement `RapidOCRBackend` with Singleton Pattern.
  - Implement logic to check `OPENRECALL_OCR_RAPID_USE_LOCAL`.
  - **Model Loading**:
    - If `True`: Load models (det/rec/cls) from `OPENRECALL_OCR_RAPID_MODEL_DIR`.
    - If `False`: Initialize with default auto-download.
  - Implement `extract_text(self, image)` for PIL/Numpy inputs.

### 4. Integration
- **Update `openrecall/server/ai/providers.py`**:
  - Add `RapidOCRProvider` class (inheriting from `OCRProvider`) that wraps `RapidOCRBackend`.
- **Update `openrecall/server/ai/factory.py`**:
  - Update `get_ocr_provider()` to return `RapidOCRProvider` when `OPENRECALL_OCR_PROVIDER` is set to `rapidocr`.

### 5. Verification
- Verify imports and instantiation.
- Print summary of changes.
