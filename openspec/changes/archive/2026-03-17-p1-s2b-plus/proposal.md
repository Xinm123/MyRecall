## Terminology

This proposal uses the following terms consistently:

- **PHash (Perceptual Hash)**: A DCT-based image hashing algorithm that produces a 64-bit hash value robust to minor visual changes (compression, brightness adjustments, small UI updates).
- **simhash field**: The database column `frames.simhash` that stores the 64-bit PHash value computed for each captured frame.
- **Hamming Distance**: The number of bit positions where two 64-bit hash values differ. Lower distance indicates higher visual similarity.
- **Similarity Detection**: The process of comparing two frames' PHash values using Hamming distance to determine if they are visually similar.

## Why

MyRecall-v3 aims to optimize data capture and processing. In the previous stage (P1-S2b), basic capture mechanisms were established. Now, in P1-S2b+ (PHash-Based Similarity Detection), the goal is to introduce a filtering layer that avoids saving redundant frames. This is necessary to reduce disk usage and computational overhead by dropping frames that are visually similar to previously captured ones, right before they are enqueued into the spool.

## What Changes

- Implement PHash computation for captured frames (output stored in `frames.simhash` field).
- Introduce an in-memory `SimhashCache` to store recent PHash values.
- Add similarity detection logic to compare incoming frames' PHash values against the cache.
- Implement pre-spool frame dropping based on the calculated similarity.
- Fallback to heartbeat mechanism when frames are dropped to ensure timeline continuity.

## Capabilities

### New Capabilities

- `simhash-similarity-detection`: Introduces PHash-based image similarity computation and an in-memory `SimhashCache` to drop redundant frames before they are enqueued into the local spool. The computed 64-bit PHash value is stored in the `frames.simhash` field. Includes heartbeat fallback logic for dropped frames.

### Modified Capabilities

- `client-capture-pipeline`: The capture pipeline is modified to integrate the PHash similarity check **before** generating a `capture_id` and enqueuing the frame into the spool. Frames deemed similar (Hamming distance ≤ threshold) and not exceeding the heartbeat interval are dropped without generating a `capture_id`.

## Impact

- **Affected Code**: `openrecall/client/recorder.py` or related pipeline components where frames are captured before enqueueing.
- **APIs**: No external HTTP API changes (as per external HTTP delta). This is strictly a client-side host modification.
- **Systems**: The Host (Client) spool ingestion layer.

## Non-goals

- OCR processing or Vision ML model execution (this is OCR-only mainline, but ML happens on Edge, not Host).
- Downstream handoff or HTTP API implementation for these dropped frames.
- Cloud-based storage or remote simhash sync.

## Source Precedence Note

When defining frozen behaviors or Gate thresholds for this proposal, the following source precedence MUST be strictly followed:
1. `docs/v3/spec.md` (Architecture & frozen behavior SSOT)
2. `docs/v3/data-model.md` (Data contracts)
3. `docs/v3/open_questions.md` (Frozen decisions)
4. `docs/v3/acceptance/phase1/p1-s2b-plus.md` (Current substage contract)
5. `docs/v3/gate_baseline.md` (Gate formulas)
