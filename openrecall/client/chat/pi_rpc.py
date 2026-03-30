"""
Pi RPC Manager for Chat Service.

Manages Pi subprocess lifecycle and stdin/stdout JSON RPC communication.

Follows screenpipe's approach:
- RPC mode: long-running process with stdin/stdout JSON communication
- Single session: fixed session_id="chat"
- Auto-start: Pi starts on first message if not running
- Auto-restart: Pi restarts on crash or provider change
"""

import json
import logging
import os
import stat
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
        self._running_provider: Optional[str] = None
        self._running_model: Optional[str] = None

        # Create workspace
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

    def start(self, provider: str, model: str) -> bool:
        """
        Start Pi process in RPC mode.

        Args:
            provider: LLM provider name (e.g., "minimax-cn", "custom")
            model: Model ID (e.g., "MiniMax-M2.7", "auto")

        Returns:
            True if started successfully

        Raises:
            RuntimeError: If Pi executable not found
        """
        with self._lock:
            # Stop existing Pi if provider/model changed
            if self.is_running():
                if self._running_provider == provider and self._running_model == model:
                    return True
                logger.info(f"[PiRpc] provider/model changed ({self._running_provider}/{self._running_model} -> {provider}/{model}), restarting Pi")
                self._do_stop()

            pi_path = find_pi_executable()
            if not pi_path:
                raise RuntimeError("Pi executable not found. Run ensure_installed() first.")

            # For custom provider: write config file and switch to zai provider
            effective_provider = provider
            if provider == "custom":
                from .config_manager import get_chat_api_base, get_api_key
                api_base = get_chat_api_base()
                api_key = get_api_key("custom")
                logger.info(f"[PiRpc] custom provider: api_base={api_base!r}, api_key={'***' if api_key else 'EMPTY'}")
                if api_base:
                    config_path = Path.home() / ".pi" / "agent" / "myrecall-llm.json"
                    config_path.parent.mkdir(parents=True, exist_ok=True)
                    config_data = {"baseUrl": api_base}
                    if api_key:
                        config_data["apiKey"] = api_key
                    config_path.write_text(json.dumps(config_data, indent=2))
                    config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
                    logger.info(f"[PiRpc] wrote myrecall-llm.json: {config_data}")
                    # Use built-in zai provider (model config from registry, baseUrl from plugin)
                    effective_provider = "zai"
                    model = "glm-4.5-flash"
                    logger.info("[PiRpc] using --provider zai --model glm-4.5-flash (pi-agent native handles reasoning_content)")
                else:
                    logger.warning("[PiRpc] no api_base for custom, using custom provider")

            cmd = [
                "bun", "run", pi_path,
                "--mode", "rpc",
                "--provider", effective_provider,
                "--model", model,
                "--workspace", str(self.workspace_dir),
            ]

            if provider == "custom":
                ext_path = Path.home() / ".myrecall" / "pi-agent" / "myrecall-llm-extension.ts"
                logger.info(f"[PiRpc] extension: {ext_path} exists={ext_path.exists()}")
                if ext_path.exists():
                    cmd.extend(["-e", str(ext_path)])
                    logger.info(f"[PiRpc] cmd: {' '.join(cmd)}")

            env = os.environ.copy()
            self.process = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, cwd=str(self.workspace_dir),
                env=env, text=True, bufsize=1,
            )
            self.stdin = self.process.stdin
            self._running_provider = provider
            self._running_model = model

            self._stop_reading.clear()
            self._stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
            self._stdout_thread.start()
            threading.Thread(target=self._read_stderr, daemon=True).start()
            return self.is_running()

    def _do_stop(self) -> None:
        """Internal stop (must be called while holding _lock)."""
        self._stop_reading.set()
        try:
            if self.stdin:
                self.stdin.write(json.dumps({"type": "abort"}) + "\n")
                self.stdin.flush()
        except Exception:
            pass
        try:
            if self.process:
                self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if self.process:
                self.process.kill()
                self.process.wait()
        self.process = None
        self.stdin = None
        self._running_provider = None
        self._running_model = None

    def stop(self) -> None:
        """Stop Pi process gracefully."""
        with self._lock:
            if not self.process:
                return
            self._do_stop()

    def send_prompt(self, content: str, images: Optional[list[str]] = None) -> str:
        """Send a prompt to Pi."""
        if not self.stdin:
            raise RuntimeError("Pi not running")
        request_id = f"req-{uuid.uuid4().hex[:8]}"
        cmd: dict[str, object] = {"type": "prompt", "id": request_id, "message": content}
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
            for line in proc_stderr:
                if self._stop_reading.is_set():
                    break
                line = line.strip()
                if line:
                    logger.info(f"[Pi stderr] {line}")
        except Exception:
            logger.warning("Pi stderr reader error", exc_info=True)
