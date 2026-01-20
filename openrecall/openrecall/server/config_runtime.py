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
        
        self.ui_show_ai: bool = True
        """Whether AI results are shown in the UI."""
        
        # Client state tracking
        self.last_heartbeat: float = time.time()
        """Unix timestamp of last client heartbeat."""
        
        # Thread safety
        self._lock = threading.RLock()
    
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
                "ui_show_ai": self.ui_show_ai,
                "last_heartbeat": self.last_heartbeat,
            }


# Module-level singleton instance
runtime_settings = RuntimeSettings()
