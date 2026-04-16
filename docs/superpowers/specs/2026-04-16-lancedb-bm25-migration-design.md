# BM25 Migration to LanceDB with jieba Tokenizer

**Date:** 2026-04-16
**Status:** Approved
**Author:** Claude

## Summary

迁移 BM25 搜索从 SQLite FTS5 到 LanceDB FTS，同时引入 jieba 分词以支持中文语义切词。统一 LanceDB 作为唯一的搜索后端（向量 + BM25），SQLite FTS 保留但不参与新数据流程。

## Motivation

1. **Operational simplicity** — 两个搜索系统（SQLite FTS + LanceDB 向量）合并为一个
2. **Chinese language support** — SQLite FTS5 `unicode61` tokenizer 对中文按字符切分，搜索质量差；jieba 提供语义分词

## Constraints

- embedding 生成使用**原始文本**（不变）
- `tokenized_text` 和 `full_text` 都存入 LanceDB
- 已有数据不迁移（将全部删除）
- SQLite FTS 保留一段时间，但**不再写入新数据**
- 主流程 pipeline 不涉及 SQLite FTS

## Architecture

### After Migration

```
                        /v1/search API
                               |
              ┌────────────────┼────────────────┐
              │                │                │
         mode=fts         mode=vector      mode=hybrid
              │                │                │
              v                v                v
      ┌──────────────┐  ┌─────────────┐  ┌────────────────┐
      │ LanceDB FTS  │  │ LanceDB     │  │ LanceDB FTS +  │
      │ BM25+jieba   │  │ Vector (不变) │  │ Vector + RRF   │
      └──────┬───────┘  └──────┬──────┘  └───────┬────────┘
             │                  │                 │
             └──────────────────┼─────────────────┘
                                │
                    ┌──────────┴──────────┐
                    │  LanceDB (单一DB)    │
                    │  表: frame_embeddings │
                    │  • embedding_vector   │
                    │  • tokenized_text    │
                    │  • full_text         │
                    │  索引:               │
                    │  • FTS(tokenized)    │
                    │  • IVF_HNSW(vector)  │
                    └─────────────────────┘
```

### Write Path (Ingest Pipeline)

```
frames.full_text
    │
    ├──→ EmbeddingWorker.generate_embedding(text=原始文本)
    │    │
    │    └──→ qwen3-vl-embedding ──→ embedding_vector (不变)
    │
    └──→ save_embedding(tokenized_text, full_text)
         │
         └──→ LanceDB FTS index on tokenized_text
```

### Query Path

```
用户查询 "Python教程"
    │
    └──→ tokenize_text(jieba) ──→ "Python 教程"
         │
         ├──→ mode=fts  ──→ LanceDB FTS (tokenized_text)
         ├──→ mode=vector ──→ LanceDB vector (query_embedding)
         └──→ mode=hybrid ──→ LanceDB FTS + vector + RRF (Python层)
```

## Design

### 1. Tokenizer Module

**File:** `openrecall/server/search/tokenizer.py` (new)

```python
import jieba

def tokenize_text(text: str) -> str:
    """中英文混合分词。

    jieba 自动保留英文单词原样（如 "Python" 不会被切开）。
    中文按语义切分（如 "机器学习" → "机器 学习"）。
    """
    if not text:
        return ""
    tokens = jieba.cut(text.strip(), cut_all=False)
    return " ".join(tokens)
```

**Behavior:**
- 输入 `""` → 返回 `""`
- 输入 `"今天天气不错"` → 返回 `"今天 天气 不错"`
- 输入 `"Python教程"` → 返回 `"Python 教程"` (jieba 跳过英文)
- 英文为主的文本输出与 SQLite FTS `unicode61` 等价

### 2. LanceDB Schema Extension

**File:** `openrecall/server/embedding/models.py`

扩展 `FrameEmbedding` 模型，新增字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `tokenized_text` | str | jieba 分词后的文本（空格分隔），用于 BM25 FTS |
| `full_text` | str | 原始全文（用于调试/展示） |

`embedding_vector` 字段**不受影响**（仍由原始文本生成）。

**Backward compatibility:** 旧记录无 `tokenized_text`/`full_text` 字段，查询时返回空。

### 3. EmbeddingStore Changes

**File:** `openrecall/server/database/embedding_store.py`

#### 3.1 Schema Update

更新 `FrameEmbeddingSchema`（pydantic LanceModel）加上新字段：

```python
class FrameEmbeddingSchema(LanceModel):
    frame_id: int = Field(description="Reference to frames.id")
    embedding_vector: Vector(1024) = Field(...)
    embedding_model: str = Field(...)
    timestamp: str = Field(...)
    app_name: str = Field(...)
    window_name: str = Field(...)
    tokenized_text: str = Field(default="", description="jieba-tokenized text for BM25")
    full_text: str = Field(default="", description="Original full text")
```

