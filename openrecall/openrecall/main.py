"""OpenRecall main entry point.

Launch modes:
- Combined:     python -m openrecall.main    (starts both server and client)
- Server only:  python -m openrecall.server  (API + Web UI)
- Client only:  python -m openrecall.client  (screenshot capture + upload)

Architecture (Producer-Consumer):
- Producer (recorder): Captures screenshots → enqueues to LocalBuffer (disk)
- Consumer (uploader): Reads from buffer → uploads to server via HTTP
- Server (Flask): Receives uploads → OCR → AI analysis → embeddings → database
"""

import signal
import sys
from threading import Thread

from openrecall.shared.config import settings
from openrecall.shared.logging_config import configure_logging

logger = configure_logging("openrecall.main")

from openrecall.server.database import create_db
from openrecall.server.app import app
from openrecall.client.recorder import get_recorder


def preload_ai_models():
    """Preload AI models at startup to avoid first-request latency."""
    if not settings.preload_models:
        logger.info("Model preloading disabled")
        return
    
    logger.info("Preloading AI models (this may take a minute)...")
    
    try:
        from openrecall.server.ai_engine import get_ai_engine
        get_ai_engine()  # Load VL model
        logger.info("✅ AI Engine (VL model) loaded")
    except Exception as e:
        logger.warning(f"⚠️ Failed to preload AI Engine: {e}")
    
    try:
        from openrecall.server.nlp import get_nlp_engine
        get_nlp_engine()  # Load embedding model
        logger.info("✅ Embedding model loaded")
    except Exception as e:
        logger.warning(f"⚠️ Failed to preload Embedding model: {e}")
    
    logger.info("Model preloading complete")


def main():
    """Start OpenRecall with graceful shutdown support.
    
    Starts both server and client in the same process.
    For separate processes, use:
    - python -m openrecall.server
    - python -m openrecall.client
    """
    # Initialize database
    create_db()

    logger.info("=" * 50)
    logger.info("OpenRecall Starting (Combined Mode)")
    logger.info("=" * 50)
    logger.info(f"Debug mode: {'ON' if settings.debug else 'OFF'}")
    logger.info(f"Data folder: {settings.base_path}")
    logger.info(f"Screenshots: {settings.screenshots_path}")
    logger.info(f"Buffer path: {settings.buffer_path}")
    logger.info(f"Database: {settings.db_path}")
    logger.info(f"API URL: {settings.api_url}")
    logger.info(f"Web UI: http://localhost:{settings.port}")
    logger.info("=" * 50)

    # Preload AI models to avoid first-request timeout
    preload_ai_models()
    
    # Start background processing worker AFTER preloading models
    from openrecall.server.app import app, init_background_worker
    init_background_worker(app)

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
        app.run(
            port=settings.port, 
            debug=settings.debug,  # Enable Flask debug mode
            use_reloader=False
        )
    except KeyboardInterrupt:
        pass
    finally:
        recorder.stop()


if __name__ == "__main__":
    main()
