# MyRecall v3

## Project Overview
MyRecall v3 (formerly OpenRecall) is a fully open-source, privacy-first alternative to proprietary digital memory solutions like Microsoft's Windows Recall or Rewind.ai. It captures your digital history through automatic screenshots and uses local AI to analyze and make them searchable via natural language queries.

### Key Features
- **Privacy-First**: All data stays local; no cloud is required.
- **Full-Text Search**: Fast FTS5-based search with metadata filtering (app, window, browser URL, focused state).
- **Local AI Processing**: Runs OCR and vision understanding entirely on the local machine (supports Qwen-VL locally or cloud providers like OpenAI/DashScope).
- **Architecture**: Split into Host (Capture + Upload via `openrecall.client`) and Edge (Processing + API via `openrecall.server`).

## Architecture & Data Storage
- **Host (Client)**: Captures events (idle, app switches, clicks), debounces, and spools them locally to a disk queue (default: `~/MRC`).
- **Edge (Server)**: Ingests the spool via an API (`POST /v1/ingest`), performs OCR, and indexes data using SQLite FTS5 (default: `~/MRS`).

## Building and Running

### Prerequisites
- Python 3.11+
- Virtual Environment recommended

### Installation
```bash
# Clone the repository and install dependencies
pip install -e .
```

### Running
The project is run in two separate processes:

**Server (Edge):**
```bash
./run_server.sh --debug
```
*Configuration via environment variables or `myrecall_server.env`.*

**Client (Host):**
```bash
./run_client.sh --debug
```
*Configuration via environment variables or `myrecall_client.env`.*

Open your browser to: `http://localhost:8083`

## Development Conventions & Testing
- **Language**: Python 3.11+
- **Testing Framework**: `pytest`
- **Running Tests**: Run `pytest` from the root directory. The `pytest.ini` is configured to run tests inside the `tests/` directory, ignoring archived tests and excluding heavy tests (e2e, perf, security, model) by default.
- **Test Markers**: 
  - `unit` (Unit Tests)
  - `integration` (Integration/Module Tests)
  - `e2e` (End-to-End System Tests)
  - `perf` (Performance Benchmark Tests)
  - `security` (Security Tests)
  - `model` (Tests requiring models/large resources)
- **Formatting & Linting**: Follows standard Python development conventions (likely formatted with `ruff`/`black` based on the presence of `.ruff_cache`).
- **License**: AGPLv3.
