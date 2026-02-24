# Vision Chat MVP (Evidence-First, Screenpipe-Aligned) — Spec + Paste-Ready Prompt

**Date**: 2026-02-23  
**Scope Lock**: Vision-only (frames + OCR + metadata) / Audio Freeze / Evidence-first / Screenpipe-aligned Search contract / Browser-local timezone authority

---

## 1. Core Problem (WHY)

MyRecall-v3 needs to converge on a single “trustworthy MVP loop” that users can rely on daily:

- Ask a question about a specific time range
- Get a concise answer
- Click evidence to verify (frames on timeline)

The key failure mode to avoid is “nice-sounding but unverifiable” chat output.

---

## 2. Scope Lock (WHAT)

### In Scope (Phase 4 MVP)

- **Vision-only grounding**:
  - Allowed sources: video frames, OCR text, metadata fields (`app_name`, `window_name`, `focused`, `browser_url`).
  - All retrieval must operate on **bounded time ranges**.
- **Chat MVP (non-streaming)**:
  - Server does **single retrieval + single summary** (no tool-calling in Phase 4).
  - UI aligns to screenpipe’s Chat presentation as much as possible (input, message list, evidence list, clickable frames).
- **Time-range summary** as the first Go/No-Go scenario:
  - “总结一下我今天 14:00-17:00 做了什么”
- **Screenpipe-aligned time semantics**:
  - UI defines time ranges in the user’s local timezone
  - UI converts to epoch seconds (`float`) and sends to server
  - Server filters by absolute time only (no timezone inference)

### Out of Scope (Non-Goals)

- Audio capture/transcription/search parity and all speaker/diarization work (Audio Freeze)
- UI/input events grounding
- Tool-calling orchestration (defer to Phase 6+)
- Streaming chat (defer to Phase 6+)
- Memory (summaries/agent state) (defer to Phase 7+)

---

## 2.5 Current vs Target (Implementation Deviation Snapshot)

This spec is target-authoritative. Current implementation deviations are explicitly tracked below to prevent planning blind spots.

| Surface | Target (this spec) | Current implementation (2026-02-24) | Convergence action |
|---|---|---|---|
| `GET /api/v1/search` browse mode | Empty/missing `q` returns browse/feed over bounded range | Empty/missing `q` currently returns empty payload | Implement browse/feed path in Phase 3 |
| `GET /api/v1/search` time bounds | `start_time` required, `end_time` optional | `start_time` not enforced at route layer | Add hard request validation in Phase 3 |
| Search modality | Vision-only retrieval for Chat grounding | Search engine still includes audio FTS candidates | Enforce vision-only search path for Chat in Phase 3 |
| `POST /api/v1/chat` | Exists and returns `answer_md + evidence[]` | Endpoint not implemented yet | Implement Phase 4 Chat API |
| `GET /api/v1/timeline` usage | Chat grounding relies on vision evidence only | Timeline returns mixed video+audio by default | Keep timeline mixed for ops; enforce vision-only in Search/Chat pipeline |

---

## 3. Evidence Contract (NON-NEGOTIABLE)

### 3.1 Chat Response Shape (recommended)

Chat endpoint should return a structured payload:

- `answer_md`: Markdown string (concise)
- `time_range`: `{ start_time, end_time, timezone }`
- `evidence[]`: list of evidence items
  - Rule: if the answer asserts user activity or specific moments, `evidence` must be **non-empty**
  - Pure how-to/explanation replies may return `evidence=[]`
  - Evidence item fields:
    - `frame_id` (int)
    - `timestamp` (epoch seconds, float)
    - `local_time` (string, rendered in user timezone)
    - `app_name`, `window_name`
    - `focused`, `browser_url`
    - `ocr_snippet` (short)
    - `frame_url` (e.g. `/api/v1/frames/:id`)

### 3.2 Evidence Rules

- Evidence MUST come from real retrieval results within the request’s time range.
- Never fabricate frame IDs, timestamps, or URLs.
- Server should validate that every `frame_id` exists before returning.

---

## 4. Phase 4 Grounding Strategy (Single Retrieval + Single Summary)

### 4.1 Why this strategy

This is the “recommended / least-bug” grounding plan:

- One bounded retrieval step
- One LLM call that only summarizes provided context
- No iterative tool calling, no agent loops

It aligns with screenpipe’s discipline: bounded time ranges, small tool surface, and clickable evidence.

### 4.2 Retrieval Source (Screenpipe-Aligned)

Phase 4 grounding uses Phase 3 Search behavior (screenpipe `/search`-like):

- Use `/api/v1/search` in **browse mode** (`q` missing or empty string)
- Use **mandatory** `start_time` (epoch seconds)
- Use optional `end_time` (epoch seconds, default now)
- Use optional filters: `app_name`, `window_name`, `focused`, `browser_url`
- Vision-only: `content_type=ocr` (or equivalent server default)

### 4.3 Sampling / Truncation (5min buckets, 2 frames per bucket)

Goal: avoid bias toward the end of the range, keep token cost bounded, and ensure coverage.

Constants (Phase 4 defaults):

- `DEFAULT_BUCKET_SECONDS = 300` (5 minutes)
- `FRAMES_PER_BUCKET = 2`
- `MAX_FRAMES = 72` (hard cap for LLM context + evidence list)
- `MAX_OCR_CHARS_PER_FRAME = 160` (truncate OCR to keep context small)

Algorithm:

