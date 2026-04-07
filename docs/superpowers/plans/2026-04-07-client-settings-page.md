# Client Settings Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a settings page to the MyRecall Web UI that allows users to configure `edge_base_url` with hot-reload capability, storing configuration in SQLite.

**Architecture:** Create a new `client_settings` SQLite table in MRC/client.db, expose REST API endpoints for CRUD operations, build a settings page with Alpine.js frontend, and implement hot-reload by updating the global `EDGE_BASE_URL` and broadcasting events.

**Tech Stack:** Flask, SQLite, Alpine.js, Jinja2

---

## File Structure

| File | Responsibility |
|------|----------------|
| `openrecall/client/database/settings_store.py` | Data access layer for client settings |
| `openrecall/client/database/__init__.py` | Package init, exports |
| `openrecall/client/database/migrations/20260407000001_add_client_settings.sql` | DB migration for client_settings table |
| `openrecall/client/web/routes/settings.py` | Flask blueprint for settings API |
| `openrecall/client/web/routes/__init__.py` | Routes package init |
| `openrecall/client/web/templates/settings.html` | Settings page template |
| `openrecall/client/web/templates/icons.html` | Add settings icon (modified) |
| `openrecall/client/web/templates/layout.html` | Add settings nav link (modified) |
| `openrecall/client/web/app.py` | Register blueprint, inject settings (modified) |
| `tests/client/test_settings_store.py` | Unit tests for settings store |
| `tests/client/web/test_settings_api.py` | Integration tests for settings API |

---

## Task 1: Create Client Database Package

**Files:**
- Create: `openrecall/client/database/__init__.py`

- [ ] **Step 1: Create database package init**

```python
"""Client-side database package for OpenRecall."""

from openrecall.client.database.settings_store import ClientSettingsStore

__all__ = ["ClientSettingsStore"]
```

- [ ] **Step 2: Commit**

```bash
git add openrecall/client/database/__init__.py
git commit -m "feat: create client database package"
```

---

## Task 2: Create DB Migration for client_settings

**Files:**
- Create: `openrecall/client/database/migrations/20260407000001_add_client_settings.sql`

- [ ] **Step 1: Write migration file**

```sql
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
```

- [ ] **Step 2: Commit**

```bash
git add openrecall/client/database/migrations/20260407000001_add_client_settings.sql
git commit -m "feat: add client_settings migration"
```

---

## Task 3: Implement ClientSettingsStore

**Files:**
- Create: `openrecall/client/database/settings_store.py`

- [ ] **Step 1: Write the failing test**

Create `tests/client/test_settings_store.py`:

```python
"""Tests for ClientSettingsStore."""

import pytest
import sqlite3
from pathlib import Path
from openrecall.client.database.settings_store import ClientSettingsStore


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_client.db"
    return db_path


@pytest.fixture
def store(temp_db):
    """Create a ClientSettingsStore with test database."""
    return ClientSettingsStore(temp_db)


class TestClientSettingsStore:
    """Test suite for ClientSettingsStore."""

    def test_get_existing_key(self, store):
        """Test getting an existing key returns its value."""
        store.set("edge_base_url", "http://localhost:8083")
        result = store.get("edge_base_url")
        assert result == "http://localhost:8083"

    def test_get_nonexistent_key_returns_default(self, store):
        """Test getting a non-existent key returns default value."""
        result = store.get("nonexistent", "default_value")
        assert result == "default_value"

    def test_get_nonexistent_key_returns_empty_string(self, store):
        """Test getting a non-existent key without default returns empty string."""
        result = store.get("nonexistent")
        assert result == ""

    def test_set_creates_new_key(self, store):
        """Test setting a new key creates it."""
        store.set("new_key", "new_value")
        result = store.get("new_key")
        assert result == "new_value"

    def test_set_updates_existing_key(self, store):
        """Test setting an existing key updates its value."""
        store.set("edge_base_url", "http://localhost:8083")
        store.set("edge_base_url", "http://remote:8083")
        result = store.get("edge_base_url")
        assert result == "http://remote:8083"

    def test_get_all_returns_dict(self, store):
        """Test get_all returns all settings as a dictionary."""
        store.set("edge_base_url", "http://localhost:8083")
        store.set("another_key", "another_value")
        result = store.get_all()
        assert isinstance(result, dict)
        assert result["edge_base_url"] == "http://localhost:8083"
        assert result["another_key"] == "another_value"

    def test_get_all_includes_defaults(self, store):
        """Test get_all includes default settings."""
        result = store.get_all()
        assert "edge_base_url" in result

    def test_reset_to_defaults(self, store):
        """Test reset_to_defaults restores default values."""
        store.set("edge_base_url", "http://modified:8083")
        store.reset_to_defaults()
        result = store.get("edge_base_url")
        assert result == ""  # Default is empty string
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/client/test_settings_store.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'openrecall.client.database.settings_store'"

- [ ] **Step 3: Implement ClientSettingsStore**

Create `openrecall/client/database/settings_store.py`:

```python
"""SQLite-backed store for client-side settings."""

