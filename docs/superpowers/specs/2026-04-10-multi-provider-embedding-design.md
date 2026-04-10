# Multi-Provider Embedding Architecture Design

**Date:** 2026-04-10
**Author:** Claude
**Status:** Approved

## Overview

Refactor embedding providers to support multiple API formats with distinct implementations. Each provider handles its own request/response format, enabling compatibility with OpenAI, DashScope native API, and custom multimodal services.

## Goals

- Support three distinct embedding providers: `openai`, `dashscope`, `multimodal`
- Each provider has its own request format matching the target API
- Simple configuration: select provider by name, no auto-detection magic
- Preserve OpenAI compatibility for future multimodal support

## Non-Goals

- Auto-detection of API format based on URL
- Complex format parameter layering
- DashScope implementation details (skeleton only for now)

---

## Architecture

### Provider Selection Flow

```
[embedding] config
      │
      ▼
provider = "multimodal" │ "openai" │ "dashscope"
      │
      ▼
get_multimodal_embedding_provider()
      │
      ├─ "openai"     → OpenAIEmbeddingProvider
      ├─ "dashscope"  → DashScopeEmbeddingProvider
      └─ "multimodal" → MultimodalEmbeddingProvider
```

### File Structure

```
openrecall/server/embedding/providers/
├── __init__.py          # Export all providers
├── base.py              # MultimodalEmbeddingProvider protocol (existing)
├── openai.py            # OpenAI official API (refactored)
├── dashscope.py         # DashScope native API (skeleton)
└── multimodal.py        # Custom multimodal API (new)
```

---

## Provider Specifications

### 1. MultimodalEmbeddingProvider (Custom API)

**Target API:** Custom service at `/v1/embeddings/multimodal`

**Request Format:**

```python
# embed_image(image_path, text)
POST /v1/embeddings/multimodal
{
    "images": ["<base64_encoded_jpeg>"],  // Pure base64, no prefix
    "texts": ["<ocr_or_ax_text>"],        // Optional
    "model": "qwen3-vl-embedding",
    "encoding_format": "float"
}

# embed_text(text) - for search queries
POST /v1/embeddings/multimodal
{
    "texts": ["<query_text>"],
    "model": "qwen3-vl-embedding",
    "encoding_format": "float"
}
```

**Response Format:**

```json
{
    "data": [{"index": 0, "embedding": [0.1, 0.2, ...]}],
    "model": "qwen3-vl-embedding"
}
```

**Implementation Notes:**
- Image encoding: Read JPEG file, base64 encode (no `data:image/jpeg;base64,` prefix)
- L2 normalize output vector
- Handle empty text case (skip `texts` field)

---

### 2. OpenAIEmbeddingProvider (Refactored)

**Target API:** OpenAI official `/v1/embeddings`

**Current State:** Attempts multimodal format that doesn't match any real API

**Refactored Behavior:**

```python
# embed_image() - NOT SUPPORTED
def embed_image(self, image_path, text=None):
    raise EmbeddingProviderRequestError(
        "OpenAI does not support image embedding. "
        "Use 'multimodal' or 'dashscope' provider."
    )

# embed_text() - Standard OpenAI format
POST /v1/embeddings
{
    "model": "text-embedding-3-small",
    "input": "<text>",
    "encoding_format": "float"
}
```

**Rationale:**
- OpenAI currently only supports text embedding
- Preserve class for future multimodal support
- Clear error message guides users to correct provider

---

### 3. DashScopeEmbeddingProvider (Skeleton)

**Target API:** DashScope native API (format TBD)

**Skeleton Implementation:**

```python
class DashScopeEmbeddingProvider(MultimodalEmbeddingProvider):
    """DashScope native API provider (implementation pending)."""

    def __init__(self, api_key: str, model_name: str, api_base: str = ""):
        self.api_key = api_key
        self.model_name = model_name
        self.api_base = api_base or "https://dashscope.aliyuncs.com/api/v1"

    def embed_image(self, image_path: str, text: Optional[str] = None) -> np.ndarray:
        raise NotImplementedError(
            "DashScope multimodal embedding not yet implemented. "
            "See: https://help.aliyun.com/document_detail/..."
        )

    def embed_text(self, text: str) -> np.ndarray:
        raise NotImplementedError(
            "DashScope text embedding not yet implemented."
        )
```

---

## Configuration

### TOML Examples

```toml
# Custom multimodal API (current deployment)
[embedding]
enabled = true
provider = "multimodal"
model = "qwen3-vl-embedding"
api_base = "http://10.77.3.162:8070/v1"
dim = 1024

# DashScope native (future)
[embedding]
provider = "dashscope"
model = "text-embedding-v3"
api_key = "sk-xxx"
api_base = "https://dashscope.aliyuncs.com/api/v1"

# OpenAI official (text only for now)
[embedding]
provider = "openai"
model = "text-embedding-3-small"
api_key = "sk-xxx"
```

---

## Factory Updates

### `openrecall/server/ai/factory.py`

```python
def get_multimodal_embedding_provider() -> "MultimodalEmbeddingProvider":
    """Get or create a cached MultimodalEmbeddingProvider instance."""
    from openrecall.server.embedding.providers import (
        MultimodalEmbeddingProvider,
        OpenAIEmbeddingProvider,
        DashScopeEmbeddingProvider,
        MultimodalEmbeddingProvider as CustomMultimodalProvider,
    )

    capability = "multimodal_embedding"
    cached = _instances.get(capability)
    if cached is not None:
        return cached

    provider = settings.embedding_provider.strip().lower()
    model_name = settings.embedding_model
    api_key = settings.embedding_api_key
    api_base = settings.embedding_api_base

    if provider == "openai":
        instance: MultimodalEmbeddingProvider = OpenAIEmbeddingProvider(
            api_key=api_key,
            model_name=model_name,
            api_base=api_base,
        )
    elif provider == "dashscope":
        instance = DashScopeEmbeddingProvider(
            api_key=api_key,
            model_name=model_name,
            api_base=api_base,
        )
    elif provider == "multimodal":
        instance = CustomMultimodalProvider(
            api_key=api_key,
            model_name=model_name,
            api_base=api_base,
        )
    else:
        raise AIProviderConfigError(f"Unknown embedding provider: {provider}")

    _instances[capability] = instance
    return instance
```

---

## Naming Changes

| Old Name | New Name | Reason |
|----------|----------|--------|
| `OpenAIMultimodalEmbeddingProvider` | `OpenAIEmbeddingProvider` | OpenAI doesn't support multimodal embedding yet |

---

## Implementation Order

1. Create `multimodal.py` with correct API format
2. Refactor `openai.py` (rename class, text-only support, clear error for images)
3. Create `dashscope.py` skeleton
4. Update `__init__.py` exports
5. Update `factory.py` provider selection
6. Add/update tests for each provider
7. Update documentation

---

## Open Questions

1. **DashScope API format:** To be documented when implementation is needed
2. **OpenAI multimodal future:** Monitor OpenAI API updates for image embedding support

---

## References

- Custom multimodal API docs: Provided by user (see conversation)
- OpenAI Embeddings API: https://platform.openai.com/docs/api-reference/embeddings
- DashScope API: https://help.aliyun.com/product/441277.html
