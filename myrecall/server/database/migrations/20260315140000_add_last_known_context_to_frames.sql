ALTER TABLE frames ADD COLUMN last_known_app TEXT DEFAULT NULL;
ALTER TABLE frames ADD COLUMN last_known_window TEXT DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_frames_last_known_app 
    ON frames(last_known_app) 
    WHERE last_known_app IS NOT NULL;