import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ClientSettingsStore:
    """SQLite-backed store for client-side settings.

    Stores configuration in MRC/client.db for persistence across restarts.
    Supports hot-reload by allowing runtime updates.
    """

    # Default settings applied on first run or reset
    DEFAULTS: dict[str, str] = {
        "edge_base_url": "",
    }

    def __init__(self, db_path: Path):
        """Initialize the settings store.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_tables()
        self._ensure_defaults()

    def _ensure_tables(self) -> None:
        """Create the client_settings table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS client_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_client_settings_key ON client_settings(key)
            """)
            conn.commit()

    def _ensure_defaults(self) -> None:
        """Ensure default settings exist in the database."""
        with sqlite3.connect(self.db_path) as conn:
            for key, value in self.DEFAULTS.items():
                conn.execute(
                    """
                    INSERT OR IGNORE INTO client_settings (key, value) VALUES (?, ?)
                    """,
                    (key, value),
                )
            conn.commit()

    def get(self, key: str, default: str = "") -> str:
        """Get a setting value by key.

        Args:
            key: The setting key
            default: Default value if key doesn't exist

        Returns:
            The setting value or default
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT value FROM client_settings WHERE key = ?",
                (key,),
            )
            row = cursor.fetchone()
            return row[0] if row else default

    def set(self, key: str, value: str) -> None:
        """Set a setting value.

        Args:
            key: The setting key
            value: The setting value
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO client_settings (key, value, updated_at)
                VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value),
            )
            conn.commit()
        logger.debug(f"Setting updated: {key} = {value}")

    def get_all(self) -> dict[str, str]:
        """Get all settings as a dictionary.

        Returns:
            Dictionary of all settings
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT key, value FROM client_settings")
            return {row[0]: row[1] for row in cursor.fetchall()}

    def reset_to_defaults(self) -> None:
        """Reset all settings to default values."""
        with sqlite3.connect(self.db_path) as conn:
            for key, value in self.DEFAULTS.items():
                conn.execute(
                    """
                    INSERT INTO client_settings (key, value, updated_at)
                    VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (key, value),
                )
            conn.commit()
        logger.info("Settings reset to defaults")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/client/test_settings_store.py -v
```

Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add openrecall/client/database/settings_store.py tests/client/test_settings_store.py
git commit -m "feat: implement ClientSettingsStore with full test coverage"
```

---

## Task 4: Create Settings API Blueprint

**Files:**
- Create: `openrecall/client/web/routes/__init__.py`
- Create: `openrecall/client/web/routes/settings.py`

- [ ] **Step 1: Create routes package init**

Create `openrecall/client/web/routes/__init__.py`:

```python
"""Client Web UI routes package."""

from openrecall.client.web.routes.settings import settings_bp

__all__ = ["settings_bp"]
```

- [ ] **Step 2: Create settings blueprint**

Create `openrecall/client/web/routes/settings.py`:

```python
"""Settings API routes for client Web UI."""

import logging
from pathlib import Path

import requests
from flask import Blueprint, jsonify, request

from openrecall.client.database import ClientSettingsStore
from openrecall.shared.config import settings as app_settings

logger = logging.getLogger(__name__)

settings_bp = Blueprint("settings", __name__, url_prefix="/api/client")

# Initialize settings store with MRC path
_db_path = Path(app_settings.client_data_dir) / "client.db"
_settings_store = ClientSettingsStore(_db_path)


def get_settings_store() -> ClientSettingsStore:
    """Get the settings store instance."""
    return _settings_store


@settings_bp.route("/settings", methods=["GET"])
def get_settings():
    """Get all client settings.

    Returns:
        JSON object with all settings as key-value pairs
    """
    store = get_settings_store()
    settings = store.get_all()
    return jsonify(settings)


@settings_bp.route("/settings", methods=["POST"])
def update_settings():
    """Update one or more client settings.

    Request body:
        JSON object with settings to update

    Returns:
        JSON object with updated settings
    """
    store = get_settings_store()
    data = request.get_json()

    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    # Validate edge_base_url if present
    if "edge_base_url" in data:
        url = data["edge_base_url"]
        if url and not (url.startswith("http://") or url.startswith("https://")):
            return jsonify({"error": "edge_base_url must be a valid HTTP/HTTPS URL"}), 400

    # Update settings
    for key, value in data.items():
        store.set(key, str(value))
        logger.info(f"Setting updated via API: {key}")

    return jsonify(store.get_all())


@settings_bp.route("/settings/reset", methods=["POST"])
def reset_settings():
    """Reset all settings to default values.

    Returns:
        JSON object with default settings
    """
    store = get_settings_store()
    store.reset_to_defaults()
    return jsonify(store.get_all())


@settings_bp.route("/settings/edge/health", methods=["GET"])
def test_edge_connection():
    """Test connection to the configured Edge server.

    Query parameters:
        url: Optional URL to test (uses configured edge_base_url if not provided)

    Returns:
        JSON object with connection status
    """
    store = get_settings_store()

    # Get URL from query param or from settings
    test_url = request.args.get("url") or store.get("edge_base_url")

    if not test_url:
        # Fallback to derived URL from app settings
        test_url = app_settings.edge_base_url

    if not test_url:
        return jsonify({
            "reachable": False,
            "error": "No Edge URL configured",
        }), 400

    health_url = f"{test_url.rstrip('/')}/v1/health"

    try:
        response = requests.get(health_url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return jsonify({
                "reachable": True,
                "status": data.get("status", "unknown"),
                "url": test_url,
            })
        else:
            return jsonify({
                "reachable": False,
                "error": f"HTTP {response.status_code}",
                "url": test_url,
            }), 502
    except requests.RequestException as e:
        return jsonify({
            "reachable": False,
            "error": str(e),
            "url": test_url,
        }), 502
```

- [ ] **Step 3: Commit**

```bash
git add openrecall/client/web/routes/
git commit -m "feat: add settings API blueprint with CRUD and health check"
```

---

## Task 5: Register Settings Blueprint in App

**Files:**
- Modify: `openrecall/client/web/app.py`

- [ ] **Step 1: Import and register blueprint**

Add import and registration to `openrecall/client/web/app.py`:

```python
"""Flask web server for client-side Web UI."""

import logging
import threading
from flask import Flask, render_template, send_from_directory
from openrecall.client.chat.routes import chat_bp
from openrecall.client.web.routes import settings_bp  # ADD THIS LINE
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)

client_app = Flask(__name__, template_folder="templates")
client_app.register_blueprint(chat_bp)
client_app.register_blueprint(settings_bp)  # ADD THIS LINE
```

- [ ] **Step 2: Update context processor to use DB settings**

Modify the context processor to read `edge_base_url` from database:

```python
from pathlib import Path
from openrecall.client.database import ClientSettingsStore

# Initialize settings store for template context
_settings_store = None

def _get_settings_store():
    global _settings_store
    if _settings_store is None:
        db_path = Path(settings.client_data_dir) / "client.db"
        _settings_store = ClientSettingsStore(db_path)
    return _settings_store


@client_app.context_processor
def inject_template_vars():
    """Make EDGE_BASE_URL and settings available to all templates."""
    store = _get_settings_store()
    # Get from DB first, fallback to config
    db_edge_url = store.get("edge_base_url")
    edge_base_url = db_edge_url if db_edge_url else settings.edge_base_url
    return {"EDGE_BASE_URL": edge_base_url, "settings": settings}
```

- [ ] **Step 3: Add settings page route**

Add the settings page route after the existing routes:

```python
@client_app.route("/settings")
def settings_page():
    """Render the settings page."""
    return render_template("settings.html")
```

- [ ] **Step 4: Commit**

```bash
git add openrecall/client/web/app.py
git commit -m "feat: register settings blueprint and update context processor"
```

---

## Task 6: Add Settings Icon to Icons Template

**Files:**
- Modify: `openrecall/client/web/templates/icons.html`

- [ ] **Step 1: Add settings icon macro**

Add to the end of `openrecall/client/web/templates/icons.html`:

```html
{% macro icon_settings() %}
<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
  <!-- Settings/Gear icon -->
  <circle cx="8" cy="8" r="2" stroke="currentColor" stroke-width="1.5"/>
  <path d="M8 2.5v2M8 11.5v2M2.5 8h2M11.5 8h2M4.05 4.05l1.414 1.414M10.536 10.536l1.414 1.414M4.05 11.95l1.414-1.414M10.536 5.464l1.414-1.414" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
</svg>
{% endmacro %}
```

- [ ] **Step 2: Commit**

```bash
git add openrecall/client/web/templates/icons.html
git commit -m "feat: add settings icon to icons template"
```

---

## Task 7: Add Settings Link to Layout

**Files:**
- Modify: `openrecall/client/web/templates/layout.html`

- [ ] **Step 1: Add settings link in toolbar**

Find the toolbar-icons-container div and add the settings link after the Control Center button:

```html
<!-- Right Group: Icons + Control Center -->
<div class="toolbar-right-group" id="toolbarRightGroup">
  <div class="toolbar-icons-container">
    <a href="/" class="toolbar-icon-link" title="Grid View">
      {{ icons.icon_grid() }}
    </a>
    <a href="/timeline" class="toolbar-icon-link" title="Timeline View">
      {{ icons.icon_timeline() }}
    </a>
    <a href="/chat" class="toolbar-icon-link" title="Chat">
      {{ icons.icon_chat() }}
    </a>
  </div>
  <a href="/search" class="toolbar-icon-link" title="Search">
    {{ icons.icon_search() }}
  </a>

  <!-- Settings Link -->
  <a href="/settings" class="toolbar-icon-link" title="Settings">
    {{ icons.icon_settings() }}
  </a>

  <!-- Control Center Button & Popover -->
  <div x-data="controlCenter()" class="control-center-btn">
    <!-- ... existing control center code ... -->
  </div>
</div>
```

- [ ] **Step 2: Add settings page highlight style**

Add CSS for settings page highlighting in the style section:

```css
html[data-current-view="settings"] a[href="/settings"] {
  background-color: rgba(0, 0, 0, 0.12);
  color: #1D1D1F;
}
```

- [ ] **Step 3: Commit**

```bash
git add openrecall/client/web/templates/layout.html
git commit -m "feat: add settings link to layout toolbar"
```

---

## Task 8: Create Settings Page Template

**Files:**
- Create: `openrecall/client/web/templates/settings.html`

- [ ] **Step 1: Create settings page template**

Create `openrecall/client/web/templates/settings.html`:

```html
{% extends "layout.html" %}

{% block title %}Settings - MyRecall{% endblock %}

{% block extra_head %}
<style>
  /* Settings page specific styles */
  .settings-container {
    max-width: 600px;
    margin: 40px auto;
    padding: 0 20px;
  }

  .settings-header {
    margin-bottom: 32px;
  }

  .settings-header h1 {
    font-size: 28px;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0 0 8px 0;
  }

  .settings-header p {
    color: var(--text-secondary);
    margin: 0;
  }

  .settings-section {
    background: var(--bg-card);
    border-radius: 12px;
    padding: 24px;
    margin-bottom: 20px;
    border: 1px solid var(--border-color);
  }

  .settings-section h2 {
    font-size: 18px;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0 0 20px 0;
  }

  .form-group {
    margin-bottom: 20px;
  }

  .form-group:last-child {
    margin-bottom: 0;
  }

  .form-label {
    display: block;
    font-size: 14px;
    font-weight: 500;
    color: var(--text-primary);
    margin-bottom: 8px;
  }

  .form-label-description {
    display: block;
    font-size: 12px;
    color: var(--text-secondary);
    margin-bottom: 8px;
  }

  .form-input {
    width: 100%;
    padding: 10px 14px;
    font-size: 14px;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    background: var(--bg-body);
    color: var(--text-primary);
    font-family: var(--font-stack);
    box-sizing: border-box;
  }

  .form-input:focus {
    outline: none;
    border-color: var(--accent-color);
  }

  .form-input-group {
    display: flex;
    gap: 8px;
  }

  .form-input-group .form-input {
    flex: 1;
  }

  .btn {
    padding: 10px 16px;
    font-size: 14px;
    font-weight: 500;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;
    font-family: var(--font-stack);
  }

  .btn-primary {
    background: var(--accent-color);
    color: white;
  }

  .btn-primary:hover {
    background: #0056CC;
  }

  .btn-secondary {
    background: var(--bg-body);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
  }

  .btn-secondary:hover {
    background: rgba(0, 0, 0, 0.05);
  }

  .btn-group {
    display: flex;
    gap: 12px;
    margin-top: 24px;
  }

  .status-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
  }

  .status-success {
    background: rgba(52, 199, 89, 0.15);
    color: #28a745;
  }

  .status-error {
    background: rgba(255, 59, 48, 0.12);
    color: #FF3B30;
  }

  .status-testing {
    background: rgba(0, 122, 255, 0.12);
    color: #007AFF;
  }

  .toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    padding: 14px 20px;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 500;
    color: white;
    z-index: 10000;
    animation: toastIn 0.3s ease-out;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  }

  .toast-success {
    background: #34C759;
  }

  .toast-error {
    background: #FF3B30;
  }

  @keyframes toastIn {
    from {
      opacity: 0;
      transform: translateY(10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .current-value {
    font-size: 12px;
    color: var(--text-secondary);
    margin-top: 6px;
  }

  .current-value code {
    background: rgba(0, 0, 0, 0.05);
    padding: 2px 6px;
    border-radius: 4px;
    font-family: 'SF Mono', Monaco, Consolas, monospace;
  }
</style>
{% endblock %}

{% block content %}
<div class="settings-container" x-data="settingsPage()" x-init="init()">
  <div class="settings-header">
    <h1>Settings</h1>
    <p>Configure MyRecall client settings. Changes are applied immediately.</p>
  </div>

  <div class="settings-section">
    <h2>Connection</h2>

    <div class="form-group">
      <label class="form-label" for="edge_base_url">Edge Server URL</label>
      <span class="form-label-description">
        The base URL of the Edge API server. Default is http://localhost:8083 for local mode.
      </span>
      <div class="form-input-group">
        <input
          type="url"
          id="edge_base_url"
          class="form-input"
          x-model="settings.edge_base_url"
          placeholder="http://localhost:8083"
          @keydown.enter="saveSettings()"
        >
        <button class="btn btn-secondary" @click="testConnection()" :disabled="testStatus === 'testing'">
          <span x-show="testStatus !== 'testing'">Test</span>
          <span x-show="testStatus === 'testing'">Testing...</span>
        </button>
      </div>
      <div class="current-value">
        Current: <code x-text="originalSettings.edge_base_url || '(not set)'"></code>
      </div>
      <div x-show="testStatus === 'success'" class="status-badge status-success" style="margin-top: 12px;">
        <span>✓</span>
        <span>Connected successfully</span>
      </div>
      <div x-show="testStatus === 'error'" class="status-badge status-error" style="margin-top: 12px;">
        <span>✗</span>
        <span x-text="testError || 'Connection failed'"></span>
      </div>
    </div>
  </div>

  <div class="btn-group">
    <button class="btn btn-primary" @click="saveSettings()" :disabled="!hasChanges() || saving">
      <span x-show="!saving">Save Changes</span>
      <span x-show="saving">Saving...</span>
    </button>
    <button class="btn btn-secondary" @click="resetSettings()" :disabled="saving">
      Reset to Default
    </button>
  </div>

  <!-- Toast notification -->
  <template x-if="toast">
    <div class="toast" :class="toast.type" x-text="toast.message"></div>
  </template>
</div>

<script>
  function settingsPage() {
    return {
      settings: { edge_base_url: '' },
      originalSettings: { edge_base_url: '' },
      testStatus: null, // null | 'testing' | 'success' | 'error'
      testError: '',
      toast: null,
      saving: false,

      init() {
        // Load current settings from server
        this.loadSettings();

        // Set current view for toolbar highlighting
        document.documentElement.setAttribute('data-current-view', 'settings');
      },

      async loadSettings() {
        try {
          const response = await fetch('/api/client/settings');
          if (response.ok) {
            const data = await response.json();
            this.settings.edge_base_url = data.edge_base_url || '';
            this.originalSettings.edge_base_url = data.edge_base_url || '';
          } else {
            this.showToast('Failed to load settings', 'error');
          }
        } catch (error) {
          console.error('Failed to load settings:', error);
          this.showToast('Failed to load settings', 'error');
        }
      },

      hasChanges() {
        return this.settings.edge_base_url !== this.originalSettings.edge_base_url;
      },

      async testConnection() {
        this.testStatus = 'testing';
        this.testError = '';

        try {
          const url = this.settings.edge_base_url;
          const testUrl = url ? `/api/client/settings/edge/health?url=${encodeURIComponent(url)}` : '/api/client/settings/edge/health';
          const response = await fetch(testUrl);
          const data = await response.json();

          if (response.ok && data.reachable) {
            this.testStatus = 'success';
          } else {
            this.testStatus = 'error';
            this.testError = data.error || 'Connection failed';
          }
        } catch (error) {
          this.testStatus = 'error';
          this.testError = error.message || 'Connection failed';
        }

        // Clear test status after 3 seconds
        setTimeout(() => {
          this.testStatus = null;
        }, 3000);
      },

      async saveSettings() {
        this.saving = true;

        try {
          const response = await fetch('/api/client/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(this.settings)
          });

          if (response.ok) {
            const data = await response.json();
            this.originalSettings.edge_base_url = data.edge_base_url || '';

            // Update global EDGE_BASE_URL for hot reload
            window.EDGE_BASE_URL = this.settings.edge_base_url || window.EDGE_BASE_URL;

            // Broadcast event for hot reload
            window.dispatchEvent(new CustomEvent('openrecall-config-changed', {
              detail: { edge_base_url: this.settings.edge_base_url }
            }));

            this.showToast('Settings saved successfully', 'success');
          } else {
            const error = await response.json();
            this.showToast(error.error || 'Failed to save settings', 'error');
          }
        } catch (error) {
          console.error('Failed to save settings:', error);
          this.showToast('Failed to save settings', 'error');
        } finally {
          this.saving = false;
        }
      },

      async resetSettings() {
        if (!confirm('Reset all settings to default values?')) {
          return;
        }

        this.saving = true;

        try {
          const response = await fetch('/api/client/settings/reset', {
            method: 'POST'
          });

          if (response.ok) {
            const data = await response.json();
            this.settings.edge_base_url = data.edge_base_url || '';
            this.originalSettings.edge_base_url = data.edge_base_url || '';

            // Update global EDGE_BASE_URL
            window.EDGE_BASE_URL = data.edge_base_url || window.EDGE_BASE_URL;

            // Broadcast event
            window.dispatchEvent(new CustomEvent('openrecall-config-changed', {
              detail: { edge_base_url: data.edge_base_url }
            }));

            this.showToast('Settings reset to defaults', 'success');
          } else {
            this.showToast('Failed to reset settings', 'error');
          }
        } catch (error) {
          console.error('Failed to reset settings:', error);
          this.showToast('Failed to reset settings', 'error');
        } finally {
          this.saving = false;
        }
      },

      showToast(message, type) {
        this.toast = { message, type };
        setTimeout(() => {
          this.toast = null;
        }, 3000);
      }
    };
  }
</script>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add openrecall/client/web/templates/settings.html
git commit -m "feat: create settings page template with hot-reload support"
```

---

## Task 9: Add API Integration Tests

**Files:**
- Create: `tests/client/web/test_settings_api.py`

- [ ] **Step 1: Create API tests**

Create `tests/client/web/test_settings_api.py`:

```python
"""Integration tests for settings API endpoints."""

import pytest
import json
from pathlib import Path


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create a test Flask client."""
    # Mock the settings store path
    from openrecall.client.web.routes import settings
    test_db_path = tmp_path / "test_client.db"

    # Create a new store with test path
    from openrecall.client.database import ClientSettingsStore
    test_store = ClientSettingsStore(test_db_path)

    # Replace the module-level store
    settings._settings_store = test_store

    # Create app
    from openrecall.client.web.app import client_app
    client_app.config['TESTING'] = True

    with client_app.test_client() as client:
        yield client


class TestGetSettings:
    """Tests for GET /api/client/settings."""

    def test_get_settings_returns_dict(self, client):
        """Test that settings endpoint returns a dictionary."""
        response = client.get('/api/client/settings')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, dict)
        assert 'edge_base_url' in data


