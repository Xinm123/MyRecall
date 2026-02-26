# OpenRecall

Take control of your digital memory with a fully open-source, privacy-first alternative to proprietary solutions like Microsoft's Windows Recall or Rewind.ai.

```
   ____                   ____                  ____   
  / __ \____  ___  ____  / __ \___  _________ _/ / /   
 / / / / __ \/ _ \/ __ \/ /_/ / _ \/ ___/ __ `/ / /    
/ /_/ / /_/ /  __/ / / / _, _/  __/ /__/ /_/ / / /     
\____/ .___/\___/_/ /_/_/ |_|\___/\___/\__,_/_/_/      
    /_/                                                                                                                         
```

## What is OpenRecall?

OpenRecall captures your digital history through automatic screenshots, then uses local AI to analyze and make them searchable. Find anything you've seen on your computer by typing natural language queries, or manually browse through your visual timeline.

## Features

- **Privacy-First**: All data stays local. No cloud, no internet required. Your screenshots and AI analysis never leave your device.
- **Hybrid Search**: Combines semantic vector search (LanceDB) with full-text search (SQLite FTS5) and intelligent reranking.
- **Local AI Processing**: Run OCR, vision understanding, and embeddings entirely on your local machine. Supports multiple AI providers:
  - **Local**: Qwen-VL for vision, Qwen-Text-Embeddings for semantic search
  - **Cloud**: OpenAI, DashScope (Qwen), and other OpenAI-compatible APIs
- **Smart Capture**: MSSIM-based deduplication, idle detection, and configurable capture intervals.
- **Cross-Platform**: Works on Windows, macOS, and Linux.
- **Runtime Control**: Pause/resume recording and AI processing from the web UI without restarting.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         OpenRecall Architecture                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐                              ┌──────────────┐     │
│  │    Client    │                              │    Server    │     │
│  │   (~/MRC)    │                              │   (~/MRS)    │     │
│  │              │                              │              │     │
│  │  ┌────────┐  │      ┌──────────────┐      │  ┌────────┐  │     │
│  │  │Recorder │──│────▶│   Buffer      │─────▶│─▶│  API   │  │     │
│  │  │(Producer)│ │      │ (Disk Queue) │      │  │ Flask  │  │     │
│  │  └────────┘  │      └──────────────┘      │  └────────┘  │     │
│  │       │       │                              │       │      │     │
│  │  ┌────────┐  │                              │  ┌────────┐  │     │
│  │  │Uploader│  │                              │  │ Worker │  │     │
│  │  │Consumer│  │                              │  │(async) │  │     │
│  │  └────────┘  │                              │  └────────┘  │     │
│  │              │                              │       │      │     │
│  │  buffer/    │      HTTP POST               │  ┌─────┴────┐ │     │
│  │  *.webp     │────▶ /api/upload             │  │ SQLite   │ │     │
│  │       multipart/form-data *.json     │    │  │ LanceDB  │ │     │
│  │              │                              │  │Screenshots│ │     │
│  └──────────────┘                              │  └─────────┘ │     │
│                                                └──────────────┘     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Client (Producer-Consumer)

- **Recorder**: Captures screenshots at configurable intervals using `mss`
- **Deduplication**: Uses MSSIM to skip similar frames
- **Buffer**: Local disk queue (`~/MRC/buffer/`) ensures no data loss when server is unavailable
- **Uploader**: Background consumer that uploads buffered screenshots to the server

### Server

- **Fast Ingestion**: `/api/upload` saves screenshots immediately and returns `202 Accepted`
- **Processing Worker**: Background thread handles OCR → Vision → Keywords → Embedding
- **Storage**:
  - `recall.db` (SQLite): Task queue and legacy fields
  - `fts.db` (SQLite FTS5): Full-text search index
  - `lancedb/`: Vector embeddings for semantic search
  - `screenshots/`: PNG image files

### Search Pipeline

1. **Query Parser**: Handles time filters (`today`, `yesterday`) and quoted keywords
2. **Dual Retrieval**: Vector search (LanceDB) + Keyword search (FTS5)
3. **Fusion**: Linear combination with boost for keyword matches
4. **Reranking**: Cross-encoder model reorders Top 30 results

## Quick Start

### Prerequisites

- Python 3.9+
- macOS / Windows / Linux

### Installation

```bash
# Clone the repository
git clone https://github.com/openrecall/openrecall.git
cd openrecall

# Install dependencies
pip install -e .
```

### Running

**Combined mode** (server + client in one process):

```bash
python -m openrecall.main
```

**Separate processes**:

```bash
# Terminal 1: Start server
python -m openrecall.server

# Terminal 2: Start client
python -m openrecall.client
```

Open your browser to: http://localhost:8083

## Configuration

Configure via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENRECALL_SERVER_DATA_DIR` | `~/MRS` | Server data directory |
| `OPENRECALL_CLIENT_DATA_DIR` | `~/MRC` | Client data directory |
| `OPENRECALL_PORT` | `8083` | Web server port |
| `OPENRECALL_CAPTURE_INTERVAL` | `10` | Screenshot interval (seconds) |
| `OPENRECALL_AI_PROVIDER` | `local` | AI provider: `local`, `dashscope`, `openai` |
| `OPENRECALL_DEVICE` | `cpu` | AI inference device: `cpu`, `cuda`, `mps` |
| `OPENRECALL_SIMILARITY_THRESHOLD` | `0.98` | MSSIM dedup threshold |

### Using Cloud AI

To use cloud AI instead of local models:

```bash
# DashScope (Qwen)
export OPENRECALL_AI_PROVIDER=dashscope
export OPENRECALL_AI_API_KEY=your-api-key

# OpenAI
export OPENRECALL_AI_PROVIDER=openai
export OPENRECALL_AI_API_KEY=sk-...
export OPENRECALL_AI_API_BASE=https://api.openai.com/v1
```

## Data Storage

Default directories:

```
~/MRC/                    # Client data
  buffer/
    *.webp               # Buffered screenshots
    *.json               # Metadata
  screenshots/           # Optional local copies

~/MRS/                    # Server data
  screenshots/
    *.png               # Processed screenshots
  db/
    recall.db           # SQLite (queue + legacy)
  fts.db                # SQLite FTS5 (full-text index)
  lancedb/              # Vector database
```

## License

AGPLv3 - See [LICENSE](LICENSE) for details.
