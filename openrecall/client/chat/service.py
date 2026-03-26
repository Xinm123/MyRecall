"""
Chat Service orchestrator.

Coordinates:
- Pi RPC Manager (subprocess communication)
- Conversation Manager (persistence)
- SSE streaming (event dispatch)
"""

import json
import os
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Optional

from .config_manager import get_default_provider, get_default_model
from .conversation import (
    create_conversation as _create_conversation,
    load_conversation,
    save_conversation,
    list_conversations,
    delete_conversation,
    add_message,
)
from .pi_rpc import PiRpcManager
from .types import Conversation, PiStatus


class ChatService:
    """
    Main orchestrator for Chat functionality.

    Responsibilities:
    - Coordinate Pi RPC Manager
    - Handle SSE streaming
    - Manage conversation persistence
    - Error handling and recovery
    - Auto-restart Pi on crash (exponential backoff)
    - Reject concurrent requests
    """

    # Auto-restart configuration
    _MAX_RETRIES = 3
    _INITIAL_BACKOFF = 1.0  # seconds

    def __init__(self, data_dir: Path):
        """
        Initialize Chat Service.

        Args:
            data_dir: Base directory for chats and workspace
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Pi RPC manager (lazy initialization)
        self._pi_manager: Optional[PiRpcManager] = None
        self._pi_lock = threading.Lock()

        # Event queues for streaming
        self._event_queues: dict[str, queue.Queue] = {}

        # Concurrent request protection
        self._active_request = False
        self._request_lock = threading.Lock()

    @property
    def chats_dir(self) -> Path:
        """Directory for conversation storage."""
        return self.data_dir / "chats"

    @property
    def workspace_dir(self) -> Path:
        """Pi workspace directory."""
        return self.data_dir / "chat-workspace"

    def _get_or_create_pi_manager(self) -> PiRpcManager:
        """Get or create Pi RPC manager."""
        with self._pi_lock:
            if self._pi_manager is None:
                self._pi_manager = PiRpcManager(
                    self.workspace_dir,
                    self._handle_pi_event,
                )
            return self._pi_manager

    def _handle_pi_event(self, event: dict) -> None:
        """Handle events from Pi stdout."""
        event_type = event.get("type")

        # Dispatch to active event queues
        for q in self._event_queues.values():
            try:
                q.put(event)
            except Exception:
                pass

    def ensure_pi_running(self) -> None:
        """Start Pi if not running."""
        mgr = self._get_or_create_pi_manager()
        if not mgr.is_running():
            provider = get_default_provider()
            model = get_default_model()
            mgr.start(provider, model)

    def create_conversation(self) -> Conversation:
        """Create a new conversation."""
        import openrecall.client.chat.conversation as conv_mod
        conv_mod.CHATS_DIR = self.chats_dir

        conv = _create_conversation()

        # Reset Pi session for new conversation
        if self._pi_manager and self._pi_manager.is_running():
            self._pi_manager.new_session()

        return conv

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Load a conversation by ID."""
        import openrecall.client.chat.conversation as conv_mod
        conv_mod.CHATS_DIR = self.chats_dir
        return load_conversation(conversation_id)

    def save_conversation(self, conversation: Conversation) -> None:
        """Save a conversation."""
        import openrecall.client.chat.conversation as conv_mod
        conv_mod.CHATS_DIR = self.chats_dir
        save_conversation(conversation)

    def list_conversations(self):
        """List all conversations."""
        import openrecall.client.chat.conversation as conv_mod
        conv_mod.CHATS_DIR = self.chats_dir
        return list_conversations()

    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation."""
        import openrecall.client.chat.conversation as conv_mod
        conv_mod.CHATS_DIR = self.chats_dir
        return delete_conversation(conversation_id)

    def switch_conversation(self, conversation_id: str) -> None:
        """Switch to a different conversation (resets Pi context)."""
        if self._pi_manager and self._pi_manager.is_running():
            self._pi_manager.new_session()

    def get_pi_status(self) -> PiStatus:
        """Get Pi process status."""
        mgr = self._get_or_create_pi_manager()
        if mgr.is_running():
            return PiStatus(
                running=True,
                pid=mgr.process.pid if mgr.process else None,
                session_id="chat",
            )
        return PiStatus(running=False)

    def stream_response(
        self,
        conversation_id: str,
        message: str,
        images: Optional[list[str]] = None,
    ):
        """
        Stream response via SSE events.

        This is a generator that yields Pi events as they arrive.

        Args:
            conversation_id: Conversation UUID
            message: User message text
            images: Optional list of base64 image strings

        Yields:
            dict: Pi event objects
        """
        import uuid

        # Reject concurrent requests
        with self._request_lock:
            if self._active_request:
                yield {"type": "error", "message": "Request already in progress", "code": "BUSY"}
                return
            self._active_request = True

        try:
            # Load or create conversation
            conv = self.get_conversation(conversation_id)
            if not conv:
                conv = self.create_conversation()

            # Ensure Pi is running (with auto-restart on failure)
            pi_mgr = self._ensure_pi_with_retry()

            # Save user message
            add_message(conv, role="user", content=message, tool_calls=None)
            self.save_conversation(conv)

        except Exception as setup_error:
            # Release request lock on setup failure
            with self._request_lock:
                self._active_request = False
            yield {"type": "error", "message": str(setup_error), "code": "PI_CRASH"}
            return

        # Create event queue for this request
        queue_id = str(uuid.uuid4())
        event_queue = queue.Queue()
        self._event_queues[queue_id] = event_queue

        try:
            # Send prompt to Pi
            pi_mgr.send_prompt(message, images)

            # Accumulate assistant response
            assistant_content = ""
            tool_calls = []

            # Yield events until agent_end
            KEEPALIVE_INTERVAL = 15  # seconds
            MAX_TIMEOUT = 300  # 5 minutes total timeout
            start_time = time.time()

            while True:
                # Check for max timeout
                if time.time() - start_time > MAX_TIMEOUT:
                    yield {"type": "error", "message": "Timeout", "code": "TIMEOUT"}
                    break

                try:
                    event = event_queue.get(timeout=KEEPALIVE_INTERVAL)
                except queue.Empty:
                    # Send keepalive event (SSE comment)
                    yield {"type": "keepalive"}
                    continue

                yield event

                # Accumulate response — only text deltas, skip thinking
                if event.get("type") == "message_update":
                    msg_evt = event.get("assistantMessageEvent", {})
                    if msg_evt.get("type") == "text_delta":
                        assistant_content += msg_evt.get("delta", "")

                elif event.get("type") == "tool_execution_start":
                    tool_calls.append({
                        "id": event.get("toolCallId", ""),
                        "name": event.get("toolName", ""),
                        "args": event.get("args", {}),
                        "status": "running",
                    })

                elif event.get("type") == "tool_execution_end":
                    tc_id = event.get("toolCallId")
                    for tc in tool_calls:
                        if tc["id"] == tc_id:
                            tc["status"] = "error" if event.get("isError") else "done"
                            tc["result"] = event.get("result", {})

                elif event.get("type") == "agent_end":
                    # Save assistant message
                    add_message(
                        conv,
                        role="assistant",
                        content=assistant_content,
                        tool_calls=tool_calls if tool_calls else None,
                    )
                    self.save_conversation(conv)
                    break

                elif event.get("type") == "error":
                    break

        finally:
            # Release request lock
            with self._request_lock:
                self._active_request = False
            # Clean up event queue
            self._event_queues.pop(queue_id, None)

    def _ensure_pi_with_retry(self) -> PiRpcManager:
        """Start Pi with exponential backoff retry on failure."""
        import time

        for attempt in range(self._MAX_RETRIES):
            try:
                self.ensure_pi_running()
                return self._pi_manager  # type: ignore[return-value]
            except Exception as e:
                if attempt == self._MAX_RETRIES - 1:
                    raise RuntimeError(f"Pi failed to start after {self._MAX_RETRIES} attempts: {e}")
                backoff = self._INITIAL_BACKOFF * (2 ** attempt)
                time.sleep(backoff)
        # satisfy type checker — unreachable
        return self._pi_manager  # type: ignore[return-value]

    def shutdown(self) -> None:
        """Shutdown the service and clean up resources."""
        with self._pi_lock:
            if self._pi_manager:
                self._pi_manager.stop()
                self._pi_manager = None
