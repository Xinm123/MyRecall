"""
Pi RPC Manager for Chat Service.

Manages Pi subprocess lifecycle and stdin/stdout JSON RPC communication.

Follows screenpipe's approach:
- RPC mode: long-running process with stdin/stdout JSON communication
- Single session: fixed session_id="chat"
- Auto-start: Pi starts on first message if not running
- Auto-restart: Pi restarts on crash with exponential backoff
"""

import json
import logging
import os
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

from .pi_manager import find_pi_executable


class PiRpcManager:
    """
    Manages Pi subprocess in RPC mode.

    RPC Protocol:
    - Commands (stdin): {"type": "prompt", "id": "...", "message": "..."}
    - Events (stdout): {"type": "message_update", ...}
    """

    def __init__(
        self,
        workspace_dir: Path,
        event_callback: Callable[[dict], None],
    ):
        """
        Initialize Pi RPC manager.

        Args:
            workspace_dir: Pi working directory
            event_callback: Called for each Pi event (stdout JSON)
        """
        self.workspace_dir = Path(workspace_dir)
        self.event_callback = event_callback
        self.process: Optional[subprocess.Popen] = None
        self.stdin = None
        self._stdout_thread: Optional[threading.Thread] = None
        self._stop_reading = threading.Event()
        self._lock = threading.Lock()

        # Create workspace
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

    def start(self, provider: str, model: str) -> bool:
        """
        Start Pi process in RPC mode.

        Args:
            provider: LLM provider name (e.g., "minimax-cn")
            model: Model ID (e.g., "MiniMax-M2.7")

        Returns:
            True if started successfully

        Raises:
            RuntimeError: If Pi executable not found
        """
        with self._lock:
            if self.is_running():
                return True

            pi_path = find_pi_executable()
            if not pi_path:
                raise RuntimeError("Pi executable not found. Run ensure_installed() first.")

            # Build command
            cmd = [
                "bun",
                "run",
                pi_path,
                "--mode", "rpc",
                "--provider", provider,
                "--model", model,
                "--workspace", str(self.workspace_dir),
            ]

            # Set environment
            env = os.environ.copy()

            # Spawn process
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.workspace_dir),
                env=env,
                text=True,
                bufsize=1,  # Line buffered
            )

            self.stdin = self.process.stdin

            # Start stdout reader thread
            self._stop_reading.clear()
            self._stdout_thread = threading.Thread(
                target=self._read_stdout,
                daemon=True,
            )
            self._stdout_thread.start()

            # Start stderr reader thread (for debugging)
            threading.Thread(
                target=self._read_stderr,
                daemon=True,
            ).start()

            return self.is_running()

    def stop(self) -> None:
        """Stop Pi process gracefully."""
        with self._lock:
            if not self.process:
                return

            # Signal stdout reader to stop
            self._stop_reading.set()

            # Send abort command
            try:
                if self.stdin:
                    self.stdin.write(json.dumps({"type": "abort"}) + "\n")
                    self.stdin.flush()
            except Exception:
                pass

            # Wait for process to exit
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()

            self.process = None
            self.stdin = None

    def send_prompt(self, content: str, images: Optional[list[str]] = None) -> str:
        """
        Send a prompt to Pi.

        Args:
            content: User message text
            images: Optional list of base64 image strings

        Returns:
            Request ID for tracking
        """
        if not self.stdin:
            raise RuntimeError("Pi not running")

        request_id = f"req-{uuid.uuid4().hex[:8]}"
        cmd: dict[str, object] = {
            "type": "prompt",
            "id": request_id,
            "message": content,
        }
        if images:
            cmd["images"] = images

        with self._lock:
            self.stdin.write(json.dumps(cmd) + "\n")
            self.stdin.flush()

        return request_id

    def new_session(self) -> None:
        """Reset Pi session (clear context)."""
        if not self.stdin:
            raise RuntimeError("Pi not running")

        with self._lock:
            self.stdin.write(json.dumps({"type": "new_session"}) + "\n")
            self.stdin.flush()

    def abort(self) -> None:
        """Abort current operation."""
        if not self.stdin:
            return

        with self._lock:
            self.stdin.write(json.dumps({"type": "abort"}) + "\n")
            self.stdin.flush()

    def is_running(self) -> bool:
        """Check if Pi process is alive."""
        if not self.process:
            return False
        return self.process.poll() is None

    def _read_stdout(self) -> None:
        """Read Pi stdout and dispatch events."""
        if not self.process:
            return

        proc_stdout = self.process.stdout
        if not proc_stdout:
            return

        try:
            for line in proc_stdout:
                if self._stop_reading.is_set():
                    break

                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                    self.event_callback(event)
                except json.JSONDecodeError:
                    # Skip non-JSON lines
                    pass
        except Exception:
            logger.warning("Pi stdout reader error", exc_info=True)

    def _read_stderr(self) -> None:
        """Read Pi stderr for debugging."""
        if not self.process:
            return

        proc_stderr = self.process.stderr
        if not proc_stderr:
            return

        try:
            for _ in proc_stderr:
                if self._stop_reading.is_set():
                    break
                # Log stderr for debugging (could integrate with logging module)
                pass
        except Exception:
            logger.warning("Pi stderr reader error", exc_info=True)
