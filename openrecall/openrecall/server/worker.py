"""Background worker for processing screenshot tasks asynchronously."""

import datetime
import logging
import sqlite3
import threading
import time
import traceback
from pathlib import Path
from typing import Optional
from uuid import uuid4

import numpy as np

from openrecall.server.database import SQLStore
from openrecall.server.ai.base import AIProviderError
from openrecall.server.ai.factory import get_ai_provider, get_embedding_provider, get_ocr_provider
from openrecall.server.config_runtime import runtime_settings
from openrecall.shared.config import settings
from openrecall.shared.models import RecallEntry

# Phase 3 Imports
from openrecall.server.utils.keywords import KeywordExtractor
from openrecall.server.utils.fusion import build_fusion_text
from openrecall.server.schema import SemanticSnapshot, Context, Content
from openrecall.server.database.vector_store import VectorStore

logger = logging.getLogger(__name__)


class _FallbackVisionProvider:
    def analyze_image(self, image_path: str) -> dict:
        return {"caption": "", "scene": "", "action": ""}


class _FallbackOCRProvider:
    def extract_text(self, image_path: str) -> str:
        return ""


class _FallbackEmbeddingProvider:
    def embed_text(self, text: str) -> np.ndarray:
        return np.zeros(int(settings.embedding_dim), dtype=np.float32)


