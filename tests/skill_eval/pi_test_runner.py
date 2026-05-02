#!/usr/bin/env python3
"""
Quick test runner for Pi multi-turn conversation validation.

Usage:
    python tests/skill_eval/pi_test_runner.py

Runs Pi with the installed myrecall-search skill against mock_server,
records API calls, and reports behavior.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Paths
MOCK_SERVER = Path(__file__).parent / "mock_server.py"
PI_CLI = (
    Path.home()
    / ".myrecall"
    / "pi-agent"
    / "node_modules"
    / "@mariozechner"
    / "pi-coding-agent"
    / "dist"
    / "cli.js"
)
SKILL_DIR = Path.home() / ".pi" / "agent" / "skills" / "myrecall-search"
MOCK_LOG = "/tmp/skill_test_multiturn.log"
SESSION_FILE = "/tmp/pi_test_session.jsonl"

def clear_mock_log():
    """Clear mock server log."""
    if os.path.exists(MOCK_LOG):
        os.remove(MOCK_LOG)


def read_mock_log() -> list[dict]:
    """Read mock server log entries."""
    if not os.path.exists(MOCK_LOG):
        return []
    entries = []
    with open(MOCK_LOG) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def start_mock_server() -> subprocess.Popen:
    """Start mock server as subprocess."""
    clear_mock_log()
    proc = subprocess.Popen(
        [sys.executable, str(MOCK_SERVER), "--port", "8083", "--log", MOCK_LOG],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Wait for server to start
    for _ in range(20):
        time.sleep(0.1)
        try:
            import urllib.request
            req = urllib.request.Request("http://localhost:8083/v1/health")
            with urllib.request.urlopen(req, timeout=1) as resp:
                if resp.status == 200:
                    break
        except Exception:
            pass
    else:
        proc.terminate()
        raise RuntimeError("Mock server failed to start")
    return proc


def run_pi(prompt: str, session: str | None = None, continue_session: bool = False,
           provider: str = "anthropic", model: str = "claude-sonnet-4-6") -> dict:
    """Run Pi CLI with a prompt, return stdout/stderr/returncode."""
    env = os.environ.copy()
    env["PI_OFFLINE"] = "1"
    # Use ANTHROPIC_OAUTH_TOKEN if available (Claude Code's auth)
    if "ANTHROPIC_AUTH_TOKEN" in env and "ANTHROPIC_OAUTH_TOKEN" not in env:
        env["ANTHROPIC_OAUTH_TOKEN"] = env["ANTHROPIC_AUTH_TOKEN"]

    cmd = [
        "bun", "run", str(PI_CLI),
        "--provider", provider,
        "--model", model,
        "--skill", str(SKILL_DIR),
        "--tools", "read,bash",
        "--no-session" if not session else "",
        "-p", prompt,
    ]

    if session:
        cmd.insert(-2, "--session")
        cmd.insert(-2, session)
    if continue_session:
        cmd.insert(-2, "--continue")

    # Remove empty strings
    cmd = [c for c in cmd if c]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }


def extract_api_calls(log_entries: list[dict]) -> list[dict]:
    """Extract API calls from mock server log."""
    calls = []
    for entry in log_entries:
        path = entry.get("path", "")
        if path.startswith("/v1/"):
            calls.append({
                "method": entry.get("method"),
                "path": path,
                "args": entry.get("args", {}),
            })
    return calls


def print_result(label: str, result: dict, calls: list[dict]):
    """Print test result."""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  Return code: {result['returncode']}")
    print(f"  API calls ({len(calls)}):")
    for call in calls:
        args_str = " ".join(f"{k}={v}" for k, v in call["args"].items())
        print(f"    {call['method']} {call['path']} {args_str}")
    if result["stderr"]:
        print(f"  Stderr (last 500 chars):")
        print(f"    {result['stderr'][-500:]}")


def test_single_turn():
    """Quick single-turn sanity check."""
    print("\n>>> SINGLE-TURN SANITY CHECK <<<")
    server = start_mock_server()
    try:
        result = run_pi("What was I doing today?")
        calls = extract_api_calls(read_mock_log())
        print_result("T1: What was I doing today?", result, calls)
        return calls
    finally:
        server.terminate()
        server.wait()


def test_multi_turn():
    """Multi-turn conversation test (D1-D4)."""
    print("\n>>> MULTI-TURN CONVERSATION TESTS <<<")

    # Remove old session file
    if os.path.exists(SESSION_FILE):
        os.remove(SESSION_FILE)

    # D1: summary -> drill-down
    print("\n--- D1: summary -> drill-down ---")
    server = start_mock_server()
    try:
        # Turn 1
        result1 = run_pi("Summarize my day today", session=SESSION_FILE)
        calls1 = extract_api_calls(read_mock_log())
        print_result("D1-T1: Summarize my day", result1, calls1)

        # Turn 2 (continue session)
        clear_mock_log()
        result2 = run_pi(
            "What was in that VSCode PR review frame?",
            session=SESSION_FILE,
            continue_session=True,
        )
        calls2 = extract_api_calls(read_mock_log())
        print_result("D1-T2: VSCode PR review details", result2, calls2)
    finally:
        server.terminate()
        server.wait()

    # D2: time pivot (today -> yesterday)
    print("\n--- D2: time pivot ---")
    if os.path.exists(SESSION_FILE):
        os.remove(SESSION_FILE)
    server = start_mock_server()
    try:
        result1 = run_pi("Summarize my day today", session=SESSION_FILE)
        calls1 = extract_api_calls(read_mock_log())
        print_result("D2-T1: Summarize today", result1, calls1)

        clear_mock_log()
        result2 = run_pi(
            "What about yesterday?",
            session=SESSION_FILE,
            continue_session=True,
        )
        calls2 = extract_api_calls(read_mock_log())
        print_result("D2-T2: What about yesterday", result2, calls2)
    finally:
        server.terminate()
        server.wait()

    # D3: search -> drill-in
    print("\n--- D3: search -> drill-in ---")
    if os.path.exists(SESSION_FILE):
        os.remove(SESSION_FILE)
    server = start_mock_server()
    try:
        result1 = run_pi("Find the PR I was reviewing", session=SESSION_FILE)
        calls1 = extract_api_calls(read_mock_log())
        print_result("D3-T1: Find PR", result1, calls1)

        clear_mock_log()
        result2 = run_pi(
            "What did the first result contain?",
            session=SESSION_FILE,
            continue_session=True,
        )
        calls2 = extract_api_calls(read_mock_log())
        print_result("D3-T2: First result details", result2, calls2)
    finally:
        server.terminate()
        server.wait()


def main():
    if not PI_CLI.exists():
        print(f"ERROR: Pi CLI not found at {PI_CLI}")
        sys.exit(1)
    if not SKILL_DIR.exists():
        print(f"ERROR: Skill not found at {SKILL_DIR}")
        sys.exit(1)

    # First, a quick single-turn sanity check
    test_single_turn()

    # Then multi-turn tests
    test_multi_turn()

    print("\n" + "="*60)
    print("  DONE")
    print("="*60)


if __name__ == "__main__":
    main()
