## 1. FramesStore — add include_nodes to get_frame_context

- [x] 1.1 Add `include_nodes: bool = False` parameter to `FramesStore.get_frame_context()`
- [x] 1.2 When `include_nodes=False`, skip `accessibility_tree_json` parsing and node list construction
- [x] 1.3 When `include_nodes=False`, skip link-node URL extraction (keep text-based URL extraction)
- [x] 1.4 When `include_nodes=False`, omit `nodes` and `nodes_truncated` from returned dict

## 2. API layer — accept include_nodes query parameter

- [x] 2.1 Parse `include_nodes` query param in `get_frame_context()` route (default: `False`)
- [x] 2.2 Pass `include_nodes` to `store.get_frame_context()`
- [x] 2.3 Update route docstring to document `include_nodes` parameter

## 3. Tests — update and expand coverage

- [x] 3.1 Update `test_chat_mvp_frame_context.py`: existing calls that assert `nodes` presence MUST pass `include_nodes=True` explicitly to preserve test coverage
- [x] 3.2 Add test: `include_nodes=false` omits `nodes` and `nodes_truncated` from response
- [x] 3.3 Add test: `include_nodes=false` still extracts URLs from text
- [x] 3.4 Add test: `include_nodes=false` with accessibility frame returns text, urls, text_source
- [x] 3.5 Add test: `include_nodes=false` with OCR frame returns text, urls, text_source
- [x] 3.6 Update `test_chat_mvp_frame_context_api.py`: add `include_nodes` to mock assertion in `test_frame_context_passes_params_to_store`
- [x] 3.7 Add API test: `include_nodes=false` results in response without `nodes` key

## 4. Documentation — update Frame Context Contract

- [x] 4.1 Add `include_nodes` parameter to the API query parameters section in docs/v3/chat/mvp.md Frame Context Contract
- [x] 4.2 Document behavior: default `false` omits `nodes` and `nodes_truncated`
