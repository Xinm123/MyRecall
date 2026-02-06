"""Phase 0 Gate Validation Suite.

One test per gate from v3/metrics/phase-gates.md.
All 19 gates must pass for Phase 0 Go decision.
"""

import io
import json
import os
import sqlite3
import time
import tracemalloc
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_test_db(db_path: Path, num_entries: int = 0) -> None:
    """Create a test database with the entries table and optional test data."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app TEXT,
            title TEXT,
            text TEXT,
            timestamp INTEGER UNIQUE,
            embedding BLOB,
            description TEXT,
            status TEXT DEFAULT 'COMPLETED'
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON entries (timestamp)")

    for i in range(num_entries):
        conn.execute(
            "INSERT INTO entries (timestamp, app, title, text, description, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (1000000 + i, f"app_{i}", f"title_{i}", f"text_{i}", f"desc_{i}", "COMPLETED"),
        )
    conn.commit()
    conn.close()


def _get_tables(db_path: Path) -> set:
    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') "
        "AND name NOT LIKE 'sqlite_%'"
    )
    tables = {row[0] for row in cursor.fetchall()}
    conn.close()
    return tables


def _get_columns(db_path: Path, table_name: str) -> set:
    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    columns = {row[1] for row in cursor.fetchall()}
    conn.close()
    return columns


# ===========================================================================
# Functional Gates (F-01 to F-04)
# ===========================================================================


class TestGateF01SchemaМigrationSuccess:
    """F-01: Schema Migration Success.

    Criteria: All new tables created (video_chunks, frames, ocr_text,
    audio_chunks, audio_transcriptions).
    """

    def test_gate_F01_schema_migration_success(self, tmp_path):
        from openrecall.server.database.migrations.runner import MigrationRunner

        db_path = tmp_path / "gate_f01.db"
        _create_test_db(db_path, num_entries=10)

        runner = MigrationRunner(db_path)
        result = runner.run()

        assert result.success, f"Migration failed: {result.error}"

        tables = _get_tables(db_path)
        required_tables = {
            "video_chunks",
            "frames",
            "ocr_text",
            "audio_chunks",
            "audio_transcriptions",
        }
        missing = required_tables - tables
        assert not missing, f"F-01 FAIL: Missing tables: {missing}"

        # Also verify FTS and schema_version
        assert "schema_version" in tables, "F-01 FAIL: schema_version missing"
        assert "ocr_text_fts" in tables, "F-01 FAIL: ocr_text_fts missing"
        assert "audio_transcriptions_fts" in tables, "F-01 FAIL: audio_transcriptions_fts missing"


class TestGateF02BackwardCompatibility:
    """F-02: Backward Compatibility.

    Criteria: Existing screenshot pipeline 100% functional after migration.
    """

    @pytest.fixture
    def migrated_client(self, tmp_path, monkeypatch):
        import importlib
        import unittest.mock as mock

        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))

        import openrecall.shared.config
        importlib.reload(openrecall.shared.config)

        # Reload sql submodule so it picks up new settings
        import openrecall.server.database.sql
        importlib.reload(openrecall.server.database.sql)
        import openrecall.server.database
        importlib.reload(openrecall.server.database)
        openrecall.server.database.SQLStore()

        from openrecall.server.database.migrations.runner import MigrationRunner
        db_path = openrecall.shared.config.settings.db_path
        runner = MigrationRunner(db_path)
        result = runner.run()
        assert result.success, f"Migration failed: {result.error}"

        import openrecall.server.auth
        importlib.reload(openrecall.server.auth)

        # Mock SearchEngine to avoid HuggingFace model download in test env
        import openrecall.server.search.engine
        mock_se = mock.MagicMock()
        mock_se.search.return_value = []
        monkeypatch.setattr(
            openrecall.server.search.engine, "SearchEngine", lambda: mock_se
        )

        import openrecall.server.api
        importlib.reload(openrecall.server.api)

        import openrecall.server.api_v1
        importlib.reload(openrecall.server.api_v1)

        import openrecall.server.app
        importlib.reload(openrecall.server.app)

        app = openrecall.server.app.app
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def test_gate_F02_backward_compatibility(self, migrated_client):
        from PIL import Image

        # Upload via legacy /api/upload
        img = Image.new("RGB", (10, 10), color="blue")
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)

        metadata = json.dumps({
            "timestamp": 1234500001,
            "app_name": "TestApp",
            "window_title": "TestWindow",
        })

        resp = migrated_client.post(
            "/api/upload",
            data={"file": (img_bytes, "test.png"), "metadata": metadata},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 202, f"F-02 FAIL: Upload returned {resp.status_code}"

        # Query via legacy /api/memories/recent
        resp = migrated_client.get("/api/memories/recent?limit=10")
        assert resp.status_code == 200, f"F-02 FAIL: Recent memories returned {resp.status_code}"

        # All legacy endpoints respond
        for endpoint in ["/api/health", "/api/memories/recent",
                         "/api/memories/latest?since=0", "/api/queue/status",
                         "/api/config", "/api/search?q="]:
            resp = migrated_client.get(endpoint)
            assert resp.status_code == 200, f"F-02 FAIL: {endpoint} returned {resp.status_code}"


class TestGateF03ApiVersioning:
    """F-03: API Versioning.

    Criteria: /api/v1/* routes functional, /api/* aliases work.
    """

    @pytest.fixture
    def v1_client(self, tmp_path, monkeypatch):
        import importlib
        import unittest.mock as mock

        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))

        import openrecall.shared.config
        importlib.reload(openrecall.shared.config)

        # Reload sql submodule so it picks up new settings
        import openrecall.server.database.sql
        importlib.reload(openrecall.server.database.sql)
        import openrecall.server.database
        importlib.reload(openrecall.server.database)
        openrecall.server.database.SQLStore()

        import openrecall.server.auth
        importlib.reload(openrecall.server.auth)

        # Mock SearchEngine to avoid HuggingFace model download in test env
        import openrecall.server.search.engine
        mock_se = mock.MagicMock()
        mock_se.search.return_value = []
        monkeypatch.setattr(
            openrecall.server.search.engine, "SearchEngine", lambda: mock_se
        )

        import openrecall.server.api
        importlib.reload(openrecall.server.api)

        import openrecall.server.api_v1
        importlib.reload(openrecall.server.api_v1)

        import openrecall.server.app
        importlib.reload(openrecall.server.app)

        app = openrecall.server.app.app
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def test_gate_F03_api_versioning(self, v1_client):
        # V1 endpoints
        v1_endpoints = [
            ("GET", "/api/v1/health"),
            ("GET", "/api/v1/memories/recent"),
            ("GET", "/api/v1/memories/latest?since=0"),
            ("GET", "/api/v1/queue/status"),
            ("GET", "/api/v1/config"),
            ("GET", "/api/v1/search?q="),
        ]
        for method, url in v1_endpoints:
            if method == "GET":
                resp = v1_client.get(url)
            assert resp.status_code == 200, f"F-03 FAIL: {url} returned {resp.status_code}"

        # Legacy aliases still work
        legacy_endpoints = [
            "/api/health",
            "/api/memories/recent",
            "/api/search?q=",
        ]
        for url in legacy_endpoints:
            resp = v1_client.get(url)
            assert resp.status_code == 200, f"F-03 FAIL: Legacy {url} returned {resp.status_code}"

        # V1 pagination envelope
        resp = v1_client.get("/api/v1/memories/recent")
        data = resp.get_json()
        assert "data" in data, "F-03 FAIL: V1 missing 'data' in response"
        assert "meta" in data, "F-03 FAIL: V1 missing 'meta' in response"


class TestGateF04ConfigurationMatrix:
    """F-04: Configuration Matrix.

    Criteria: All 4 deployment modes configurable (local, remote,
    debian_client, debian_server).
    """

    def test_gate_F04_configuration_matrix(self, tmp_path, monkeypatch):
        import importlib
        from openrecall.shared.config_presets import get_preset, VALID_MODES

        # All 4 modes exist
        assert VALID_MODES == {"local", "remote", "debian_client", "debian_server"}, (
            f"F-04 FAIL: Expected 4 modes, got {VALID_MODES}"
        )

        # Each mode produces valid preset
        for mode in VALID_MODES:
            preset = get_preset(mode)
            assert "runs_server" in preset, f"F-04 FAIL: {mode} missing runs_server"
            assert "runs_client" in preset, f"F-04 FAIL: {mode} missing runs_client"

        # Default mode is 'local' when env var not set
        monkeypatch.delenv("OPENRECALL_DEPLOYMENT_MODE", raising=False)
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))

        import openrecall.shared.config
        importlib.reload(openrecall.shared.config)
        s = openrecall.shared.config.Settings()
        assert s.deployment_mode == "local", f"F-04 FAIL: Default mode is '{s.deployment_mode}'"

        # Env template files exist
        config_dir = Path(__file__).resolve().parent.parent / "config"
        for mode in ["local", "remote", "debian_client", "debian_server"]:
            env_file = config_dir / f"{mode}.env"
            assert env_file.exists(), f"F-04 FAIL: Missing {env_file}"


# ===========================================================================
# Performance Gates (P-01 to P-02)
# ===========================================================================


class TestGateP01MigrationLatency:
    """P-01: Migration Latency.

    Criteria: <5 seconds for 10K entries.
    """

    def test_gate_P01_migration_latency(self, tmp_path):
        from openrecall.server.database.migrations.runner import MigrationRunner

        db_path = tmp_path / "gate_p01.db"
        _create_test_db(db_path, num_entries=10000)

        runner = MigrationRunner(db_path)
        result = runner.run()

        assert result.success, f"P-01 FAIL: Migration failed: {result.error}"
        assert result.elapsed_seconds < 5.0, (
            f"P-01 FAIL: Migration took {result.elapsed_seconds:.2f}s (target: <5s)"
        )


class TestGateP02QueryOverhead:
    """P-02: Query Overhead.

    Criteria: Schema changes add <10ms to typical queries.
    """

    def test_gate_P02_query_overhead(self, tmp_path, monkeypatch):
        import importlib

        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))

        import openrecall.shared.config
        importlib.reload(openrecall.shared.config)
        db_path = openrecall.shared.config.settings.db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # Create DB with 100 entries
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app TEXT, title TEXT, text TEXT,
                timestamp INTEGER UNIQUE, embedding BLOB,
                description TEXT, status TEXT DEFAULT 'COMPLETED'
            )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON entries (timestamp)")
        for i in range(100):
            conn.execute(
                "INSERT INTO entries (timestamp, app, title, text, status) "
                "VALUES (?, ?, ?, ?, 'COMPLETED')",
                (2000000 + i, f"app_{i}", f"title_{i}", f"text_{i}"),
            )
        conn.commit()

        # Benchmark before migration
        def benchmark(conn):
            times = []
            for _ in range(100):
                start = time.perf_counter()
                conn.execute(
                    "SELECT id, app, title, text, timestamp, status "
                    "FROM entries ORDER BY timestamp DESC LIMIT 50"
                ).fetchall()
                times.append(time.perf_counter() - start)
            return sorted(times)[len(times) // 2]

        baseline = benchmark(conn)
        conn.close()

        # Apply migration
        from openrecall.server.database.migrations.runner import MigrationRunner
        runner = MigrationRunner(db_path)
        result = runner.run()
        assert result.success

        # Benchmark after migration
        conn = sqlite3.connect(str(db_path))
        post = benchmark(conn)
        conn.close()

        overhead_ms = (post - baseline) * 1000
        assert overhead_ms < 10, (
            f"P-02 FAIL: Query overhead {overhead_ms:.2f}ms exceeds 10ms "
            f"(baseline: {baseline * 1000:.2f}ms, post: {post * 1000:.2f}ms)"
        )


# ===========================================================================
# Stability Gates (S-01 to S-02)
# ===========================================================================


class TestGateS01DataIntegrity:
    """S-01: Data Integrity.

    Criteria: Zero data loss during migration (SHA256 checksum match).
    """

    def test_gate_S01_data_integrity(self, tmp_path):
        from openrecall.server.database.migrations.runner import MigrationRunner
        from openrecall.server.database.migrations.integrity import (
            compute_entries_checksum,
            save_checksum,
            verify_checksum,
        )

        db_path = tmp_path / "gate_s01.db"
        _create_test_db(db_path, num_entries=500)

        # Checksum before
        conn = sqlite3.connect(str(db_path))
        checksum_before = compute_entries_checksum(conn)
        checksum_path = tmp_path / "checksum.txt"
        save_checksum(checksum_before, checksum_path)
        conn.close()

        # Migrate
        runner = MigrationRunner(db_path)
        result = runner.run()
        assert result.success

        # Checksum after
        conn = sqlite3.connect(str(db_path))
        assert verify_checksum(conn, checksum_path), (
            "S-01 FAIL: Checksum mismatch - data integrity violation"
        )
        conn.close()


class TestGateS02RollbackSuccess:
    """S-02: Rollback Success.

    Criteria: Rollback restores original state in <2 minutes.
    """

    def test_gate_S02_rollback_success(self, tmp_path):
        from openrecall.server.database.migrations.runner import MigrationRunner
        from openrecall.server.database.migrations.rollback import MigrationRollback

        db_path = tmp_path / "gate_s02.db"
        _create_test_db(db_path, num_entries=1000)

        # Forward migration
        runner = MigrationRunner(db_path)
        result = runner.run()
        assert result.success

        # Rollback
        rollback = MigrationRollback(db_path)
        rb_result = rollback.rollback()

        assert rb_result.success, f"S-02 FAIL: Rollback failed: {rb_result.error}"
        assert rb_result.elapsed_seconds < 120, (
            f"S-02 FAIL: Rollback took {rb_result.elapsed_seconds:.1f}s (target: <120s)"
        )

        # Verify original state restored
        tables = _get_tables(db_path)
        v3_tables = {
            "schema_version", "video_chunks", "frames", "ocr_text",
            "audio_chunks", "audio_transcriptions",
            "ocr_text_fts", "audio_transcriptions_fts",
        }
        remaining = tables & v3_tables
        assert not remaining, f"S-02 FAIL: V3 tables still present: {remaining}"

        # Verify entry count
        assert rb_result.entries_before == 1000
        assert rb_result.entries_after == 1000


# ===========================================================================
# Resource Gates (R-01 to R-02)
# ===========================================================================


class TestGateR01MigrationMemory:
    """R-01: Peak Memory.

    Criteria: Migration uses <500MB RAM.
    """

    def test_gate_R01_migration_memory(self, tmp_path):
        from openrecall.server.database.migrations.runner import MigrationRunner

        db_path = tmp_path / "gate_r01.db"
        _create_test_db(db_path, num_entries=10000)

        runner = MigrationRunner(db_path)
        result = runner.run()

        assert result.success
        assert result.peak_memory_mb < 500, (
            f"R-01 FAIL: Peak memory {result.peak_memory_mb:.1f}MB exceeds 500MB"
        )


class TestGateR02SchemaOverhead:
    """R-02: Disk Space.

    Criteria: Schema overhead <10MB (empty tables).
    """

    def test_gate_R02_schema_overhead(self, tmp_path):
        from openrecall.server.database.migrations.runner import MigrationRunner

        db_path = tmp_path / "gate_r02.db"
        _create_test_db(db_path)

        size_before = db_path.stat().st_size

        runner = MigrationRunner(db_path)
        result = runner.run()
        assert result.success

        size_after = db_path.stat().st_size
        overhead_mb = (size_after - size_before) / (1024 * 1024)

        assert overhead_mb < 10, (
            f"R-02 FAIL: Schema overhead {overhead_mb:.2f}MB exceeds 10MB"
        )


# ===========================================================================
# Data Governance Gates (DG-01 to DG-04)
# ===========================================================================


class TestGateDG01PiiClassificationPolicy:
    """DG-01: PII Classification Policy.

    Criteria: Document defines PII categories (screen text, audio, faces).
    """

    def test_gate_DG01_pii_classification_policy(self):
        policy_path = (
            Path(__file__).resolve().parent.parent
            / "v3" / "results" / "pii-classification-policy.md"
        )
        assert policy_path.exists(), f"DG-01 FAIL: Missing {policy_path}"

        content = policy_path.read_text()

        required_categories = [
            "Screen text",
            "Application credentials",
            "Audio speech",
            "Speaker identity",
            "Facial images",
            "App usage patterns",
        ]
        for category in required_categories:
            assert category in content, (
                f"DG-01 FAIL: PII category '{category}' not found in policy"
            )


class TestGateDG02EncryptionSchema:
    """DG-02: Encryption Schema Design.

    Criteria: Database schema supports encryption fields.
    """

    def test_gate_DG02_encryption_schema(self, tmp_path):
        from openrecall.server.database.migrations.runner import MigrationRunner

        db_path = tmp_path / "gate_dg02.db"
        _create_test_db(db_path)

        runner = MigrationRunner(db_path)
        result = runner.run()
        assert result.success

        # video_chunks must have encrypted column
        vc_cols = _get_columns(db_path, "video_chunks")
        assert "encrypted" in vc_cols, "DG-02 FAIL: video_chunks missing 'encrypted' column"
        assert "checksum" in vc_cols, "DG-02 FAIL: video_chunks missing 'checksum' column"

        # audio_chunks must have encrypted column
        ac_cols = _get_columns(db_path, "audio_chunks")
        assert "encrypted" in ac_cols, "DG-02 FAIL: audio_chunks missing 'encrypted' column"
        assert "checksum" in ac_cols, "DG-02 FAIL: audio_chunks missing 'checksum' column"


class TestGateDG03RetentionPolicy:
    """DG-03: Retention Policy Design.

    Criteria: Schema includes created_at, expires_at fields.
    """

    def test_gate_DG03_retention_policy(self, tmp_path):
        from openrecall.server.database.migrations.runner import MigrationRunner

        db_path = tmp_path / "gate_dg03.db"
        _create_test_db(db_path, num_entries=5)

        runner = MigrationRunner(db_path)
        result = runner.run()
        assert result.success

        # entries table
        entries_cols = _get_columns(db_path, "entries")
        assert "created_at" in entries_cols, "DG-03 FAIL: entries missing 'created_at'"
        assert "expires_at" in entries_cols, "DG-03 FAIL: entries missing 'expires_at'"

        # video_chunks table
        vc_cols = _get_columns(db_path, "video_chunks")
        assert "created_at" in vc_cols, "DG-03 FAIL: video_chunks missing 'created_at'"
        assert "expires_at" in vc_cols, "DG-03 FAIL: video_chunks missing 'expires_at'"

        # audio_chunks table
        ac_cols = _get_columns(db_path, "audio_chunks")
        assert "created_at" in ac_cols, "DG-03 FAIL: audio_chunks missing 'created_at'"
        assert "expires_at" in ac_cols, "DG-03 FAIL: audio_chunks missing 'expires_at'"

        # Retention policy document exists
        policy_path = (
            Path(__file__).resolve().parent.parent
            / "v3" / "results" / "retention-policy-design.md"
        )
        assert policy_path.exists(), "DG-03 FAIL: Missing retention-policy-design.md"


class TestGateDG04AuthPlaceholder:
    """DG-04: API Authentication Placeholder.

    Criteria: API routes include auth decorator (even if localhost).
    """

    def test_gate_DG04_auth_placeholder(self, tmp_path, monkeypatch):
        import importlib
        import unittest.mock as mock

        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))

        import openrecall.shared.config
        importlib.reload(openrecall.shared.config)

        # Reload sql submodule so it picks up new settings
        import openrecall.server.database.sql
        importlib.reload(openrecall.server.database.sql)
        import openrecall.server.database
        importlib.reload(openrecall.server.database)
        openrecall.server.database.SQLStore()

        import openrecall.server.auth
        importlib.reload(openrecall.server.auth)

        # Mock SearchEngine to avoid HuggingFace model download in test env
        import openrecall.server.search.engine
        mock_se = mock.MagicMock()
        mock_se.search.return_value = []
        monkeypatch.setattr(
            openrecall.server.search.engine, "SearchEngine", lambda: mock_se
        )

        import openrecall.server.api
        importlib.reload(openrecall.server.api)

        import openrecall.server.api_v1
        importlib.reload(openrecall.server.api_v1)

        import openrecall.server.app
        importlib.reload(openrecall.server.app)

        app = openrecall.server.app.app

        # Verify auth module exists and exports require_auth
        from openrecall.server.auth import require_auth
        assert callable(require_auth), "DG-04 FAIL: require_auth not callable"

        # Verify v1 routes are present
        v1_routes = [
            rule.rule for rule in app.url_map.iter_rules()
            if rule.rule.startswith("/api/v1/")
        ]
        assert len(v1_routes) > 0, "DG-04 FAIL: No /api/v1/ routes registered"

        # Verify v1 health endpoint works (auth passes in Phase 0)
        app.config["TESTING"] = True
        with app.test_client() as client:
            resp = client.get("/api/v1/health")
            assert resp.status_code == 200, "DG-04 FAIL: Auth-decorated endpoint not accessible"


# ===========================================================================
# Upload Queue Gates (UQ-01 to UQ-05)
# ===========================================================================


class TestGateUQ01BufferCapacity:
    """UQ-01: Buffer Capacity Enforcement.

    Criteria: Client respects 100GB max capacity, oldest chunk deleted (FIFO).
    """

    def test_gate_UQ01_buffer_capacity(self, tmp_path):
        from openrecall.client.upload_queue import UploadQueue

        buffer_dir = tmp_path / "buffer"
        buffer_dir.mkdir(parents=True, exist_ok=True)

        # Create files exceeding capacity (use very small capacity for test)
        for i in range(10):
            f = buffer_dir / f"chunk_{i}.dat"
            f.write_bytes(b"x" * 100)
            os.utime(f, (1000 + i, 1000 + i))

        # 500 bytes capacity, 10 files * 100 bytes = 1000 bytes
        queue = UploadQueue(buffer_dir=buffer_dir, max_size_gb=500 / (1024**3))
        deleted = queue._enforce_capacity()

        total_size = queue.get_total_size()
        assert total_size <= queue.max_size_bytes, (
            f"UQ-01 FAIL: Total size {total_size} exceeds capacity {queue.max_size_bytes}"
        )


class TestGateUQ02TTLCleanup:
    """UQ-02: TTL Cleanup.

    Criteria: Chunks >7 days auto-deleted.
    """

    def test_gate_UQ02_ttl_cleanup(self, tmp_path):
        from openrecall.client.upload_queue import UploadQueue

        buffer_dir = tmp_path / "buffer"
        buffer_dir.mkdir(parents=True, exist_ok=True)

        # Create files >7 days old
        old_time = time.time() - (8 * 24 * 3600)
        for i in range(3):
            f = buffer_dir / f"old_{i}.dat"
            f.write_bytes(b"old")
            os.utime(f, (old_time, old_time))

        # Create recent files
        for i in range(2):
            f = buffer_dir / f"new_{i}.dat"
            f.write_bytes(b"new")

        queue = UploadQueue(buffer_dir=buffer_dir, ttl_days=7)
        deleted = queue.cleanup_expired()

        assert deleted == 3, f"UQ-02 FAIL: Expected 3 expired deletions, got {deleted}"
        remaining = list(buffer_dir.iterdir())
        assert len(remaining) == 2, f"UQ-02 FAIL: Expected 2 remaining, got {len(remaining)}"


class TestGateUQ03FifoDeletion:
    """UQ-03: FIFO Deletion.

    Criteria: Oldest chunks deleted first when capacity reached.
    """

    def test_gate_UQ03_fifo_deletion(self, tmp_path):
        from openrecall.client.upload_queue import UploadQueue

        buffer_dir = tmp_path / "buffer"
        buffer_dir.mkdir(parents=True, exist_ok=True)

        # Create files with sequential ages
        for i in range(5):
            f = buffer_dir / f"chunk_{i}.dat"
            f.write_bytes(b"x" * 50)
            os.utime(f, (1000 + i, 1000 + i))

        queue = UploadQueue(buffer_dir=buffer_dir, max_size_gb=100 / (1024**3))

        # Verify sorting is oldest first
        files = queue._get_files_sorted_by_age()
        mtimes = [f.stat().st_mtime for f in files]
        assert mtimes == sorted(mtimes), (
            f"UQ-03 FAIL: Files not sorted by age (oldest first)"
        )

        # Enforce capacity - should delete oldest first
        queue._enforce_capacity()

        remaining = sorted(buffer_dir.iterdir(), key=lambda p: p.stat().st_mtime)
        if len(remaining) < 5:
            # Some were deleted - verify oldest were removed
            remaining_names = {f.name for f in remaining}
            assert "chunk_4.dat" in remaining_names, (
                "UQ-03 FAIL: Newest file deleted instead of oldest"
            )


class TestGateUQ04PostUploadDeletion:
    """UQ-04: Post-Upload Deletion.

    Criteria: Successful upload deletes local copy within 1s.
    """

    def test_gate_UQ04_post_upload_deletion(self, tmp_path):
        from PIL import Image
        from openrecall.client.upload_queue import UploadQueue

        queue = UploadQueue(buffer_dir=tmp_path / "buffer")
        img = Image.new("RGB", (10, 10), color="green")
        item_id = queue.enqueue(img, {"timestamp": 9000, "active_app": "test"})

        # Verify file exists
        assert queue.storage_dir.exists()

        start = time.perf_counter()
        queue.commit([item_id])
        elapsed = time.perf_counter() - start

        assert elapsed < 1.0, (
            f"UQ-04 FAIL: Post-upload deletion took {elapsed:.3f}s (target: <1s)"
        )

        # Verify files removed
        json_file = queue.storage_dir / f"{item_id}.json"
        assert not json_file.exists(), "UQ-04 FAIL: JSON file not deleted after commit"


class TestGateUQ05RetryBackoff:
    """UQ-05: Retry Exponential Backoff.

    Criteria: Retry delays: 1min -> 5min -> 15min -> 1h -> 6h.
    """

    def test_gate_UQ05_retry_backoff(self):
        from openrecall.client.upload_queue import UploadQueue

        expected_schedule = {
            1: 60,      # 1 minute
            2: 300,     # 5 minutes
            3: 900,     # 15 minutes
            4: 3600,    # 1 hour
            5: 21600,   # 6 hours
        }

        for retry_count, expected_delay in expected_schedule.items():
            actual = UploadQueue.get_backoff_delay(retry_count)
            assert actual == expected_delay, (
                f"UQ-05 FAIL: Retry {retry_count} expected {expected_delay}s, got {actual}s"
            )

        # Cap test: beyond schedule length
        assert UploadQueue.get_backoff_delay(10) == 21600, (
            "UQ-05 FAIL: Backoff not capped at 21600s (6h)"
        )
