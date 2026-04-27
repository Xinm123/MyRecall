-- Add local_timestamp column for UTC+8 timezone support
ALTER TABLE frames ADD COLUMN local_timestamp TEXT;

-- Index for local time queries
CREATE INDEX idx_frames_local_timestamp ON frames(local_timestamp);
