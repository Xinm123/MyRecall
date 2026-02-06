# MyRecall-v3 Retention Policy Design

**Version**: 1.0
**Date**: 2026-02-06
**Phase**: 0 (Foundation)
**Status**: Approved

---

## Purpose

This document describes the data retention mechanism designed in Phase 0 for MyRecall v3. The schema foundation is laid in Phase 0; actual cleanup enforcement is implemented in Phase 1/2 workers.

---

## Schema Support

All data tables include retention-supporting columns:

| Column | Type | Purpose | Default |
|--------|------|---------|---------|
| `created_at` | TEXT | Record creation timestamp | `datetime('now')` |
| `expires_at` | TEXT | Scheduled expiration time | NULL (no expiration) |

### Tables with retention columns:
- `entries` (added via ALTER TABLE in migration)
- `video_chunks` (built-in)
- `frames` (built-in)
- `ocr_text` (built-in)
- `audio_chunks` (built-in)
- `audio_transcriptions` (built-in)

---

## Retention Rules

| Rule | Value | Configurable Via |
|------|-------|-----------------|
| **Default retention period** | 30 days | `OPENRECALL_RETENTION_DAYS` env var |
| **Minimum retention** | 1 day | Hard-coded floor |
| **Maximum retention** | Unlimited (NULL expires_at) | Setting expires_at to NULL |

---

## Cleanup Mechanism

### Phase 0 (Current)
- Schema columns created (`created_at`, `expires_at`)
- No active cleanup job
- `expires_at` is NULL for all rows (no automatic deletion)

### Phase 1/2 (Future)
- Background cleanup job runs as part of ProcessingWorker
- Periodically scans for rows where `expires_at < datetime('now')`
- Deletes expired rows and associated files (screenshots, video chunks, audio chunks)
- Runs at configurable interval (default: every 6 hours)

### Phase 5 (Future)
- Server-side enforcement of retention policy
- Admin API to set/update retention period
- Audit logging of deletions

---

## Backfill Strategy

During Phase 0 migration:
1. `created_at` column added to existing `entries` table
2. Existing entries backfilled: `created_at = datetime(timestamp, 'unixepoch')`
3. `expires_at` set to empty string (no expiration for existing data)

---

## File Cleanup

When a database row expires:
1. Delete the row from the database
2. Delete associated files:
   - Screenshots: `{screenshots_path}/{timestamp}.png`
   - Video chunks: `{file_path}` from `video_chunks` table
   - Audio chunks: `{file_path}` from `audio_chunks` table
3. Clean up orphaned FTS entries
4. Log the deletion for audit

---

## Upload Queue TTL

The client-side upload queue (ADR-0002) has a separate TTL:
- **TTL**: 7 days
- **Purpose**: Prevent disk bloat if server is unavailable
- **Mechanism**: Files with mtime > 7 days are deleted by `UploadQueue.cleanup_expired()`
- **This is independent of server-side retention policy**
