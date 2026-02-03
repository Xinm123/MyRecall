I will implement Phase 3 with the following plan, ensuring `conda activate MRv2` is used for all verification steps.

# Refactor OpenRecall to V2 - Phase 3: The Processing Brain (AI Pipeline)

## 1. Implement Keyword Extractor
- **File**: `openrecall/server/utils/keywords.py` (New)
- **Class**: `KeywordExtractor`
- **Logic**:
    - Tokenize text using regex `\w+`.
    - Filter stopwords (hardcoded common English list) and short words (<3 chars).
    - Return Top-10 most frequent words.

## 2. Implement Structured Fusion
- **File**: `openrecall/server/utils/fusion.py` (New)
- **Function**: `build_fusion_text(snapshot: SemanticSnapshot) -> str`
- **Logic**: Construct the text string for embedding using strict tagging format:
  ```text
  [APP] {app_name}
  [TITLE] {window_title}
  [SCENE] {scene_tag}
  [ACTION] {action_tag}
  [CAPTION] {caption}
  [KEYWORDS] {comma_separated_keywords}
  [OCR_HEAD] {first_300_chars_of_ocr}
  ```

## 3. Update Vision Provider (JSON Output)
- **File**: `openrecall/server/ai/base.py` & `openrecall/server/ai/providers.py`
- **Action**: 
    - Update `AIProvider.analyze_image` signature to return `dict` (or `Any`).
    - Update `LocalProvider`, `OpenAIProvider`, and `DashScopeProvider`.
- **Logic**:
    - Change System Prompt to force JSON output with keys: `caption`, `scene`, `action`.
    - Implement JSON parsing of the LLM response.
    - Add fallback: If parsing fails, use the raw text as `caption` and set tags to empty.

## 4. Refactor Worker Orchestrator
- **File**: `openrecall/server/worker.py`
- **Action**: Rewrite `_process_task` pipeline.
- **New Workflow**:
    1.  **OCR**: Extract text via `ocr_provider`.
    2.  **Vision**: Analyze image via `ai_provider` (now returns dict).
    3.  **Keywords**: Extract via `KeywordExtractor`.
    4.  **Construct**: Create `SemanticSnapshot` (Pydantic model).
    5.  **Fusion**: Generate dense text via `build_fusion_text`.
    6.  **Embedding**: Generate vector via `embedding_provider`.
    7.  **Save**: 
        - `VectorStore.add_snapshot()` (LanceDB)
        - `FTSStore.add_document()` (SQLite FTS)
        - `db.mark_task_completed()` (Legacy DB status update)

## 5. Verification (Env: MRv2)
- **File**: `tests/test_phase3_brain.py` (New)
- **Logic**:
    - Mock `ocr_provider`, `vision_provider`, `embedding_provider`.
    - Manually trigger `process_task`.
    - Verify data integrity in LanceDB and SQLite FTS.
- **Execution**: Run `pytest tests/test_phase3_brain.py` in `MRv2` environment.