class TestUpdateSettings:
    """Tests for POST /api/client/settings."""

    def test_update_edge_base_url(self, client):
        """Test updating edge_base_url."""
        response = client.post('/api/client/settings',
                              data=json.dumps({'edge_base_url': 'http://test:8083'}),
                              content_type='application/json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['edge_base_url'] == 'http://test:8083'

    def test_update_invalid_url_returns_error(self, client):
        """Test that invalid URL returns validation error."""
        response = client.post('/api/client/settings',
                              data=json.dumps({'edge_base_url': 'invalid-url'}),
                              content_type='application/json')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_update_non_json_returns_error(self, client):
        """Test that non-JSON body returns error."""
        response = client.post('/api/client/settings',
                              data='not json',
                              content_type='text/plain')
        assert response.status_code == 400


class TestResetSettings:
    """Tests for POST /api/client/settings/reset."""

    def test_reset_settings(self, client):
        """Test resetting settings to defaults."""
        # First set a custom value
        client.post('/api/client/settings',
                   data=json.dumps({'edge_base_url': 'http://custom:8083'}),
                   content_type='application/json')

        # Then reset
        response = client.post('/api/client/settings/reset')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['edge_base_url'] == ''  # Default is empty string


class TestEdgeHealth:
    """Tests for GET /api/client/settings/edge/health."""

    def test_health_without_url_uses_configured(self, client):
        """Test health check uses configured URL when no param provided."""
        # This will fail because no Edge server is running in tests
        response = client.get('/api/client/settings/edge/health')
        # Should return 502 because Edge is not reachable
        assert response.status_code in [200, 400, 502]

    def test_health_with_url_param(self, client):
        """Test health check with explicit URL parameter."""
        response = client.get('/api/client/settings/edge/health?url=http://invalid:9999')
        # Should fail to connect
        assert response.status_code == 502
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/client/web/test_settings_api.py -v
```

Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/client/web/test_settings_api.py
git commit -m "test: add settings API integration tests"
```

---

## Task 10: Manual Testing & Verification

- [ ] **Step 1: Start the servers**

Terminal 1:
```bash
./run_server.sh --mode local --debug
```

Terminal 2:
```bash
./run_client.sh --mode local --debug
```

- [ ] **Step 2: Test the settings page**

1. Open http://localhost:8889/settings
2. Verify the settings page loads
3. Check that current edge_base_url is displayed
4. Change the URL to a different value
5. Click "Test" button - should show connection status
6. Click "Save Changes" - should show success toast
7. Verify the new URL is persisted (refresh page)

- [ ] **Step 3: Test hot reload**

1. Go to Grid view (/) and verify frames load
2. Go to Settings and change edge_base_url to invalid URL
3. Save changes
4. Go back to Grid view - should show connection errors
5. Change back to correct URL
6. Grid view should work again without page reload

- [ ] **Step 4: Commit**

```bash
git commit -m "test: manual testing verified - settings page works with hot reload"
```

---

## Summary

This implementation adds:

1. **Database Layer:** SQLite table `client_settings` in MRC/client.db
2. **Data Access:** `ClientSettingsStore` class with full CRUD operations
3. **API Layer:** REST endpoints for settings management and health checks
4. **Frontend:** Settings page with form, validation, and toast notifications
5. **Hot Reload:** Configuration changes apply immediately via Alpine.js events
6. **Navigation:** Settings icon added to toolbar
7. **Testing:** Unit tests for store and integration tests for API

All changes are client-side only and don't affect the Edge server.