#### 3.2 FTS Search Method

> **Note:** LanceDB FTS does not natively support time range or metadata filters via the FTS query itself. Filters on `app_name`, `window_name`, `timestamp` are applied in the Python layer after LanceDB returns results (via `FramesStore.get_frames_by_ids` + metadata check). This is acceptable since LanceDB is fast at initial retrieval and filtering in Python is cheap at result-set size.

```python
def search_fts(self, query: str, limit: int = 20) -> List[dict]:
    """BM25 FTS search via LanceDB.

    Args:
        query: Pre-tokenized (jieba) query string
        limit: Max results

    Returns:
        List of matching records. Each dict contains frame_id and a BM25
        score in the "_score" key. Note: verify the actual column name by
        checking returned dict keys — if "_score" is absent, check for
        "score" or other names in the LanceDB result dict.
    """
    table = self.db.open_table(self.table_name)
    result = (
        table.search(query, query_type="fts")
        .limit(limit)
        .to_list()
    )
    return result
```

#### 3.3 FTS Index Creation

在 `_init_table()` 或新增 `_ensure_fts_index()` 中：

```python
def _ensure_fts_index(self) -> None:
    """Ensure FTS index exists on tokenized_text column."""
    table = self.db.open_table(self.table_name)
    try:
        table.create_fts_index("tokenized_text")
        logger.info("Created FTS index on tokenized_text")
    except Exception as e:
        if "already exists" in str(e):
            pass
        else:
            raise
```

### 4. EmbeddingService Changes

**File:** `openrecall/server/embedding/service.py`

扩展 `save_embedding` 方法签名：

```python
def save_embedding(
    self,
    conn,
    frame_id: int,
    embedding: FrameEmbedding,
    timestamp: str,
    app_name: str = "",
    window_name: str = "",
    tokenized_text: str = "",   # 新增
    full_text: str = "",        # 新增
) -> None:
    embedding.frame_id = frame_id
    embedding.timestamp = timestamp
    embedding.app_name = app_name
    embedding.window_name = window_name
    embedding.tokenized_text = tokenized_text  # 新增
    embedding.full_text = full_text            # 新增
    self.embedding_store.save_embedding(embedding)
```

### 5. EmbeddingWorker Changes

**File:** `openrecall/server/embedding/worker.py`

在 `save_embedding` 调用处增加两个参数：

```python
from openrecall.server.search.tokenizer import tokenize_text

# worker.py — _process_batch 中
raw_text = frame.get("full_text") or ""
tokenized = tokenize_text(raw_text)

self.service.save_embedding(
    conn,
    frame_id,
    embedding,
    timestamp=frame.get("timestamp") or "",
    app_name=frame.get("app_name") or "",
    window_name=frame.get("window_name") or "",
    tokenized_text=tokenized,   # 新增
    full_text=raw_text,         # 新增
)
```

### 6. HybridSearchEngine Changes

**File:** `openrecall/server/search/hybrid_engine.py`

#### 6.1 New LanceDB FTS Query Path

**Browse mode (empty query)** uses the existing `_get_recent_embedded_frames` method — no new code needed. It already returns recent `queryable` frames from SQLite. **Query mode** is new:

```python
def _fts_only_search(self, q: str, limit: int, offset: int, **kwargs) -> Tuple[List[Dict, int]]:
    """FTS-only search via LanceDB with jieba tokenizer."""
    from openrecall.server.search.tokenizer import tokenize_text
    from openrecall.server.database.frames_store import FramesStore

    frames_store = FramesStore()

    # Browse mode (no query): reuse existing method
    if not q or q.isspace():
        return self._get_recent_embedded_frames(frames_store.db_path, limit, offset)

    # Tokenize query with jieba
    tokenized_q = tokenize_text(q)

    # Search LanceDB FTS
    lance_results = self._embedding_store.search_fts(tokenized_q, limit=limit + offset)

    # Fetch full frame data from SQLite
    frame_ids = [r["frame_id"] for r in lance_results]
    frame_data_map = frames_store.get_frames_by_ids(frame_ids)

    results = []
    for r in lance_results[offset:offset + limit]:
        frame = frame_data_map.get(r["frame_id"], {})
        ts = frame.get("timestamp") if frame.get("timestamp") else (r.get("timestamp") or "")
        results.append({
            "frame_id": r["frame_id"],
            "score": r.get("_score"),
            "fts_score": r.get("_score"),
            "cosine_score": None,       # FTS-only has no vector score
            "vector_rank": None,        # FTS-only has no vector rank
            "timestamp": ts,
            "text": (r.get("full_text") or "")[:200],
            "text_source": frame.get("text_source", ""),
            "app_name": frame.get("app_name") or r.get("app_name", ""),
            "window_name": frame.get("window_name") or r.get("window_name", ""),
            "browser_url": frame.get("browser_url"),
            "focused": frame.get("focused"),
            "device_name": frame.get("device_name") or "monitor_0",
            "frame_url": f"/v1/frames/{r['frame_id']}",
            "embedding_status": frame.get("embedding_status", ""),
        })

    return results, len(lance_results)
```

