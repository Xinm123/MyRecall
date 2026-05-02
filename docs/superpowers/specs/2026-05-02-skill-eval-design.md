# Skill Evaluation Design: myrecall-search vs myrecall (Modular)

**Date**: 2026-05-02  
**Status**: Draft — pending review

---

## 1. Problem Statement

We maintain 4 variants of the `myrecall-search` skill in `openrecall/client/chat/skills/`:

| Variant | File(s) | Lines | Structure |
|---------|---------|-------|-----------|
| `myrecall-search` v1 (current prod) | `SKILL.md` | 432 | Step Decision Tree + Common Scenario Mappings (structural contradiction) |
| `myrecall-search` v2 | `v2/SKILL.md` | 311 | Step Tree + Question Map + Anti-patterns |
| `myrecall-search` v3 | `v3/SKILL.md` | 279 | Question Map only (single source) |
| `myrecall` (modular) | `SKILL.md` + `summary.md` + `search.md` + `content.md` | 465 total | Progressive node loading |

A **static analysis** (`tests/skill_eval/EVALUATION_REPORT.md`) already compared v1/v2/v3 on redundancy, contradiction, and maintenance cost. But **we have never run real agent behavior tests** on any version, nor compared the modular `myrecall/` variant against monolithic versions.

This spec defines a **behavior-driven evaluation framework** that:
1. Feeds each skill to a real LLM agent (Pi via minimax-cn)
2. Sends a curated set of prompts
3. Records which API endpoints the agent calls
4. Scores correctness (endpoint choice, params, redundancy, multi-turn context reuse)
5. Produces a quantitative comparison report

---

## 2. Goals & Success Criteria

### Primary Goals
1. **Measure endpoint correctness**: Does the agent call the right API for each prompt?
2. **Measure parameter correctness**: Are required params (`start_time`, `end_time`, `q`, `app_name`) present?
3. **Measure call efficiency**: Does the agent make redundant calls?
4. **Measure multi-turn context reuse**: In a 2-turn conversation, does the agent extract info from turn 1 to avoid re-querying in turn 2?
5. **Measure modular overhead**: Does the `myrecall/` modular skill require extra node-file reads, and does that hurt or help?

### Success Criteria
- All 4 skills run through all prompts (3 runs each) within 3 hours wall-clock
- Average score ≥ 80/100 for at least one skill (averaged across all prompts and runs)
- Multi-turn context reuse rate ≥ 60% (at least 2 of 4 D-scenarios show reuse)
- Report clearly identifies which skill variant is optimal for production

---

## 3. Skills Under Test

### 3.1 Monolithic Skills (v1, v2, v3)

These are single-file skills. For testing, each is copied to `~/.pi/agent/skills/myrecall-search/SKILL.md` with URL substitution (`localhost:8083` → `localhost:18083`).

### 3.2 Modular Skill (`myrecall/`)

Structure:
```
myrecall/
  SKILL.md      — Entry point: progressive disclosure strategy + node loading instructions
  summary.md    — Activity summary endpoint docs
  search.md     — Search endpoint docs
  content.md    — Frame context + image endpoint docs
```

For testing, the entire directory is copied to `~/.pi/agent/skills/myrecall/` with URL substitution. Pi's `--skill` flag accepts a directory.

**Expected modular behavior**:
- Turn 1 "Summarize my day": Read `SKILL.md` → Read `summary.md` → call `/activity-summary`
- Turn 2 "Find PR": Read `SKILL.md` → Read `search.md` → call `/search`
- The extra `Read` calls are **measurable overhead** that we score.

---

## 4. Test Prompts

### 4.1 Group A — Existing English Prompts (12)

Reused from `tests/skill_eval/test_cases.json`:

| ID | Prompt | Expected Primary Endpoint | Forbidden |
|---|---|---|---|
| T1 | What was I doing today? | `/activity-summary` | `/search` |
| T2 | Which apps did I use yesterday? | `/activity-summary` | `/search` |
| T3 | Find the PR I was reviewing | `/search` | — |
| T4 | Did I see anything about AI? | `/search` | — |
| T5 | Did I open GitHub today? | `/activity-summary` or composite | — |
| T6 | What was I doing in frame 42? | `/frames/42/context` | `/search`, `/activity-summary` |
| T7 | What did I code in VSCode? | `/search` + `app_name` | — |
| T8 | How long did I spend on Safari? | `/activity-summary` | `/search` |
| T9 | Show me a screenshot | `/search` or `/activity-summary` (acceptable) | — |
| T10 | Show me frame 42 | `/frames/42` | `/search` |
| T11 | Summarize my day | `/activity-summary` | `/search` |
| T12 | Did I see anything about React in the last hour? | `/search` | `/activity-summary` |

