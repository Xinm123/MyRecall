-- Migration: 20260321120000_dual_hash_storage.sql
-- Created: 2026-03-21
-- Purpose: Add phash column for visual similarity (separate from text simhash)
-- Aligns with screenpipe's dual-hash architecture:
--   - simhash: text-based, word 3-shingles (accessibility/OCR text)
--   - phash: image-based, perceptual hash (visual similarity)

-- Add phash column for visual similarity detection
ALTER TABLE frames ADD COLUMN phash INTEGER DEFAULT NULL;

-- Create index for phash lookups (partial index for efficiency)
CREATE INDEX IF NOT EXISTS idx_frames_phash ON frames(phash) WHERE phash IS NOT NULL;