> **Note:** `timestamp` fallback uses `frame.get("timestamp")` first, then `r.get("timestamp")` only if the frame-level value is falsy. `_get_recent_embedded_frames` handles browse mode; query mode uses this new method.

#### 6.2 Hybrid Search Update

`_hybrid_search` 中 FTS 部分改走 LanceDB：

```python
def _hybrid_search(self, q: str, fts_weight: float, vector_weight: float,
                   limit: int, offset: int, **kwargs) -> Tuple[List[Dict], int]:
    # Tokenizer import is in _fts_only_search; no new import needed here.

    # LanceDB FTS with jieba (through _fts_only_search)
    fts_results, _ = self._fts_only_search(q, limit=limit * 2, offset=0, **kwargs)

    # LanceDB vector (unchanged)
    vector_results = []
    vector_similarities = {}
    if q and not q.isspace():
        # ... vector search unchanged ...
        pass

    # RRF fusion (unchanged)
    merged = reciprocal_rank_fusion(
        fts_results, vector_results, fts_weight=fts_weight, vector_weight=vector_weight
    )
    # ...
```

### 7. SQLite FTS Handling

**File:** `openrecall/server/search/engine.py`

- 保留 `SearchEngine` 类（SQLite FTS 查询）
- 标记为 **deprecated**（docstring 注明）
- 不再被 `HybridSearchEngine` 调用
- 后续单独 PR 删除

**Files unchanged:**
- `openrecall/server/database/frames_store.py` — 不涉及
- `openrecall/server/database/migrations/` — 不新增 migration
- `openrecall/server/api_v1.py` — 路由不变

## Dependency

**File:** `pyproject.toml`

```toml
[project.dependencies]
jieba = ">=0.42"
```

## API Compatibility

| 端点 | 行为 |
|------|------|
| `GET /v1/search?mode=fts&q=...` | LanceDB FTS (jieba分词) |
| `GET /v1/search?mode=vector&q=...` | LanceDB vector (不变) |
| `GET /v1/search?mode=hybrid&q=...` | LanceDB FTS + vector + RRF (不变) |
| `GET /v1/search?q=...` (默认) | mode=hybrid (不变) |

## Rollout Plan

> **Task dependency:** Task 3 must complete before Task 4. Task 3 adds `tokenized_text`/`full_text` fields to the pydantic `FrameEmbedding` model; Task 4 mirrors these fields in the LanceDB `FrameEmbeddingSchema`. Both tasks modify the same class hierarchy.

### Phase 1: Implementation
1. 添加 `jieba` 依赖
2. 实现 `tokenizer.py`
3. 扩展 LanceDB schema
4. 实现 `search_fts()` 方法
5. 更新 `EmbeddingService.save_embedding`
6. 更新 `EmbeddingWorker` 传入 `tokenized_text`
7. 更新 `HybridSearchEngine` 使用 LanceDB FTS
8. 标记 `SearchEngine` 为 deprecated

### Phase 2: Verification
- 手动测试中英文查询结果
- 性能对比（旧 vs 新 FTS 路径）
- 确认 SQLite FTS 不再被写入

### Phase 3: Cleanup (后续 PR)
- 删除 SQLite FTS triggers（迁移 SQL）
- 删除 `SearchEngine` 类
- 删除 `openrecall/server/search/engine.py`

## Risks

| 风险 | 缓解 |
|------|------|
| jieba 分词质量不如预期 | 前期手动验证中英文混合场景 |
| LanceDB FTS 性能不如 SQLite FTS | benchmark 对比；LanceDB 是列存，对扫描友好 |
| 冷数据删除前误删 FTS | Phase 1 不动 SQLite FTS，仅保留 |

## Success Criteria

1. 新 ingest 的 frame 可通过 LanceDB FTS 搜索到
2. jieba 分词后中文查询质量明显提升
3. `mode=hybrid` 混合搜索正常工作
4. `mode=fts` 路径走 LanceDB（而非 SQLite FTS）
5. 所有现有测试通过
