"""Background worker for processing screenshot tasks asynchronously."""

import logging
import sqlite3
import threading
import time
import traceback
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from openrecall.server import database as db
from openrecall.server.nlp import get_nlp_engine
from openrecall.server.ocr import extract_text_from_image
from openrecall.server.ai_engine import get_ai_engine
from openrecall.server.config_runtime import runtime_settings
from openrecall.shared.config import settings
from openrecall.shared.models import RecallEntry

logger = logging.getLogger(__name__)


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
        
        # Get engine instances (lazy-loaded singletons)
        ai_engine = get_ai_engine()
        nlp_engine = get_nlp_engine()
        
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
                    pending_count = db.get_pending_count(conn)
                    
                    if pending_count == 0:
                        if self._stop_event.wait(0.1):
                            continue
                        runtime_settings.wait_for_change(0.4)
                        continue
                    
                    # Determine LIFO vs FIFO mode
                    lifo_mode = pending_count >= settings.processing_lifo_threshold
                    mode_str = "LIFO (newest first)" if lifo_mode else "FIFO (oldest first)"
                    
                    # Get next task
                    task = db.get_next_task(conn, lifo_mode=lifo_mode)
                    
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
                    if not db.mark_task_processing(conn, task.id):
                        self._stop_event.wait(0.1)
                        continue
                    
                    # Execute processing pipeline
                    with runtime_settings._lock:
                        ai_processing_version = runtime_settings.ai_processing_version
                    self._process_task(conn, task, ai_engine, nlp_engine, ai_processing_version)
                    
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
        ai_engine,
        nlp_engine,
        ai_processing_version: int
    ):
        """Process a single task through the OCR → AI → NLP pipeline.
        
        Args:
            conn: Database connection.
            task: The task to process.
            ai_engine: AI engine instance for image analysis.
            nlp_engine: NLP engine instance for text embedding.
        """
        try:
            def should_cancel() -> bool:
                with runtime_settings._lock:
                    return (
                        (not runtime_settings.ai_processing_enabled)
                        or runtime_settings.ai_processing_version != ai_processing_version
                    )

            if should_cancel():
                db.mark_task_cancelled_if_processing(conn, task.id)
                return

            # Reconstruct image path from timestamp
            image_path = settings.screenshots_path / f"{task.timestamp}.png"
            
            if not image_path.exists():
                logger.error(f"❌ Task #{task.id}: Image not found at {image_path}")
                db.mark_task_failed(conn, task.id)
                return
            
            # Load image and convert to numpy array for OCR
            image = Image.open(image_path)
            image_array = np.array(image)
            
            # Step 1: OCR text extraction
            if should_cancel():
                db.mark_task_cancelled_if_processing(conn, task.id)
                return
            text = extract_text_from_image(image_array)
            if settings.debug:
                logger.debug(f"  OCR: {len(text)} chars extracted")
            
            # Step 2: AI image analysis (pass PIL Image object)
            if should_cancel():
                db.mark_task_cancelled_if_processing(conn, task.id)
                return
            description = ai_engine.analyze_image(image)
            if settings.debug:
                logger.debug(f"  AI: {len(description)} chars description")
            
            # Step 3: Generate text embedding
            # Combine text and description for richer embedding
            combined_text = f"{text}\n{description}"
            
            if settings.debug:
                logger.debug("="*80)
                logger.debug(f"  📝 OCR文本 ({len(text)} chars):\n{text}")
                logger.debug("="*80)
                logger.debug(f"  🤖 VL描述 ({len(description)} chars):\n{description}")
                logger.debug("="*80)
                logger.debug(f"  🔗 合并文本 (总计 {len(combined_text)} chars):\n{combined_text}")
                logger.debug("="*80)
            
            if should_cancel():
                db.mark_task_cancelled_if_processing(conn, task.id)
                return
            embedding = nlp_engine.encode(combined_text)
            if settings.debug:
                logger.debug(f"  NLP: Embedding shape {embedding.shape}")
            
            # Mark as completed
            if should_cancel():
                db.mark_task_cancelled_if_processing(conn, task.id)
                return
            success = db.mark_task_completed(
                conn,
                task.id,
                text,
                description,
                embedding
            )
            
            if success:
                if settings.debug:
                    logger.info(f"✅ Task #{task.id} completed successfully")
            else:
                if should_cancel():
                    db.mark_task_cancelled_if_processing(conn, task.id)
                    return
                logger.error(f"⚠️ Task #{task.id}: Failed to update database")
        
        except Exception as e:
            logger.error(f"❌ Task #{task.id} failed: {e}")
            logger.error(traceback.format_exc())
            db.mark_task_failed(conn, task.id)
