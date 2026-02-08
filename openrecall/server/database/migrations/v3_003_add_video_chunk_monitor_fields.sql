-- v3_003: add monitor identity columns for monitor-id driven capture
ALTER TABLE video_chunks ADD COLUMN monitor_id TEXT DEFAULT '';
ALTER TABLE video_chunks ADD COLUMN monitor_width INTEGER DEFAULT 0;
ALTER TABLE video_chunks ADD COLUMN monitor_height INTEGER DEFAULT 0;
ALTER TABLE video_chunks ADD COLUMN monitor_is_primary INTEGER DEFAULT 0;
ALTER TABLE video_chunks ADD COLUMN monitor_backend TEXT DEFAULT '';
ALTER TABLE video_chunks ADD COLUMN monitor_fingerprint TEXT DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_video_chunks_monitor_id ON video_chunks(monitor_id);
