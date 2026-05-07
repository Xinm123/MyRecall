-- Migration: Description Fields Redesign
-- Date: 2026-04-08
-- Changes: Replace entities_json + intent with tags_json, expand narrative/summary lengths

-- SQLite doesn't support ALTER COLUMN, so we need to recreate the table

-- Step 1: Create new table with new schema
CREATE TABLE frame_descriptions_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    frame_id INTEGER NOT NULL REFERENCES frames(id),
    narrative TEXT NOT NULL,
    summary TEXT NOT NULL,
    tags_json TEXT NOT NULL DEFAULT '[]',
    description_model TEXT,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(frame_id)
);

-- Step 2: Copy data from old table (migrate existing descriptions)
-- entities_json and intent are dropped, tags_json gets empty array
INSERT INTO frame_descriptions_new (
    id, frame_id, narrative, summary, tags_json, description_model, generated_at
)
SELECT
    id,
    frame_id,
    narrative,
    summary,
    '[]',  -- tags_json default to empty array
    description_model,
    generated_at
FROM frame_descriptions;

-- Step 3: Drop old table
DROP TABLE frame_descriptions;

-- Step 4: Rename new table
ALTER TABLE frame_descriptions_new RENAME TO frame_descriptions;

-- Step 5: Recreate indexes
CREATE INDEX idx_fd_frame_id ON frame_descriptions(frame_id);
