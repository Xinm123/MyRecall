-- Migration v3_001: Add multimodal tables for Phase 1 (video) and Phase 2 (audio)
-- Version: 1
-- Date: 2026-02-06
-- Description: Creates schema_version, video_chunks, frames, ocr_text,
--              audio_chunks, audio_transcriptions tables + FTS5 virtual tables
--              + governance columns on existing entries table.

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now')),
    description TEXT
);

-- Video chunks (populated in Phase 1)
CREATE TABLE IF NOT EXISTS video_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    device_name TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT,
    encrypted INTEGER DEFAULT 0,
    checksum TEXT
);

-- Frames (populated in Phase 1)
CREATE TABLE IF NOT EXISTS frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_chunk_id INTEGER NOT NULL,
    offset_index INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    app_name TEXT DEFAULT '',
    window_name TEXT DEFAULT '',
    focused INTEGER DEFAULT 0,
    browser_url TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (video_chunk_id) REFERENCES video_chunks(id) ON DELETE CASCADE
);

-- OCR text for frames (populated in Phase 1)
CREATE TABLE IF NOT EXISTS ocr_text (
    frame_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    text_json TEXT,
    ocr_engine TEXT DEFAULT '',
    text_length INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (frame_id) REFERENCES frames(id) ON DELETE CASCADE
);

-- Audio chunks (populated in Phase 2)
CREATE TABLE IF NOT EXISTS audio_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    timestamp REAL NOT NULL,
    device_name TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT,
    encrypted INTEGER DEFAULT 0,
    checksum TEXT
);

-- Audio transcriptions (populated in Phase 2)
CREATE TABLE IF NOT EXISTS audio_transcriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audio_chunk_id INTEGER NOT NULL,
    offset_index INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    transcription TEXT NOT NULL,
    transcription_engine TEXT DEFAULT '',
    speaker_id INTEGER,
    start_time REAL,
    end_time REAL,
    text_length INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (audio_chunk_id) REFERENCES audio_chunks(id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_frames_video_chunk_id ON frames(video_chunk_id);
CREATE INDEX IF NOT EXISTS idx_frames_timestamp ON frames(timestamp);
CREATE INDEX IF NOT EXISTS idx_frames_app_name ON frames(app_name);
CREATE INDEX IF NOT EXISTS idx_frames_timestamp_offset ON frames(timestamp, offset_index);
CREATE INDEX IF NOT EXISTS idx_ocr_text_frame_id ON ocr_text(frame_id);
CREATE INDEX IF NOT EXISTS idx_audio_transcriptions_chunk_id ON audio_transcriptions(audio_chunk_id);
CREATE INDEX IF NOT EXISTS idx_audio_transcriptions_timestamp ON audio_transcriptions(timestamp);
CREATE INDEX IF NOT EXISTS idx_audio_transcriptions_chunk_ts ON audio_transcriptions(audio_chunk_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_video_chunks_created_at ON video_chunks(created_at);
CREATE INDEX IF NOT EXISTS idx_audio_chunks_created_at ON audio_chunks(created_at);

-- FTS5 virtual tables (for future Phase 1/2 writes)
CREATE VIRTUAL TABLE IF NOT EXISTS ocr_text_fts USING fts5(
    text, app_name, window_name,
    frame_id UNINDEXED,
    tokenize='unicode61'
);

CREATE VIRTUAL TABLE IF NOT EXISTS audio_transcriptions_fts USING fts5(
    transcription, device,
    audio_chunk_id UNINDEXED, speaker_id UNINDEXED,
    tokenize='unicode61'
);