### 4.2 Group B — Chinese Prompts (12)

Mirror of Group A to validate multilingual robustness:

| ID | Prompt | Maps to |
|---|---|---|
| T1-zh | 我今天在干啥? | T1 |
| T2-zh | 我昨天用了哪些 app? | T2 |
| T3-zh | 找一下我之前在 review 的那个 PR | T3 |
| T4-zh | 我有没有看过 AI 相关的内容? | T4 |
| T5-zh | 我今天打开过 GitHub 吗? | T5 |
| T6-zh | 我在 frame 42 里在干啥? | T6 |
| T7-zh | 我在 VSCode 里写了什么代码? | T7 |
| T8-zh | 我今天在 Safari 上花了多久? | T8 |
| T9-zh | 给我看一张截图 | T9 |
| T10-zh | 给我看 frame 42 | T10 |
| T11-zh | 总结一下我今天 | T11 |
| T12-zh | 最近一小时我看过 React 相关的吗? | T12 |

### 4.3 Group C — Module Loading Tests (5)

Specifically designed to exercise modular skill's node-loading behavior:

| ID | Prompt | Expected Behavior (modular) | Expected (monolithic) |
|---|---|---|---|
| M1 | Summarize my activity | Read `summary.md` → `/activity-summary` | Read `SKILL.md` → `/activity-summary` |
| M2 | Find frames containing "password" | Read `search.md` → `/search?q=password` | Read `SKILL.md` → `/search?q=password` |
| M3 | What text is in frame 42? | Read `content.md` → `/frames/42/context` | Read `SKILL.md` → `/frames/42/context` |
| M4 | Show me frame 42 screenshot | Read `content.md` → `/frames/42` | Read `SKILL.md` → `/frames/42` |
| M5 | Which apps did I use today? | **No *additional* node read needed** — main `SKILL.md` already contains the Question-to-Endpoint Map | Read `SKILL.md` → `/activity-summary` |

> M5 is a **negative control**: the main `SKILL.md` already contains the Question-to-Endpoint Map, so the agent should not need to read any node file. If it does, that's unnecessary overhead.

### 4.4 Group D — Multi-Turn Conversations (4 scenarios, 8 turns)

Each scenario is a 2-turn conversation within a single Pi session.

#### D1: Summary → Drill-down
```
T1: "Summarize my day today"
    → Expected: /activity-summary (returns frame_id 102: "Reviewing PR #456 in VSCode")

T2: "Tell me more about that PR review in VSCode"
    → Expected: /frames/102/context (reuses frame_id from T1)
    → Forbidden in T2: /search (should not re-search)
```

#### D2: Time Pivot
```
T1: "Summarize my day today"
    → Expected: /activity-summary (today)

T2: "What about yesterday?"
    → Expected: /activity-summary (yesterday) — same endpoint, different time range
    → Forbidden in T2: /search
```

#### D3: Search → Drill-in
```
T1: "Find the PR I was reviewing"
    → Expected: /search?q=PR (returns [201, 202])

T2: "What did the first search result contain?"
    → Expected: /frames/201/context (reuses "first result = frame 201" from T1)
    → Forbidden in T2: /search (should not re-search)
```

#### D4: Modular Cross-Node Switch
```
T1: "Summarize my activity"
    → Modular: Read SKILL.md → Read summary.md → /activity-summary
    → Monolithic: Read SKILL.md → /activity-summary

T2: "Find frames containing 'password'"
    → Modular: Read SKILL.md → Read search.md → /search?q=password
    → Monolithic: Read SKILL.md → /search?q=password
```

> D4 scored on standard 120-point scale. Overhead metrics (node reads per turn) reported separately for analysis.

---

## 5. Mock Server Enhancements

Current `mock_server.py` has hardcoded data with a single date (2026-04-30) and `or True` in search filtering. For reliable evaluation, enhance:

### 5.1 Date-Aware Responses

