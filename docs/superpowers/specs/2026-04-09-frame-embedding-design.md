# Frame Embedding Design

**Date:** 2026-04-09
**Author:** Claude
**Status:** Approved

## Overview

Add multimodal embedding support for frames using qwen3-vl-embedding model. This enables:
1. **Semantic search**: Natural language queries like "GitHub login page" to find semantically similar screenshots
2. **Similar frame lookup**: Find visually/semantically similar frames for deduplication or analysis

The design uses a hybrid search approach combining FTS5 text search with vector similarity search.

## Goals

- Support multimodal (image + text) embedding generation via API calls
- Enable semantic search for natural language queries
- Enable similar frame lookup functionality
- Integrate with existing FTS5 search via hybrid retrieval
- Support both cloud APIs (DashScope) and local network services (vLLM)

## Non-Goals

- Local model inference (delegated to external API services)
- Batch embedding generation (planned for v2)
- Separate image-only and text-only embeddings (single fused embedding for simplicity)

---

## Architecture

### High-Level Flow

```
Frame Ingestion
      │
      ▼
OCR/AX Processing ──▶ full_text ready
      │
      ├──────────────────────────────────┐
      ▼                                  ▼
DescriptionWorker                    EmbeddingWorker
(parallel)                           (parallel)
      │                                  │
      ▼                                  ▼
frame_descriptions              frame_embeddings (LanceDB)
      │                                  │
      └──────────────┬───────────────────┘
                     ▼
              Search Request
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
     FTS Search            Vector Search
         │                       │
         └───────────┬───────────┘
                     ▼
            RRF Fusion
                     │
                     ▼
             Final Results
```

### Components

1. **EmbeddingWorker**: Background worker that generates embeddings for frames
2. **MultimodalEmbeddingProvider**: Protocol for embedding API providers
3. **EmbeddingStore**: LanceDB storage for frame embeddings
4. **HybridSearchEngine**: Fuses FTS and vector search results

---

## Data Model

### SQLite Extensions

#### frames table extension

```sql
ALTER TABLE frames ADD COLUMN embedding_status TEXT DEFAULT NULL;
  -- NULL = not queued
  -- 'pending' = queued for embedding
  -- 'processing' = worker is processing
  -- 'completed' = embedding available
  -- 'failed' = generation failed after max retries
```

#### embedding_tasks table

```sql
CREATE TABLE embedding_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    frame_id INTEGER NOT NULL REFERENCES frames(id),
    status TEXT DEFAULT 'pending',     -- pending / processing / completed / failed
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    next_retry_at TIMESTAMP,           -- For exponential backoff
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    UNIQUE(frame_id)
);

CREATE INDEX idx_et_status ON embedding_tasks(status);
CREATE INDEX idx_et_next_retry ON embedding_tasks(next_retry_at);
CREATE INDEX idx_et_frame_id ON embedding_tasks(frame_id);
```

### LanceDB Schema

```python
from lancedb.pydantic import LanceModel, Vector
from pydantic import Field

class FrameEmbedding(LanceModel):
    """Frame embedding stored in LanceDB"""
    frame_id: int = Field(description="Reference to frames.id")
    embedding_vector: Vector(1024) = Field(description="qwen3-vl-embedding output")
    embedding_model: str = Field(default="qwen3-vl-embedding")

    # Redundant metadata for filtering without JOIN
    timestamp: str = Field(description="ISO8601 UTC")
    app_name: str = Field(default="")
    window_name: str = Field(default="")
```

---

## Embedding Strategy

### Single Fused Embedding

Use image + text fusion embedding:

```python
embedding = provider.embed_image(
    image_path=frame.image_path,
    text=frame.full_text  # accessibility_text or ocr_text
)
```

**Rationale:**
- qwen3-vl-embedding is designed for multimodal retrieval
- Single embedding simplifies storage and search
- Text differences reflect semantic differences (useful for both search and similarity)

### Text Source

Use `frames.full_text` as the text input:
- If AX succeeded: `full_text = accessibility_text`
- If AX failed: `full_text = ocr_text`

---

## Provider Architecture

### Protocol

