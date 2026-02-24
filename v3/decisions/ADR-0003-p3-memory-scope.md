# ADR-0003: P3 Memory Scope Definition

**Status**: Approved (deferred to Phase 7)

**Date**: 2026-02-06

**Deciders**: User + AI Architect
**SupersededBy**: N/A
**Supersedes**: N/A
**Scope**: target

---

## Context

MyRecall v3 roadmap included "P3: Memory" as a priority, but the scope was undefined. Three interpretations emerged:

- **Option A**: Daily/weekly activity summaries
- **Option B**: User preferences, projects, people (contextual memory)
- **Option C**: Persistent agent state (multi-turn reasoning memory)

The question arose: What does "memory capability" actually mean, and when should it be implemented?

## Decision

**P3 Memory** is defined as:

1. **(A) Daily/Weekly Activity Summaries**: Auto-generated digests of user activity
2. **(C) Persistent Agent State**: Multi-turn conversation memory and learned user context

**Option B** (user preferences, projects, people) is considered a subset of C and will be included in agent state.

**Implementation**: Deferred to **Phase 7** (Week 25+ 推迟实施,待Phase 4完成后启动)

**Gate finalization policy**: Phase 7 Go/No-Go gates are finalized only after Phase 4 production learnings are reviewed.

## Rationale

### Why A + C?

1. **User value**: Summaries provide tangible value (review "what did I do last week?")
2. **Chat enhancement**: Agent state makes chat smarter (remembers past conversations, user preferences)
3. **Complementary**: Summaries are data-driven, agent state is interaction-driven
4. **Incremental**: Can be built in stages (summaries first, then agent state)

### Why NOT Now (MVP)?

1. **Foundation dependency**: Requires Phase 4 (Chat) to be complete first
2. **Not MVP-critical**: Core value is multi-modal search + basic chat
3. **Learning opportunity**: Phase 4 will reveal what memory features users actually need
4. **Timeline pressure**: 20周硬约束(约5个月)对应Phase 5部署迁移 - must focus on P0-P4

### Why NOT Option B Separately?

- Option B (user preferences, projects, people) is a natural subset of Option C (agent state)
- Implementing them separately would create redundant storage and APIs
- Better to have a unified "agent memory" that includes preferences

## Consequences

### Positive ✅

- Clear scope definition reduces ambiguity
- Phase 4 roadmap remains focused on simple chat
- Memory design can leverage Phase 4 learnings (what users actually ask)
- Timeline flexibility (not on critical path)

### Negative ❌

- Memory capabilities won't be available at MVP launch
- May need to refactor chat API later to integrate memory
- Users won't experience "intelligent agent" behavior initially

## Implementation Plan (Phase 7)

### Component 1: Summary Engine

**Trigger**: Scheduled background job (daily at 2AM, weekly on Monday)

**Process**:
1. Query timeline data for time period (last 24h or 7 days)
2. Aggregate activity by app, window title, keywords
3. Send to LLM with prompt: "Summarize this user's activity"
4. Store summary in new `summaries` table

**API**:
```
GET /api/v1/memory/summary?date=YYYY-MM-DD&type=daily|weekly
```

### Component 2: Agent Memory Store

**Storage**:
- **User preferences**: Work hours, important projects, frequent contacts
- **Conversation history**: Past chat interactions (truncated to last N turns)
- **Learned patterns**: "User typically codes in VSCode 9-5, meetings on Zoom in afternoons"

**API**:
```
POST /api/v1/memory/preference
{
  "key": "work_hours",
  "value": "09:00-17:00 PST"
}

GET /api/v1/memory/context
// Returns all user context for chat LLM prompt injection
```

**Chat Integration**:
- Chat API calls `get_user_context()` before invoking LLM
- Injects context into system prompt: "User works 9-5, currently working on ProjectX, prefers concise answers"

### Go/No-Go Gates (决议已定,需Phase 7执行时验证)

Based on:
- User feedback on what memory features matter most
- LLM token cost vs. value tradeoffs
- Privacy/security considerations for storing long-term context

## Alternatives Considered

### Option 1: A Only (Summaries)
- **Pros**: Simpler, clear user value
- **Cons**: Doesn't enhance chat intelligence
- **Rejected**: Too narrow, misses opportunity for smarter agent

### Option 2: C Only (Agent State)
- **Pros**: Focused on chat enhancement
- **Cons**: No standalone value outside of chat
- **Rejected**: Summaries provide value even if user doesn't use chat

### Option 3: Implement in Phase 4
- **Pros**: Smarter chat from day 1
- **Cons**: Adds 1-2 weeks to Phase 4, increases MVP risk
- **Rejected**: Timeline pressure, better to validate basic chat first

## Success Criteria (Phase 7)

- [ ] Daily summaries generated and stored within 5min of 2AM job
- [ ] Summary quality rated ≥7/10 by user (manual review)
- [ ] Chat responses include relevant user context (validated in testing)
- [ ] Agent memory persists across sessions (conversation history restored)

## Related ADRs

- ADR-0001: Python-First Principle
- ADR-0002: Thin Client Architecture (memory data stored on Debian server)

## References

- Phase 7 roadmap status: `v3/milestones/roadmap-status.md#phase-7-memory-capabilities`
- Decision log (memory): `v3/milestones/roadmap-status.md#-resolution-3-p3-memory-capability-definition-2026-02-06`
- OpenClaw memory concepts: https://docs.openclaw.ai/concepts/memory
