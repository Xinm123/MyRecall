-- Migration v3_002: Add processing status to video_chunks
-- Version: 2
-- Date: Phase 1
-- Description: Adds status column for video chunk processing state machine
--              (PENDING -> PROCESSING -> COMPLETED/FAILED)
--              and index on status for worker queue polling.

ALTER TABLE video_chunks ADD COLUMN status TEXT DEFAULT 'PENDING';
CREATE INDEX IF NOT EXISTS idx_video_chunks_status ON video_chunks(status);
