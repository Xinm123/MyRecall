# Proposal: Add `include_nodes` parameter to frame context endpoint

## Why

The `/v1/frames/{id}/context` endpoint always includes a `nodes` array in its response. For simple text-grounding queries (e.g., "what was on my screen?"), `text` + `urls` provide sufficient context, but `nodes` adds significant token overhead (potentially 40-60% of total response size). An opt-out parameter allows chat consumers to reduce token usage when structural node data is not needed.

## What Changes

- **New query parameter** `include_nodes` on `GET /v1/frames/{id}/context`
  - Type: boolean (`true`/`false`)
  - Default: `false` (nodes omitted by default — this is a deliberate contract change)
  - When `false`: response omits `nodes` and `nodes_truncated` fields entirely
  - When `true`: response includes `nodes` and `nodes_truncated` (existing behavior)

- **URL extraction preserved**: When `include_nodes=false`, URLs are still extracted from `text` via regex. Link-node URL extraction is skipped, but text-based URL extraction covers the common case.

- **Breaking change for callers relying on `nodes`**: Callers already using `max_text_length`/`max_nodes` without `include_nodes` will get the new default (`include_nodes=false`), meaning they will no longer receive `nodes` unless they explicitly opt in with `include_nodes=true`. Callers relying on `nodes` must update to pass `include_nodes=true`.

## Capabilities

### New Capabilities

- `frame-context-nodes-control`: Controls whether the `nodes` field is included in frame context API responses. The endpoint accepts `include_nodes` as a query parameter to gate node serialization. When disabled, the response contract shrinks to `frame_id`, `text`, `text_source`, `urls`, `browser_url`, `status`. The `nodes_truncated` field is also omitted when nodes are disabled.

## Impact

- **API layer** (`openrecall/server/api_v1.py`): New query parameter parsing and conditional response shaping
- **Store layer** (`openrecall/server/database/frames_store.py`): `get_frame_context()` skips `accessibility_tree_json` parsing and node list building when `include_nodes=False`, reducing compute and memory overhead
- **Chat MVP**: When implemented, the `myrecall-search` skill MUST explicitly pass `include_nodes=true` on `/v1/frames/{id}/context` calls that need structural node data.
- **Contract**: The default response shape of `/v1/frames/{id}/context` changes from `{..., nodes, urls, ...}` to `{urls, ...}` (nodes opt-in). Existing consumers not passing `include_nodes` will silently receive a different response shape.
