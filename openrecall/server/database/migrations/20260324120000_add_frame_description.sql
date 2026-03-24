-- Migration: 20260324120000_add_frame_description.sql
-- Created: 2026-03-24
-- Purpose: Add frame description support for AI-generated narrative descriptions
-- Tables: frame_descriptions (store generated descriptions per frame),
--         description_tasks (task queue for description generation pipeline),
--         frames.description_status (tracks description generation state)
-- Note: Transaction is managed by migrations_runner.py, do not add BEGIN/COMMIT here.

-- 1. Add description_status to frames table
ALTER TABLE frames ADD COLUMN description_status TEXT DEFAULT NULL;

-- 2. Create frame_descriptions table
CREATE TABLE IF NOT EXISTS frame_descriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    frame_id INTEGER NOT NULL REFERENCES frames(id),
    narrative TEXT NOT NULL,
    entities_json TEXT NOT NULL,
    intent TEXT NOT NULL,
    summary TEXT NOT NULL,
    description_model TEXT,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(frame_id)
);
CREATE INDEX IF NOT EXISTS idx_fd_frame_id ON frame_descriptions(frame_id);

-- 3. Create description_tasks table
CREATE TABLE IF NOT EXISTS description_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    frame_id INTEGER NOT NULL REFERENCES frames(id),
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending','processing','completed','failed')),
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    next_retry_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    UNIQUE(frame_id)
);
CREATE INDEX IF NOT EXISTS idx_dt_status ON description_tasks(status);
CREATE INDEX IF NOT EXISTS idx_dt_next_retry ON description_tasks(next_retry_at);
