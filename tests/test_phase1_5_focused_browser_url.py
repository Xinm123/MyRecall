"""Phase 1.5 tests: focused/browser_url pipeline (Requirement B)."""
import importlib
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image


def _init_test_db(db_path: Path):
    """Create test database with all required tables."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE IF NOT EXISTS entries (id INTEGER PRIMARY KEY AUTOINCREMENT, app TEXT, title TEXT, text TEXT, timestamp INTEGER UNIQUE, embedding BLOB, description TEXT, status TEXT DEFAULT 'COMPLETED')")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON entries (timestamp)")
    conn.execute("CREATE TABLE IF NOT EXISTS video_chunks (id INTEGER PRIMARY KEY AUTOINCREMENT, file_path TEXT NOT NULL, device_name TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')), expires_at TEXT, encrypted INTEGER DEFAULT 0, checksum TEXT, status TEXT DEFAULT 'PENDING', app_name TEXT DEFAULT '', window_name TEXT DEFAULT '')")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video_chunks_status ON video_chunks(status)")
    conn.execute("CREATE TABLE IF NOT EXISTS frames (id INTEGER PRIMARY KEY AUTOINCREMENT, video_chunk_id INTEGER NOT NULL, offset_index INTEGER NOT NULL, timestamp REAL NOT NULL, app_name TEXT DEFAULT '', window_name TEXT DEFAULT '', focused INTEGER DEFAULT 0, browser_url TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')), FOREIGN KEY (video_chunk_id) REFERENCES video_chunks(id) ON DELETE CASCADE)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_frames_video_chunk_id ON frames(video_chunk_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_frames_timestamp ON frames(timestamp)")
    conn.execute("CREATE TABLE IF NOT EXISTS ocr_text (frame_id INTEGER NOT NULL, text TEXT NOT NULL, text_json TEXT, ocr_engine TEXT DEFAULT '', text_length INTEGER, created_at TEXT NOT NULL DEFAULT (datetime('now')), FOREIGN KEY (frame_id) REFERENCES frames(id) ON DELETE CASCADE)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ocr_text_frame_id ON ocr_text(frame_id)")
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS ocr_text_fts USING fts5(text, app_name, window_name, frame_id UNINDEXED, tokenize='unicode61')")
    conn.commit()
    conn.close()


def _init_fts_db(fts_path: Path):
    """Create FTS database."""
    fts_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(fts_path))
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS ocr_fts USING fts5(snapshot_id UNINDEXED, ocr_text, caption, keywords)")
    conn.commit()
    conn.close()


@pytest.fixture
def sql_store(tmp_path, monkeypatch):
    """Create an isolated SQLStore with test DB."""
    monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
    monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))
    importlib.reload(importlib.import_module("openrecall.shared.config"))

    from openrecall.shared.config import settings
    db_path = settings.db_path
    fts_path = settings.fts_path
    _init_test_db(db_path)
    _init_fts_db(fts_path)

    import openrecall.server.database.sql
    importlib.reload(openrecall.server.database.sql)
    import openrecall.server.database
    importlib.reload(openrecall.server.database)

    from openrecall.server.database import SQLStore
    store = SQLStore()
    return store


class TestInsertFrameFocusedBrowserUrl:
    """Tests for insert_frame focused/browser_url write behavior."""

    def test_insert_frame_focused_true_stores_1(self, sql_store):
        """insert_frame(focused=True) stores focused=1 in DB."""
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")
        frame_id = sql_store.insert_frame(
            video_chunk_id=chunk_id, offset_index=0, timestamp=1000.0,
            focused=True,
        )
        assert frame_id is not None

        from openrecall.shared.config import settings
        conn = sqlite3.connect(str(settings.db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT focused FROM frames WHERE id=?", (frame_id,)).fetchone()
        conn.close()
        assert row["focused"] == 1

    def test_insert_frame_focused_none_stores_null(self, sql_store):
        """insert_frame(focused=None) stores NULL in DB."""
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")
        frame_id = sql_store.insert_frame(
            video_chunk_id=chunk_id, offset_index=0, timestamp=1000.0,
            focused=None,
        )
        assert frame_id is not None

        from openrecall.shared.config import settings
        conn = sqlite3.connect(str(settings.db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT focused FROM frames WHERE id=?", (frame_id,)).fetchone()
        conn.close()
        assert row["focused"] is None

    def test_insert_frame_browser_url_stored(self, sql_store):
        """insert_frame(browser_url='https://x.com') stores URL correctly."""
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")
        frame_id = sql_store.insert_frame(
            video_chunk_id=chunk_id, offset_index=0, timestamp=1000.0,
            browser_url="https://x.com",
        )
        assert frame_id is not None

        from openrecall.shared.config import settings
        conn = sqlite3.connect(str(settings.db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT browser_url FROM frames WHERE id=?", (frame_id,)).fetchone()
        conn.close()
        assert row["browser_url"] == "https://x.com"

    def test_insert_frame_browser_url_none_stores_null(self, sql_store):
        """insert_frame(browser_url=None) stores NULL in DB."""
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")
        frame_id = sql_store.insert_frame(
            video_chunk_id=chunk_id, offset_index=0, timestamp=1000.0,
            browser_url=None,
        )
        assert frame_id is not None

        from openrecall.shared.config import settings
        conn = sqlite3.connect(str(settings.db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT browser_url FROM frames WHERE id=?", (frame_id,)).fetchone()
        conn.close()
        assert row["browser_url"] is None


class TestQueryReturnsFocusedBrowserUrl:
    """Tests for query_frames_by_time_range and search_video_fts returning focused/browser_url."""

    def test_query_frames_returns_focused_browser_url(self, sql_store):
        """query_frames_by_time_range() returns focused and browser_url."""
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")
        sql_store.insert_frame(
            video_chunk_id=chunk_id, offset_index=0, timestamp=1000.0,
            app_name="Safari", window_name="MyPage",
            focused=True, browser_url="https://example.com",
        )

        frames, total = sql_store.query_frames_by_time_range(
            start_time=999.0, end_time=1001.0,
        )
        assert total == 1
        assert frames[0]["focused"] is True
        assert frames[0]["browser_url"] == "https://example.com"

    def test_query_frames_normalizes_null_focused(self, sql_store):
        """query_frames_by_time_range() normalizes NULL focused -> None (not 0 or False)."""
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")
        sql_store.insert_frame(
            video_chunk_id=chunk_id, offset_index=0, timestamp=1000.0,
            focused=None,
        )

        frames, total = sql_store.query_frames_by_time_range(
            start_time=999.0, end_time=1001.0,
        )
        assert total == 1
        # focused should be Python None, not False or 0
        assert frames[0]["focused"] is None

    def test_search_video_fts_returns_focused_browser_url(self, sql_store):
        """search_video_fts() returns focused and browser_url from joined frames."""
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")
        frame_id = sql_store.insert_frame(
            video_chunk_id=chunk_id, offset_index=0, timestamp=1000.0,
            app_name="Chrome", window_name="Search",
            focused=True, browser_url="https://google.com",
        )
        sql_store.insert_ocr_text(frame_id, "Python programming tutorial")
        sql_store.insert_ocr_text_fts(
            frame_id, "Python programming tutorial",
            app_name="Chrome", window_name="Search",
        )

        results = sql_store.search_video_fts("Python", limit=10)
        assert len(results) == 1
        assert results[0]["focused"] is True
        assert results[0]["browser_url"] == "https://google.com"


class TestTimelineAPIFocusedBrowserUrl:
    """Test timeline API response includes focused/browser_url."""

    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        """Flask test client with seeded data including focused/browser_url."""
        import unittest.mock as mock

        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))

        import openrecall.shared.config
        importlib.reload(openrecall.shared.config)

        import openrecall.server.database.sql
        importlib.reload(openrecall.server.database.sql)
        import openrecall.server.database
        importlib.reload(openrecall.server.database)
        openrecall.server.database.SQLStore()

        from openrecall.shared.config import settings
        db_path = settings.db_path
        frames_path = settings.frames_path

        # Create tables
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE IF NOT EXISTS video_chunks (id INTEGER PRIMARY KEY AUTOINCREMENT, file_path TEXT NOT NULL, device_name TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')), expires_at TEXT, encrypted INTEGER DEFAULT 0, checksum TEXT, status TEXT DEFAULT 'PENDING', app_name TEXT DEFAULT '', window_name TEXT DEFAULT '')")
        conn.execute("CREATE TABLE IF NOT EXISTS frames (id INTEGER PRIMARY KEY AUTOINCREMENT, video_chunk_id INTEGER NOT NULL, offset_index INTEGER NOT NULL, timestamp REAL NOT NULL, app_name TEXT DEFAULT '', window_name TEXT DEFAULT '', focused INTEGER DEFAULT 0, browser_url TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')), FOREIGN KEY (video_chunk_id) REFERENCES video_chunks(id) ON DELETE CASCADE)")
        conn.execute("CREATE TABLE IF NOT EXISTS ocr_text (frame_id INTEGER NOT NULL, text TEXT NOT NULL, text_json TEXT, ocr_engine TEXT DEFAULT '', text_length INTEGER, created_at TEXT NOT NULL DEFAULT (datetime('now')), FOREIGN KEY (frame_id) REFERENCES frames(id) ON DELETE CASCADE)")
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS ocr_text_fts USING fts5(text, app_name, window_name, frame_id UNINDEXED, tokenize='unicode61')")
        conn.commit()

        # Seed data WITH focused and browser_url
        conn.execute(
            "INSERT INTO video_chunks (file_path, device_name, status) VALUES (?, ?, ?)",
            ("/tmp/test.mp4", "primary", "COMPLETED"),
        )
        chunk_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        frames_path.mkdir(parents=True, exist_ok=True)
        # Frame with focused=true and browser_url
        conn.execute(
            "INSERT INTO frames (video_chunk_id, offset_index, timestamp, app_name, window_name, focused, browser_url) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (chunk_id, 0, 1000.0, "Chrome", "GitHub", 1, "https://github.com"),
        )
        frame_id_1 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO ocr_text (frame_id, text, text_length) VALUES (?, ?, ?)",
            (frame_id_1, "GitHub code review", 18),
        )
        img = Image.new("RGB", (100, 100), color="blue")
        img.save(str(frames_path / f"{frame_id_1}.png"))

        # Frame with focused=NULL and browser_url=NULL
        conn.execute(
            "INSERT INTO frames (video_chunk_id, offset_index, timestamp, app_name, window_name, focused, browser_url) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (chunk_id, 1, 1005.0, "Terminal", "bash", None, None),
        )
        frame_id_2 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO ocr_text (frame_id, text, text_length) VALUES (?, ?, ?)",
            (frame_id_2, "Terminal session", 15),
        )
        img.save(str(frames_path / f"{frame_id_2}.png"))

        conn.commit()
        conn.close()

        import openrecall.server.auth
        importlib.reload(openrecall.server.auth)

        import openrecall.server.search.engine
        mock_se = mock.MagicMock()
        mock_se.search.return_value = []
        monkeypatch.setattr(openrecall.server.search.engine, "SearchEngine", lambda: mock_se)

        import openrecall.server.api
        importlib.reload(openrecall.server.api)
        import openrecall.server.api_v1
        importlib.reload(openrecall.server.api_v1)
        import openrecall.server.app
        importlib.reload(openrecall.server.app)

        app = openrecall.server.app.app
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    def test_timeline_response_includes_focused_and_browser_url(self, client):
        """Timeline API response JSON includes focused and browser_url fields."""
        resp = client.get("/api/v1/timeline?start_time=0&end_time=9999999")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["meta"]["total"] == 2

        frames = data["data"]
        # Frame 0: Chrome with focused=True and browser_url
        chrome_frame = next(f for f in frames if f["app_name"] == "Chrome")
        assert "focused" in chrome_frame
        assert "browser_url" in chrome_frame
        assert chrome_frame["focused"] is True
        assert chrome_frame["browser_url"] == "https://github.com"

        # Frame 1: Terminal with focused=None and browser_url=None
        terminal_frame = next(f for f in frames if f["app_name"] == "Terminal")
        assert "focused" in terminal_frame
        assert "browser_url" in terminal_frame
        # NULL focused should be None in JSON (null), not False
        assert terminal_frame["focused"] is None
        assert terminal_frame["browser_url"] is None


class TestSearchAPIFocusedBrowserUrlCompatibility:
    """Test /api/v1/search additive optional fields + backward compatibility."""

    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        import unittest.mock as mock

        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))

        import openrecall.shared.config
        importlib.reload(openrecall.shared.config)
        from openrecall.shared.config import settings

        _init_test_db(settings.db_path)
        _init_fts_db(settings.fts_path)

        import openrecall.server.database.sql
        importlib.reload(openrecall.server.database.sql)
        import openrecall.server.database
        importlib.reload(openrecall.server.database)
        openrecall.server.database.SQLStore()

        video_result = {
            "snapshot": None,
            "video_data": {
                "frame_id": 42,
                "timestamp": 1700000000.0,
                "app_name": "Chrome",
                "window_name": "GitHub PR",
                "text_snippet": "Fix metadata resolver",
                "focused": True,
                "browser_url": "https://github.com/org/repo/pull/1",
            },
        }
        snapshot_result = SimpleNamespace(
            id="snap-1",
            context=SimpleNamespace(
                timestamp=1700000001.0,
                app_name="Terminal",
                window_title="zsh",
            ),
            content=SimpleNamespace(caption="run tests", scene_tag="coding"),
            image_path="/tmp/1700000001.png",
        )

        mock_se = mock.MagicMock()

        def _search_side_effect(query, limit=50):
            if query == "video":
                return [video_result]
            return [snapshot_result]

        mock_se.search.side_effect = _search_side_effect

        import openrecall.server.search.engine
        monkeypatch.setattr(openrecall.server.search.engine, "SearchEngine", lambda: mock_se)

        import openrecall.server.api
        importlib.reload(openrecall.server.api)
        import openrecall.server.api_v1
        importlib.reload(openrecall.server.api_v1)
        import openrecall.server.app
        importlib.reload(openrecall.server.app)

        app = openrecall.server.app.app
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    def test_search_video_result_includes_focused_browser_url(self, client):
        resp = client.get("/api/v1/search?q=video&limit=10")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["meta"]["total"] == 1
        item = payload["data"][0]
        # Existing fields remain present
        assert item["id"] == "vframe:42"
        assert item["window_title"] == "GitHub PR"
        assert item["scene_tag"] == "video_frame"
        # New additive optional fields
        assert item["focused"] is True
        assert item["browser_url"] == "https://github.com/org/repo/pull/1"

    def test_search_snapshot_result_keeps_old_shape_plus_null_optionals(self, client):
        resp = client.get("/api/v1/search?q=snapshot&limit=10")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["meta"]["total"] == 1
        item = payload["data"][0]
        # Existing fields remain unchanged
        assert item["id"] == "snap-1"
        assert item["app_name"] == "Terminal"
        assert item["window_title"] == "zsh"
        # Additive optional fields default to null when not available
        assert item["focused"] is None
        assert item["browser_url"] is None
