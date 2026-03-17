"""OCR Processor: Execute OCR and return structured results.

This module wraps RapidOCRBackend and provides structured error classification
for the V3ProcessingWorker to handle different failure modes.

SSOT: design.md D2 - OCR result classification
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from PIL import Image

from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


class OcrStatus(Enum):
    """Status of OCR operation result."""

    SUCCESS = "success"  # Non-empty text extracted
    EMPTY_TEXT = "empty_text"  # OCR returned empty string
    FAILED = "failed"  # OCR engine exception or null result


@dataclass
class OcrResult:
    """Structured result from OCR execution.

    Attributes:
        status: SUCCESS, EMPTY_TEXT, or FAILED
        text: Extracted text (empty string if no text or failed)
        text_json: Bounding boxes data for future UI features (dict or None)
        error_reason: Error classification for FAILED status
        elapsed_ms: Processing time in milliseconds
        text_length: Length of extracted text (0 if failed or empty)
    """

    status: OcrStatus
    text: str = ""
    text_json: Optional[dict] = None
    error_reason: Optional[str] = None
    elapsed_ms: float = 0.0
    text_length: int = 0

    def __post_init__(self):
        # Ensure text_length matches actual text length
        self.text_length = len(self.text) if self.text else 0

    @property
    def is_success(self) -> bool:
        """True if OCR extracted non-empty text."""
        return self.status == OcrStatus.SUCCESS

    @property
    def is_failed(self) -> bool:
        """True if OCR failed (exception, null result, or empty text)."""
        return self.status in (OcrStatus.FAILED, OcrStatus.EMPTY_TEXT)


def execute_ocr(image_path: str, frame_id: Optional[int] = None) -> OcrResult:
    """Execute OCR on an image and return a structured result.

    This function:
    1. Loads the image from disk
    2. Calls RapidOCRBackend to extract text with bounding boxes
    3. Generates OCR visualization image (if frame_id provided)
    4. Classifies the result (success/empty/failed)
    5. Returns structured OcrResult with timing info and text_json

    Args:
        image_path: Path to the image file (JPEG expected)
        frame_id: Optional frame ID for generating visualization image

    Returns:
        OcrResult with status, text, text_json, error_reason, and elapsed_ms

    Note:
        Per design.md D2, we distinguish:
        - Exception during OCR -> FAILED with error_reason
        - Empty string return -> EMPTY_TEXT
        - Non-empty string -> SUCCESS (with text_json populated)
    """
    start_time = time.perf_counter()

    try:
        # Load image
        path = Path(image_path)
        if not path.exists():
            return OcrResult(
                status=OcrStatus.FAILED,
                error_reason=f"OCR_FAILED: image_not_found path={image_path}",
                elapsed_ms=0.0,
            )

        # Import here to avoid circular imports and allow lazy loading
        from openrecall.server.ocr.rapid_backend import RapidOCRBackend

        backend = RapidOCRBackend()

        # Build visualization output path if frame_id is provided
        vis_output_path = None
        if frame_id is not None:
            vis_dir = settings.server_data_dir / "ocr_vis"
            vis_output_path = str(vis_dir / f"{frame_id}.jpg")

        # Load image as PIL Image
        with Image.open(path) as img:
            # Convert to RGB if needed (handles grayscale, RGBA, etc.)
            if img.mode != "RGB":
                img = img.convert("RGB")

            # Call extract_text_with_boxes - may raise exceptions per D2
            output = backend.extract_text_with_boxes(img, vis_output_path=vis_output_path)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Classify result per design.md D2
        if not output.text:
            return OcrResult(
                status=OcrStatus.EMPTY_TEXT,
                error_reason="OCR_EMPTY_TEXT",
                elapsed_ms=elapsed_ms,
            )

        # Success - non-empty text with bounding boxes
        return OcrResult(
            status=OcrStatus.SUCCESS,
            text=output.text,
            text_json=output.to_json_dict() if output.boxes else None,
            elapsed_ms=elapsed_ms,
        )

    except FileNotFoundError as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        return OcrResult(
            status=OcrStatus.FAILED,
            error_reason=f"OCR_FAILED: file_not_found {e}",
            elapsed_ms=elapsed_ms,
        )

    except Exception as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        # Classify as FAILED with exception info
        error_type = type(e).__name__
        error_msg = str(e)
        return OcrResult(
            status=OcrStatus.FAILED,
            error_reason=f"OCR_FAILED: {error_type}: {error_msg}",
            elapsed_ms=elapsed_ms,
        )
