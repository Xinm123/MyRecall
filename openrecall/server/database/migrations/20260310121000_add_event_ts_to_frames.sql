ALTER TABLE frames ADD COLUMN event_ts TEXT DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_frames_event_ts ON frames(event_ts)
    WHERE event_ts IS NOT NULL;
