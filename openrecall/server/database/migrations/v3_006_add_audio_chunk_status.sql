-- v3_006: Add status column to audio_chunks for async processing pipeline
-- Mirrors v3_002 pattern (video_chunks status column)
-- Phase 2.0: Audio MVP

ALTER TABLE audio_chunks ADD COLUMN status TEXT DEFAULT 'PENDING';