```python
# openrecall/server/embedding/providers/base.py

class MultimodalEmbeddingProvider(ABC):
    """Multimodal embedding provider protocol"""

    @abstractmethod
    def embed_image(
        self,
        image_path: str,
        text: Optional[str] = None
    ) -> np.ndarray:
        """Generate embedding for image with optional text context.

        Args:
            image_path: Path to image file
            text: Optional text context (OCR/AX text)

        Returns:
            Normalized embedding vector
        """
        raise NotImplementedError

    @abstractmethod
    def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for text query.

        Args:
            text: Query text

        Returns:
            Normalized embedding vector
        """
        raise NotImplementedError
```

### OpenAI-Compatible Provider

Supports cloud APIs (DashScope) and local network services (vLLM):

```python
class OpenAIMultimodalEmbeddingProvider(MultimodalEmbeddingProvider):
    """OpenAI-compatible multimodal embedding provider"""

    def __init__(
        self,
        api_key: str,
        model_name: str,
        api_base: str = ""
    ):
        self.api_key = api_key.strip() if api_key else ""
        self.model_name = model_name.strip()
        self.api_base = _normalize_api_base(api_base or "https://api.openai.com/v1")

    def embed_image(self, image_path: str, text: Optional[str] = None) -> np.ndarray:
        # API call with image + optional text
        ...

    def embed_text(self, text: str) -> np.ndarray:
        # API call with text only (for queries)
        ...
```

### Configuration

```toml
# server.toml

[embedding]
enabled = true
provider = "openai"           # openai (supports DashScope and vLLM)
model = "qwen3-vl-embedding"  # Embedding model name
api_key = ""                  # API key (optional for local vLLM)
api_base = ""                 # API base URL (e.g., http://localhost:8000/v1)
dim = 1024                    # Embedding dimension

# Worker settings (optional, defaults shown)
poll_interval_ms = 2000       # Polling interval for task queue
max_retries = 3               # Max retry attempts before marking failed
```

**Examples:**

```toml
# Local vLLM service (no auth required)
[embedding]
enabled = true
provider = "openai"
model = "qwen3-vl-embedding"
api_base = "http://localhost:8000/v1"

# DashScope cloud API
[embedding]
enabled = true
provider = "openai"
model = "text-embedding-v3"
api_key = "sk-xxx"
api_base = "https://dashscope.aliyuncs.com/compatible-mode/v1"
```

---

## Worker Architecture

### EmbeddingWorker

Independent worker running parallel to DescriptionWorker:

```python
class EmbeddingWorker:
    """Background worker for embedding generation"""

    def run(self):
        while self.running:
            # 1. Poll for pending tasks
            task = self._claim_pending_task()
            if not task:
                sleep(self.poll_interval)
                continue

            try:
                # 2. Load frame data
                frame = self._load_frame(task.frame_id)

                # 3. Generate embedding
                embedding = self._provider.embed_image(
                    image_path=frame.image_path,
                    text=frame.full_text
                )

                # 4. Store in LanceDB
                self._store.save_embedding(frame.id, embedding)

                # 5. Mark completed
                self._mark_completed(task.id)

            except Exception as e:
                self._handle_failure(task, e)
```

### Trigger Timing

EmbeddingWorker runs **parallel** to DescriptionWorker:
- Both are triggered after OCR/AX processing completes
- No dependency between them
- Each has its own task queue

```
Frame ready (OCR complete)
    │
    ├──▶ Create description_task
    │
    └──▶ Create embedding_task
```

### Retry Backoff

| Attempt | Delay |
|---------|-------|
| Retry 1 | 1 minute |
| Retry 2 | 5 minutes |
| Retry 3 | 15 minutes |
| After 3 | `status='failed'` |

---

## Hybrid Search

### Search Flow

```
Query "GitHub login page"
        │
        ▼
┌───────────────────────┐
│   Parallel Execution  │
│  ┌─────────────────┐  │
│  │  FTS5 Search    │──┼──▶ Results A (ranked by FTS)
│  └─────────────────┘  │
│  ┌─────────────────┐  │
│  │ Vector Search   │──┼──▶ Results B (ranked by similarity)
│  └─────────────────┘  │
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│    RRF Fusion         │
└───────────────────────┘
        │
        ▼
   Final Results
```

