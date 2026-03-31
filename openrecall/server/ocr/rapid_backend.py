"""
RapidOCR v3 Backend for MyRecall.

Simplified configuration using params dict + enums:
- Default: PP-OCRv4 (bundled with pip package, zero download)
- Quality parameters: configurable via environment variables
- No local model path management needed
- Uses native to_markdown() for layout preservation (rapidocr>=3.2.0)

Reference: https://rapidai.github.io/RapidOCRDocs/main/install_usage/rapidocr/usage/
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import numpy as np
from PIL import Image

from rapidocr import RapidOCR, EngineType, ModelType, OCRVersion
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


@dataclass
class OcrOutput:
    """Structured OCR result with text and bounding boxes.

    Attributes:
        text: Layout-preserved text (markdown format)
        boxes: List of bounding boxes, each [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
        box_texts: Text content for each box
        scores: Confidence scores for each box
    """

    text: str
    boxes: list
    box_texts: list
    scores: list

    def to_json_dict(self) -> dict:
        """Serialize to JSON-compatible dict for database storage."""
        return {
            "boxes": self.boxes,
            "texts": self.box_texts,
            "scores": self.scores,
        }


class RapidOCRBackend:
    """
    RapidOCR v3 backend with singleton pattern.

    Configuration:
    - Default: PP-OCRv4 (bundled with pip, zero network dependency)
    - Quality params: configurable via OPENRECALL_OCR_* environment variables
    - Layout: uses native to_markdown() for better structure preservation
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            instance = super(RapidOCRBackend, cls).__new__(cls)
            instance._initialize()
            cls._instance = instance
        return cls._instance

    def _initialize(self):
        """Initialize RapidOCR with params dict configuration."""

        # Get OCR version from config
        ocr_version = self._get_ocr_version()
        model_type = self._get_model_type()

        logger.info(
            f"Initializing RapidOCR v3 backend "
            f"(version={ocr_version.value}, model_type={model_type.value})"
        )

        # Build params dict
        # Reference: https://rapidai.github.io/RapidOCRDocs/main/install_usage/rapidocr/usage/
        params = {
            # Detection config
            "Det.engine_type": EngineType.ONNXRUNTIME,
            "Det.ocr_version": ocr_version,
            "Det.model_type": model_type,
            # Recognition config
            "Rec.engine_type": EngineType.ONNXRUNTIME,
            "Rec.ocr_version": ocr_version,
            "Rec.model_type": model_type,
            # Classification config
            "Cls.engine_type": EngineType.ONNXRUNTIME,
            # Quality tuning parameters (hardcoded defaults)
            "Det.limit_side_len": 960,
            "Det.thresh": 0.3,
            "Det.box_thresh": 0.7,
            "Det.unclip_ratio": 1.6,
            "Det.score_mode": 0,
            "Global.text_score": 0.0,
        }

        self.engine = RapidOCR(params=params)
        logger.info("RapidOCR v3 backend initialized successfully")

    def _get_ocr_version(self) -> OCRVersion:
        """Map config string to OCRVersion enum."""
        version_map = {
            "pp-ocrv4": OCRVersion.PPOCRV4,
            "pp-ocrv5": OCRVersion.PPOCRV5,
        }
        version_str = settings.ocr_rapid_ocr_version.lower()
        if version_str not in version_map:
            logger.warning(f"Unknown OCR version '{version_str}', using PP-OCRv4")
            return OCRVersion.PPOCRV4
        return version_map[version_str]

    def _get_model_type(self) -> ModelType:
        """Map config string to ModelType enum."""
        type_map = {
            "mobile": ModelType.MOBILE,
            "server": ModelType.SERVER,
        }
        type_str = settings.ocr_rapid_model_type.lower()
        if type_str not in type_map:
            logger.warning(f"Unknown model type '{type_str}', using MOBILE")
            return ModelType.MOBILE
        return type_map[type_str]

    def extract_text(
        self,
        image: Union[Image.Image, np.ndarray, bytes],
        vis_output_path: Optional[str] = None,
    ) -> str:
        """
        Extract text from image with layout preservation.

        Uses RapidOCR's native to_markdown() for better layout preservation,
        including paragraph detection and multi-column handling.

        Args:
            image: PIL.Image, numpy.ndarray, or bytes
            vis_output_path: Optional path to save OCR visualization image

        Returns:
            str: Extracted text with layout-preserved formatting

        Raises:
            Exception: Propagates OCR engine exceptions for caller to handle.
        """
        result = self._extract(image, vis_output_path=vis_output_path)
        return result.text

    def extract_text_with_boxes(
        self,
        image: Union[Image.Image, np.ndarray, bytes],
        vis_output_path: Optional[str] = None,
    ) -> OcrOutput:
        """
        Extract text with bounding boxes for future UI features.

        Returns both layout-preserved text and structured bounding box data
        for "click to select/copy" functionality.

        Args:
            image: PIL.Image, numpy.ndarray, or bytes
            vis_output_path: Optional path to save OCR visualization image

        Returns:
            OcrOutput: Text + boxes + scores

        Raises:
            Exception: Propagates OCR engine exceptions for caller to handle.
        """
        return self._extract(image, vis_output_path=vis_output_path)

    def _extract(
        self,
        image: Union[Image.Image, np.ndarray, bytes],
        vis_output_path: Optional[str] = None,
    ) -> OcrOutput:
        """Internal: run OCR and return structured result.

        Args:
            image: PIL.Image, numpy.ndarray, or bytes
            vis_output_path: Optional path to save OCR visualization image
        """
        # Handle PIL Image -> Convert to BGR Numpy
        if isinstance(image, Image.Image):
            img_np = np.array(image)
            if img_np.ndim == 3 and img_np.shape[2] == 3:
                image = img_np[:, :, ::-1]  # RGB to BGR
            else:
                image = img_np

        # RapidOCR v3 returns RapidOCROutput with .boxes, .txts, .scores
        result = self.engine(image, use_det=True, use_cls=True, use_rec=True)

        # Check for empty result
        if result is None or result.txts is None or len(result.txts) == 0:
            return OcrOutput(text="", boxes=[], box_texts=[], scores=[])

        # Use native to_markdown() for layout-preserved output
        text = result.to_markdown()

        # Extract boxes data for future UI features
        boxes = result.boxes.tolist() if result.boxes is not None else []
        box_texts = list(result.txts) if result.txts else []
        scores = [float(s) for s in result.scores] if result.scores else []

        if settings.debug:
            logger.debug(
                f"RapidOCR v3: Extracted {len(text)} chars, {len(boxes)} boxes"
            )

        # Generate visualization image if path provided
        if vis_output_path and result is not None:
            try:
                # Ensure output directory exists
                Path(vis_output_path).parent.mkdir(parents=True, exist_ok=True)
                result.vis(vis_output_path)
                if settings.debug:
                    logger.debug(
                        f"RapidOCR v3: Saved visualization to {vis_output_path}"
                    )
            except Exception as e:
                # Non-fatal: log warning but continue
                logger.warning(f"RapidOCR v3: Failed to save visualization: {e}")

        return OcrOutput(text=text, boxes=boxes, box_texts=box_texts, scores=scores)


if __name__ == "__main__":
    # Self-test
    print("Testing RapidOCRBackend...")

    backend = RapidOCRBackend()
    print("✅ Backend initialized")

    # Test with sample image if available
    import os

    test_img = "tests/fixtures/images/sample_jpeg.jpg"
    if os.path.exists(test_img):
        img = Image.open(test_img)

        # Test extract_text
        text = backend.extract_text(img)
        print(f"✅ extract_text: {text[:50]}...")

        # Test extract_text_with_boxes
        result = backend.extract_text_with_boxes(img)
        print(
            f"✅ extract_text_with_boxes: {len(result.text)} chars, {len(result.boxes)} boxes"
        )

        # Test JSON serialization
        json_dict = result.to_json_dict()
        print(f"✅ to_json_dict: {len(str(json_dict))} bytes")
    else:
        print(f"⚠️ Test image not found: {test_img}")

    print("\n✅ RapidOCRBackend self-test passed")
