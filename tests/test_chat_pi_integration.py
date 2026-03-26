"""
Integration tests for Phase 1 chat foundation.

Requires:
  - MyRecall Edge server running on localhost:8083
  - bun installed on system
  - MINIMAX_CN_API_KEY or KIMI_API_KEY environment variable

Mark: @pytest.mark.integration
"""

import os
import subprocess
from pathlib import Path

import pytest

from openrecall.client.chat.config_manager import (
    get_api_key,
    get_default_model,
    get_default_provider,
)
from openrecall.client.chat.pi_manager import (
    PiInstallError,  # noqa: F401
    ensure_installed,
    find_bun_executable,
    find_pi_executable,
)  # noqa: F401


def is_edge_server_reachable() -> bool:
    """Check if Edge server is running on localhost:8083."""
    import urllib.request

    try:
        req = urllib.request.Request("http://localhost:8083/v1/health")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


@pytest.mark.integration
class TestPiInstallation:
    def test_bun_is_available(self):
        """bun executable must be available."""
        bun = find_bun_executable()
        assert bun is not None, "bun not found. Install from https://bun.sh"

    def test_pi_can_be_installed(self):
        """ensure_installed installs Pi without error."""
        if not find_bun_executable():
            pytest.skip("bun not installed")
        try:
            ensure_installed()
        except PiInstallError as e:
            pytest.fail(f"Pi installation failed: {e}")

    def test_pi_executable_found_after_install(self):
        """find_pi_executable returns cli.js path after installation."""
        if not find_bun_executable():
            pytest.skip("bun not installed")
        ensure_installed()
        pi_path = find_pi_executable()
        assert pi_path is not None, "pi executable not found after installation"
        assert Path(pi_path).exists(), f"pi executable does not exist: {pi_path}"


@pytest.mark.integration
class TestApiKeyResolution:
    def test_minimax_cn_api_key_from_env(self):
        """get_api_key resolves MINIMAX_CN_API_KEY for minimax-cn."""
        if not os.environ.get("MINIMAX_CN_API_KEY"):
            pytest.skip("MINIMAX_CN_API_KEY not set")
        result = get_api_key("minimax-cn")
        assert result == os.environ["MINIMAX_CN_API_KEY"]

    def test_kimi_api_key_from_env(self):
        """get_api_key resolves KIMI_API_KEY for kimi-coding."""
        if not os.environ.get("KIMI_API_KEY"):
            pytest.skip("KIMI_API_KEY not set")
        result = get_api_key("kimi-coding")
        assert result == os.environ["KIMI_API_KEY"]

    def test_default_provider_and_model(self):
        """Default provider and model constants are correct."""
        assert get_default_provider() == "minimax-cn"
        assert get_default_model() == "MiniMax-M2.7"


@pytest.mark.integration
class TestPiExecution:
    @pytest.fixture(autouse=True)
    def check_prereqs(self):
        """Skip if prerequisites not met."""
        if not find_bun_executable():
            pytest.skip("bun not installed")
        if not is_edge_server_reachable():
            pytest.skip("Edge server not running on localhost:8083")
        if not (
            os.environ.get("MINIMAX_CN_API_KEY") or os.environ.get("KIMI_API_KEY")
        ):
            pytest.skip("Neither MINIMAX_CN_API_KEY nor KIMI_API_KEY is set")

    def test_pi_can_call_activity_summary(self, tmp_path):
        """Pi can successfully call /v1/activity-summary."""
        ensure_installed()
        pi_path = find_pi_executable()
        assert pi_path is not None

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Run Pi with a simple prompt that calls /v1/activity-summary
        # Pi runs in non-interactive print mode
        env = os.environ.copy()
        provider = "minimax-cn" if env.get("MINIMAX_CN_API_KEY") else "kimi-coding"

        result = subprocess.run(
            [
                "bun",
                "run",
                pi_path,
                "--workspace",
                str(workspace),
                "--provider",
                provider,
                "--no-stream",
                "-p",
                "Use curl to call GET http://localhost:8083/v1/activity-summary "
                "with start_time and end_time parameters (use date command to generate "
                "ISO timestamps for the last hour). Report what apps were used.",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )

        # Check that Pi ran without crashing
        assert result.returncode == 0, (
            f"Pi execution failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Check that /v1/activity-summary was accessible (no connection error)
        combined = result.stdout + result.stderr
        assert "Connection refused" not in combined, (
            "Edge server not reachable from Pi"
        )
        assert "ECONNREFUSED" not in combined, (
            "Edge server not reachable from Pi"
        )

    def test_skill_is_installed_at_correct_location(self):
        """myrecall-search skill is copied to ~/.pi/agent/skills/."""
        ensure_installed()
        skill_path = (
            Path.home()
            / ".pi"
            / "agent"
            / "skills"
            / "myrecall-search"
            / "SKILL.md"
        )
        assert skill_path.exists(), f"Skill not found at {skill_path}"
        content = skill_path.read_text()
        assert "myrecall-search" in content
        assert "/v1/activity-summary" in content
        assert "/v1/search" in content
        assert "/v1/frames" in content
