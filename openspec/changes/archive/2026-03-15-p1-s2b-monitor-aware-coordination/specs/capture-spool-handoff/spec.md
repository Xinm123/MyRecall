## ADDED Requirements

### Requirement: Capture completion MUST write one atomic spool payload per persisted frame
For each successful capture-completion event, the Host MUST write one atomic `.jpg + .json` spool pair that contains the screenshot and the canonical capture metadata required by the v3 mainline: `capture_id`, `timestamp`, `capture_trigger`, `device_name`, `app_name`, `window_name`, and `event_ts` when available. The metadata written to the spool MUST describe the same capture cycle as the image bytes.

Within S2b terminology, `timestamp` is the Host capture-completion / spool-write completion time and is the value referred to as `capture_completed_ts` in Gate math. `event_ts` remains the Host trigger time, and `ingested_at` remains the Edge DB commit time.

#### Scenario: Successful capture writes canonical image and metadata together
- **WHEN** a monitor-bound capture completes successfully
- **THEN** the Host MUST atomically write exactly one JPEG spool item and one JSON metadata file for that `capture_id`

#### Scenario: Routing-filtered trigger produces no spool artifact
- **WHEN** the coordinator resolves a trigger to `routing_filtered`
- **THEN** the Host MUST NOT create a spool image, spool metadata file, or persisted frame for that trigger

### Requirement: S2b latency timestamps MUST remain unambiguous across Host and Edge
Whenever a persisted frame participates in S2b evidence, `event_ts`, `timestamp`, and `ingested_at` MUST preserve their distinct meanings and MUST NOT be silently conflated or rewritten. Samples with missing or invalid observational timestamps MAY still be accepted for compatibility, but they MUST be excluded from latency proof calculations.

#### Scenario: Persisted capture preserves ordered timing terms
- **WHEN** a capture is successfully persisted and ingested
- **THEN** `event_ts` MUST represent trigger time, `timestamp` MUST represent Host capture completion time, and `ingested_at` MUST represent Edge commit time for that sample

### Requirement: The S2b handoff to `/v1/ingest` MUST preserve the OCR-only mainline contract
The Host-to-Edge handoff MUST preserve S2b capture-completion semantics without reviving AX-era dependencies. `/v1/ingest` success for the v3 mainline MUST depend only on the screenshot plus the frozen capture metadata. `browser_url` MUST remain reserved/`null`, and AX compatibility fields MUST remain optional and non-blocking.

#### Scenario: Canonical S2b payload is sufficient for ingest
- **WHEN** the Host uploads a spool item that includes only screenshot bytes plus the canonical S2b metadata fields
- **THEN** the Edge MUST be able to accept and persist that frame without requiring AX-specific fields

#### Scenario: Reserved fields do not change S2b correctness
- **WHEN** compatibility fields such as `accessibility_text` or `content_hash` are absent or `null`
- **THEN** the S2b capture-completion handoff MUST remain valid for the v3 OCR-only mainline
