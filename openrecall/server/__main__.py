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
import tempfile
from pathlib import Path

from openrecall.shared.config import settings
from openrecall.shared.logging_config import configure_logging

logger = configure_logging("openrecall.server")

from openrecall.server.app import app


def _warmup_ocr_provider(provider) -> None:
    """Warm up OCR provider using a tiny local image."""
    from PIL import Image

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        warmup_path = Path(tmp.name)
    try:
        Image.new("RGB", (2, 2), color="white").save(warmup_path, format="PNG")
        provider.extract_text(str(warmup_path))
    finally:
        warmup_path.unlink(missing_ok=True)


def preload_ai_models():
    """Preload AI models at startup to avoid first-request latency."""
    if not settings.preload_models:
        logger.info("Model preloading disabled")
        return
    
    logger.info("Preloading AI models (this may take a minute)...")
    
    try:
        from openrecall.server.ai.factory import get_ai_provider

        provider = (settings.vision_provider or settings.ai_provider).strip().lower()
        if provider == "local":
            get_ai_provider("vision")
            logger.info("✅ AI Engine (VL model) loaded")
        else:
            logger.info(f"Skipping VL model preload (provider={provider})")
    except Exception as e:
        logger.warning(f"⚠️ Failed to preload AI Engine: {e}")
    
    try:
        from openrecall.server.ai.factory import get_embedding_provider

        embedding_provider = (settings.embedding_provider or settings.ai_provider).strip().lower()
        if embedding_provider == "local":
            get_embedding_provider()
            logger.info("✅ Embedding model loaded")
        else:
            logger.info(f"Skipping embedding model preload (provider={embedding_provider})")
    except Exception as e:
        logger.warning(f"⚠️ Failed to preload Embedding model: {e}")

    try:
        from openrecall.server.ai.factory import get_ocr_provider

        ocr_provider_name = (settings.ocr_provider or settings.ai_provider).strip().lower()
        if ocr_provider_name in {"local", "rapidocr", "doctr"}:
            ocr_provider = get_ocr_provider()
            _warmup_ocr_provider(ocr_provider)
            logger.info("✅ OCR model warmed up (provider=%s)", ocr_provider_name)
        else:
            logger.info(f"Skipping OCR model preload (provider={ocr_provider_name})")
    except Exception as e:
        logger.warning(f"⚠️ Failed to preload OCR model: {e}")
    
    logger.info("Model preloading complete")


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
        logger.info(f"  - Mode: {'Local Models' if use_local else 'Auto-Download'}")
        if use_local:
            logger.info(f"  - Model Dir: {settings.ocr_rapid_model_dir}")
            
    logger.info("=" * 50)

    # Preload AI models to avoid first-request timeout
    preload_ai_models()
    
    # Start workers AFTER preloading models
    from openrecall.server.app import init_background_worker, init_video_worker
    init_background_worker(app)
    init_video_worker(app)

    # Flag to prevent duplicate signal handling
    _shutting_down = False

    def shutdown_handler(signum, frame):
        nonlocal _shutting_down
        if _shutting_down:
            return
        _shutting_down = True
        
        logger.info("")
        logger.info("Received shutdown signal, stopping server...")
        
        # Stop workers gracefully if they were initialized
        try:
            workers = [
                ("background worker", "worker"),
                ("video worker", "video_worker"),
            ]
            for label, attr in workers:
                worker = getattr(app, attr, None)
                if worker:
                    logger.info(f"Stopping {label}...")
                    worker.stop()
                    worker.join(timeout=5)
                    logger.info(f"{label.capitalize()} stopped")
        except Exception as e:
            logger.warning(f"Error stopping workers: {e}")
        
        logger.info("Server shutdown complete")
        sys.exit(0)
    
    # Register shutdown handlers
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    def _shutdown_workers_on_exit():
        for attr in ("worker", "video_worker"):
            worker = getattr(app, attr, None)
            if worker:
                try:
                    worker.stop()
                except Exception:
                    pass

    atexit.register(_shutdown_workers_on_exit)

    # Start the Flask server
    try:
        app.run(
            host=settings.host,
            port=settings.port, 
            debug=settings.debug,  # Enable Flask debug mode based on config
            use_reloader=False, 
            threaded=True
        )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
