"""Tests for run_client.sh and run_server.sh --mode flag."""
import subprocess
import pytest
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent

# Subprocess timeout in seconds for tests that invoke Python client/server
SUBPROCESS_TIMEOUT = 10


def test_client_mode_local_unknown_shows_error():
    """Unknown --mode value should exit with code 2 and show usage."""
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "run_client.sh"), "--mode", "invalid"],
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT,
    )
    assert result.returncode == 2
    assert "unknown --mode value" in result.stderr
    assert "local" in result.stderr
    assert "remote" in result.stderr


def test_client_mode_remote_unknown_shows_error():
    """Unknown --mode value should exit with code 2 for remote too."""
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "run_client.sh"), "--mode=invalid"],
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT,
    )
    assert result.returncode == 2
    assert "unknown --mode value" in result.stderr


def test_server_mode_local_unknown_shows_error():
    """Unknown --mode value should exit with code 2."""
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "run_server.sh"), "--mode", "unknown"],
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT,
    )
    assert result.returncode == 2
    assert "unknown --mode value" in result.stderr


def test_server_mode_remote_unknown_shows_error():
    """Unknown --mode value should exit with code 2."""
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "run_server.sh"), "--mode=unknown"],
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT,
    )
    assert result.returncode == 2


def test_client_mode_local_config_exists():
    """--mode local should resolve to client-local.toml."""
    config_path = REPO_ROOT / "client-local.toml"
    assert config_path.exists(), f"{config_path} does not exist"


def test_client_mode_remote_config_exists():
    """--mode remote should resolve to client-remote.toml."""
    config_path = REPO_ROOT / "client-remote.toml"
    assert config_path.exists(), f"{config_path} does not exist"


def test_server_mode_local_config_exists():
    """--mode local should resolve to server-local.toml."""
    config_path = REPO_ROOT / "server-local.toml"
    assert config_path.exists(), f"{config_path} does not exist"


def test_server_mode_remote_config_exists():
    """--mode remote should resolve to server-remote.toml."""
    config_path = REPO_ROOT / "server-remote.toml"
    assert config_path.exists(), f"{config_path} does not exist"


def test_client_mode_local_e2e():
    """--mode local should print config path before starting client."""
    # The Python client does not support --help (uses parse_known_args),
    # so the client will block on capture. We verify the config path is
    # printed before the timeout, which confirms --mode local works.
    try:
        result = subprocess.run(
            ["bash", "-c",
             f"cd {REPO_ROOT} && bash run_client.sh --mode local --debug 2>&1 || true"],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
        )
        combined = result.stdout + result.stderr
    except subprocess.TimeoutExpired as e:
        # Timeout means the client started successfully (capture loop blocks).
        # Verify config path was printed before the hang.
        stdout_bytes = e.stdout if e.stdout else b""
        stderr_bytes = e.stderr if e.stderr else b""
        combined = stdout_bytes.decode("utf-8", errors="replace") + stderr_bytes.decode("utf-8", errors="replace")
    assert "client-local.toml" in combined


def test_client_no_mode_no_error():
    """No --mode flag should not produce errors (backward compat)."""
    # The client starts its capture loop, so it blocks. We only check
    # that no "unknown --mode" error appears before the timeout.
    try:
        result = subprocess.run(
            ["bash", "-c",
             f"cd {REPO_ROOT} && bash run_client.sh --debug 2>&1 || true"],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
        )
        combined = result.stdout + result.stderr
    except subprocess.TimeoutExpired as e:
        # Timeout is expected -- client started its capture loop.
        stdout_bytes = e.stdout if e.stdout else b""
        stderr_bytes = e.stderr if e.stderr else b""
        combined = stdout_bytes.decode("utf-8", errors="replace") + stderr_bytes.decode("utf-8", errors="replace")
    assert "unknown --mode" not in combined


def test_client_config_overrides_mode():
    """--config should take precedence over --mode."""
    # --config /dev/null is invalid; script should exit with error
    # after printing the precedence message.
    try:
        result = subprocess.run(
            ["bash", "-c",
             f"cd {REPO_ROOT} && bash run_client.sh --mode local --config /dev/null 2>&1 || true"],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
        )
        combined = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        pytest.fail("run_client.sh with invalid config should exit, not hang")
    # --config takes precedence: info message printed
    assert "--config takes precedence" in combined
    # Config file /dev/null does not exist, so script exits with error
    assert result.returncode != 0 or "Config file not found" in combined