class ProcessingWorker(threading.Thread):
    """Background worker thread that processes PENDING screenshot tasks.
    
    Implements dynamic flow control:
    - LIFO mode (newest first) when queue size >= threshold
    - FIFO mode (oldest first) when queue size < threshold
    
    Thread-safe with isolated database connection.
    """
    
    def __init__(self):
        """Initialize the processing worker."""
        super().__init__(daemon=True, name="ProcessingWorker")
        self._stop_event = threading.Event()
        self.keyword_extractor = KeywordExtractor()
        logger.info("ProcessingWorker initialized")
    
    def stop(self):
        """Signal the worker to stop processing."""
        logger.info("Stop signal received")
        self._stop_event.set()
    
    def run(self):
        """Main processing loop. Runs until stopped."""
        logger.info("🚀 ProcessingWorker started")
        
        # Thread-isolated database connection
        conn = sqlite3.connect(str(settings.db_path))
        
        # Initialize Phase 3 Stores
        try:
            vector_store = VectorStore()
            sql_store = SQLStore()
        except Exception as e:
            logger.error(f"Failed to initialize stores: {e}")
            # We continue, but processing will likely fail or degrade
            vector_store = None
            sql_store = None
        
        # Get engine instances (lazy-loaded singletons)
        try:
            ai_provider = get_ai_provider()
        except Exception as e:
            logger.error(f"Failed to initialize vision provider: {e}")
            ai_provider = _FallbackVisionProvider()

        try:
            ocr_provider = get_ocr_provider()
        except Exception as e:
            logger.error(f"Failed to initialize OCR provider: {e}")
            ocr_provider = _FallbackOCRProvider()

        try:
            embedding_provider = get_embedding_provider()
        except Exception as e:
            logger.error(f"Failed to initialize embedding provider: {e}")
            embedding_provider = _FallbackEmbeddingProvider()
        logger.info(
            "🤖 AI Engine initialized: "
            f"vision={settings.vision_provider or settings.ai_provider}, "
            f"ocr={settings.ocr_provider or settings.ai_provider}, "
            f"embedding={settings.embedding_provider or settings.ai_provider}, "
            f"rerank={settings.reranker_mode}({settings.reranker_model})"
        )
        
        try:
            while not self._stop_event.is_set():
                try:
                    # Phase 8.2: Check if AI processing is enabled
                    if not runtime_settings.ai_processing_enabled:
                        if self._stop_event.wait(0.1):
                            continue
                        runtime_settings.wait_for_change(0.4)
                        continue
                    
                    # Check queue size and determine processing order
                    pending_count = sql_store.get_pending_count(conn) if sql_store else 0
                    
                    if pending_count == 0:
                        if self._stop_event.wait(0.1):
                            continue
                        runtime_settings.wait_for_change(0.4)
                        continue
                    
                    # Determine LIFO vs FIFO mode
                    lifo_mode = pending_count >= settings.processing_lifo_threshold
                    mode_str = "LIFO (newest first)" if lifo_mode else "FIFO (oldest first)"
                    
                    # Get next task
                    task = sql_store.get_next_task(conn, lifo_mode=lifo_mode) if sql_store else None
                    
                    if task is None:
                        # Race condition: task was taken by another process
                        if self._stop_event.wait(0.05):
                            continue
                        runtime_settings.wait_for_change(0.05)
                        continue
                    
                    # Log processing start
                    if settings.debug:
                        logger.info(
                            f"📥 Processing task #{task.id} (timestamp={task.timestamp}) "
                            f"[Queue: {pending_count}, Mode: {mode_str}]"
                        )
                    
                    # Mark as PROCESSING
                    if not (sql_store and sql_store.mark_task_processing(conn, task.id)):
                        self._stop_event.wait(0.1)
                        continue
                    
                    # Execute processing pipeline
                    with runtime_settings._lock:
                        ai_processing_version = runtime_settings.ai_processing_version
                    self._process_task(
                        conn,
                        task,
                        ai_provider,
                        ocr_provider,
                        embedding_provider,
                        vector_store,
                        sql_store,
                        ai_processing_version,
                    )
                    
                except Exception as e:
                    logger.error(f"Error in worker loop: {e}")
                    logger.error(traceback.format_exc())
                    # Continue processing other tasks
                    self._stop_event.wait(0.5)
        
        finally:
            # Cleanup
            conn.close()
            logger.info("ProcessingWorker stopped and connection closed")
    
    def _process_task(
        self,
        conn: sqlite3.Connection,
        task: RecallEntry,
        ai_provider,
        ocr_provider,
        embedding_provider,
        vector_store,
        sql_store,
        ai_processing_version: int
    ):
        """Process a single task through the OCR → AI → NLP pipeline (Phase 3)."""
        try:
            def should_cancel() -> bool:
                with runtime_settings._lock:
                    return (
                        (not runtime_settings.ai_processing_enabled)
                        or runtime_settings.ai_processing_version != ai_processing_version
                    )

            if should_cancel():
                if sql_store:
                    sql_store.mark_task_cancelled_if_processing(conn, task.id)
                return

            # Reconstruct image path from timestamp
            image_path = settings.screenshots_path / f"{task.timestamp}.png"
            
            if not image_path.exists():
                logger.error(f"❌ Task #{task.id}: Image not found at {image_path}")
                if sql_store:
                    sql_store.mark_task_failed(conn, task.id)
                return
            
            # Step 1: OCR text extraction
            if should_cancel():
                if sql_store:
                    sql_store.mark_task_cancelled_if_processing(conn, task.id)
                return
            try:
                text = ocr_provider.extract_text(str(image_path))
            except AIProviderError as e:
                logger.warning(f"⚠️ Task #{task.id}: OCR provider failed: {e}")
                text = ""
            except Exception as e:
                logger.warning(f"⚠️ Task #{task.id}: OCR provider unexpected error: {e}")
                text = ""
            if settings.debug:
                logger.debug(f"  OCR: {len(text)} chars extracted")
                if len(text) > 0:
                    # Log first 100 chars of extracted text for debugging
                    preview_text = text[:100].replace('\n', ' ')
                    logger.debug(f"  OCR Preview: {preview_text}...")
            
            # Step 2: AI image analysis (Phase 3: Returns JSON dict)
            if should_cancel():
                if sql_store:
                    sql_store.mark_task_cancelled_if_processing(conn, task.id)
                return
            try:
                vision_data = ai_provider.analyze_image(str(image_path))
                if not isinstance(vision_data, dict):
                    vision_data = {"caption": str(vision_data), "scene": "", "action": ""}
            except AIProviderError as e:
                logger.warning(f"⚠️ Task #{task.id}: AI provider failed: {e}")
                vision_data = {"caption": "", "scene": "", "action": ""}
            except Exception as e:
                logger.warning(f"⚠️ Task #{task.id}: AI provider unexpected error: {e}")
                vision_data = {"caption": "", "scene": "", "action": ""}
            
            caption = vision_data.get("caption", "") or ""
            scene = vision_data.get("scene", "") or ""
            action = vision_data.get("action", "") or ""

            if settings.debug:
                logger.debug(f"  AI: {len(caption)} chars description. Tags: {scene}, {action}")
            
            # Step 3: Keyword Extraction
            keywords = self.keyword_extractor.extract(text)

            # Step 4: Construct SemanticSnapshot
            dt = datetime.datetime.fromtimestamp(task.timestamp)
            time_bucket = dt.strftime("%Y-%m-%d-%H")
            
            snapshot = SemanticSnapshot(
                id=str(uuid4()),
                image_path=str(image_path),
                context=Context(
                    app_name=task.app or "Unknown",
                    window_title=task.title or "Unknown",
                    timestamp=task.timestamp,
                    time_bucket=time_bucket
                ),
                content=Content(
                    ocr_text=text,
                    ocr_head=text[:300],
                    caption=caption,
                    keywords=keywords,
                    scene_tag=scene,
                    action_tag=action
                ),
                embedding_vector=[0.0] * settings.embedding_dim # Placeholder
            )

            # Step 5: Structured Fusion
            fusion_text = build_fusion_text(snapshot)
            
            if settings.debug:
                logger.debug("="*80)
                logger.debug(f"  🔗 Fusion Text:\n{fusion_text}")
                logger.debug("="*80)

            # Fusion Text Logging (Debug Feature)
            if settings.fusion_log_enabled:
                try:
                    log_dir = Path("logs")
                    log_dir.mkdir(exist_ok=True)
                    log_file = log_dir / "fusion_debug.log"
                    with open(log_file, "a", encoding="utf-8") as f:
                        f.write(f"\n--- Task #{task.id} [{datetime.datetime.now()}] ---\n")
                        f.write("--- Full OCR Text ---\n")
                        f.write(text)
                        f.write("\n--- Fusion Text ---\n")
                        f.write(fusion_text)
                        f.write("\n" + "="*50 + "\n")
                except Exception as e:
                    logger.warning(f"Failed to write fusion log: {e}")
            
            # Step 6: Generate Embedding
            if should_cancel():
                if sql_store:
                    sql_store.mark_task_cancelled_if_processing(conn, task.id)
                return
            try:
                embedding = embedding_provider.embed_text(fusion_text)
                # Convert to list for Pydantic serialization (silences warning)
                if hasattr(embedding, 'tolist'):
                    snapshot.embedding_vector = embedding.tolist()
                else:
                    snapshot.embedding_vector = embedding
            except AIProviderError as e:
                logger.warning(f"⚠️ Task #{task.id}: Embedding provider failed: {e}")
                embedding = np.zeros(int(settings.embedding_dim), dtype=np.float32)
                snapshot.embedding_vector = embedding.tolist()
            except Exception as e:
                logger.warning(f"⚠️ Task #{task.id}: Embedding provider unexpected error: {e}")
                embedding = np.zeros(int(settings.embedding_dim), dtype=np.float32)
                snapshot.embedding_vector = embedding.tolist()
            
            if settings.debug:
                logger.debug(f"  NLP: Embedding shape {embedding.shape}")
            
            # Step 7: Save to Stores
            if should_cancel():
                if sql_store:
                    sql_store.mark_task_cancelled_if_processing(conn, task.id)
                return
            
            if vector_store:
                try:
                    vector_store.add_snapshot(snapshot)
                except Exception as e:
                    logger.error(f"Failed to save to LanceDB: {e}")
            
            if sql_store:
                try:
                    sql_store.add_document(snapshot.id, text, caption, keywords)
                except Exception as e:
                    logger.error(f"Failed to save to FTS: {e}")

            # Mark as completed in Legacy DB
            # We map 'description' to 'caption' for legacy compatibility
            success = False
            if sql_store:
                success = sql_store.mark_task_completed(
                    conn,
                    task.id,
                    text,
                    caption,
                    embedding
                )
            
            if success:
                if settings.debug:
                    logger.info(f"✅ Task #{task.id} completed successfully (Phase 3 Pipeline)")
            else:
                if should_cancel():
                    if sql_store:
                        sql_store.mark_task_cancelled_if_processing(conn, task.id)
                    return
                logger.error(f"⚠️ Task #{task.id}: Failed to update database")
        
        except Exception as e:
            logger.error(f"❌ Task #{task.id} failed: {e}")
            logger.error(traceback.format_exc())
            if sql_store:
                sql_store.mark_task_failed(conn, task.id)
