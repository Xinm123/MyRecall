"""OpenRecall Server entry point.

Launch with: python -m openrecall.server [--config=/path/to/server.toml]
"""

import atexit
import argparse
import sqlite3
import signal
import sys
from pathlib import Path
from typing import Optional

from openrecall.shared.logging_config import configure_logging

logger = None  # Set in main() after settings are initialized

_description_worker = None  # module-level reference for shutdown
_embedding_worker = None  # module-level reference for shutdown


def _parse_args():
    parser = argparse.ArgumentParser(prog="openrecall-server")
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to TOML config file (default: ~/.myrecall/server.toml)",
    )
    return parser.parse_known_args()[0]


def _load_settings(config_path: Optional[str] = None):
    from openrecall.server.config_server import ServerSettings

    settings_obj = ServerSettings.from_toml(config_path)
    return settings_obj


_args = _parse_args()
settings = _load_settings(_args.config)

# Make new settings the global singleton for server modules
import openrecall.shared.config

openrecall.shared.config.settings = settings

from openrecall.server.app import app
from openrecall.server.database.migrations_runner import run_migrations


def ensure_v3_schema(
    db_path: Optional[Path] = None,
    migrations_dir: Optional[Path] = None,
) -> None:
    target_db_path = db_path or settings.db_path
    target_migrations_dir = migrations_dir or (
        Path(__file__).resolve().parent / "database" / "migrations"
    )
    with sqlite3.connect(str(target_db_path)) as conn:
        run_migrations(conn, target_migrations_dir)
    if logger is not None:
        logger.info(
            "v3 schema migrations ensured: db=%s migrations=%s",
            target_db_path,
            target_migrations_dir,
        )


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

        provider = settings.ai_provider.strip().lower()
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

        embedding_provider = settings.ai_provider.strip().lower()
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
    global _description_worker
    from openrecall.server.queue_driver import NoopQueueDriver

    driver = NoopQueueDriver()
    driver.start()

    if settings.description_enabled:
        from openrecall.server.database.frames_store import FramesStore
        from openrecall.server.description.worker import DescriptionWorker

        store = FramesStore()
        _description_worker = DescriptionWorker(store)
        _description_worker.start()
        logger.info("DescriptionWorker started (noop mode)")

    return driver


def _preload_ocr_model():
    """Preload OCR model for processing_mode='ocr'.

    Fail-fast: If RapidOCR initialization fails, exit immediately.
    Do NOT silently fall back to noop mode.

    Per specs/processing-mode-switch/spec.md:
    - Only load OCR (RapidOCR), no VL/Embedding models
    - Log error and call sys.exit(1) on failure
    """
    logger.info("Preloading OCR model (RapidOCR)...")

    try:
        from openrecall.server.ocr.rapid_backend import RapidOCRBackend

        # Initialize the singleton - this triggers model loading
        _ = RapidOCRBackend()
        logger.info("✅ OCR model loaded successfully")
    except Exception as e:
        logger.error("❌ Failed to load OCR model: %s", e)
        logger.error("Cannot start in OCR mode without OCR model. Exiting.")
        sys.exit(1)


def _start_ocr_mode():
    """Start the V3ProcessingWorker for OCR processing."""
    global _description_worker, _embedding_worker
    from openrecall.server.processing.v3_worker import V3ProcessingWorker

    worker = V3ProcessingWorker()
    worker.start()

    store = None  # Shared store for workers

    if settings.description_enabled:
        from openrecall.server.database.frames_store import FramesStore
        from openrecall.server.description.worker import DescriptionWorker

        store = FramesStore()
        _description_worker = DescriptionWorker(store)
        _description_worker.start()
        logger.info("DescriptionWorker started (ocr mode)")

    if settings.embedding_enabled:
        from openrecall.server.database.frames_store import FramesStore
        from openrecall.server.embedding.worker import EmbeddingWorker

        # Reuse store if already created by DescriptionWorker
        if store is None:
            store = FramesStore()
        _embedding_worker = EmbeddingWorker(store)
        _embedding_worker.start()
        logger.info("EmbeddingWorker started (ocr mode)")

    return worker


def main():
    global logger
    logger = configure_logging("openrecall.server")
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

    ensure_v3_schema()

    processing_mode = settings.processing_mode.strip().lower()
    worker = None

    if processing_mode == "noop":
        worker = _start_noop_mode()
    elif processing_mode == "ocr":
        _preload_ocr_model()
        worker = _start_ocr_mode()
        logger.info("MRV3 processing_mode=ocr")
    else:
        # Legacy mode: load all AI models
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
            else:
                app_worker = getattr(app, "worker", None)
                if app_worker is not None:
                    logger.info("Stopping background worker...")
                    app_worker.stop()
                    app_worker.join(timeout=5)
                    logger.info("Background worker stopped")
        except Exception as e:
            logger.warning(f"Error stopping worker: {e}")

        # Stop DescriptionWorker
        if _description_worker is not None:
            logger.info("Stopping DescriptionWorker...")
            _description_worker.stop()
            _description_worker.join(timeout=5)
            logger.info("DescriptionWorker stopped")
        else:
            app_desc_worker = getattr(app, "description_worker", None)
            if app_desc_worker is not None:
                logger.info("Stopping DescriptionWorker (legacy mode)...")
                app_desc_worker.stop()
                app_desc_worker.join(timeout=5)
                logger.info("DescriptionWorker stopped")

        # Stop EmbeddingWorker
        if _embedding_worker is not None:
            logger.info("Stopping EmbeddingWorker...")
            _embedding_worker.stop()
            _embedding_worker.join(timeout=5)
            logger.info("EmbeddingWorker stopped")

        logger.info("Server shutdown complete")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    def _cleanup_worker() -> None:
        if worker is not None:
            worker.stop()
        else:
            app_worker = getattr(app, "worker", None)
            if app_worker is not None:
                app_worker.stop()
        if _description_worker is not None:
            _description_worker.stop()
        else:
            app_desc_worker = getattr(app, "description_worker", None)
            if app_desc_worker is not None:
                app_desc_worker.stop()
        if _embedding_worker is not None:
            _embedding_worker.stop()

    atexit.register(_cleanup_worker)

    # Emit processing mode log (already emitted for 'ocr' mode above)
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