1. Let `range_seconds = end_time - start_time`.
2. Compute `bucket_seconds`:
   - Start with `DEFAULT_BUCKET_SECONDS`.
   - If `ceil(range_seconds / bucket_seconds) * FRAMES_PER_BUCKET > MAX_FRAMES`, auto-widen:
     - `bucket_seconds = ceil(range_seconds / (MAX_FRAMES / FRAMES_PER_BUCKET))`
     - Ensure `bucket_seconds >= DEFAULT_BUCKET_SECONDS`.
3. Partition `[start_time, end_time)` into contiguous buckets.
4. For each bucket:
   - Select up to 2 frames within the bucket (deterministic):
     - `first` (earliest timestamp)
     - `last` (latest timestamp, if distinct)
5. If total selected frames still exceeds `MAX_FRAMES`, drop overflow from the densest buckets (stable rule) until within cap.
6. If the candidate frame count is already small (<= `MAX_FRAMES`), keep all frames (still sorted chronologically).

### 4.4 LLM Context Packing (Text-Only)

Phase 4 does **not** send raw frame images to the LLM.

For each selected frame, pack a small text block:

- `local_time` (user timezone)
- `app_name`, `window_name`
- `browser_url` (if present)
- `focused` (if present)
- `ocr_snippet` (truncate to `MAX_OCR_CHARS_PER_FRAME`)
- `frame_id` + `frame_url` (for evidence linking)

Then call the LLM once to produce:

- a short time-range summary (paragraphs + bullet list)
- `evidence[]` referencing the provided `frame_id`s only

---

## 5. “System Prompt + Skill” Pattern (HOW)

### 5.1 Dynamic System Prompt (Phase 4)

Generate at request time and include:

- Current time (ISO)
- User timezone (IANA tz name + UTC offset)
- Hard rules (bounded time range; no fabricated evidence; vision-only; no images)
- Output schema reminders (`answer_md`, `evidence[]`)

Screenpipe reference:
- `screenpipe/apps/screenpipe-app-tauri/components/standalone-chat.tsx` (`buildSystemPrompt`)

### 5.2 Skill-Style Tooling (Phase 6+, not Phase 4)

We still model server internals as a “skill surface” to keep boundaries clean, but Phase 4 does not do tool-calling.

Future (Phase 6+) candidates:

- `search_ocr(start_time, end_time, q?, filters...)` → `/api/v1/search`
- `get_frame(frame_id)` → `/api/v1/frames/:id`

Screenpipe reference:
- `screenpipe/apps/screenpipe-app-tauri/src-tauri/assets/skills/screenpipe-search/SKILL.md` (bounded `/search`)

---

## 6. Provider Strategy (Cloud Test → Debian Local)

- Phase 4 testing uses a cloud LLM.
- Phase 5/6 transitions to a Debian-box local LLM.
- Both MUST be OpenAI-compatible at the API boundary, so no app-level branching is required.

Optional (recommended) architecture direction:

- Adopt a **registry-style** provider interface (inspired by nanobot’s ProviderSpec/registry) so `ChatProvider` is swappable.
- Phase 4 should keep this minimal: only wrap what’s needed for one non-streaming call.

---

## 7. Milestones (Roadmap Snapshot)

Authoritative tracker:
- `MyRecall/v3/milestones/roadmap-status.md`

Near-term:
- Phase 3: Vision Search Parity (screenpipe-aligned search contract, browse mode)
- Phase 4: Vision Chat MVP (single retrieval + single summary; evidence-first; non-streaming)

---

## 8. Paste-Ready Prompt (Optimized)

Use this prompt for future “critical discussion → converge → update docs” sessions:

"""
你是我的「首席架构师 + 技术产品负责人」，目标是把 MyRecall-v3 收敛到可交付的 vision-only Chat MVP，并尽可能对齐 screenpipe 的交互与约束模式。

硬约束（不可违背）：
1) Vision-only：Chat/Search 只能使用 video frames + OCR + metadata（app/window/focused/browser_url）。
2) Audio Freeze：暂停所有音频相关开发与对齐（采集/存储/检索/Chat 集成）。
3) Evidence-first：当回答涉及用户活动/具体时刻的断言时，必须输出 evidence[]（真实 frame_id + timestamp + frame_url）；纯说明回答允许 evidence 为空；禁止编造证据。
4) Time semantics（对齐 screenpipe）：以浏览器本地时区定义时间范围；前端转 epoch seconds；后端只做绝对时间过滤。
5) Phase 4 grounding：单轮检索 + 单次总结（服务端做检索/排序/采样/截断，把候选 OCR+metadata 喂给 LLM，总结并生成 evidence[]）；不做 tool-calling；不传 raw frame image。
6) Sampling：默认 5 分钟/桶，每桶最多 2 帧；时间范围过长时自动扩大桶宽以控制总帧数（有硬上限）。

Phase 3 Search contract（对齐 screenpipe /search）：
- q 可选；q 为空表示 browse/feed 模式（按 timestamp DESC）
- start_time 必填（epoch seconds）；end_time 可选（默认 now）
- 支持过滤：app_name/window_name/focused/browser_url

第一个 Go/No-Go 用例（必须优先打通）：
- “总结一下我今天 14:00-17:00 做了什么”（非流式；vision-only；必须带 evidence[] 可点击验证）

你必须保持批判性：
- 主动质疑不成立的用例（例如需要音频才能回答的“讨论”）
- 每个结构性选择都给出：理由、优势、劣势、失败信号、对产出影响
- 同时说明 screenpipe 的处理方式（给出 repo 内对应文件/模块名），以及 MyRecall 是否可对齐/差异点

输出要求（必须落盘到 MyRecall/v3）：
- 一份“核心功能列表 + 优先级排序”（明确 In/Out scope）
- 一份“可执行 roadmap + milestones”（含阶段 gates、关键文件/接口、风险与回滚）
"""
