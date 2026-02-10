-- Migration v3_006: Add status column to audio_chunks for processing workflow
-- Version: 6
-- Date: 2026-02-09
-- Description: Adds status column and indexes for audio chunk processing
--              state machine (PENDING -> PROCESSING -> COMPLETED/FAILED),
--              mirroring video_chunks status pattern from v3_002.

ALTER TABLE audio_chunks ADD COLUMN status TEXT DEFAULT 'PENDING';
CREATE INDEX IF NOT EXISTS idx_audio_chunks_status ON audio_chunks(status);
CREATE INDEX IF NOT EXISTS idx_audio_chunks_timestamp ON audio_chunks(timestamp);
