## Terminology

This specification uses the following terms consistently:

- **PHash (Perceptual Hash)**: A DCT-based image hashing algorithm that produces a 64-bit hash value.
- **simhash field**: The database column `frames.simhash` that stores the 64-bit PHash value.
- **Hamming Distance**: The number of differing bit positions between two 64-bit hash values.
- **Similarity Threshold**: Maximum Hamming distance (default: 8 bits) below which two frames are considered similar.
- **Trigger Type**: The event that caused the capture (IDLE, CLICK, APP_SWITCH, MANUAL).

## Capture Flow with PHash Similarity Detection

```
┌─────────────────────────────────────────────────────────────────┐
│ Monitor Worker Capture Cycle                                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                  1. Screenshot captured
                              │
                              ▼
                  2. Check trigger type
                     (IDLE, CLICK, APP_SWITCH, MANUAL)
                              │
                    ┌─────────┴─────────┐
                    │                   │
              IDLE trigger         Other triggers
                    │                   │
                    ▼                   ▼
         Skip simhash check     3. Check if simhash enabled
         Enqueue directly              for this trigger
                    │                   │
                    │         ┌─────────┴─────────┐
                    │         │                   │
                    │    Enabled for         Disabled for
                    │    trigger type        trigger type
                    │         │                   │
                    │         ▼                   │
                    │   4. Compute PHash          │
                    │      (64-bit)               │
                    │         │                   │
                    │         ▼                   │
                    │   5. Check Hamming          │
                    │      distance               │
                    │         │                   │
                    │   ┌─────┴─────┐             │
                    │   │           │             │
                    │ Similar    Dissimilar       │
                    │   │           │             │
                    │   ▼           │             │
                    │ Skip frame    │             │
                    │ (no enqueue)  │             │
                    │               │             │
                    └───────────────┴─────────────┘
                                    │
                                    ▼
                          6. Enqueue to spool
                              - Generate capture_id
                              - Write JPEG to spool
                              - Write metadata JSON
                              - Store PHash in frames.simhash
                                    │
                                    ▼
                          7. Update SimhashCache
                             - Add PHash + timestamp
                             - Evict oldest if full
```

**Key Points**:
1. **IDLE triggers always skip simhash** - ensuring timeline continuity
2. **Dropped frames do NOT generate `capture_id`** - they are discarded before ID assignment
3. **Each `device_name` has independent cache**
4. **Simhash can be enabled/disabled per trigger type** (CLICK, APP_SWITCH)

## ADDED Requirements

### Requirement: Trigger-Type-Based Simhash Control
The system SHALL allow simhash dedup to be enabled or disabled independently for CLICK and APP_SWITCH trigger types. IDLE triggers SHALL always skip simhash dedup.

#### Scenario: IDLE trigger capture
- **WHEN** a frame is captured due to an IDLE trigger
- **THEN** the frame is enqueued directly without simhash computation.
- **AND** timeline continuity is guaranteed (at least one frame every `idle_capture_interval_ms`).

#### Scenario: CLICK trigger with simhash enabled
- **WHEN** `simhash_enabled_for_click=true` (default)
- **AND** a frame is captured due to a CLICK trigger
- **THEN** simhash dedup is applied.

#### Scenario: CLICK trigger with simhash disabled
- **WHEN** `simhash_enabled_for_click=false`
- **AND** a frame is captured due to a CLICK trigger
- **THEN** the frame is enqueued directly without simhash computation.

### Requirement: Simhash Computation
The system SHALL compute a perceptual hash (PHash) for each captured screen frame when simhash is enabled for the trigger type.

#### Scenario: Frame captured with simhash enabled
- **WHEN** a screen frame is successfully captured by the client
- **AND** simhash is enabled for the trigger type
- **THEN** the system computes its 64-bit PHash representation before proceeding to the spool logic.
- **AND** the PHash value is stored in the `frames.simhash` field (if frame is enqueued).

### Requirement: Similarity Cache
The system SHALL maintain an in-memory cache (`SimhashCache`) of recently captured and non-dropped frame PHash values.

#### Scenario: Updating cache
- **WHEN** a frame is accepted (not dropped) for spooling
- **THEN** its 64-bit PHash value and enqueue timestamp are added to the in-memory cache.
- **AND** the oldest hash is evicted if the cache reaches capacity (`simhash_cache_size_per_device`).

