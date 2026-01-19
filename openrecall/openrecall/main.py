"""OpenRecall main entry point.

Launch with: python -m openrecall.main

Architecture (Producer-Consumer):
- Producer (recorder): Captures screenshots → enqueues to LocalBuffer (disk)
- Consumer (uploader): Reads from buffer → uploads to server via HTTP
- Server (Flask): Receives uploads → OCR → embeddings → database
"""

import logging
import signal
import sys
from threading import Thread

from openrecall.shared.config import settings

# Configure logging based on debug setting
log_level = logging.DEBUG if settings.debug else logging.INFO
logging.basicConfig(
    level=log_level,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)

# Suppress noisy third-party loggers (even in debug mode)
noisy_loggers = [
    "PIL",
    "h5py",
    "urllib3",
    "matplotlib",
    "fontTools",
]
for name in noisy_loggers:
    logging.getLogger(name).setLevel(logging.WARNING)

# In non-debug mode, also suppress these
if not settings.debug:
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
from openrecall.server.database import create_db
from openrecall.server.app import app
from openrecall.client.recorder import get_recorder


def main():
    """Start OpenRecall with graceful shutdown support.
    
    Uses Producer-Consumer pattern for resilient screenshot handling.
    """
    # Initialize database
    create_db()

    logger.info("=" * 50)
    logger.info("OpenRecall Starting")
    logger.info("=" * 50)
    logger.info(f"Data folder: {settings.base_path}")
    logger.info(f"Screenshots: {settings.screenshots_path}")
    logger.info(f"Buffer path: {settings.buffer_path}")
    logger.info(f"Database: {settings.db_path}")
    logger.info(f"API URL: {settings.api_url}")
    logger.info(f"Web UI: http://localhost:{settings.port}")
    logger.info("=" * 50)

    # Get recorder (manages Producer + Consumer)
    recorder = get_recorder()
    
    # Flag to prevent duplicate signal handling
    _shutting_down = False
    
    # Signal handler for graceful shutdown
    def shutdown_handler(signum, frame):
        nonlocal _shutting_down
        if _shutting_down:
            return  # Ignore duplicate signals
        _shutting_down = True
        
        logger.info("")
        logger.info("Received shutdown signal, stopping...")
        recorder.stop()
        logger.info("Shutdown complete")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # Start the recorder thread (Producer + Consumer manager)
    recorder_thread = Thread(target=recorder.run_capture_loop, daemon=True)
    recorder_thread.start()

    # Start the Flask server on main thread
    try:
        app.run(port=settings.port, use_reloader=False)
    except KeyboardInterrupt:
        pass
    finally:
        recorder.stop()


if __name__ == "__main__":
    main()
