"""P1-S3 Processing Module: OCR processing pipeline for v3 Edge.

This module provides OCR-only processing for captured frames:
- ocr_processor: Execute OCR and return structured results
- idempotency: Prevent duplicate OCR processing
- v3_worker: Background worker for frame processing
"""

from openrecall.server.processing.ocr_processor import OcrResult, OcrStatus, execute_ocr
from openrecall.server.processing.idempotency import check_ocr_text_exists
from openrecall.server.processing.v3_worker import V3ProcessingWorker

__all__ = ["OcrResult", "OcrStatus", "execute_ocr", "check_ocr_text_exists", "V3ProcessingWorker"]
