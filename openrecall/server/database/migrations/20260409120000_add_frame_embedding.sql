-- Migration: 20260409120000_add_frame_embedding.sql
-- Created: 2026-04-09
-- Purpose: Add frame embedding support for multimodal vector search
-- Tables: embedding_tasks (task queue for embedding generation),
--         frames.embedding_status (tracks embedding generation state)
-- Note: Transaction is managed by migrations_runner.py, do not add BEGIN/COMMIT here.

-- 1. Add embedding_status to frames table
ALTER TABLE frames ADD COLUMN embedding_status TEXT DEFAULT NULL;

-- 2. Create embedding_tasks table
CREATE TABLE IF NOT EXISTS embedding_tasks (
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

CREATE INDEX IF NOT EXISTS idx_et_status ON embedding_tasks(status);
CREATE INDEX IF NOT EXISTS idx_et_next_retry ON embedding_tasks(next_retry_at);
CREATE INDEX IF NOT EXISTS idx_et_frame_id ON embedding_tasks(frame_id);
