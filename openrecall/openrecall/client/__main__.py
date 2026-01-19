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
    logger.info(f"Buffer path: {settings.buffer_path}")
    logger.info(f"Server API: {settings.api_url}")
    logger.info(f"Capture interval: {settings.capture_interval}s")
    logger.info(f"Upload timeout: {settings.upload_timeout}s")
    logger.info(f"Primary monitor only: {settings.primary_monitor_only}")
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
