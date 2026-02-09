-- v3_005: add start/end timestamps for precise offset guard validation
-- Phase 1.5: enables frame-to-chunk time window checking
ALTER TABLE video_chunks ADD COLUMN start_time REAL;
ALTER TABLE video_chunks ADD COLUMN end_time REAL;

CREATE INDEX IF NOT EXISTS idx_video_chunks_start_time ON video_chunks(start_time);
