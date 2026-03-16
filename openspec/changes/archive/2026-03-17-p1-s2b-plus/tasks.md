## Implementation Tasks

### 1. Similarity Engine Setup

- [x] 1.1 Add `imagehash>=4.3` dependency to `requirements.txt` for PHash computation.
- [x] 1.2 Create `openrecall/client/hash_utils.py` with PHash computation utilities using the `imagehash` library. Implement functions for: computing 64-bit PHash from PIL Image, calculating Hamming distance between two hashes, and checking similarity against a threshold.
- [x] 1.3 Create the in-memory `SimhashCache` class with a configurable size/sliding window for storing recent hashes.
- [x] 1.4 Write unit tests for the PHash calculation and `SimhashCache` logic to verify correct insertion, eviction, and Hamming distance calculation.

### 2. Similarity Detection Integration

- [x] 2.1 Update `openrecall/client/recorder.py` (or equivalent capture module) to initialize the `SimhashCache` on startup.
- [x] 2.2 Inject the simhash calculation and similarity check immediately after frame capture but before `capture_id` generation.
- [x] 2.3 Implement the dropping mechanism: if the new frame's simhash has a Hamming distance less than the threshold compared to cached hashes, drop the frame.
- [x] 2.4 Add PHash configuration parameters to `openrecall/shared/config.py` (see `design.md` Configuration Management section for field definitions). Ensure default values adhere to `docs/v3/gate_baseline.md`.

### 3. Heartbeat Fallback Implementation

- [x] 3.1 Implement a heartbeat timer within the capture loop that tracks the time since the last successfully spooled frame.
- [x] 3.2 Add logic to bypass the similarity dropping if the heartbeat threshold is exceeded, forcing the frame to be spooled.
- [x] 3.3 Add configuration for the heartbeat interval in the client settings.
- [x] 3.4 Write integration tests to ensure that the heartbeat correctly fires when consecutive frames are identical and the simhash drops them.

## Acceptance Verification

### 4. Verification & Testing

- [x] 4.1 Run the client locally and verify via logging that visually similar frames are correctly dropped and not enqueued into the spool.
- [x] 4.2 Verify that after the heartbeat threshold elapses (e.g., leaving the screen static), a frame is successfully forced into the spool.
- [x] 4.3 Check that the overall data loss and spool volume comply with the Gate/SLO thresholds defined in `docs/v3/gate_baseline.md`.
- [x] 4.4 Run all unit and integration tests to ensure no regressions in the capture pipeline.
