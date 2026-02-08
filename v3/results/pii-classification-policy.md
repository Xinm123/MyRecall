# MyRecall-v3 PII Classification Policy

**Version**: 1.1
**Date**: 2026-02-07
**Phase**: 0 baseline, refreshed in Phase 1
**Status**: Approved (Phase 1 monitor-id privacy guidance added)

---

## Purpose

This document classifies personally identifiable information (PII) that MyRecall may capture through its multi-modal recording pipeline (screen, audio), and defines the handling strategy for each category.

---

## PII Categories

| # | PII Category | Data Source | Sensitivity | Phase | Detection Strategy | Handling |
|---|---|---|---|---|---|---|
| 1 | **Screen text** (names, emails, SSN, phone numbers) | OCR on video frames | High | Phase 1 | Regex patterns on OCR text (future implementation) | Encrypted at rest (filesystem); retention policy enforced |
| 2 | **Application credentials** (passwords, API keys, tokens) | OCR on browser/terminal frames | Critical | Phase 1 | Pattern matching for common credential formats (future) | No persistent storage of detected credentials; redaction policy |
| 3 | **Audio speech content** (conversations, dictation) | Whisper transcription of audio | High | Phase 2 | Encryption at rest; no content filtering in Phase 2.0 | Filesystem encryption (FileVault/LUKS); retention policy |
| 4 | **Speaker identity** (voice patterns) | Speaker diarization (Phase 2.1) | Medium | Phase 2.1 (optional) | Opt-in only per ADR-0004 | Speaker embeddings stored only if user opts in |
| 5 | **Facial images** in video frames | Video frame capture | High | Phase 1 | No face detection in Phase 1 | No face storage policy; frames store screen content only |
| 6 | **App usage patterns** (apps used, timestamps, window titles) | Frame metadata | Low | Phase 0+ | Metadata collected by default | Retention policy (30 days default); user can delete |

---

## Handling Principles

1. **Minimize collection**: Only capture what is needed for the core use case (screen recall and audio transcription).
2. **Encrypt at rest**: All captured data relies on filesystem encryption (macOS FileVault / Linux LUKS). Application-layer encryption fields (`encrypted` column) are reserved for future Phase 5 enforcement.
3. **Retention limits**: All tables include `created_at` and `expires_at` fields. Default retention is 30 days (configurable via `OPENRECALL_RETENTION_DAYS`).
4. **User control**: User can delete any data at any time. Phase 5 will add a dedicated Deletion API.
5. **No external data sharing**: All data stays on the user's machine (or their Debian server in Phase 5). No cloud analytics or telemetry.

---

## Multi-Screen Privacy Capture Guide

For multi-monitor setups, configure monitor allowlist explicitly to avoid capturing sensitive side screens.

1. Use `OPENRECALL_VIDEO_MONITOR_IDS` to record only approved displays (comma-separated monitor IDs).
2. Keep `OPENRECALL_PRIMARY_MONITOR_ONLY=true` when only the primary work screen should be captured.
3. Keep chat/IM/finance dashboards on excluded monitors when possible.
4. Verify selected monitor IDs at client startup logs before long recording sessions.
5. Re-validate monitor mapping after display hot-plug/reboot on Linux/Windows (index ordering can change).

Example:

```bash
# Record only monitor IDs 69734144 and 69734145
OPENRECALL_VIDEO_MONITOR_IDS=69734144,69734145
OPENRECALL_PRIMARY_MONITOR_ONLY=false
```

---

## Phase-by-Phase Implementation

| Phase | PII Action |
|-------|------------|
| **Phase 0** | Schema supports encryption fields and retention timestamps. PII policy documented. |
| **Phase 1** | Video frames captured; no PII detection yet. Filesystem encryption assumed. |
| **Phase 2.0** | Audio transcribed; no PII filtering. Filesystem encryption assumed. |
| **Phase 2.1** | Speaker diarization opt-in only (ADR-0004). |
| **Phase 5** | API authentication enforced. Deletion API. HTTPS/TLS. Audit logging. |

---

## Review Schedule

This policy should be reviewed at:
- Phase 1 completion (video pipeline active)
- Phase 2 completion (audio pipeline active)
- Phase 5 completion (remote deployment)
