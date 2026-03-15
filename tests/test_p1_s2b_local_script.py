from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "acceptance" / "p1_s2b_local.sh"


@pytest.mark.unit
def test_p1_s2b_local_script_exists_and_is_executable() -> None:
    assert SCRIPT_PATH.exists(), "scripts/acceptance/p1_s2b_local.sh must exist"
    assert SCRIPT_PATH.is_file()
    assert SCRIPT_PATH.stat().st_mode & 0o111, "script must be executable"


@pytest.mark.unit
def test_p1_s2b_local_script_help_returns_usage() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT_PATH), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Usage:" in result.stdout
    assert "p1_s2b_local.sh" in result.stdout
    assert "p1-s2b-metrics.json" in result.stdout


@pytest.mark.unit
def test_p1_s2b_local_script_writes_static_evidence_bundle(tmp_path: Path) -> None:
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
            "--exclude-broken-window",
            "--exclude-alias-only",
            "--exclude-mixed-version",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
        env={**os.environ},
    )

    assert result.returncode == 1

    log_path = evidence_dir / "p1-s2b-local-gate.log"
    metrics_path = evidence_dir / "p1-s2b-metrics.json"
    health_path = evidence_dir / "p1-s2b-health-snapshots.json"
    context_path = evidence_dir / "p1-s2b-context.json"
    spool_path = evidence_dir / "p1-s2b-spool-check.json"
    topology_path = evidence_dir / "p1-s2b-topology-evidence.json"
    proof_path = evidence_dir / "p1-s2b-proof-samples.json"
    ui_path = evidence_dir / "p1-s2b-ui-proof.md"

    assert log_path.exists()
    assert metrics_path.exists()
    assert health_path.exists()
    assert context_path.exists()
    assert spool_path.exists()
    assert topology_path.exists()
    assert proof_path.exists()
    assert ui_path.exists()

    metrics = json.loads(metrics_path.read_text())
    assert metrics["metrics"]["trigger_target_routing_correctness"] is None
    assert metrics["metrics"]["device_binding_correctness"] is None
    assert metrics["metrics"]["single_monitor_duplicate_capture_rate"] is None
    assert metrics["metrics"]["topology_rebuild_correctness"] is None
    assert "capture_to_ingest_latency_ms" in metrics["metrics"]
    assert metrics["proof_sample_rules"]["broken_window"] is True
    assert metrics["proof_sample_rules"]["alias_only_excluded"] is True
    assert metrics["proof_sample_rules"]["mixed_version_excluded"] is True
    assert metrics["spool_check_file"] == "p1-s2b-spool-check.json"

    topology = json.loads(topology_path.read_text())
    assert topology["method"] in {"injected", "manual"}
    assert set(topology["scenarios"].keys()) == {"SC-T1", "SC-T2", "SC-T3", "SC-T4"}

    proof = json.loads(proof_path.read_text())
    assert "SC-R1" in proof["scenario_status"]
    assert "SC-T4" in proof["scenario_status"]

    spool = json.loads(spool_path.read_text())
    assert "item_count" in spool
    assert "items" in spool
