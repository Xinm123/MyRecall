-- Migration v3_008: Add source/timing fields to audio_chunks
-- Version: 8
-- Date: 2026-02-13
-- Description: Adds start/end time and source direction metadata to audio_chunks
--              for timeline-style audio rendering and filtering.

ALTER TABLE audio_chunks ADD COLUMN start_time REAL;
ALTER TABLE audio_chunks ADD COLUMN end_time REAL;
ALTER TABLE audio_chunks ADD COLUMN is_input INTEGER;
ALTER TABLE audio_chunks ADD COLUMN source_kind TEXT DEFAULT 'unknown';

-- Backfill timing fields from existing timestamp
UPDATE audio_chunks
SET start_time = timestamp
WHERE start_time IS NULL;

UPDATE audio_chunks
SET end_time = timestamp
WHERE end_time IS NULL;

-- Backfill source_kind from device name heuristics
UPDATE audio_chunks
SET source_kind = CASE
    WHEN LOWER(COALESCE(device_name, '')) LIKE '%mic%' THEN 'input'
    WHEN LOWER(COALESCE(device_name, '')) LIKE '%microphone%' THEN 'input'
    WHEN LOWER(COALESCE(device_name, '')) LIKE '%system%' THEN 'output'
    WHEN LOWER(COALESCE(device_name, '')) LIKE '%speaker%' THEN 'output'
    WHEN LOWER(COALESCE(device_name, '')) LIKE '%loopback%' THEN 'output'
    ELSE 'unknown'
END
WHERE source_kind IS NULL OR source_kind = '' OR source_kind = 'unknown';

-- Align is_input with source_kind
UPDATE audio_chunks
SET is_input = CASE
    WHEN source_kind = 'input' THEN 1
    WHEN source_kind = 'output' THEN 0
    ELSE NULL
END
WHERE is_input IS NULL;

CREATE INDEX IF NOT EXISTS idx_audio_chunks_start_time ON audio_chunks(start_time);
CREATE INDEX IF NOT EXISTS idx_audio_chunks_source_kind ON audio_chunks(source_kind);
