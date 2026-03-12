# OpenSpec Apply Workflow & Task Checkbox Updates — Authoritative Reference

**Date Generated:** March 12, 2026  
**OpenSpec Version:** 1.2.0  
**Status:** Current & verified against official CLI behavior

---

## Table of Contents

1. [Quick Command Reference](#quick-command-reference)
2. [Core Workflow: Selection → Status → Instructions → Apply](#core-workflow)
3. [Task Checkbox Updates (Critical Caveat)](#task-checkbox-updates)
4. [Practical Examples](#practical-examples)
5. [Known Issues & Workarounds](#known-issues--workarounds)
6. [Skills Integration & Expected Behavior](#skills-integration--expected-behavior)

---

## Quick Command Reference

### Status Inspection

```bash
# List all changes with task counts
openspec list --json

# Output:
# {
#   "changes": [
#     {
#       "name": "p1-s2b-ax-capture",
#       "completedTasks": 51,
#       "totalTasks": 86,
#       "lastModified": "2026-03-12T06:48:04.037Z",
#       "status": "in-progress"
#     }
#   ]
# }
```

### Check Change Status

```bash
openspec status --change "<change-name>" --json
openspec status --change "<change-name>" --schema <schema-override>

# Returns:
# - schemaName: workflow being used (e.g., "spec-driven")
# - artifacts: array of { id, status ("done"|"ready"|"blocked") }
# - isComplete: boolean
```

### Get Apply Instructions

```bash
openspec instructions apply --change "<change-name>" --json
openspec instructions apply --change "<change-name>" --schema <schema-override>

# Returns:
# - contextFiles: paths to read (varies by schema: proposal/specs/design/tasks)
# - progress: { total, complete, remaining }
# - tasks: array of task objects with status
# - state: "ready" | "blocked" | "all_done"
# - instruction: dynamic guidance based on current state
```

### Artifact-Specific Instructions

```bash
# Get instructions for creating a specific artifact
openspec instructions <artifact-id> --change "<change-name>" --json

# artifact-id examples: "proposal", "design", "tasks", "specs"
# Returns:
# - template: markdown structure to fill in
# - instruction: specific guidance
# - outputPath: where to write the artifact
# - dependencies: artifacts to read first
# - rules: constraints to apply
```

---

## Core Workflow

### Phase 1: Select the Change

**Option A: Explicit name (recommended)**
```bash
openspec instructions apply --change "p1-s2b-ax-capture" --json
```

**Option B: Discover available changes**
```bash
openspec list --json  # Get all changes + modification times
```

- Sort by `lastModified` descending (most recent = current work)
- For parallel multi-agent applies: user selects which group to focus on
- Infer from conversation context if clear (e.g., "continue S2b" → "p1-s2b-ax-capture")

---

### Phase 2: Understand Schema & Artifacts

```bash
openspec status --change "p1-s2b-ax-capture" --json
```

**Parse response for:**
- `schemaName`: Determines artifact flow (e.g., "spec-driven" = proposal → design → tasks → apply)
- `artifacts`: Which are done, ready, blocked
- `isComplete`: Whether all artifacts exist

**Common schemas:**
| Schema | Artifact Flow | Apply Starts When |
|--------|---------------|-------------------|
| `spec-driven` | proposal → specs → design → tasks | tasks.md exists |
| `tdd` | proposal → design → tasks | tasks.md exists |
| Custom | Varies | Per schema definition |

---

### Phase 3: Load Context Before Implementation

```bash
openspec instructions apply --change "p1-s2b-ax-capture" --json
```

**Extract from response:**
- `contextFiles`: List of files to read BEFORE starting tasks
  - For spec-driven: typically `[proposal.md, specs/, design.md, tasks.md]`
  - Read these in order for full context
- `progress`: Current task count (e.g., "51 of 86 complete")
- `state`: One of:
  - `"ready"` → proceed to implementation
  - `"blocked"` → missing artifacts; suggest openspec-continue-change
  - `"all_done"` → all tasks complete; suggest openspec-archive-change

**Handle blocked state:**
```bash
# If state = "blocked", check status for artifact dependencies:
openspec status --change "p1-s2b-ax-capture" --json
# Then use: openspec-continue-change skill to unblock
```

---

### Phase 4: Implement Tasks with Checkbox Tracking

**Task Format in tasks.md:**
```markdown
## Implementation Tasks

### 1. Slice A - Setup
- [ ] 1.1 Task description
- [ ] 1.2 Another task
- [x] 1.3 Already done

### 2. Slice B - Feature
- [ ] 2.1 Next task
```

**Checkbox States:**
- `- [ ]` = pending (not started)
- `- [x]` = complete (finished)

**Update Procedure (CRITICAL — See [Task Checkbox Updates](#task-checkbox-updates)):**

```bash
# After implementing each task:
# 1. Make code changes
# 2. Update the checkbox in tasks.md:
#    - [ ] 2.1 Task → - [x] 2.1 Task
# 3. (Do NOT commit yet during apply)
# 4. Continue to next task
```

---

## Task Checkbox Updates

### ⚠️ CRITICAL CAVEAT: Deterministic Sync Is Currently Unsolved

**Reference:** [GitHub Issue #805 - feat(apply): explore deterministic task completion sync](https://github.com/Fission-AI/OpenSpec/issues/805)  
**Status (2026-03-05):** Open — root cause identified, approach TBD

**The Problem:**
- When agents/humans complete tasks during `/opsx:apply`, the checkbox state (`- [ ]` → `- [x]`) is NOT automatically synced
- `openspec list --json` shows `completedTasks: 0` even after full apply run
- Reason: The coder prompt says "mark task complete" but provides no mechanism
- In parallel multi-agent applies: multiple agents may edit `tasks.md` simultaneously → race conditions / overwrites

**Current Workaround (Manual but Reliable):**

1. **Edit `tasks.md` directly after each task:**
   ```markdown
   # Before:
   - [ ] 4.3 GREEN: Modify openrecall/client/recorder.py
   
   # After implementing:
   - [x] 4.3 GREEN: Modify openrecall/client/recorder.py
   ```

2. **For parallel multi-agent workflows:**
   - Each agent edits their own task group sequentially within the group
   - After each edit, send a completion signal (e.g., SendMessage)
   - Team-lead receives signal, verifies tasks.md was updated, confirms in single location

3. **Verify sync worked:**
   ```bash
   openspec list --json
   # Expected: "completedTasks": 51, "totalTasks": 86
   # If "completedTasks" still 0, checkboxes weren't parsed correctly
   ```

**Three Proposed Solutions (Issue #805):**

| Approach | Pros | Cons | Status |
|----------|------|------|--------|
| **Agent edits tasks.md directly** | Simple, minimal overhead | Requires agents to find exact line; no undo/verify | Under evaluation |
| **Team-lead marks done on signal** | Centralized, deterministic, one source of truth | Adds coordination overhead | Under evaluation |
| **Post-run reconciliation script** | Batch update after all agents finish | Delayed feedback, requires external tracking | Under evaluation |

**Recommendation for Robust Execution:**
- Until Issue #805 is resolved, **treat checkbox updates as a manual checklist item**
- Add to your apply-phase checklist: "After each task → update checkbox in tasks.md"
- Verify with `openspec list --json` at the end of the session

---

## Practical Examples

### Example 1: Single-Agent Apply (Complete Flow)

```bash
# 1. Select change
openspec list --json
# → Shows: p1-s2b-ax-capture (51/86 tasks complete)

# 2. Check status
openspec status --change "p1-s2b-ax-capture" --json
# → Shows: schemaName="spec-driven", isComplete=false

# 3. Get apply instructions
openspec instructions apply --change "p1-s2b-ax-capture" --json
# → Returns: contextFiles=[...], progress={...}, state="ready"

# 4. Read context files
cat openspec/changes/p1-s2b-ax-capture/proposal.md
cat openspec/changes/p1-s2b-ax-capture/design.md
cat openspec/changes/p1-s2b-ax-capture/tasks.md

# 5. Start implementing
# - Pick first incomplete task: "4.3 GREEN: Modify openrecall/client/recorder.py"
# - Make code changes
# - Update checkbox: - [ ] 4.3... → - [x] 4.3...
# - Repeat until done or blocked

# 6. Verify at end
openspec list --json
# → Should show updated completedTasks count
```

### Example 2: Parallel Multi-Agent Apply (Team Workflow)

**Setup:**
- Change: `p1-s2b-ax-capture` (86 tasks total, divided into 3 groups)
- Group 1 (tasks 1-30): Agent A
- Group 2 (tasks 31-60): Agent B  
- Group 3 (tasks 61-86): Agent C

**Workflow:**

```bash
# Team-lead: Initialize
openspec instructions apply --change "p1-s2b-ax-capture" --json
# Send contextFiles to all agents

# Agent A (sequential within group):
openspec instructions apply --change "p1-s2b-ax-capture" --json
# Read context, implement tasks 1-5
# Update checkboxes in tasks.md (tasks 1-5)
# Send: "Tasks 1-5 complete"

# Agent B (parallel, different group):
openspec instructions apply --change "p1-s2b-ax-capture" --json
# Read context, implement tasks 31-35
# Update checkboxes in tasks.md (tasks 31-35)
# Send: "Tasks 31-35 complete"

# Agent A continues:
# Implement tasks 6-10, update checkboxes
# Send: "Tasks 6-10 complete"

# Team-lead (after all agents finish):
openspec list --json
# Verify: completedTasks matches expected total
git diff openspec/changes/p1-s2b-ax-capture/tasks.md
# Confirm all expected checkboxes are [x]
```

**Key Safeguard:**
- Each agent commits/pushes their section of `tasks.md` changes AFTER their completion signal
- Prevents simultaneous edits to same file
- Team-lead waits for git history to reflect all agent commits before declaring complete

---

## Known Issues & Workarounds

### Issue #1: Task Checkbox Sync Not Deterministic (Issue #805)

**Symptom:** `openspec list --json` shows `completedTasks: 0` after tasks were completed

**Cause:** Checkboxes were not updated in `tasks.md`, or format was incorrect

**Workaround:**
```bash
# Verify format is correct:
cat openspec/changes/p1-s2b-ax-capture/tasks.md | grep "^\s*- \[.\]"

# Expected: - [x] or - [ ] (space or x between brackets)
# Common mistake: - [x ] (extra space), - [X] (capital X)

# Fix all occurrences:
sed -i 's/- \[X\]/- [x]/g' openspec/changes/p1-s2b-ax-capture/tasks.md
sed -i 's/- \[x \]/- [x]/g' openspec/changes/p1-s2b-ax-capture/tasks.md
sed -i 's/- \[ \]/- [ ]/g' openspec/changes/p1-s2b-ax-capture/tasks.md
```

**Verify:**
```bash
openspec list --json
# If still showing 0, re-check format or check if file was saved properly
```

### Issue #2: Blocked State When Artifacts Missing

**Symptom:** `openspec instructions apply` returns `state: "blocked"`

**Cause:** Missing prerequisite artifact(s) (e.g., `design.md` not created yet)

**Resolution:**
```bash
openspec status --change "p1-s2b-ax-capture" --json
# Check `artifacts` array for `status: "ready"` items

# Use openspec-continue-change to create missing artifacts:
# (user invokes skill, not manual CLI)
```

### Issue #3: Schema Mismatch When Overriding

**Symptom:** `openspec instructions apply` returns unexpected artifact list

**Cause:** Schema override via `--schema` flag doesn't match actual change schema

**Workaround:**
```bash
# Always check current schema first:
openspec status --change "p1-s2b-ax-capture" --json | grep schemaName

# Only override if absolutely necessary:
openspec instructions apply --change "p1-s2b-ax-capture" --schema spec-driven --json
# If override conflicts, remove flag and let CLI auto-detect
```

---

## Skills Integration & Expected Behavior

### openspec-apply-change Skill

**When to invoke:**
- User says: "Let's start implementing" / "Work on the tasks" / "Apply the change"
- During apply phase of spec-driven workflow

**What it does:**
1. Selects change (infers from context or prompts user)
2. Announces: `Using change: p1-s2b-ax-capture`
3. Runs `openspec status --json` to understand schema
4. Runs `openspec instructions apply --json` to get dynamic guidance
5. Reads context files (proposal, design, specs, tasks)
6. Implements tasks in a loop:
   - Shows: `Working on task N/M: <description>`
   - Implements code
   - Updates checkbox: `- [ ]` → `- [x]`
   - Continues
7. On completion: shows final status, suggests archive

**Expected Output:**
```
## Implementing: p1-s2b-ax-capture (schema: spec-driven)

Reading context:
- proposal.md ✓
- specs/auth-session/spec.md ✓
- design.md ✓
- tasks.md ✓

Progress: 51/86 tasks complete

Working on task 52/86: 4.3 GREEN: Modify openrecall/client/recorder.py
[... implementation ...}
✓ Task complete

Working on task 53/86: 4.3a RED: Add worker runtime tests
[... implementation ...]
✓ Task complete

...

## Implementation Complete

**Change:** p1-s2b-ax-capture
**Progress:** 86/86 tasks complete ✓

All tasks finished! Ready to archive.
```

### openspec-continue-change Skill

**When apply is blocked:**
- Skill detects `state: "blocked"` from instructions output
- Returns: "This change is blocked — you need to create the next artifact first."
- Suggests invoking openspec-continue-change

**Workflow:**
```bash
openspec status --change "p1-s2b-ax-capture" --json
# Suppose: design.md is ready, tasks.md not yet created

# User invokes openspec-continue-change
# Skill runs: openspec instructions tasks --change "p1-s2b-ax-capture" --json
# Creates tasks.md using template
# Then: openspec-apply-change can proceed
```

### openspec-verify-change Skill

**When to invoke:**
- After implementing all tasks, before archiving
- To ensure tasks are complete AND code changes are correct

**What it does:**
1. Parses tasks.md, counts checkboxes
2. Searches codebase for spec requirement evidence
3. Checks for test coverage per scenario
4. Generates verification report
5. Lists any missing tasks or requirements

**Expected Output:**
```
## Verification Report: p1-s2b-ax-capture

| Dimension    | Status              |
|--------------|---------------------|
| Completeness | 86/86 tasks ✓       |
| Correctness  | 15/15 requirements  |
| Coherence    | Design-adherent ✓   |

No issues found. Ready to archive.
```

---

## Summary: Robust Apply Execution Checklist

- [ ] Run `openspec list --json` — identify target change
- [ ] Run `openspec status --change "<name>" --json` — confirm schema
- [ ] Run `openspec instructions apply --change "<name>" --json` — check for blocking issues
- [ ] Read all `contextFiles` before starting implementation
- [ ] For each task:
  - [ ] Implement code changes
  - [ ] Update checkbox in tasks.md: `- [ ]` → `- [x]`
  - [ ] Verify edit was saved
- [ ] After completing all tasks:
  - [ ] Run `openspec list --json` — verify completedTasks updated
  - [ ] Invoke openspec-verify-change — check correctness
  - [ ] Invoke openspec-archive-change — finalize change
- [ ] Commit with message: `feat(p1-s2b-ax-capture): implement all tasks`

---

## References

- **OpenSpec Official:** https://openspec.dev/
- **GitHub Repository:** https://github.com/Fission-AI/OpenSpec
- **Issue #805 (Task Sync):** https://github.com/Fission-AI/OpenSpec/issues/805
- **Local Skills:**
  - `/Users/pyw/old/MyRecall/.opencode/skills/openspec-apply-change/SKILL.md`
  - `/Users/pyw/old/MyRecall/.opencode/skills/openspec-verify-change/SKILL.md`
  - `/Users/pyw/old/MyRecall/.opencode/skills/openspec-continue-change/SKILL.md`
- **Live Example Change:** `openspec/changes/p1-s2b-ax-capture/` (51/86 tasks complete)