### Requirement: Similarity Detection and Dropping
The system SHALL compare the PHash of a newly captured frame against the `SimhashCache`. If the Hamming distance is below the configured similarity threshold, the frame SHALL be dropped.

#### Scenario: Similar frame detected
- **WHEN** the Hamming distance between the new frame's PHash and cached PHash values is below the similarity threshold (≤ 8 bits by default)
- **THEN** the frame is discarded without generating a `capture_id`.
- **AND** the frame is NOT enqueued into the local spool.

#### Scenario: Dissimilar frame detected
- **WHEN** the Hamming distance between the new frame's PHash and cached PHash values meets or exceeds the similarity threshold (> 8 bits)
- **THEN** the frame is accepted for spooling.
- **AND** a `capture_id` is generated.

## Multi-Device Isolation Strategy

The `SimhashCache` enforces strict per-device isolation:

1. **Independent Caches**: Each `device_name` maintains its own isolated cache entry
2. **Cross-Device Similarity**: NOT detected - frames from different devices are never compared for similarity
3. **Parallel Enqueue**: Frames from different devices may be enqueued simultaneously even if visually similar

**Example**:
- Device A (monitor_0) captures frame at T=0s (PHash=0xABC)
- Device B (monitor_1) captures frame at T=1s (PHash=0xABC, identical content)
- Both frames are enqueued (each device has independent cache)

## Timeline Continuity Guarantee

**IDLE triggers ensure timeline continuity** by bypassing simhash dedup entirely:

- `idle_capture_interval_ms` (default: 30000ms) guarantees at least one frame every 30 seconds
- No separate heartbeat mechanism is needed
- Even during static screen periods, IDLE captures ensure the timeline remains continuous

**Example Timeline**:
- T=0s: Frame A enqueued (IDLE trigger, PHash=0x123)
- T=2s: Frame B similar to A (CLICK trigger, distance=4) → **dropped** (no capture_id)
- T=5s: Frame C similar to A (CLICK trigger, distance=3) → **dropped** (no capture_id)
- T=30s: Frame D enqueued (IDLE trigger) → **always enqueued**, timeline guaranteed

## Edge Cases and Boundary Conditions

| Scenario | Behavior | Rationale |
|----------|----------|-----------|
| First frame (cache empty) | Enqueue normally, write PHash to cache | No historical data to compare |
| Process restart (cache lost) | Enqueue normally, rebuild cache from scratch | In-memory cache is not persisted; acceptable trade-off for performance |
| Continuous static screen | IDLE captures every 30s bypassing simhash | Ensures timeline continuity without heartbeat |
| PHash computation failure | Enqueue normally without PHash | Failure should not block capture pipeline |
| `simhash_dedup_enabled=false` | Enqueue all frames without similarity check | Allows disabling feature without code changes |
| Multi-monitor identical content | Each device enqueues independently | Cross-device similarity detection is out of scope |

## Configuration Reference

| Parameter | Default | Environment Variable | Description |
|-----------|---------|---------------------|-------------|
| `simhash_dedup_enabled` | `true` | `OPENRECALL_SIMHASH_DEDUP_ENABLED` | Master switch for simhash dedup |
| `simhash_dedup_threshold` | `8` | `OPENRECALL_SIMHASH_DEDUP_THRESHOLD` | Hamming distance threshold |
| `simhash_cache_size_per_device` | `1` | `OPENRECALL_SIMHASH_CACHE_SIZE` | Hashes cached per device |
| `simhash_enabled_for_click` | `true` | `OPENRECALL_SIMHASH_ENABLED_FOR_CLICK` | Dedup for CLICK triggers |
| `simhash_enabled_for_app_switch` | `true` | `OPENRECALL_SIMHASH_ENABLED_FOR_APP_SWITCH` | Dedup for APP_SWITCH triggers |

**Note**: IDLE triggers always skip simhash regardless of configuration.

---
**Acceptance impact**: This capability introduces a new mechanism for pre-spool dropping. It impacts the volume of frames sent to the spool and the Server. Validation must ensure the trigger-type-based simhash control works correctly and that the PHash dropping logic complies with the expected loss rate thresholds defined in `docs/v3/gate_baseline.md`.
