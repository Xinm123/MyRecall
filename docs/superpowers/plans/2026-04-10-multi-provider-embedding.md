# Multi-Provider Embedding Architecture Implementation Plan

> **Status:** ✅ COMPLETED (2026-04-10)

**Goal:** Refactor embedding providers to support three distinct API formats: OpenAI (text-only), DashScope (skeleton), and custom multimodal API (qwen3-vl-embedding).

**Architecture:** Create three separate provider classes with distinct request formats. Factory selects provider by name (`openai`, `dashscope`, `multimodal`). Each provider implements `MultimodalEmbeddingProvider` protocol with `embed_image()` and `embed_text()` methods.

**Tech Stack:** Python, requests, numpy, pytest

---

## Implementation Summary

### Commits

| Commit | Description |
|--------|-------------|
| `1663535` | feat(embedding): add QwenVLEmbeddingProvider for qwen3-vl-embedding API |
| `08896b1` | feat(embedding): add DashScopeEmbeddingProvider skeleton |
| `fcb6d07` | refactor(embedding): rename to OpenAIEmbeddingProvider, text-only support |
| `34745b3` | feat(embedding): export all embedding providers |
| `6340bb1` | feat(embedding): add provider selection in factory |
| `73deb44` | fix(config): add lancedb_path property to ServerSettings |
| `0297754` | docs: update embedding documentation for multi-provider architecture |

### Files Changed

| File | Change |
|------|--------|
| `openrecall/server/embedding/providers/multimodal.py` | Created: QwenVLEmbeddingProvider |
| `openrecall/server/embedding/providers/dashscope.py` | Created: DashScopeEmbeddingProvider skeleton |
| `openrecall/server/embedding/providers/openai.py` | Refactored: renamed class, text-only, error for images |
| `openrecall/server/embedding/providers/__init__.py` | Updated: export all providers |
| `openrecall/server/ai/factory.py` | Updated: provider selection logic |
| `openrecall/server/config_server.py` | Fixed: added lancedb_path property |
| `myrecall_server.toml.example` | Updated: embedding provider options |
| `CLAUDE.md` | Updated: architecture documentation |
| `docs/superpowers/specs/2026-04-09-frame-embedding-design.md` | Updated: reference to multi-provider spec |

### Provider Capabilities

| Provider | `embed_image()` | `embed_text()` | Use Case |
|----------|-----------------|----------------|----------|
| `multimodal` (QwenVL) | ✅ Fusion embedding | ✅ | Custom qwen3-vl-embedding API |
| `openai` | ❌ Raises error | ✅ | OpenAI text-embedding API |
| `dashscope` | ❌ NotImplementedError | ❌ NotImplementedError | Future implementation |

### Configuration

```toml
[embedding]
enabled = true
provider = "multimodal"        # Options: multimodal, openai, dashscope
model = "qwen3-vl-embedding"
api_base = "http://10.77.3.162:8070/v1"
dim = 1024
```

### E2E Verification

Tested via `test_embedding_e2e.sh`:
- Frame upload → Task queue → Worker processing → LanceDB storage
- Vector search: `/v1/search?q=test&mode=vector`
- Hybrid search: `/v1/search?q=test&mode=hybrid`
- Similar frames: `/v1/frames/{frame_id}/similar`

---

## File Structure

```
openrecall/server/embedding/providers/
├── __init__.py          # Exports all providers
├── base.py              # MultimodalEmbeddingProvider protocol
├── openai.py            # OpenAIEmbeddingProvider (text-only)
├── dashscope.py         # DashScopeEmbeddingProvider (skeleton)
└── multimodal.py        # QwenVLEmbeddingProvider (qwen3-vl-embedding)
```

---

## Task Checklist

### Task 1: Create QwenVLEmbeddingProvider ✅

- [x] Step 1.1: Write failing test for QwenVLEmbeddingProvider initialization
- [x] Step 1.2: Run test to verify it fails
- [x] Step 1.3: Create multimodal.py with QwenVLEmbeddingProvider class
- [x] Step 1.4: Run initialization tests
- [x] Step 1.5: Write failing test for embed_text
- [x] Step 1.6: Run test to verify it passes
- [x] Step 1.7: Write failing test for embed_image (fusion)
- [x] Step 1.8: Run tests to verify they pass
- [x] Step 1.9: Commit QwenVLEmbeddingProvider

### Task 2: Refactor OpenAI Provider ✅

- [x] Step 2.1: Write failing test for embed_image error
- [x] Step 2.2: Run test to verify it fails
- [x] Step 2.3: Refactor openai.py - rename class and add image error
- [x] Step 2.4: Update test class name
- [x] Step 2.5: Run all OpenAI provider tests
- [x] Step 2.6: Commit OpenAI provider refactor

### Task 3: Create DashScope Provider Skeleton ✅

- [x] Step 3.1: Write failing test for DashScope provider skeleton
- [x] Step 3.2: Run test to verify it fails
- [x] Step 3.3: Create dashscope.py skeleton
- [x] Step 3.4: Run tests to verify they pass
- [x] Step 3.5: Commit DashScope provider skeleton

### Task 4: Update Provider Exports ✅

- [x] Step 4.1: Update __init__.py exports
- [x] Step 4.2: Verify imports work
- [x] Step 4.3: Commit exports update

### Task 5: Update Factory Provider Selection ✅

- [x] Step 5.1: Update get_multimodal_embedding_provider function
- [x] Step 5.2: Run factory tests
- [x] Step 5.3: Commit factory update

### Task 6: Final Verification ✅

- [x] Step 6.1: Run all embedding tests
- [x] Step 6.2: Run full test suite
- [x] Step 6.3: Final commit with all changes
- [x] Documentation update (added post-implementation)

---

## Summary

| Task | Description | Status |
|------|-------------|--------|
| 1 | Create QwenVLEmbeddingProvider | ✅ Complete |
| 2 | Refactor OpenAI provider | ✅ Complete |
| 3 | Create DashScope skeleton | ✅ Complete |
| 4 | Update exports | ✅ Complete |
| 5 | Update factory | ✅ Complete |
| 6 | Final verification | ✅ Complete |
| - | Documentation update | ✅ Complete |

---

## References

- Design Spec: `docs/superpowers/specs/2026-04-10-multi-provider-embedding-design.md`
- Frame Embedding Design: `docs/superpowers/specs/2026-04-09-frame-embedding-design.md`
