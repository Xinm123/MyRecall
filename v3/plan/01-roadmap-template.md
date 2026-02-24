# Phase Template for MyRecall-v3

**Use this template for planning each new phase.**

---

## Phase N: [Phase Name]

**Status**: [Not Started | In Progress | Complete | Blocked | Paused | Frozen | Superseded]
**Scope Type**: [Target Plan | Current-State Snapshot | Historical Record]
**Superseded By**: [ADR-XXXX | N/A]
**Timeline**: Week X-Y (Z days)
**Owner**: [Name]
**Priority**: [P0 | P1 | P2 | P3 | P4]

---

### 1. Goal (WHY)

**Objective**: [One-sentence description of what this phase achieves]

**Business Value**: [How does this phase contribute to project goals?]

**User Impact**: [What can users do after this phase that they couldn't before?]

---

### 2. Scope (WHAT)

**In-Scope**:
- [ ] Feature A
- [ ] Feature B
- [ ] Feature C

**Out-of-Scope (Non-Goals)**:
- ❌ Explicitly excluded feature X (defer to Phase N+1)
- ❌ Explicitly excluded feature Y (not needed for MVP)

---

### 3. Key Tasks (HOW)

**Task Breakdown** (assign to sub-phases if >5 tasks):

| Task | Description | Estimated Days | Dependencies | Assignee | Status |
|------|-------------|----------------|--------------|----------|--------|
| 3.1 | [Task name] | [Days] | [Phase/Task] | [Name] | ⬜️ |
| 3.2 | [Task name] | [Days] | [Phase/Task] | [Name] | ⬜️ |
| 3.3 | [Task name] | [Days] | [Phase/Task] | [Name] | ⬜️ |

**Critical Files**:
- `/path/to/file1.py` - [Purpose]
- `/path/to/file2.py` - [Purpose]

---

### 4. Inputs & Outputs

**Inputs** (prerequisites from previous phases):
- [ ] Input A from Phase N-1 (e.g., schema migration complete)
- [ ] Input B from Phase N-1 (e.g., API versioning in place)

**Outputs** (deliverables for next phases):
- ✅ Output A for Phase N+1 (e.g., video chunks in database)
- ✅ Output B for Phase N+1 (e.g., timeline API endpoint)

**Current vs Target Drift (Required when Scope Type = Target Plan)**:

| Surface | Target Contract | Current Reality | Gap Owner | Target Phase |
|---|---|---|---|---|
| `/api/v1/example` | [Desired behavior] | [Current behavior] | [Owner] | [Phase] |

---

### 5. Milestones

| Milestone | Description | Target Date | Actual Date | Status |
|-----------|-------------|-------------|-------------|--------|
| M1: [Name] | [Description] | Week X | TBD | ⬜️ |
| M2: [Name] | [Description] | Week Y | TBD | ⬜️ |
| M3: [Name] | [Description] | Week Z | TBD | ⬜️ |

---

### 6. Acceptance Criteria (GO/NO-GO GATES)

#### 6.1 Functional Gates

| Gate | Criteria | Validation Method | Status |
|------|----------|-------------------|--------|
| **Gate 1** | [Specific measurable criterion] | [How to test] | ⬜️ |
| **Gate 2** | [Specific measurable criterion] | [How to test] | ⬜️ |

#### 6.2 Performance Gates

| Metric | Target | Measurement Method | Status |
|--------|--------|-------------------|--------|
| **Latency** | <X seconds | [How to measure] | ⬜️ |
| **CPU Usage** | <Y% | [How to measure] | ⬜️ |
| **Memory** | <Z MB | [How to measure] | ⬜️ |

#### 6.3 Quality Gates

| Metric | Target | Measurement Method | Status |
|--------|--------|-------------------|--------|
| **Accuracy** | ≥X% | [How to measure] | ⬜️ |
| **Precision** | ≥Y% | [How to measure] | ⬜️ |

#### 6.4 Stability Gates

| Gate | Criteria | Validation Method | Status |
|------|----------|-------------------|--------|
| **Continuous Run** | Zero crashes over X hours | [How to test] | ⬜️ |
| **Success Rate** | >Y% over Z days | [How to measure] | ⬜️ |

---

### 7. Estimated Timeline

**Total Duration**: [X] days / [Y] weeks

**Breakdown**:
- Week 1: [Tasks 1-3]
- Week 2: [Tasks 4-6]
- Week 3: [Tasks 7-9]

**Confidence Level**: [High | Medium | Low] - [Explain why]

---

### 8. Parallel Tasks (If Any)

**Tasks That Can Run Concurrently**:
1. Task A (independent of Task B)
2. Task B (independent of Task A)

**Resource Requirements**:
- Parallelization requires [X] developers / [Y] machines

---

### 9. Major Risks & Mitigation Strategies

| Risk | Trigger | Probability | Impact | Mitigation | Owner |
|------|---------|-------------|--------|------------|-------|
| **Risk 1** | [What signals this risk?] | [Low/Med/High] | [Low/Med/High/Critical] | [How to mitigate?] | [Name] |
| **Risk 2** | [What signals this risk?] | [Low/Med/High] | [Low/Med/High/Critical] | [How to mitigate?] | [Name] |

**Overall Risk Level**: [Low | Medium | High]

---

### 10. Degradation Strategies (Failure Handling)

| Failure Scenario | Detection Method | Fallback Behavior | Recovery Path |
|------------------|------------------|-------------------|---------------|
| **Scenario 1** | [How to detect?] | [What happens?] | [How to recover?] |
| **Scenario 2** | [How to detect?] | [What happens?] | [How to recover?] |

---

### 11. Failure Signals (ABORT CONDITIONS)

**Abandon this phase approach if**:
- [ ] Signal 1: [Specific measurable condition that indicates approach is failing]
- [ ] Signal 2: [Specific measurable condition that indicates approach is failing]

**Alternative Approach** (if abandoned):
- [Describe backup plan]

---

### 12. Validation Metrics

**How to Measure Success**:

| Dimension | Metric | Target | Actual | Status |
|-----------|--------|--------|--------|--------|
| **Performance** | [Metric name] | [Target value] | TBD | ⬜️ |
| **Accuracy** | [Metric name] | [Target value] | TBD | ⬜️ |
| **Stability** | [Metric name] | [Target value] | TBD | ⬜️ |
| **Resource Usage** | [Metric name] | [Target value] | TBD | ⬜️ |
| **User Experience** | [Metric name] | [Target value] | TBD | ⬜️ |

**Validation Report Location**: `v3/results/phase-N-validation.md`

---

### 13. Dependencies

**Upstream Dependencies** (this phase depends on):
- [ ] Phase N-1: [Specific deliverable]
- [ ] External: [Tool/library/service]

**Downstream Dependencies** (phases that depend on this):
- Phase N+1: [Specific requirement]
- Phase N+2: [Specific requirement]

**Blocking Issues**: [None | Issue #123 - Description]

---

### 14. Open Questions (Requires Decision)

| Question | Options | Recommendation | Decision By | Status |
|----------|---------|----------------|-------------|--------|
| **Q1** | A, B, C | [Recommended option] | [Date/Person] | ⬜️ |
| **Q2** | A, B | [Recommended option] | [Date/Person] | ⬜️ |

---

### 15. Team & Resources

**Team**:
- Lead: [Name]
- Contributors: [Name 1], [Name 2]
- Reviewers: [Name 3]

**Resource Requirements**:
- [ ] [X] developers for [Y] days
- [ ] [Z] GPU hours for testing
- [ ] Cloud resources: [Description]

---

### 16. Communication Plan

**Stakeholder Updates**:
- **Frequency**: [Daily | Weekly | At milestones]
- **Channel**: [Slack | Email | Stand-up]
- **Format**: [Progress report template]

**Review Points**:
- [ ] Kickoff meeting (before phase start)
- [ ] Mid-phase review (Day X)
- [ ] Phase completion review (after go/no-go gates)

---

### 17. Documentation Updates

**Docs to Update During This Phase**:
- [ ] `v3/milestones/roadmap-status.md` (progress tracking)
- [ ] `v3/decisions/ADR-NNNN-*.md` (if major decision made)
- [ ] `README.md` (user-facing features)
- [ ] Code comments (inline documentation)

---

### 18. Change Log

| Date | Type | Description | Impact |
|------|------|-------------|--------|
| YYYY-MM-DD | [Plan/Scope/Timeline] | [What changed?] | [How does it affect other phases?] |

---

## Approval

- **Planned By**: [Name] on [Date]
- **Reviewed By**: [Name] on [Date]
- **Approved By**: [Name] on [Date]
- **Status**: [Draft | Under Review | Approved | Rejected | Paused | Frozen | Superseded]
