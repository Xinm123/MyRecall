## Terminology

This design uses the following terms consistently:

- **PHash (Perceptual Hash)**: A DCT-based image hashing algorithm that produces a 64-bit hash value robust to minor visual changes.
- **simhash field**: The database column `frames.simhash` that stores the 64-bit PHash value.
- **Hamming Distance**: The number of differing bit positions between two 64-bit hash values. Lower distance = higher similarity.
- **Similarity Threshold**: Maximum Hamming distance (default: 8 bits) below which two frames are considered similar.

## Context

MyRecall-v3 operates primarily as an OCR-only, vision-only application. As defined in P1-S2b+, the current substage introduces a critical optimization: PHash-Based Similarity Detection. Currently, the Host (client) captures frames continuously, which can lead to rapid storage consumption and unnecessary OCR processing on the Edge (server) if the user's screen is mostly static. To mitigate this, a filtering mechanism using perceptual hashing (PHash) is needed to drop visually similar frames before they are enqueued into the local spool (prior to `capture_id` generation).

## Goals / Non-Goals

**Goals:**
- Implement a lightweight PHash computation on the Host (Client) side in Python (output: 64-bit integer stored in `frames.simhash`).
- Maintain an in-memory `SimhashCache` to keep track of the most recent frame PHash values.
- Introduce similarity detection logic that compares new frames' PHash values to cached ones based on a Hamming distance threshold.
- Drop frames deemed "similar" before they enter the spool queue (and before `capture_id` generation).
- Ensure timeline continuity via IDLE triggers which always skip simhash dedup (guaranteed periodic frame capture).

**Non-Goals:**
- Offloading the similarity check or PHash computation to the Server/Edge.
- Processing or modifying the OCR mainline logic on the Edge.
- Modifying any external HTTP APIs or performing remote simhash synchronization.

## Decisions

**1. PHash for Similarity Computation**
- **Decision**: Use the `imagehash` library to compute 64-bit PHash values. The library internally uses `scipy.fftpack.dct` (already a project dependency) and provides a reliable, well-tested implementation.
- **Implementation**: Wrap `imagehash.phash()` in `openrecall/client/hash_utils.py`:
  ```python
  import imagehash
  from PIL import Image

  def compute_phash(image: Image.Image) -> int:
      """Compute 64-bit PHash from PIL Image."""
      hash_obj = imagehash.phash(image, hash_size=8)
      return int(str(hash_obj), 16)  # Convert hex string to int
  ```
- **Rationale**:
  - Mature library (1.5k+ stars, 10+ years maintenance), avoids ~50-100 lines of custom DCT code
  - Minimal extra dependency (`imagehash` is pure Python, reuses existing scipy/PIL/numpy stack)
  - Built-in Hamming distance calculation (`hash1 - hash2`)
  - Easy to experiment with alternative algorithms (dhash/ahash/whash) if needed
- **Alternatives Considered**: 
  - Exact pixel comparison (too sensitive to noise)
  - SSIM (computationally heavier)
  - Custom scipy DCT implementation (maintainability cost outweighs ~0.5ms perf gain)
- **Screenpipe pattern**: 'aligned' (Screenpipe uses perceptual hashing for similarity checks).

**2. In-Memory SimhashCache**
- **Decision**: Implement an in-memory sliding window cache (e.g., storing the last $N$ PHash values per device) to compare the current frame's hash against recent history.
- **Rationale**: Keeps the similarity check extremely fast. Persisting to disk is unnecessary since a fresh start only means the first frame is captured, which is acceptable.
- **Alternatives Considered**: SQLite-backed cache (adds latency to the critical path of the capture loop).
- **Screenpipe pattern**: 'aligned'.

**3. Pre-Spool Frame Dropping**
- **Decision**: The similarity check is positioned immediately after frame capture but BEFORE `capture_id` generation and spool enqueueing. Dropped frames do NOT generate a `capture_id`.
- **Rationale**: Complies with the architectural boundary defined for P1-S2b+. Dropping early saves disk space (spool queue) and avoids unnecessary event processing downstream.
- **Alternatives Considered**: Post-spool dropping (wastes disk I/O).

**4. IDLE Trigger Always Bypasses Simhash**
- **Decision**: IDLE triggers always skip simhash dedup and are enqueued directly. This ensures timeline continuity even when the screen is static.
- **Rationale**: The IDLE trigger fires every `idle_capture_interval_ms` (default: 30 seconds), guaranteeing periodic frame capture. This eliminates the need for a separate heartbeat mechanism while ensuring no long gaps in the capture timeline.
- **Configuration**: Simhash dedup can be independently enabled/disabled for CLICK and APP_SWITCH triggers via `simhash_enabled_for_click` and `simhash_enabled_for_app_switch`.
- **Alternatives Considered**: Heartbeat fallback mechanism (added complexity, required additional configuration).
- **Screenpipe pattern**: 'aligned' (Screenpipe uses periodic capture as timeline anchor).

## Configuration Management

All PHash-related parameters are defined in `openrecall/shared/config.py` and can be overridden via environment variables:

| Parameter | Default | Environment Variable | Scope | Hot Reload |
|-----------|---------|---------------------|-------|------------|
| `simhash_dedup_enabled` | `true` | `OPENRECALL_SIMHASH_DEDUP_ENABLED` | Host process | No (restart required) |
| `simhash_dedup_threshold` | `8` | `OPENRECALL_SIMHASH_DEDUP_THRESHOLD` | Host process | No (restart required) |
| `simhash_cache_size_per_device` | `1` | `OPENRECALL_SIMHASH_CACHE_SIZE` | Host process | No (restart required) |
| `simhash_enabled_for_click` | `true` | `OPENRECALL_SIMHASH_ENABLED_FOR_CLICK` | Host process | No (restart required) |
| `simhash_enabled_for_app_switch` | `true` | `OPENRECALL_SIMHASH_ENABLED_FOR_APP_SWITCH` | Host process | No (restart required) |

**Note**: IDLE triggers always skip simhash dedup regardless of configuration, ensuring timeline continuity.

**Configuration Priority**: Environment variable > Default value

**Storage**: All values are loaded at Host process startup and remain immutable until restart.

## Relationship to Legacy MSSIM Code

**Status**: The codebase contains unused MSSIM (Mean Structural Similarity Index) functions (`is_similar()`, `mean_structured_similarity_index()` in `recorder.py`) and related configuration (`similarity_threshold`, `disable_similarity_filter` in `config.py`).

**These are dead code - not called by any active code path.**

**Strategy for P1-S2b+**:
1. PHash-based similarity detection is the **FIRST** active similarity detection system in production
2. Implement PHash detection as a **NEW** capability using distinct `simhash_*` prefixed config names
3. MSSIM code can be removed in future cleanup (P2+) - out of scope for P1-S2b+
4. Why new config names: Avoid confusion with legacy MSSIM config that has different semantics (float 0.98 vs int 8) and different units (MSSIM similarity vs Hamming distance)

## Risks / Trade-offs

- **[Risk] Sensitivity of PHash Threshold** → **Mitigation**: The Hamming distance threshold for similarity must be configurable. If it is too low, duplicate frames pass through; if too high, valid small UI changes (like typing a character) are missed. We will rely on `docs/v3/gate_baseline.md` for initial calibration.
- **[Risk] CPU Overhead of Hashing** → **Mitigation**: Ensure the PHash implementation is optimized (e.g., downscaling images before hashing). Python's PIL/Pillow or OpenCV will be utilized for efficient resizing.
