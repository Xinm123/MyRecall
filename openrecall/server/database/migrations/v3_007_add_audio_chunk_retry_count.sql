-- Migration v3_007: Add retry_count column to audio_chunks
-- Version: 7
-- Date: 2026-02-09
-- Description: Tracks retry attempts for failed audio chunks to prevent
--              infinite reprocessing of permanently broken files.

ALTER TABLE audio_chunks ADD COLUMN retry_count INTEGER DEFAULT 0;
