-- v3_004: persist chunk-level app/window metadata for frame attribution
ALTER TABLE video_chunks ADD COLUMN app_name TEXT DEFAULT '';
ALTER TABLE video_chunks ADD COLUMN window_name TEXT DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_video_chunks_app_name ON video_chunks(app_name);
