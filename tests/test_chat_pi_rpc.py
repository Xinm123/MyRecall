"""Tests for Pi RPC manager."""
import json
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import subprocess
import threading
import time

from openrecall.client.chat.pi_rpc import PiRpcManager


class MockProcess:
    """Mock subprocess.Popen for testing."""
    def __init__(self, stdout_lines=None):
        self.stdin = MagicMock()
        self.stdout = MagicMock()
        self.stderr = MagicMock()
        self.pid = 12345
        self._poll = None
        self._stdout_lines = stdout_lines or []

        # Setup stdout to return lines
        self.stdout.__iter__ = lambda self: iter(self._stdout_lines)

    def poll(self):
        return self._poll

    def terminate(self):
        self._poll = -15

    def kill(self):
        self._poll = -9

    def wait(self, timeout=None):
        return 0


class TestPiRpcManager:
    def test_init_creates_workspace(self, tmp_path):
        """PiRpcManager creates workspace directory on init."""
        workspace = tmp_path / "workspace"
        events = []
        mgr = PiRpcManager(workspace, lambda e: events.append(e))
        assert workspace.exists()

    def test_is_running_false_before_start(self, tmp_path):
        """is_running returns False before start()."""
        workspace = tmp_path / "workspace"
        events = []
        mgr = PiRpcManager(workspace, lambda e: events.append(e))
        assert mgr.is_running() is False

    @patch("openrecall.client.chat.pi_rpc.find_pi_executable")
    @patch("subprocess.Popen")
    def test_start_spawns_process(self, mock_popen, mock_find_pi, tmp_path):
        """start() spawns Pi process with correct arguments."""
        mock_find_pi.return_value = "/path/to/cli.js"
        mock_popen.return_value = MockProcess()

        workspace = tmp_path / "workspace"
        events = []
        mgr = PiRpcManager(workspace, lambda e: events.append(e))

        result = mgr.start("minimax-cn", "MiniMax-M2.7")
        assert result is True
        assert mgr.is_running() is True

        # Verify subprocess was called with correct args
        call_args = mock_popen.call_args
        assert "bun" in call_args[0][0]
        assert "--mode" in call_args[0][0]
        assert "rpc" in call_args[0][0]

    @patch("openrecall.client.chat.pi_rpc.find_pi_executable")
    @patch("subprocess.Popen")
    def test_stop_terminates_process(self, mock_popen, mock_find_pi, tmp_path):
        """stop() terminates the Pi process."""
        mock_find_pi.return_value = "/path/to/cli.js"
        mock_process = MockProcess()
        mock_popen.return_value = mock_process

        workspace = tmp_path / "workspace"
        events = []
        mgr = PiRpcManager(workspace, lambda e: events.append(e))

        mgr.start("minimax-cn", "MiniMax-M2.7")
        mgr.stop()

        assert mgr.is_running() is False

    @patch("openrecall.client.chat.pi_rpc.find_pi_executable")
    @patch("subprocess.Popen")
    def test_send_prompt_writes_to_stdin(self, mock_popen, mock_find_pi, tmp_path):
        """send_prompt() writes JSON command to stdin."""
        mock_find_pi.return_value = "/path/to/cli.js"
        mock_process = MockProcess()
        mock_popen.return_value = mock_process

        workspace = tmp_path / "workspace"
        events = []
        mgr = PiRpcManager(workspace, lambda e: events.append(e))
        mgr.start("minimax-cn", "MiniMax-M2.7")

        request_id = mgr.send_prompt("Hello, Pi!")
        assert request_id is not None

        # Verify stdin.write was called
        assert mock_process.stdin.write.called

    @patch("openrecall.client.chat.pi_rpc.find_pi_executable")
    @patch("subprocess.Popen")
    def test_new_session_sends_command(self, mock_popen, mock_find_pi, tmp_path):
        """new_session() sends new_session command to Pi."""
        mock_find_pi.return_value = "/path/to/cli.js"
        mock_process = MockProcess()
        mock_popen.return_value = mock_process

        workspace = tmp_path / "workspace"
        events = []
        mgr = PiRpcManager(workspace, lambda e: events.append(e))
        mgr.start("minimax-cn", "MiniMax-M2.7")

        mgr.new_session()
        # Verify stdin.write was called with new_session command
        write_calls = [str(c) for c in mock_process.stdin.write.call_args_list]
        assert any("new_session" in str(c) for c in write_calls)

    def test_find_pi_executable_none_raises(self, tmp_path):
        """start() raises if Pi executable not found."""
        workspace = tmp_path / "workspace"
        events = []
        mgr = PiRpcManager(workspace, lambda e: events.append(e))

        with patch("openrecall.client.chat.pi_rpc.find_pi_executable", return_value=None):
            with pytest.raises(RuntimeError, match="Pi executable not found"):
                mgr.start("minimax-cn", "MiniMax-M2.7")