| Query Date | `activity-summary` returns | `search` returns |
|---|---|---|
| 2026-05-02 (today) | VSCode PR review, Safari browsing, Python tests | frames 201, 202 |
| 2026-05-01 (yesterday) | Safari docs reading, Slack discussion, Xcode build | frames 301, 302 |
| Other dates | Empty / zero frames | Empty |

Implementation: parse `start_time` from query params, extract the date portion, return matching dataset.

### 5.2 Real Search Filtering

Remove `or True`. Implement keyword matching against:
- `description.summary` (e.g., "Reviewing PR #456")
- `window_name` (e.g., "pull_request.py")
- `text` field (when `include_text=true`)

| Query | Matches |
|---|---|
| `q=PR` | frame 201 (window: pull_request.py) |
| `q=AI` | frame 203 (description: "Reading about AI models") |
| `q=React` | frame 204 (text: "Building a React component") |
| `q=password` or `q=密码` | frame 205 (text: "change your password") |
| `q=code` | frames 201, 202 (VSCode windows) |
| `q=*` or empty | all frames |

### 5.3 Frame Context Differentiation

Current `/frames/{id}/context` returns the same narrative for all IDs. Change to:

| frame_id | `description.narrative` | `app_name` |
|---|---|---|
| 101 | "Browsing GitHub issues in Safari" | Safari |
| 102 | "Reviewing PR #456 in VSCode" | VSCode |
| 103 | "Writing Python unit tests" | VSCode |
| 201 | "Editing pull_request.py in VSCode" | VSCode |
| 202 | "Writing test_runner.py in VSCode" | VSCode |
| 203 | "Reading about AI models" | Safari |
| 204 | "Building a React component" | VSCode |
| 205 | "Changing password on settings page" | Chrome |

### 5.4 Chinese Content Support

Add Chinese text fields to some frames so Chinese prompts can match:

```json
{
  "frame_id": 101,
  "text": "浏览 GitHub 问题列表...",
  "description": {"summary": "在 Safari 中浏览 GitHub 问题"}
}
```

---

## 6. Scoring Framework

### 6.1 Single-Turn Scoring (100 points)

| Dimension | Points | Rule |
|---|---|---|
| **Endpoint** | 40 | Primary endpoint called? Partial credit (30) for acceptable alternative. |
| **Parameters** | 30 | All required params present? -10 per missing param. |
| **No Redundant** | 30 | No forbidden endpoints called? 0 if any forbidden endpoint used. |
| **Total** | **100** | |

### 6.2 Multi-Turn Scoring (120 points)

Same as single-turn, plus:

| Dimension | Points | Rule |
|---|---|---|
| **Context Reuse** | 20 | T2 uses information extracted from T1 (frame_id, time range, app_name) without re-querying. Partial (10) if some reuse + some re-query. |
| **Total** | **120** | |

### 6.3 Modular Overhead Scoring (bonus, not counted in main total)

For modular skill only, tracked separately:

| Metric | Description |
|---|---|
| **Node Reads** | Count of `Read` tool calls targeting `.md` node files per prompt |
| **Extra Turns** | Number of turns where a node read was necessary vs. monolithic's zero |
| **Overhead per Prompt** | Average node reads per prompt |

### 6.4 Aggregate Metrics

Per skill, compute:
- **Average Score** (all prompts, all runs)
- **Pass Rate** (% of prompts scoring ≥ 80)
- **Variance** (stddev across 3 runs — measures consistency)
- **Context Reuse Rate** (% of multi-turn T2 showing reuse)

---

## 7. Harness Design

### 7.1 Architecture

```
+------------------+     +------------------+     +------------------+
|   Test Script    |────▶|   Pi CLI Agent   |────▶|   Mock Server    |
|  (Python)        |     |  (minimax-cn)    |     |  (port 18083)    |
|                  |◀────|                  |◀────|                  |
+------------------+     +------------------+     +------------------+
       │
       ▼
+--------------------------------------------------+
|  Skill Variant (copied to ~/.pi/agent/skills/)   |
|  - v1/v2/v3: myrecall-search/SKILL.md            |
|  - modular: myrecall/ (directory)                |
+--------------------------------------------------+
```

### 7.2 Skill Switching Procedure

For each skill variant:
1. **Stop** any running Pi process
2. **Copy** skill files to `~/.pi/agent/skills/myrecall-search/` (or `myrecall/`)
3. **Substitute** URL: `localhost:8083` → `localhost:18083`
4. **Clear** mock server log
5. **Run** prompt sequence
6. **Collect** log → score → next variant

