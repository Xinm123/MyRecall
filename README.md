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
- **Hybrid AI Search**: Combines FTS5 full-text search with LanceDB vector search via RRF fusion. Supports FTS-only, vector-only, and hybrid modes.
- **AI Processing**: Run OCR and vision understanding locally or via cloud APIs:
  - **Local**: Qwen-VL for vision
  - **Cloud**: OpenAI, DashScope (Qwen), SiliconFlow, and other OpenAI-compatible APIs
- **Smart Capture**: Event-driven capture (app switches, clicks, idle fallback) with debouncing and content-based deduplication.
- **Accessibility-First Text Extraction**: Uses macOS AX (accessibility) as primary text source, with OCR fallback.
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
│  │   (~/.myrecall/client)    │                              │   (~/.myrecall/server)    │     │
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

- **Capture**: Event-driven (idle/app_switch/manual/click) with three-layer debouncing (3000ms)
- **Spool**: Local disk queue (`~/.myrecall/client/spool/`) for reliability
- **Uploader**: Background consumer with idempotent retry
- **Deduplication**: `capture_id` idempotency + trigger/capture coordination; `content_hash` is reserved for future use

### Edge (Processing + API)

- **Ingest**: `POST /v1/ingest` (幂等)
- **Processing**: OCR, AI description generation, vector embedding pipeline
- **Storage**:
  - `db/edge.db`: frames, embedding_tasks
  - `fts.db`: FTS5 全文索引
  - `frames/`: JPEG snapshots
  - `screenshots/`: Legacy PNG
  - `lancedb/`: Vector embeddings
- **Search**: Hybrid search (FTS5 + LanceDB via RRF fusion) + FTS-only mode + Vector-only mode

### Search Pipeline

1. **Query Sanitization**: User queries are sanitized for FTS5 MATCH syntax (token wrapping, operator escaping)
2. **Search Modes**: Three modes — `fts` (BM25 full-text), `vector` (cosine similarity), `hybrid` (RRF fusion of both)
3. **Metadata Filtering**: Time range, app_name, window_name, browser_url, focused filters applied via B-tree indexes or FTS
4. **Sorting & Pagination**: Results ordered by relevance rank (when `q` provided) or timestamp DESC; pagination via offset/limit

### Chat & AI Assistant

The client web UI includes an AI chat interface grounded in your visual history:

- **Grounded Responses**: Answers cite actual screenshot frames via OCR text and AI-generated descriptions
- **Streaming**: Real-time SSE streaming for responsive chat experience
- **Session Management**: Multi-turn conversations with history, reset, and per-conversation context
- **Provider Flexibility**: Configurable LLM provider, model, and API key via web UI settings or TOML config

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
./run_server.sh --mode local --debug
```

```bash
# Run client (Terminal 2)
./run_client.sh --mode local --debug
```

Open your browser to: http://localhost:8889

## Configuration

Configure via environment variables or TOML config files (recommended):

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENRECALL_SERVER_DATA_DIR` | `~/.myrecall/server` | Edge data directory |
| `OPENRECALL_CLIENT_DATA_DIR` | `~/.myrecall/client` | Host spool directory |
| `OPENRECALL_PORT` | `8083` | Edge API server port |
| `OPENRECALL_CLIENT_WEB_PORT` | `8889` | Client web UI server port |
| `OPENRECALL_CLIENT_WEB_ENABLED` | `true` | Enable client web UI server |
| `OPENRECALL_DEBUG` | `false` | Enable debug logging |
| `OPENRECALL_AI_PROVIDER` | `local` | AI provider: `local`, `dashscope`, `openai` |
| `OPENRECALL_DEVICE` | `cpu` | AI inference device: `cpu`, `cuda`, `mps` |
| `OPENRECALL_CAPTURE_INTERVAL` | `10` | Legacy: screenshot interval (seconds), mapped to `idle_capture_interval_ms` if not set |
| `OPENRECALL_SIMILARITY_THRESHOLD` | `0.98` | Legacy MSSIM threshold (v3 uses content_hash; retained for compatibility) |

### TOML Configuration (Recommended)

Create `server-local.toml` and `client-local.toml` in the project root (or `~/.myrecall/`). Example `server-local.toml`:

```toml
[server]
host = "127.0.0.1"
port = 8083

[paths]
data_dir = "~/.myrecall/server"

[description]
enabled = true
provider = "openai"
model = "Qwen/Qwen3-VL-8B-Instruct"
api_key = ""          # fill in your own API key
api_base = "https://api.siliconflow.cn/v1/"
```

Run with `./run_server.sh --mode local` to auto-load `server-local.toml`, or pass `--config=/path/to/config.toml` explicitly.

### Timezone Note

MyRecall currently operates in **UTC+8 (Asia/Shanghai)** timezone for all display and query timestamps. The `local_timestamp` column in the database stores timestamps in this timezone without an offset suffix. Cross-timezone support is on the roadmap.

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
~/.myrecall/client/                              # Host spool (OPENRECALL_CLIENT_DATA_DIR)
  spool/                            # Queued screenshots awaiting upload
    *.jpg                          # Buffered frames (JPEG)
    *.json                         # Metadata alongside each frame
  screenshots/                     # Optional local copies (if enabled)
  buffer/                          # Local buffer when server is unavailable
  cache/                           # Cache directory

~/.myrecall/server/                              # Edge data (OPENRECALL_SERVER_DATA_DIR)
  frames/                          # v3 JPEG snapshots (main storage)
  screenshots/                     # Legacy PNG screenshots (v2 compatibility)
  db/
    edge.db                        # v3 SQLite (frames + embedding_tasks)
  fts.db                           # SQLite FTS5 (full-text search)
  lancedb/                         # Vector embeddings
```

## License

AGPLv3 - See [LICENSE](LICENSE) for details.
