# ADR-0004: Speaker Identification as Optional Feature

**Status**: Superseded
**SupersededBy**: ADR-0005 (2026-02-23)
**Supersedes**: N/A
**Scope**: historical

**Date**: 2026-02-06

**Deciders**: User + AI Architect

---

> Historical record: this ADR captured pre-pivot audio scope decisions.
> For MVP critical path, audio work is frozen by ADR-0005.

## Context

MyRecall v3 Phase 2 (Audio Capture) is split into two sub-phases:

- **Phase 2.0 (Week 7-8)**: Audio MVP - system + mic + VAD + Whisper transcription
- **Phase 2.1 (Week 9-10)**: Speaker Identification - pyannote-audio diarization + speaker clustering

The question arose: Is speaker identification required for MVP, or truly optional?

## Decision

**Phase 2.1 (Speaker Identification) is OPTIONAL**:

1. Complete Phase 2.0 first (basic audio capture + transcription)
2. User evaluates audio quality and use cases after Phase 2.0 validation (Week 8)
3. **If speaker tracking not needed** → Skip Phase 2.1 entirely
4. **If needed** → Implement Phase 2.1 (Week 9-10)

**Decision trigger**: Phase 2.0验证完成后(Week 8-9边界),由User根据ADR-0004行45-50的验证标准决定是否实施Phase 2.1

## Rationale

### Why Optional?

1. **Use case dependency**: Speaker ID value depends heavily on how user works
   - **High value**: Frequent meetings with 3+ participants, need to attribute quotes
   - **Low value**: Solo work, 1:1 calls, screen shares without audio discussion

2. **Complexity cost**: Speaker diarization adds:
   - 2 weeks implementation time
   - PyTorch + pyannote.audio dependencies (~2GB)
   - GPU acceleration considerations (CPU diarization is slow)
   - Speaker clustering tuning (DER <20% is non-trivial)

3. **Validate first**: Better to validate Phase 2.0 audio quality before committing
   - Whisper WER acceptable?
   - VAD filtering working?
   - Audio sync with timeline correct?

4. **Timeline flexibility**: Can save 2 weeks if not needed (Week 9-10 freed up)

### Why NOT Mandatory?

- **Not MVP-critical**: Core value is searchable transcripts, not speaker attribution
- **Risk reduction**: Phase 2.0 is already complex (audio capture + transcription)
- **User preference**: Some users may prefer NOT tracking speakers (privacy concern)

## Consequences

### Positive ✅

- Reduced MVP timeline risk (can skip 2 weeks if not needed)
- Simpler Phase 2.0 scope (fewer moving parts to debug)
- User has data to make informed decision (not guessing upfront)
- Privacy-friendly default (speaker tracking is opt-in)

### Negative ❌

- May need to retrofit speaker ID later if user wants it
- Audio chunks already stored won't have speaker embeddings (would need reprocessing)
- Decision point at Week 8 creates uncertainty in planning

## Implementation Considerations

### Phase 2.0 Design Implications

**API must support optional speaker field from day 1**:

```python
# AudioChunk model (Pydantic)
class AudioChunk:
    id: str
    timestamp: datetime
    duration: float
    audio_path: str
    transcript: str
    speaker_id: Optional[str] = None  # ⚠️ Must be nullable
    device: str  # "system" or "microphone"
```

**Database schema**:
```sql
CREATE TABLE audio_chunks (
    id TEXT PRIMARY KEY,
    timestamp INTEGER,
    audio_path TEXT,
    transcript TEXT,
    speaker_id TEXT,  -- NULL if Phase 2.1 not implemented
    device TEXT
);
```

### Phase 2.1 Retrofit Plan (If Implemented)

1. **Add speaker processing pipeline**:
   - Diarization: `pyannote.audio` VAD + speaker embedding
   - Clustering: Group similar embeddings into speaker IDs
   - Label: Assign `speaker_id` to each chunk

2. **Backfill existing data** (optional):
   - Re-process stored audio chunks through diarization
   - Update `speaker_id` field in database
   - **Risk**: May be slow for large datasets (100+ hours of audio)

3. **API additions**:
   ```
   GET /api/v1/speakers  # List all speaker IDs
   POST /api/v1/speakers/{id}/label  # Rename "Speaker 1" → "John"
   GET /api/v1/search?speaker_id=sp_001  # Filter by speaker
   ```

## Decision Criteria (Week 8 Validation)

User should consider speaker ID if:

- [ ] Has frequent meetings with 3+ participants
- [ ] Needs to attribute quotes to specific people
- [ ] Cross-device audio capture (multiple PCs, need speaker deduplication)
- [ ] Willing to trade 2 weeks + GPU resources for speaker tracking

User should skip if:

- [ ] Primarily solo work (not many multi-party conversations)
- [ ] Transcripts are "good enough" without speaker labels
- [ ] Privacy concerns about persistent speaker profiles
- [ ] Timeline pressure (need to start Phase 3 by Week 11)

## Alternatives Considered

### Option 1: Mandatory Speaker ID
- **Pros**: Feature-complete audio, no decision point
- **Cons**: Adds 2 weeks to timeline, may not be used by user
- **Rejected**: Not worth forced timeline cost for uncertain value

### Option 2: Cloud Speaker ID (e.g., AssemblyAI)
- **Pros**: No local implementation, fast time-to-market
- **Cons**: Requires cloud API (costs $$$), privacy concerns, network dependency
- **Rejected**: Violates "local-first" principle, ongoing cost

### Option 3: Speaker ID in Phase 7 (with Memory)
- **Pros**: Defer entirely to post-MVP
- **Cons**: Misses opportunity to collect speaker data from day 1
- **Rejected**: If user wants it, better to decide after Phase 2.0 (Week 8) than wait until Phase 7 (Week 25+)

## Success Criteria (If Phase 2.1 Implemented)

- [ ] Diarization Error Rate (DER) ≤20%
- [ ] Speaker clustering stable over 24-hour continuous recording
- [ ] Cross-device speaker matching (same person on 2 PCs recognized)
- [ ] API allows renaming speakers ("Speaker 1" → "Alice")

## Related ADRs

- ADR-0001: Python-First Principle
- ADR-0002: Thin Client Architecture (speaker embeddings stored on Debian server)

## References

- Historical Phase 2.1 section: `v3/milestones/roadmap-status.md#phase-21-audio-parity-with-screenpipe-paused--frozen`
- Superseding decision: `v3/decisions/ADR-0005-vision-only-chat-pivot.md`
- Screenpipe audio implementation (reference): `screenpipe/`
