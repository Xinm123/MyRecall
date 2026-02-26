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

from openrecall.server.app import app


def preload_ai_models():
    """Preload AI models at startup to avoid first-request latency."""
    if not settings.preload_models:
        logger.info("Model preloading disabled")
        return

    logger.info("Preloading AI models (this may take a minute)...")
    all_loaded = True

    # 1. Vision/Language Model
    try:
        from openrecall.server.ai.factory import get_ai_provider

        provider = (settings.vision_provider or settings.ai_provider).strip().lower()
        if provider == "local":
            get_ai_provider("vision")
            logger.info("✅ VL Model loaded successfully")
        else:
            logger.info(f"⏭️  Skip VL model (provider={provider})")
    except Exception as e:
        logger.error(f"❌ Failed to load VL model: {e}")
        all_loaded = False

    # 2. Embedding Model
    try:
        from openrecall.server.ai.factory import get_embedding_provider

        embedding_provider = (
            (settings.embedding_provider or settings.ai_provider).strip().lower()
        )
        if embedding_provider == "local":
            get_embedding_provider()
            logger.info("✅ Embedding model loaded successfully")
        else:
            logger.info(f"⏭️  Skip embedding model (provider={embedding_provider})")
    except Exception as e:
        logger.error(f"❌ Failed to load embedding model: {e}")
        all_loaded = False

    # 3. OCR Model (RapidOCR)
    try:
        ocr_provider = (settings.ocr_provider or settings.ai_provider).strip().lower()
        if ocr_provider == "rapidocr" and settings.ocr_rapid_use_local:
            # Initialize OCR to trigger model loading
            from openrecall.server.ocr.rapid_backend import RapidOCRBackend

            _ = RapidOCRBackend()
            logger.info("✅ OCR model loaded successfully")
        elif ocr_provider == "rapidocr":
            logger.info("⏭️  Skip OCR model (using auto-download)")
        else:
            logger.info(f"⏭️  Skip OCR model (provider={ocr_provider})")
    except Exception as e:
        logger.error(f"❌ Failed to load OCR model: {e}")
        all_loaded = False

    if all_loaded:
        logger.info("🎉 All AI models loaded successfully!")
    else:
        logger.warning("⚠️ Some models failed to load. Check logs above.")


def main():
    """Start the OpenRecall server."""
    # Database initialized on app import

    logger.info("=" * 50)
    logger.info("OpenRecall Server Starting")
    logger.info("=" * 50)
    logger.info(f"Debug mode: {'ON' if settings.debug else 'OFF'}")
    logger.info(f"Data folder: {settings.base_path}")
    logger.info(f"Cache folder: {settings.cache_path}")
    logger.info(f"Screenshots: {settings.screenshots_path}")
    logger.info(f"Database: {settings.db_path}")
    logger.info(f"Bind: {settings.host}:{settings.port}")
    logger.info(f"API URL: http://{settings.host}:{settings.port}/api")
    logger.info(f"Web UI: http://{settings.host}:{settings.port}")
    logger.info(f"Device: {settings.device}")
    logger.info(f"Processing: LIFO threshold = {settings.processing_lifo_threshold}")

    # Log OCR Provider Info
    ocr_provider = (settings.ocr_provider or settings.ai_provider).strip().lower()
    logger.info(f"OCR Provider: {ocr_provider}")
    if ocr_provider == "rapidocr":
        use_local = settings.ocr_rapid_use_local
        use_gpu = settings.ocr_rapid_use_gpu
        logger.info(f"  - Mode: {'Local Models' if use_local else 'Auto-Download'}")
        logger.info(f"  - GPU: {'Enabled' if use_gpu else 'Disabled (CPU)'}")
        if use_local:
            logger.info(f"  - Model Dir: {settings.ocr_rapid_model_dir}")

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
            if hasattr(app, "worker") and app.worker:
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
    atexit.register(
        lambda: app.worker.stop() if hasattr(app, "worker") and app.worker else None
    )

    # Start the Flask server
    try:
        app.run(
            host=settings.host,
            port=settings.port,
            debug=settings.debug,  # Enable Flask debug mode based on config
            use_reloader=False,
            threaded=True,
        )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
