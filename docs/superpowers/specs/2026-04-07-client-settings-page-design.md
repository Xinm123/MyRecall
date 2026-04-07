# Client Settings Page Design

**Date:** 2026-04-07
**Author:** Claude
**Status:** Approved

## Overview

Add a settings page to the MyRecall Web UI that allows users to configure client-side parameters with hot-reload capability. The first configuration parameter is `edge_base_url`, which controls the Edge API server endpoint.

## Goals

- Provide a dedicated settings page accessible from the Web UI
- Store configuration in SQLite database (MRC/client.db) for persistence
- Support hot-reload: configuration changes take effect immediately without restart
- Design for extensibility: easy to add more configuration parameters

## Architecture

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│   Web UI (8889) │──────│  Client Settings │──────│   SQLite (MRC)  │
│  settings.html  │      │    API Routes    │      │ client_settings │
└─────────────────┘      └──────────────────┘      └─────────────────┘
         │                                               │
         │                    ┌──────────────────┐      │
         └────────────────────│  Hot Reload via  │◄─────┘
                              │  Memory + Event  │
                              └──────────────────┘
```

## Components

### 1. Database Layer (MRC/client.db)

**Migration File:** `openrecall/client/database/migrations/20260407000001_add_client_settings.sql`

```sql
-- Client settings table for Web UI configuration
CREATE TABLE IF NOT EXISTS client_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_client_settings_key ON client_settings(key);

-- Insert default edge_base_url
INSERT OR IGNORE INTO client_settings (key, value) VALUES ('edge_base_url', '');
```

**Storage Location:** `~/MRC/client.db` (separate from server's `~/MRS/edge.db`)

### 2. Data Access Layer

**File:** `openrecall/client/database/settings_store.py`

```python
class ClientSettingsStore:
    """SQLite-backed store for client-side settings."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._ensure_tables()

    def get(self, key: str, default: str = "") -> str:
        """Get a setting value by key."""

    def set(self, key: str, value: str) -> None:
        """Set a setting value."""

    def get_all(self) -> dict[str, str]:
        """Get all settings as a dictionary."""

    def reset_to_defaults(self) -> None:
        """Reset all settings to default values."""
```

### 3. API Layer (Client Flask)

**File:** `openrecall/client/web/routes/settings.py`

**Routes:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/client/settings` | Get all client settings |
| POST | `/api/client/settings` | Update one or more settings |
| POST | `/api/client/settings/reset` | Reset to defaults |
| GET | `/api/client/settings/edge/health` | Test Edge connection |

**Request/Response Format:**

```json
// GET /api/client/settings
{
  "edge_base_url": "http://localhost:8083"
}

// POST /api/client/settings
{
  "edge_base_url": "http://10.77.3.162:8083"
}
```

### 4. Frontend Layer

**Template:** `openrecall/client/web/templates/settings.html`

**Route:** `/settings`

**Features:**
- Form with input field for `edge_base_url`
- "Test Connection" button to verify Edge server is reachable
- "Save" button to persist changes
- "Reset to Default" button
- Success/error toast notifications

**Hot Reload Implementation:**

```javascript
// settings.html Alpine.js component
function settingsPage() {
  return {
    settings: { edge_base_url: '' },
    originalSettings: { edge_base_url: '' },
    testStatus: null, // 'success' | 'error' | 'testing'

    async saveSettings() {
      // 1. Save to database via API
      await fetch('/api/client/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this.settings)
      });

      // 2. Update global EDGE_BASE_URL
      window.EDGE_BASE_URL = this.settings.edge_base_url;

      // 3. Broadcast event for hot reload
      window.dispatchEvent(new CustomEvent('openrecall-config-changed', {
        detail: { edge_base_url: this.settings.edge_base_url }
      }));
    },

    async testConnection() {
      // Test if Edge server is reachable
    }
  };
}
```

### 5. Navigation Integration

**Update:** `openrecall/client/web/templates/layout.html`

Add settings icon to toolbar (right side of Control Center button):

```html
<a href="/settings" class="toolbar-icon-link" title="Settings">
  {{ icons.icon_settings() }}
</a>
```

Add new icon to `icons.html`:
```html
{% macro icon_settings() %}
<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
  <!-- Gear/Settings icon -->
  <circle cx="8" cy="8" r="2" stroke="currentColor" stroke-width="1.5"/>
  <path d="M8 3v2M8 11v2M3 8h2M11 8h2M4.343 4.343l1.414 1.414M10.243 10.243l1.414 1.414M4.343 11.657l1.414-1.414M10.243 5.757l1.414-1.414" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
</svg>
{% endmacro %}
```

## Configuration Priority

Settings are resolved in this order (higher priority wins):

1. Runtime memory (from DB, hot-reload capable)
2. Environment variable (`OPENRECALL_EDGE_BASE_URL`)
3. TOML config file (`client-*.toml`)
4. Default value (`http://localhost:8083`)

## Data Flow

### Initial Page Load

```
1. Client Web UI starts
2. Load settings from DB (or create defaults)
3. Inject EDGE_BASE_URL into layout.html template
4. Browser loads with correct API endpoint
```

### Settings Update (Hot Reload)

```
1. User changes edge_base_url in settings page
2. Click "Save"
3. POST to /api/client/settings
4. Server updates DB
5. Frontend updates window.EDGE_BASE_URL
6. Dispatch 'openrecall-config-changed' event
7. All components refresh using new endpoint
```

## Security Considerations

- Settings API is local-only (binds to localhost)
- No authentication needed for local Web UI
- Edge URL validation: must be valid HTTP/HTTPS URL

## Future Extensibility

The design supports easy addition of new settings:

1. Add column to `client_settings` table (via migration)
2. Update frontend form with new field
3. Settings automatically available via API

Example future settings:
- `capture_interval`
- `theme` (light/dark)
- `language`
- `auto_refresh_interval`

## Files to Create/Modify

**New Files:**
- `openrecall/client/database/__init__.py`
- `openrecall/client/database/settings_store.py`
- `openrecall/client/database/migrations/20260407000001_add_client_settings.sql`
- `openrecall/client/web/routes/__init__.py`
- `openrecall/client/web/routes/settings.py`
- `openrecall/client/web/templates/settings.html`

**Modified Files:**
- `openrecall/client/web/app.py` - Register settings blueprint and inject DB settings
- `openrecall/client/web/templates/layout.html` - Add settings icon link
- `openrecall/client/web/templates/icons.html` - Add settings icon

## Testing Strategy

1. **Unit Tests:**
   - `ClientSettingsStore.get/set/get_all/reset`
   - Settings API endpoints

2. **Integration Tests:**
   - Settings page loads correctly
   - Change edge_base_url and verify hot reload
   - Test connection button works

3. **Manual Tests:**
   - Verify settings persist across page reloads
   - Verify settings persist across client restarts

## Migration Path

For existing users:
1. First run creates `client_settings` table with defaults
2. If `OPENRECALL_EDGE_BASE_URL` env var is set, use it as initial value
3. Otherwise use TOML config value
4. Otherwise use default (`http://localhost:8083`)
