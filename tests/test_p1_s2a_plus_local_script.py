from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "acceptance" / "p1_s2a_plus_local.sh"


@pytest.mark.unit
def test_p1_s2a_plus_local_script_exists_and_is_executable() -> None:
    assert SCRIPT_PATH.exists(), "scripts/acceptance/p1_s2a_plus_local.sh must exist"
    assert SCRIPT_PATH.is_file()
    assert SCRIPT_PATH.stat().st_mode & 0o111, "script must be executable"


@pytest.mark.unit
def test_p1_s2a_plus_local_script_help_returns_usage() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT_PATH), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Usage:" in result.stdout
    assert "p1_s2a_plus_local.sh" in result.stdout
    assert "p1-s2a-plus-context.json" in result.stdout


@pytest.mark.unit
def test_p1_s2a_plus_local_script_writes_static_evidence_bundle(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "evidence"
    result = subprocess.run(
        [
            "bash",
            str(SCRIPT_PATH),
            "--skip-pytest",
            "--base-url",
            "http://127.0.0.1:9",
            "--sample-seconds",
            "2",
            "--evidence-dir",
            str(evidence_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "OPENRECALL_PERMISSION_POLL_INTERVAL_SEC": "10",
            "OPENRECALL_MIN_CAPTURE_INTERVAL_MS": "1000",
        },
    )

    assert result.returncode == 1

    log_path = evidence_dir / "p1-s2a-plus-local-gate.log"
    transitions_path = evidence_dir / "p1-s2a-plus-permission-transitions.jsonl"
    health_path = evidence_dir / "p1-s2a-plus-health-snapshots.json"
    ui_proof_path = evidence_dir / "p1-s2a-plus-ui-proof.md"
    context_path = evidence_dir / "p1-s2a-plus-context.json"

    assert log_path.exists()
    assert transitions_path.exists()
    assert health_path.exists()
    assert ui_proof_path.exists()
    assert context_path.exists()

    context = json.loads(context_path.read_text())
    assert context["terminal_mode"] == "Terminal mode"
    assert context["git_rev"]
    assert context["execution_window"]["run_ts"]
    assert context["execution_window"]["sample_seconds"] == 2
    assert context["permission_env"]["OPENRECALL_PERMISSION_POLL_INTERVAL_SEC"] == "10"

    health = json.loads(health_path.read_text())
    assert health["run_ts"]
    assert health["snapshots"]
    first_snapshot = health["snapshots"][0]
    assert set(first_snapshot) >= {
        "ts",
        "endpoint",
        "status",
        "http_code",
        "capture_permission_status",
        "capture_permission_reason",
        "health_status",
    }

    transition_lines = [
        line for line in transitions_path.read_text().splitlines() if line.strip()
    ]
    assert transition_lines
    first_transition = json.loads(transition_lines[0])
    assert set(first_transition) >= {
        "ts",
        "capture_permission_status",
        "capture_permission_reason",
        "health_status",
        "http_code",
    }

    ui_proof = ui_proof_path.read_text()
    assert "startup_not_determined" in ui_proof
    assert "startup_denied" in ui_proof
    assert "revoked_mid_run" in ui_proof
    assert "restored_after_denied" in ui_proof
    assert "stale_permission_state" in ui_proof
