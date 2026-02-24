# ADR-0001: Python-First Architecture Constraint

**Status**: Accepted
**Date**: 2026-02-06
**Deciders**: Product Owner + Chief Architect
**Context**: MyRecall-v3 technology stack selection
**SupersededBy**: N/A
**Supersedes**: N/A
**Scope**: target

---

## Context and Problem Statement

MyRecall-v3 was originally planned as multi-modal data capture (video + audio) with continuous 24/7 recording, which is performance-intensive. The reference project (screenpipe) uses Rust for performance. Should MyRecall-v3 follow the same approach, or maintain a Python-first architecture?

## Recontextualization (2026-02-23, ADR-0005)

This ADR remains active after the vision-only pivot:

- The MVP critical path is now vision-only (Search/Chat), but the language/runtime constraint is unchanged.
- Python-first still applies to all current and future phases.
- Audio freeze changes priority, not the architectural language decision.

---

## Decision Drivers

1. **Development Speed**: Time to market is critical (Week 22 outer bound for MVP deployment)
2. **Maintainability**: Team familiarity with technology stack
3. **Ecosystem**: Availability of libraries for ML/AI tasks (OCR, Whisper, embeddings)
4. **Performance**: Ability to handle 24/7 recording without excessive resource usage
5. **Flexibility**: Ability to swap components (e.g., LLM providers, OCR engines)

---

## Considered Options

### Option A: Python-First (All Core Logic in Python)
- **Description**: Implement all core business logic in Python, use external tools (FFmpeg) for heavy lifting
- **Pros**:
  - Rapid development (existing Python codebase)
  - Rich ML/AI ecosystem (Transformers, sentence-transformers, faster-whisper)
  - Easy integration with LLM APIs (OpenAI, Anthropic)
  - Team expertise
- **Cons**:
  - Potentially higher CPU/memory usage
  - May hit performance bottlenecks in data-intensive sections
  - GIL (Global Interpreter Lock) limits true parallelism

### Option B: Rust-First (Port to Rust)
- **Description**: Rewrite core components in Rust, following screenpipe's architecture
- **Pros**:
  - Best performance and memory efficiency
  - No GIL limitations
  - Proven approach (screenpipe architecture)
- **Cons**:
  - Steep learning curve (team ramp-up)
  - Slower development (rewrites take time)
  - Smaller ML/AI ecosystem (fewer Rust libraries)
  - Risk of missing 20-week (5-month) deadline

### Option C: Hybrid (Python + Rust Sidecar)
- **Description**: Python for core logic, Rust sidecar processes for performance-critical paths
- **Pros**:
  - Balance of development speed and performance
  - Can optimize bottlenecks without full rewrite
- **Cons**:
  - Increased complexity (IPC, process management)
  - Two languages to maintain
  - More points of failure

---

## Decision Outcome

**Chosen Option: Option A (Python-First)**

### Rationale

1. **Delivery Deadline is Hard Constraint**: Week 22 remains the outer bound for MVP deployment. Rewriting to Rust would jeopardize that critical path. Python leverages existing codebase and team expertise.

2. **Bottlenecks Can Be Mitigated**:
   - **Video recording**: Use FFmpeg CLI (battle-tested, efficient)
   - **Audio transcription**: Use faster-whisper (CTranslate2 backend, 3-5x faster than openai-whisper)
   - **OCR**: Use existing DocTR/RapidOCR (already optimized)
   - **Python optimization**: Use multiprocessing/asyncio for parallelism

3. **Premature Optimization**: No quantified evidence that Python will be a bottleneck. screenpipe's Rust choice was driven by different constraints (cross-platform native app, no Python on target systems).

4. **Flexibility**: Python's ML/AI ecosystem allows rapid experimentation (swap LLM providers, OCR engines, embedding models).

### Optimization Sequence (If Performance Issues Arise)

1. **Python-Layer Optimization** (first resort):
   - Algorithm improvements (e.g., batch processing, async/await)
   - Multiprocessing for CPU-bound tasks
   - Caching and indexing

2. **External Tools** (second resort):
   - FFmpeg for video processing (already planned)
   - GStreamer if FFmpeg insufficient
   - C/C++ extensions via Cython or PyBind11

3. **Rust Sidecar** (last resort, only if quantified evidence):
   - Independent sidecar process (not embedded in main codebase)
   - Example: Rust-based frame extraction service if Python bottleneck proven
   - Communicate via HTTP/gRPC (loose coupling)

---

## Consequences

### Positive

- ✅ Faster development (leverage existing Python codebase)
- ✅ Easier maintenance (team Python expertise)
- ✅ Rich ML/AI ecosystem (Transformers, faster-whisper, pyannote-audio)
- ✅ More flexible for experimentation (LLM providers, models)
- ✅ Lower risk of missing 20-week (5-month) deadline

### Negative

- ⚠️ May require optimization if performance bottlenecks discovered (mitigated by optimization sequence)
- ⚠️ GIL limitations for CPU-bound parallelism (mitigated by multiprocessing)
- ⚠️ Higher memory footprint than Rust (acceptable tradeoff for development speed)

### Neutral

- 🔄 Can revisit Rust sidecar if quantified evidence emerges
- 🔄 External tools (FFmpeg) provide performance without Rust rewrite

---

## Validation

**Success Criteria** (Phase 1 Phase Gates):
- Video recording overhead <5% CPU
- Frame extraction <2s per frame
- Storage <50GB per day (24/7 recording)

**Failure Signals** (triggers re-evaluation):
- Recording overhead >10% CPU (double target)
- Frame extraction >10s per frame (5x slower than target)
- Python optimization exhausted with no improvement

**Re-evaluation Trigger**:
If Phase 1 gates fail after exhausting Python optimization sequence (1-2 weeks of optimization attempts), revisit Option C (Rust sidecar for frame extraction).

---

## Related ADRs

### Existing ADRs

- **ADR-0002**: Thin Client Architecture (deployment model, affects Phase 5 planning)
- **ADR-0003**: P3 Memory Scope Definition (clarifies "memory capability" requirements)
- **ADR-0004**: Speaker Identification as Optional Feature (historical, superseded for MVP path)
- **ADR-0005**: Vision-Only Chat Pivot + Audio Freeze

### Planned ADRs (TBD)

Future architectural decisions that may be documented:

- **ADR-000X**: FFmpeg vs PyAV vs opencv-python (Phase 1 video stack - document if performance issues arise)
- **ADR-000X**: faster-whisper vs openai-whisper (Phase 2 audio stack - document if WER issues arise)
- **ADR-000X**: API versioning and backward compatibility (Phase 0/5 - document if breaking changes needed)
- **ADR-000X**: SQLite + LanceDB vs alternatives (Phase 0 - document if storage performance issues arise)

**Note**: "Planned ADRs" will only be written if the relevant technical decision requires formal documentation (e.g., contentious choice, significant tradeoffs, or failure signal triggered).

---

## References

- screenpipe architecture: `screenpipe/crates/`
- Python multiprocessing: https://docs.python.org/3/library/multiprocessing.html
- faster-whisper benchmark: https://github.com/guillaumekln/faster-whisper#benchmark
- CTranslate2 (faster-whisper backend): https://github.com/OpenNMT/CTranslate2

---

## Approval

- **Product Owner**: Approved (prioritize 20-week deployment deadline)
- **Chief Architect**: Approved (Python-first with fallback plan)
- **Date**: 2026-02-06
