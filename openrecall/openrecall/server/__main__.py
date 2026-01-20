"""OpenRecall Server entry point.

Launch with: python -m openrecall.server

The server handles:
- REST API for screenshot uploads
- OCR processing
- AI-powered image analysis (Qwen3-VL)
- Embedding generation (Qwen3-Embedding)
- Database storage and semantic search
- Background task processing worker
"""

import atexit
import signal
import sys

from openrecall.shared.config import settings
from openrecall.shared.logging_config import configure_logging

logger = configure_logging("openrecall.server")

from openrecall.server.database import create_db
from openrecall.server.app import app


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
    """Start the OpenRecall server."""
    # Initialize database
    create_db()

    logger.info("=" * 50)
    logger.info("OpenRecall Server Starting")
    logger.info("=" * 50)
    logger.info(f"Debug mode: {'ON' if settings.debug else 'OFF'}")
    logger.info(f"Data folder: {settings.base_path}")
    logger.info(f"Screenshots: {settings.screenshots_path}")
    logger.info(f"Database: {settings.db_path}")
    logger.info(f"API URL: http://localhost:{settings.port}/api")
    logger.info(f"Web UI: http://localhost:{settings.port}")
    logger.info(f"Device: {settings.device}")
    logger.info(f"Processing: LIFO threshold = {settings.processing_lifo_threshold}")
    logger.info("=" * 50)

    # Preload AI models to avoid first-request timeout
    preload_ai_models()
    
    # Start background processing worker AFTER preloading models
    from openrecall.server.app import init_background_worker
    init_background_worker(app)

    # Flag to prevent duplicate signal handling
    _shutting_down = False

    def shutdown_handler(signum, frame):
        nonlocal _shutting_down
        if _shutting_down:
            return
        _shutting_down = True
        
        logger.info("")
        logger.info("Received shutdown signal, stopping server...")
        
        # Stop worker gracefully if it was initialized
        try:
            if hasattr(app, 'worker') and app.worker:
                logger.info("Stopping background worker...")
                app.worker.stop()
                app.worker.join(timeout=5)
                logger.info("Background worker stopped")
        except Exception as e:
            logger.warning(f"Error stopping worker: {e}")
        
        logger.info("Server shutdown complete")
        sys.exit(0)
    
    # Register shutdown handlers
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    atexit.register(lambda: app.worker.stop() if hasattr(app, 'worker') and app.worker else None)

    # Start the Flask server
    try:
        app.run(
            port=settings.port, 
            debug=settings.debug,  # Enable Flask debug mode based on config
            use_reloader=False, 
            threaded=True
        )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
