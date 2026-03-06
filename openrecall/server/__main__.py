"""OpenRecall Server entry point.

Launch with: python -m openrecall.server
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


def _start_noop_mode():
    from openrecall.server.queue_driver import NoopQueueDriver

    driver = NoopQueueDriver()
    driver.start()
    return driver


def main():
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
    logger.info(f"Processing mode: {settings.processing_mode}")

    logger.info("=" * 50)

    processing_mode = settings.processing_mode.strip().lower()
    worker = None

    if processing_mode == "noop":
        worker = _start_noop_mode()
    else:
        preload_ai_models()
        from openrecall.server.app import init_background_worker

        init_background_worker(app)

    _shutting_down = False

    def shutdown_handler(signum, frame):
        nonlocal _shutting_down
        if _shutting_down:
            return
        _shutting_down = True

        logger.info("")
        logger.info("Received shutdown signal, stopping server...")

        try:
            if worker is not None:
                logger.info("Stopping queue driver...")
                worker.stop()
                logger.info("Queue driver stopped")
            elif hasattr(app, "worker") and app.worker:
                logger.info("Stopping background worker...")
                app.worker.stop()
                app.worker.join(timeout=5)
                logger.info("Background worker stopped")
        except Exception as e:
            logger.warning(f"Error stopping worker: {e}")

        logger.info("Server shutdown complete")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    atexit.register(
        lambda: worker.stop()
        if worker is not None
        else (app.worker.stop() if hasattr(app, "worker") and app.worker else None)
    )

    if processing_mode == "noop":
        logger.info("MRV3 processing_mode=noop")

    try:
        app.run(
            host=settings.host,
            port=settings.port,
            debug=settings.debug,
            use_reloader=False,
            threaded=True,
        )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
