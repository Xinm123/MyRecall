-- Migration: 20260414000000_add_visibility_status.sql
-- Created: 2026-04-14
-- Purpose: Add visibility_status column to track when frames are fully queryable
--          (OCR + description + embedding complete)
-- Note: Transaction is managed by migrations_runner.py, do not add BEGIN/COMMIT here.

-- 1. Add visibility_status column to frames table
ALTER TABLE frames ADD COLUMN visibility_status TEXT DEFAULT 'pending';

-- 2. Create index for query performance (visibility_status + timestamp DESC for chronological queries)
CREATE INDEX idx_frames_visibility ON frames(visibility_status, timestamp DESC);

-- 3. Backfill existing frames that are already fully processed
--    A frame is 'queryable' when all three processing stages are 'completed'
UPDATE frames
SET visibility_status = 'queryable'
WHERE status = 'completed'
  AND description_status = 'completed'
  AND embedding_status = 'completed';

-- 4. Backfill frames with permanent failures in any processing stage
UPDATE frames
SET visibility_status = 'failed'
WHERE status = 'failed'
   OR description_status = 'failed'
   OR embedding_status = 'failed';
