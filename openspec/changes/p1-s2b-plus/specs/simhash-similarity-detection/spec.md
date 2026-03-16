## Terminology

This specification uses the following terms consistently:

- **PHash (Perceptual Hash)**: A DCT-based image hashing algorithm that produces a 64-bit hash value.
- **simhash field**: The database column `frames.simhash` that stores the 64-bit PHash value.
- **Hamming Distance**: The number of differing bit positions between two 64-bit hash values.
- **Similarity Threshold**: Maximum Hamming distance (default: 8 bits) below which two frames are considered similar.

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
                  2. Compute PHash (64-bit)
                     (using scipy.fftpack.dct)
                              │
                              ▼
                  3. Query SimhashCache
                     (per device_name)
                              │
                              ▼
                  4. Check Hamming distance
                     (current vs. cached)
                              │
                    ┌─────────┴─────────┐
                    │                   │
          Distance ≤ 8 bits          Distance > 8 bits
                    │                   │
                    ▼                   │
         5a. Check heartbeat          │
             timeout?                  │
              │    │                   │
       No timeout  Timeout             │
              │    │                   │
              ▼    └───────────────────┤
        Skip frame                      │
        (drop, no capture_id)           │
                                        ▼
                              5b. Enqueue to spool
                                  - Generate capture_id
                                  - Write JPEG to spool
                                  - Write metadata JSON
                                  - Store PHash in frames.simhash
                                        │
                                        ▼
                              6. Update SimhashCache
                                 - Add PHash + timestamp
                                 - Evict oldest if full
```

**Key Points**:
1. **Dropped frames do NOT generate `capture_id`** - they are discarded before ID assignment
2. **Heartbeat timeout is calculated from last successful enqueue time** (not capture time)
3. **Each `device_name` has independent cache and heartbeat timer**

## ADDED Requirements

### Requirement: Simhash Computation
The system SHALL compute a perceptual hash (PHash) for each captured screen frame immediately after capture.

#### Scenario: Frame captured
- **WHEN** a screen frame is successfully captured by the client
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
- **AND** the heartbeat interval has not been exceeded
- **THEN** the frame is discarded without generating a `capture_id`.
- **AND** the frame is NOT enqueued into the local spool.

#### Scenario: Dissimilar frame detected
- **WHEN** the Hamming distance between the new frame's PHash and cached PHash values meets or exceeds the similarity threshold (> 8 bits)
- **THEN** the frame is accepted for spooling.
- **AND** a `capture_id` is generated.

### Requirement: Heartbeat Fallback
The system SHALL force a frame to be captured and spooled if no frames have been spooled for a duration exceeding the heartbeat threshold, regardless of similarity.

#### Scenario: Heartbeat threshold exceeded
- **WHEN** consecutive frames have been dropped due to similarity
- **AND** the time since the last successfully enqueued frame exceeds the heartbeat interval (`simhash_heartbeat_interval_sec`, default 300s)
- **THEN** the next captured frame is accepted and spooled regardless of similarity.
- **AND** the similarity cache is updated with the new PHash value and enqueue timestamp.

## Multi-Device Isolation Strategy

The `SimhashCache` enforces strict per-device isolation:

1. **Independent Caches**: Each `device_name` maintains its own isolated cache entry
2. **Independent Timers**: Each device has its own heartbeat timer starting from its last successful enqueue
3. **Cross-Device Similarity**: NOT detected - frames from different devices are never compared for similarity
4. **Parallel Enqueue**: Frames from different devices may be enqueued simultaneously even if visually similar

**Example**:
- Device A (monitor_0) captures frame at T=0s (PHash=0xABC)
- Device B (monitor_1) captures frame at T=1s (PHash=0xABC, identical content)
- Both frames are enqueued (each device has independent cache)
- Device A heartbeat timer: T=0s → T=300s
- Device B heartbeat timer: T=1s → T=301s

## Edge Cases and Boundary Conditions

| Scenario | Behavior | Rationale |
|----------|----------|-----------|
| First frame (cache empty) | Enqueue normally, write PHash to cache | No historical data to compare |
| Process restart (cache lost) | Enqueue normally, rebuild cache from scratch | In-memory cache is not persisted; acceptable trade-off for performance |
| Continuous static screen (300s+) | Force enqueue at 300s as heartbeat, reset timer | Prevents timeline gaps that could be misinterpreted as crashes |
| PHash computation failure | Enqueue normally without PHash | Failure should not block capture pipeline |
| `simhash_dedup_enabled=false` | Enqueue all frames without similarity check | Allows disabling feature without code changes |
| Multi-monitor identical content | Each device enqueues independently | Cross-device similarity detection is out of scope |

## Heartbeat Fallback Semantics (SSOT)

**Definition**: Heartbeat interval is measured from the **last successful enqueue time** (not capture time).

**Calculation**:
```
heartbeat_timeout = last_enqueue_timestamp + simhash_heartbeat_interval_sec
current_time >= heartbeat_timeout → force enqueue
```

**Example Timeline**:
- T=0s: Frame A enqueued (timestamp=0s, PHash=0x123)
- T=5s: Frame B similar to A (distance=4) → **dropped** (no capture_id)
- T=10s: Frame C similar to A (distance=3) → **dropped** (no capture_id)
- T=300s: Heartbeat timeout reached
- T=305s: Frame D similar to A (distance=5) → **force enqueue** (capture_id generated, timer reset)
- T=310s: Frame E similar to D (distance=2) → dropped again

**Key Insight**: Heartbeat ensures at least one frame every `simhash_heartbeat_interval_sec` seconds, even during static screen periods.

---
**Acceptance impact**: This capability introduces a new mechanism for pre-spool dropping. It impacts the volume of frames sent to the spool and the Server. Validation must ensure the Heartbeat mechanism correctly fires and that the PHash dropping logic complies with the expected loss rate thresholds defined in `docs/v3/gate_baseline.md`.