### RRF (Reciprocal Rank Fusion)

```python
def reciprocal_rank_fusion(
    fts_results: List[SearchResult],
    vector_results: List[VectorResult],
    k: int = 60,
    fts_weight: float = 0.5,
    vector_weight: float = 0.5,
) -> List[Tuple[int, float]]:
    """
    RRF formula: score = Σ (weight / (k + rank))

    Advantages:
    - No score normalization needed
    - Rank-based, robust to outliers
    """
    scores = defaultdict(float)

    for rank, result in enumerate(fts_results, start=1):
        scores[result.frame_id] += fts_weight / (k + rank)

    for rank, result in enumerate(vector_results, start=1):
        scores[result.frame_id] += vector_weight / (k + rank)

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

---

## API Design

### Extended Search Endpoint

```
GET /v1/search?q=GitHub登录&mode=hybrid&fts_weight=0.5&vector_weight=0.5

Parameters:
- mode: 'fts' (FTS only) | 'vector' (vector only) | 'hybrid' (default)
- fts_weight: Weight for FTS results in hybrid mode (0.0-1.0, default 0.5)
- vector_weight: Weight for vector results in hybrid mode (0.0-1.0, default 0.5)
```

### Similar Frames Endpoint

```
GET /v1/frames/{frame_id}/similar?limit=10

Response:
{
  "frame_id": 123,
  "similar_frames": [
    {"frame_id": 456, "similarity": 0.95, "timestamp": "...", "app_name": "..."},
    ...
  ]
}
```

### Embedding Management Endpoints

```
POST /v1/frames/{frame_id}/embedding
# Manually trigger embedding generation

GET /v1/embedding/tasks/status
# Return queue statistics:
# {"pending": 15, "processing": 2, "completed": 1280, "failed": 3}

POST /v1/admin/embedding/backfill
# Trigger backfill for historical frames
```

---

## File Structure

```
openrecall/
├── server/
│   ├── embedding/                    # NEW: Embedding feature module
│   │   ├── __init__.py
│   │   ├── models.py                 # FrameEmbedding Pydantic model
│   │   ├── providers/
│   │   │   ├── __init__.py
│   │   │   ├── base.py               # MultimodalEmbeddingProvider protocol
│   │   │   ├── openai.py             # OpenAI-compatible provider
│   │   │   └── dashscope.py          # DashScope provider (optional)
│   │   ├── service.py                # EmbeddingService
│   │   └── worker.py                 # EmbeddingWorker
│   ├── database/
│   │   ├── migrations/
│   │   │   └── 20260409120000_add_frame_embedding.sql
│   │   ├── embedding_store.py        # NEW: LanceDB embedding store
│   │   └── frames_store.py           # EXTEND: embedding_status field
│   ├── search/
│   │   ├── engine.py                 # EXISTING: FTS search
│   │   └── hybrid_engine.py          # NEW: Hybrid search
│   └── api_v1.py                     # EXTEND: New endpoints
└── tests/
    ├── test_embedding_provider.py
    ├── test_embedding_worker.py
    ├── test_hybrid_search.py
    └── test_embedding_api.py
```

---

## Implementation Order

1. **Database migration** - Add embedding_status and embedding_tasks table
2. **Provider layer** - MultimodalEmbeddingProvider protocol + OpenAI implementation
3. **LanceDB store** - EmbeddingStore with FrameEmbedding schema
4. **Worker** - EmbeddingWorker with retry logic
5. **Hybrid search** - RRF fusion + extended search API
6. **Similar frames API** - /frames/{id}/similar endpoint
7. **Tests** - Unit + integration tests

---

## Open Questions

1. **Embedding dimension**: Confirm qwen3-vl-embedding output dimension (assumed 1024)
2. **API format**: Verify exact API request/response format for multimodal embedding
3. **Batch processing**: Consider batch embedding API for efficiency (v2)

---

## References

- qwen3-vl-embedding: https://github.com/QwenLM/Qwen3-VL-Embedding
- Frame Description Design: `docs/superpowers/specs/2026-03-24-frame-description-design.md`
- FTS Unification Design: `docs/superpowers/specs/2026-03-25-fts-unification-design.md`
