## Context

The `/v1/frames/{id}/context` endpoint (`openrecall/server/api_v1.py:get_frame_context`) currently always includes a `nodes` array in its response. The `nodes` field is parsed from `accessibility_tree_json` stored in the database. For simple chat grounding queries, `nodes` represents significant token overhead (potentially 40-60% of response size) without proportional value when only aggregated text context is needed.

## Goals / Non-Goals

**Goals:**
- Add `include_nodes` query parameter to `/v1/frames/{id}/context`
- Default to `false` (nodes omitted) to reduce token usage for default consumers
- Allow explicit opt-in with `include_nodes=true` to preserve existing behavior for consumers that need `nodes`
- When `include_nodes=false`, skip `accessibility_tree_json` parsing entirely to reduce compute overhead
- URL extraction from text via regex remains functional when `include_nodes=false`

**Non-Goals:**
- Adding a complementary `include_text=false` or `include_urls=false` parameter
- Changing the shape of `nodes` entries
- Modifying `max_nodes` behavior (remains as limiting count, not omitting)
- Screenpipe parity for `include_nodes` (screenpipe does not have this parameter)

## Decisions

### Decision 1: Default value — `false`

**Chosen:** `include_nodes` defaults to `false`.

**Rationale:** The primary motivation is token reduction. Defaulting to `false` means consumers who need `nodes` must explicitly opt in, which is the correct safety-first default for a feature whose primary value is reducing output size.

**Alternative considered — default `true`:**
- Less disruptive to existing consumers
- But means the "cheap" path is opt-in, defeating the purpose of making the lightweight response the default
- We want `include_nodes=false` to be the common case

### Decision 2: Placement of conditional logic — Store layer

**Chosen:** The `FramesStore.get_frame_context()` method handles the `include_nodes` flag.

**Rationale:** Parsing `accessibility_tree_json` into a node list happens in the store layer. When `include_nodes=false`, the store can skip the JSON parse entirely, reducing both CPU and memory overhead. URL extraction from text (via `_extract_urls_from_text`) is independent of node parsing and remains in the store. The API layer passes the flag through without response-shaping logic.

**Alternative considered — API layer only:**
- Simpler store interface (no new parameter)
- But `accessibility_tree_json` would still be parsed even when nodes aren't needed
- Wasteful for the primary motivation

### Decision 3: API response — field omission vs. empty array

**Chosen:** When `include_nodes=false`, the `nodes` field is completely absent from the response (not `nodes: []`).

**Rationale:** The motivation is token reduction. Returning `nodes: []` still costs 2 tokens and can confuse consumers expecting the field to always exist. Omitting the field is cleaner and more consistent with how `nodes_truncated` behaves (only present when relevant).

### Decision 4: URL extraction when `include_nodes=false`

**Chosen:** URLs are still extracted from `text` via regex when `include_nodes=false`. Link-node URL extraction is skipped.

**Rationale:** Text-based URL extraction (`_extract_urls_from_text`) is independent of node parsing — it runs against the already-available `text` field. Skipping it would lose URL data entirely. Link-node URL extraction (which pulls URLs from `AXLink`/`AXHyperlink`/`link` role nodes) is a secondary optimization that requires node parsing, so it is skipped when `include_nodes=false`. In practice, most URLs in accessibility-captured frames also appear in the aggregated `text`, so text-based extraction covers the common case.

**Screenpipe alignment:** No comparable pattern — screenpipe does not offer this parameter.

### Decision 5: Existing truncation parameters remain unchanged

`max_text_length` and `max_nodes` continue to work as before. When `include_nodes=false`, `max_nodes` has no effect (since nodes are not returned). No conflict arises.

## Risks / Trade-offs

- **[Breaking contract change]** Any caller that depends on `nodes` without explicitly passing `include_nodes=true` will silently stop receiving it. This includes the as-yet-unimplemented `myrecall-search` skill (see [Future skill impact]).
- **[Future skill impact]** The `myrecall-search` skill does not yet exist (see docs/v3/chat/mvp.md for the design). When it is implemented, it MUST explicitly pass `include_nodes=true` on `/v1/frames/{id}/context` calls that need structural node data. The Frame Context Contract in mvp.md (§4) will be updated accordingly (Task §4).
- **[Incomplete URL extraction]** When `include_nodes=false`, URLs that only appear in link-node text (not in aggregated text) are missed. This is acceptable since text-based extraction covers most real-world URLs.

## Migration Plan

This change deploys in a single phase — default is `false` from day one.

1. **Implement** — add `include_nodes` parameter with default `False` in store and API layer
2. **Update tests** — all existing tests that assert `nodes` presence MUST pass `include_nodes=True` explicitly (Task §3)
3. **Update docs** — Frame Context Contract reflects new default (Task §4)
4. **No rollback concern** — any caller can opt back into full nodes by passing `include_nodes=true`

## Open Questions

- Should the `myrecall-search` skill default to `include_nodes=true` always, or selectively based on query type?
