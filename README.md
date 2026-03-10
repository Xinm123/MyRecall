# MyRecall v3

Take control of your digital memory with a fully open-source, privacy-first alternative to proprietary solutions like Microsoft's Windows Recall or Rewind.ai. (formerly OpenRecall)

```
   ____                   ____                  ____   
  / __ \____  ___  ____  / __ \___  _________ _/ / /   
 / / / / __ \/ _ \/ __ \/ /_/ / _ \/ ___/ __ `/ / /    
/ /_/ / /_/ /  __/ / / / _, _/  __/ /__/ /_/ / / /     
\____/ .___/\___/_/ /_/_/ |_|\___/\___/\__,_/_/_/      
      /_/
```

## What is MyRecall?

MyRecall v3 captures your digital history through automatic screenshots, then uses local AI to analyze and make them searchable. Find anything you've seen on your computer by typing natural language queries, or manually browse through your visual timeline.

## Features

- **Privacy-First**: All data stays local. No cloud, no internet required. Your screenshots never leave your device.
- **Full-Text Search**: Fast FTS5-based search with metadata filtering (app, window, browser URL, focused state).
- **Local AI Processing**: Run OCR and vision understanding entirely on your local machine. Supports multiple AI providers:
  - **Local**: Qwen-VL for vision
  - **Cloud**: OpenAI, DashScope (Qwen), and other OpenAI-compatible APIs
- **Smart Capture**: Event-driven capture (app switches, clicks, idle fallback) with debouncing and content-based deduplication.
- **Cross-Platform**: Works on Windows, macOS, and Linux (P1: macOS-only for event-driven features).
- **Runtime Control**: Pause/resume recording and AI processing from the web UI without restarting.
- **Chat with Context**: AI chat grounded in your visual history with proper citations.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         MyRecall v3 Architecture                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐                              ┌──────────────┐     │
│  │     Host     │                              │      Edge     │     │
│  │   (~/MRC)    │                              │   (~/MRS)    │     │
│  │              │                              │              │     │
│  │  ┌────────┐  │      ┌──────────────┐      │  ┌────────┐  │     │
│  │  │Capture │──│────▶│    Spool      │─────▶│─▶│  Ingest│  │     │
│  │  │Manager │  │      │ (Disk Queue) │      │  │  API   │  │     │
│  │  └────────┘  │      └──────────────┘      │  └────────┘  │     │
│  │       │       │                              │       │      │     │
│  │  ┌────────┐  │                              │  ┌────────┐  │     │
│  │  │  Hash  │  │                              │  │Worker  │  │     │
│  │  │Compute │  │                              │  │(async) │  │     │
│  │  └────────┘  │                              │  └────────┘  │     │
│  │              │                              │       │      │     │
│  │  spool/     │      HTTP POST               │  ┌─────┴────┐ │     │
│  │  *.jpg      │────▶ /v1/ingest              │  │ SQLite   │ │     │
│  │       +.json│                              │  │ + FTS5  │ │     │
│  │              │                              │  │ frames/ │ │     │
│  └──────────────┘                              │  └─────────┘ │     │
│                                                └──────────────┘     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Host (Capture + Upload)

- **Capture**: Event-driven (idle/app_switch/manual/click) with debouncing (1000ms)
- **Spool**: Local disk queue (`~/MRC/spool/`) for reliability
- **Uploader**: Background consumer with idempotent retry
- **Deduplication**: Compute `content_hash` (SHA256) for Edge-side dedup

### Edge (Processing + API)

- **Ingest**: `POST /v1/ingest` (幂等)
- **Processing**: AX-first + OCR-fallback; 索引时零 AI 增强
- **Storage**:
  - `db/edge.db`: frames, accessibility, ocr_text
  - `fts.db`: FTS5 全文索引
  - `frames/`: JPEG snapshots
  - `screenshots/`: Legacy PNG
- **Search**: FTS + 过滤；Chat 通过 Pi Sidecar

### Search Pipeline

1. **Query Sanitization**: User queries are sanitized for FTS5 MATCH syntax (token wrapping, operator escaping)
2. **Content-Type Routing**: Searches are routed by `content_type` parameter:
   - `ocr`: Searches OCR fallback results (`ocr_text_fts` + `frames_fts`)
   - `accessibility`: Searches AX-collected text (`accessibility_fts` + `accessibility` table)
   - `all` (default): Parallel search of both paths, merged by timestamp DESC
3. **Metadata Filtering**: Time range, app_name, window_name, browser_url, focused filters applied via B-tree indexes or FTS
4. **Sorting & Pagination**: Results ordered by FTS5 rank (when `q` provided) or timestamp DESC; pagination via offset/limit

**Note**: P1 uses pure full-text search (FTS5) without vector embeddings or reranking, in alignment with screenpipe's vision-only design. Vector embeddings are reserved for P2+ experimental use.

## Quick Start

### Prerequisites

- Python 3.11+
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

**Separate processes**:

```bash
# Run server (Terminal 1)
./run_server.sh --debug
```

```bash
# Run client (Terminal 2)
./run_client.sh --debug
```

Open your browser to: http://localhost:8083

## Configuration

Configure via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENRECALL_SERVER_DATA_DIR` | `~/MRS` | Edge data directory |
| `OPENRECALL_CLIENT_DATA_DIR` | `~/MRC` | Host spool directory |
| `OPENRECALL_PORT` | `8083` | Web server port |
| `OPENRECALL_CAPTURE_INTERVAL` | `10` | Legacy: screenshot interval (seconds), mapped to `idle_capture_interval_ms` if not set |
| `OPENRECALL_AI_PROVIDER` | `local` | AI provider: `local`, `dashscope`, `openai` |
| `OPENRECALL_DEVICE` | `cpu` | AI inference device: `cpu`, `cuda`, `mps` |
| `OPENRECALL_SIMILARITY_THRESHOLD` | `0.98` | Legacy MSSIM threshold (v3 uses content_hash; retained for compatibility) |

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

```
~/MRC/                              # Host spool (OPENRECALL_CLIENT_DATA_DIR)
  spool/                            # Queued screenshots awaiting upload
    *.jpg                          # Buffered frames (JPEG)
    *.json                         # Metadata alongside each frame
  screenshots/                     # Optional local copies (if enabled)

~/MRS/                              # Edge data (OPENRECALL_SERVER_DATA_DIR)
  frames/                          # v3 JPEG snapshots (main storage)
  screenshots/                     # Legacy PNG screenshots (v2 compatibility)
  db/
    edge.db                        # v3 SQLite (task queue + frames)
  fts.db                           # SQLite FTS5 (full-text search)
  lancedb/                         # Vector embeddings (P2+ experimental, not used in P1)
```

## License

AGPLv3 - See [LICENSE](LICENSE) for details.
