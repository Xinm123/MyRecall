"""OpenRecall Client entry point.

Launch with: python -m openrecall.client

The client handles:
- Screenshot capture (Producer)
- Local buffering when server is unavailable
- Uploading to server (Consumer)
"""

import signal
import sys
import time

from openrecall.shared.config import settings
from openrecall.shared.logging_config import configure_logging

logger = configure_logging("openrecall.client")

from openrecall.client.recorder import get_recorder


def main():
    """Start the OpenRecall client (recorder + uploader)."""
    logger.info("=" * 50)
    logger.info("OpenRecall Client Starting")
    logger.info("=" * 50)
    logger.info(f"Debug mode: {'ON' if settings.debug else 'OFF'}")
    logger.info(f"Buffer path: {settings.buffer_path}")
    logger.info(f"Client screenshots: {settings.client_screenshots_path} (enabled={settings.client_save_local_screenshots})")
    logger.info(f"Cache folder: {settings.cache_path}")
    logger.info(f"Server API: {settings.api_url}")
    logger.info(f"Capture interval: {settings.capture_interval}s")
    logger.info(f"Upload timeout: {settings.upload_timeout}s")
    logger.info(f"Primary monitor only: {settings.primary_monitor_only}")
    logger.info(
        "Video monitor IDs: %s",
        settings.video_monitor_id_list if settings.video_monitor_id_list else "auto",
    )
    logger.info(
        "Profile-change restart: %s | Pool max bytes: %s",
        settings.video_pipeline_restart_on_profile_change,
        settings.video_pool_max_bytes,
    )
    logger.info(
        "SCK retries: max=%s backoff=%ss perm_backoff=%ss auto_recover=%s",
        settings.sck_start_retry_max,
        settings.sck_retry_backoff_seconds,
        settings.sck_permission_backoff_seconds,
        settings.sck_auto_recover_from_legacy,
    )
    logger.info("=" * 50)

    # Get recorder (manages Producer + Consumer)
    recorder = get_recorder()
    
    # Flag to prevent duplicate signal handling
    _shutting_down = False

    def shutdown_handler(signum, frame):
        nonlocal _shutting_down
        if _shutting_down:
            return
        _shutting_down = True
        
        logger.info("")
        logger.info("Received shutdown signal, stopping client...")
        recorder.stop()
        logger.info("Client shutdown complete")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # Run the capture loop on main thread
    try:
        recorder.run_capture_loop()
    except KeyboardInterrupt:
        pass
    finally:
        recorder.stop()


if __name__ == "__main__":
    main()
