"""Runtime settings singleton for OpenRecall server.

Manages runtime configuration state with thread-safe access.
Tracks feature toggles and client heartbeat status.
"""

import time
import threading


class RuntimeSettings:
    """Thread-safe singleton for runtime configuration.
    
    Manages feature toggles and client state:
    - Recording enable/disable
    - Upload enable/disable
    - AI processing enable/disable
    - UI AI visibility
    - Client heartbeat tracking
    """
    
    def __init__(self):
        """Initialize runtime settings with defaults."""
        # Feature toggles
        self.recording_enabled: bool = True
        """Whether the client recorder is active."""
        
        self.upload_enabled: bool = True
        """Whether uploads from client to server are enabled."""
        
        self.ai_processing_enabled: bool = True
        """Whether AI processing pipeline is active."""

        self.ai_processing_version: int = 0
        """Monotonic version for AI processing toggle; used to cancel in-flight tasks."""
        
        self.ui_show_ai: bool = True
        """Whether AI results are shown in the UI."""
        
        # Client state tracking
        self.last_heartbeat: float = time.time()
        """Unix timestamp of last client heartbeat."""

        self.capture_mode: str = "unknown"
        """Client-reported capture mode: monitor_id|legacy|paused|unknown."""

        self.sck_available: bool = False
        """Whether client currently reports SCK availability."""

        self.sck_last_error_code: str = ""
        """Last structured SCK error code reported by client."""

        self.sck_last_error_at: float = 0.0
        """Unix timestamp when the last structured SCK error happened."""

        self.selected_monitors: list[str] = []
        """List of monitor IDs selected by the active capture mode."""
        
        # Thread safety
        self._lock = threading.RLock()
        self._change_event = threading.Event()
    
    def to_dict(self) -> dict:
        """Convert all settings to dictionary.
        
        Returns:
            Dictionary with all runtime settings fields.
        """
        with self._lock:
            return {
                "recording_enabled": self.recording_enabled,
                "upload_enabled": self.upload_enabled,
                "ai_processing_enabled": self.ai_processing_enabled,
                "ai_processing_version": self.ai_processing_version,
                "ui_show_ai": self.ui_show_ai,
                "last_heartbeat": self.last_heartbeat,
                "capture_mode": self.capture_mode,
                "sck_available": self.sck_available,
                "sck_last_error_code": self.sck_last_error_code,
                "sck_last_error_at": self.sck_last_error_at,
                "selected_monitors": list(self.selected_monitors),
            }

    def notify_change(self) -> None:
        self._change_event.set()

    def wait_for_change(self, timeout: float) -> None:
        self._change_event.wait(timeout)
        self._change_event.clear()


# Module-level singleton instance
runtime_settings = RuntimeSettings()
