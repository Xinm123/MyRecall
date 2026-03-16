## MODIFIED Requirements

### Requirement: Client Capture Loop
The capture loop SHALL orchestrate the acquisition of screen frames, apply filtering, and enqueue them to the local spool.

#### Capture Pipeline Flow (P1-S2b+)

```
┌──────────────────────────────────────────────────────────────┐
│ Capture Event (idle/app_switch/manual/click)                 │
└──────────────────────────────────────────────────────────────┘
                          │
                          ▼
              1. Route to target monitor
                          │
                          ▼
              2. Capture screenshot
                          │
                          ▼
              3. Compute PHash (64-bit)
                 [NEW in P1-S2b+]
                          │
                          ▼
              4. Query SimhashCache
                 (per device_name)
                          │
                          ▼
              5. Check similarity
                          │
                 ┌────────┴────────┐
                 │                 │
           Similar &          Not similar OR
           no heartbeat       heartbeat timeout
           timeout            exceeded
                 │                 │
                 ▼                 │
         DROP FRAME                 │
         (no capture_id             │
         generated)                 │
                                 ▼
                     6. Generate capture_id
                        (UUID v7)
                                 │
                                 ▼
                     7. Enqueue to spool
                        - Write JPEG
                        - Write metadata JSON
                        - Include PHash in metadata
                                 │
                                 ▼
                     8. Update SimhashCache
                        - Store PHash + timestamp
```

**Critical Timing Constraints**:
1. `capture_id` is generated ONLY for frames that pass the similarity check (or heartbeat fallback)
2. Dropped frames do NOT generate `capture_id` - they are completely discarded before ID assignment
3. PHash computation happens BEFORE `capture_id` generation (not after)

#### Scenario: Frame processing pipeline
- **WHEN** the capture loop acquires a new screen frame
- **THEN** it first computes the frame's 64-bit PHash value.
- **THEN** it queries the `SimhashCache` to check similarity (Hamming distance ≤ threshold).
- **THEN** if the frame is deemed similar AND the heartbeat threshold is not exceeded, it is dropped WITHOUT generating a `capture_id`.
- **THEN** if the frame is NOT similar, OR the heartbeat threshold IS exceeded, a `capture_id` is generated (UUID v7) and the frame is enqueued to the spool.

#### Scenario: Dropped frame lifecycle
- **WHEN** a frame is dropped due to similarity
- **THEN** no `capture_id` is generated.
- **AND** no entry is written to the spool directory.
- **AND** no data is sent to the Edge server.
- **AND** a log entry is written: `MRV3 similar_frame_skipped device_name=X hamming_distance=N trigger_type=Y`

#### Scenario: Enqueued frame lifecycle
- **WHEN** a frame is accepted for spooling
- **THEN** a `capture_id` (UUID v7) is generated.
- **AND** the frame is written to `~/MRC/spool/{capture_id}.jpg`.
- **AND** metadata is written to `~/MRC/spool/{capture_id}.json` (including PHash value).
- **AND** the PHash value and enqueue timestamp are stored in `SimhashCache`.
