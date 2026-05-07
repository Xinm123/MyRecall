-- Add UNIQUE constraint to ocr_text.frame_id
-- Migration: 20260317000001_ocr_text_unique_frame_id.sql
-- Created: 2026-03-17
-- Purpose: Ensure each frame has at most one ocr_text row (P1-S3 idempotency D5.1)

-- Drop the existing non-unique index if it exists
DROP INDEX IF EXISTS idx_ocr_text_frame_id;

-- Create unique index to enforce one-to-one relationship
CREATE UNIQUE INDEX IF NOT EXISTS idx_ocr_text_frame_id_unique ON ocr_text(frame_id);