### 7.3 Pi Invocation

```bash
PI_OFFLINE=1 \
MINIMAX_CN_API_KEY="$KEY" \
bun run ~/.myrecall/pi-agent/node_modules/@mariozechner/pi-coding-agent/dist/cli.js \
  --provider minimax-cn \
  --model MiniMax-M2 \
  --skill ~/.pi/agent/skills/myrecall-search \
  --no-skills \
  --tools read,bash \
  --session /tmp/pi_session_{scenario}.jsonl \
  -p "$PROMPT"
```

For multi-turn, second turn adds `--continue`:
```bash
  --continue -p "$PROMPT2"
```

### 7.4 Log Parsing

Mock server writes JSON lines to `/tmp/skill_test_multiturn.log`:
```json
{"timestamp": "2026-05-02T10:00:00Z", "method": "GET", "path": "/v1/search", "args": {"q": "PR", "limit": "5"}}
```

Test script parses these entries, filters by `/v1/` prefix, and feeds to `evaluate.py` scoring logic.

---

## 8. Execution Plan

### Phase 1: Infrastructure (1 day)
1. Enhance `mock_server.py` with date-aware responses, real search filtering, differentiated frame contexts
2. Add Chinese text content to mock data
3. Write `pi_test_runner.py` — harness that runs Pi, collects logs, scores results
4. Validate harness with 2-3 manual runs

### Phase 2: Execution (1 day)
1. Run all 4 skills × 33 prompts × 3 runs
2. Total runs: ~420 turns (including multi-turn T2s)
3. Estimated wall time: ~3 hours (parallelization: can run skills sequentially, but each skill's prompts must be sequential to preserve Pi session state)

### Phase 3: Analysis (0.5 day)
1. Aggregate scores per skill
2. Compute variance, pass rate, context reuse rate
3. Write comparison report

### Phase 4: Decision (0.5 day)
1. Present report to stakeholders
2. Recommend which skill to promote to production
3. Document migration plan if switching

---

## 9. Deliverables

| Deliverable | Location | Format |
|---|---|---|
| Enhanced mock server | `tests/skill_eval/mock_server.py` | Python (Flask) |
| Test harness | `tests/skill_eval/pi_test_runner.py` | Python |
| Scoring script | `tests/skill_eval/evaluate.py` (enhanced) | Python |
| Test case definitions | `tests/skill_eval/test_cases_v2.json` | JSON |
| Raw results | `tests/skill_eval/results/{skill}/{run}.json` | JSON |
| Comparison report | `tests/skill_eval/EVALUATION_REPORT_V2.md` | Markdown |

---

## 10. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Pi CLI behavior changes across versions | Medium | High | Pin Pi version (`@mariozechner/pi-coding-agent@0.60.0`) |
| minimax-cn API rate limiting | Medium | Medium | Add 2s delay between runs; retry on 429 |
| Mock server data insufficient for some prompts | Low | Medium | Pre-validate all prompts against mock data before full run |
| Pi session state not preserved correctly | Low | High | Validate with `--continue` flag; fallback to single-turn if broken |
| Modular skill's `Read` calls not visible in logs | Low | Medium | Pi's `--verbose` mode or parse stdout for tool execution events |
| Test takes longer than estimated | Medium | Low | Run overnight; results are deterministic enough to batch |

---

## 11. Open Questions

1. Should we test with **multiple models** (e.g., MiniMax-M2 vs MiniMax-M2.5) to measure skill robustness across model capabilities?
2. Should we include **negative tests** (e.g., "delete all my frames") to verify skill's "out of scope" section is effective?
3. Should the modular skill's `summary.md`/`search.md`/`content.md` be **also tested standalone** (without main `SKILL.md`) to see if they work in isolation?

---

## Appendix A: Prompt-to-Expected Mapping (Complete)

See sections 4.1–4.4 above.

## Appendix B: Mock Data Schema

```json
{
  "dates": {
    "2026-05-02": {
      "activity_summary": { "apps": [...], "descriptions": [...] },
      "search_frames": [...]
    },
    "2026-05-01": {
      "activity_summary": { "apps": [...], "descriptions": [...] },
      "search_frames": [...]
    }
  },
  "frame_contexts": {
    "101": { "narrative": "...", "app_name": "Safari", ... },
    "102": { "narrative": "...", "app_name": "VSCode", ... }
  }
}
```
