# OpenRecall AI Assistant Instructions

## 🔭 Project Overview
OpenRecall is a localized, privacy-first alternative to Windows Recall. It captures screen history, processes it locally (OCR & Embeddings), and provides a semantic search interface.

### 🏗 Architecture & Core Components
- **Entry Point**: `openrecall/app.py` initializes the Flask web server and starts the `record_screenshots_thread` background thread.
- **Recording Loop**: `openrecall/screenshot.py` manages the capture cycle:
  1.  **Capture**: Uses `mss` to grab screenshots of monitors.
  2.  **Deduplication**: Uses `is_similar` (SSIM) to discard duplicate frames.
  3.  **Processing**: Extracts text (`ocr.py`) and generates embeddings (`nlp.py`).
  4.  **Storage**: Saves image to disk (`.webp`) and metadata to `recall.db`.
- **Storage**:
  - **Database**: SQLite (`entries` table with timestamp, text, embeddings).
  - **Images**: Saved as high-quality WebP files in the app data directory.
- **Search**: Performed using cosine similarity on embeddings (`openrecall/nlp.py`).

### 📦 Data Layout
Data is stored in OS-specific app data folders (defined in `openrecall/config.py`):
- **macOS**: `~/Library/Application Support/openrecall`
- **Windows**: `%APPDATA%\openrecall`
- **Linux**: `~/.local/share/openrecall`
- **Structure**:
  - `recall.db`: SQLite database.
  - `screenshots/`: Directory containing captured images.
  - `sentence_transformers/`: Cached ML models.

## 🛠 Developer Workflows

### Running the Application
Run the module directly from the root workspace:
```bash
python -m openrecall.app
```
**Arguments:**
- `--storage-path <path>`: Override default data directory.
- `--primary-monitor-only`: Capture only the main display.

### Testing
- Tests are located in `tests/`.
- Run with `pytest`.

### Dependencies & Integration
- **Platform Specifics**: `setup.py` defines OS-specific dependencies (e.g., `pyobjc` for macOS, `pywin32` for Windows).
- **OCR**: Relies on `python-doctr` (or similar libraries depending on config).
- **Embeddings**: Uses `sentence_transformers` (requires internet on first run to download models).

## 📝 Coding Conventions & Patterns
- **Threading**: The recording loop runs in a separate `threading.Thread` initiated in `app.py`. Ensure thread safety when modifying shared resources.
- **Type Hinting**: Use standard Python type hints (`List`, `Optional`, `Tuple`).
- **Path Management**: Always use `os.path.join` and reference paths from `openrecall.config`.
- **Database Access**: Use the context managers in `openrecall/database.py` for safe connection handling. `sqlite3.Row` is used for dictionary-like column access.
- **Web UI**: `app.py` uses simplified inline Jinja2 strings (`render_template_string`). Maintain this pattern for simple views unless complexity demands separate files.

### ⚠️ Known Implementation Details
- **Text Extraction**: Only screenshots with extractable text are indexed into the database.
- **Image Comparison**: Uses SSIM (Structural Similarity Index) to prevent storage bloat.
