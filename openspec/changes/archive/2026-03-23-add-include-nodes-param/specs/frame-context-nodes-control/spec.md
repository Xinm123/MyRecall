# Frame Context Nodes Control

Controls whether the `nodes` field is included in `/v1/frames/{id}/context` API responses.

## ADDED Requirements

### Requirement: include_nodes query parameter

The `/v1/frames/{id}/context` endpoint SHALL accept an `include_nodes` boolean query parameter.

#### Scenario: include_nodes defaults to false
- **WHEN** a client calls `GET /v1/frames/{id}/context` without passing `include_nodes`
- **THEN** `nodes` and `nodes_truncated` fields are absent from the response

#### Scenario: include_nodes explicitly false
- **WHEN** a client calls `GET /v1/frames/{id}/context?include_nodes=false`
- **THEN** `nodes` and `nodes_truncated` fields are absent from the response

#### Scenario: include_nodes explicitly true
- **WHEN** a client calls `GET /v1/frames/{id}/context?include_nodes=true`
- **THEN** `nodes` is present in the response with parsed accessibility nodes
- **AND** `nodes_truncated` is present when `max_nodes` truncation was applied

#### Scenario: include_nodes accepts true/false string values
- **WHEN** a client calls with `include_nodes=true` or `include_nodes=false`
- **THEN** the parameter is parsed as a boolean and applied correctly

### Requirement: nodes field omission

When `include_nodes=false`, the response SHALL NOT include the `nodes` field at all (field is absent, not present as an empty array).

#### Scenario: nodes field absent (not empty array)
- **WHEN** `include_nodes=false`
- **THEN** the response JSON does not contain a `nodes` key
- **AND** the response JSON does not contain a `nodes_truncated` key

#### Scenario: include_nodes=false with accessibility frame
- **WHEN** a frame has `text_source=accessibility` and `include_nodes=false`
- **THEN** `text`, `text_source`, `urls`, `browser_url`, and `status` are present
- **AND** `nodes` is absent

#### Scenario: include_nodes=false with OCR frame
- **WHEN** a frame has `text_source=ocr` and `include_nodes=false`
- **THEN** `text`, `text_source`, `urls`, `browser_url`, and `status` are present
- **AND** `nodes` is absent

### Requirement: URL extraction independent of include_nodes

URL extraction from the `text` field SHALL continue to function when `include_nodes=false`. Link-node URL extraction SHALL be skipped when `include_nodes=false`.

#### Scenario: URLs extracted from text when include_nodes=false
- **WHEN** `include_nodes=false` and the text field contains URLs
- **THEN** URLs are still extracted from text via regex and included in `urls` array

### Requirement: max_nodes has no effect when include_nodes=false

The `max_nodes` parameter SHALL have no effect when `include_nodes=false`.

#### Scenario: max_nodes ignored when include_nodes=false
- **WHEN** a client calls with `include_nodes=false&max_nodes=10`
- **THEN** `nodes` is absent from the response (not limited to 10)
