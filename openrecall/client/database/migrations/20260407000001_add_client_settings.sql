-- Migration: Add client_settings table for Web UI configuration
-- Created: 2026-04-07

-- Client settings table for hot-reload configuration
CREATE TABLE IF NOT EXISTS client_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Index for faster lookups
CREATE INDEX IF NOT EXISTS idx_client_settings_key ON client_settings(key);

-- Default settings
INSERT OR IGNORE INTO client_settings (key, value) VALUES ('edge_base_url', '');
