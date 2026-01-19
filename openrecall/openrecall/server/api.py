"""REST API Blueprint for OpenRecall server.

Provides HTTP endpoints for client-server communication:
- Health check endpoint
- Screenshot upload endpoint with parallel OCR + AI processing
"""

import logging
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from flask import Blueprint, jsonify, request
from PIL import Image

from openrecall.server.database import insert_entry
from openrecall.server.nlp import get_embedding
from openrecall.server.ocr import extract_text_from_image
from openrecall.server.ai_engine import get_ai_engine

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint.
    
    Returns:
        JSON response with status "ok" and HTTP 200.
    """
    return jsonify({"status": "ok"}), 200


@api_bp.route("/upload", methods=["POST"])
def upload():
    """Upload screenshot data for processing.
    
    Expects JSON payload:
    {
        "image": list (flattened numpy array data),
        "shape": list (original image shape),
        "dtype": str (numpy dtype name),
        "timestamp": int (Unix timestamp),
        "active_app": str (active application name),
        "active_window": str (active window title)
    }
    
    Returns:
        JSON response with status and optional message.
    """
    data = request.get_json()
    
    if not data:
        return jsonify({"status": "error", "message": "No JSON data provided"}), 400
    
    required_fields = ["image", "shape", "dtype", "timestamp", "active_app", "active_window"]
    for field in required_fields:
        if field not in data:
            return jsonify({"status": "error", "message": f"Missing field: {field}"}), 400
    
    try:
        # Reconstruct numpy array from JSON data
        image_array = np.array(data["image"], dtype=data["dtype"]).reshape(data["shape"])
        timestamp = int(data["timestamp"])
        active_app = str(data["active_app"])
        active_window = str(data["active_window"])
        
        # Convert to PIL Image for AI engine
        pil_image = Image.fromarray(image_array)
        
        # Parallel processing: OCR + AI description
        with ThreadPoolExecutor(max_workers=2) as executor:
            ocr_future = executor.submit(extract_text_from_image, image_array)
            ai_future = executor.submit(_safe_analyze_image, pil_image)
            
            text: str = ocr_future.result()
            description: str | None = ai_future.result()
        
        # Store entry if OCR extracts meaningful text OR AI provides description
        if text.strip() or description:
            # Fusion Strategy: Combine visual description + OCR for richer embedding
            combined_text = _build_fusion_text(description, text)
            embedding: np.ndarray = get_embedding(combined_text)
            insert_entry(text, timestamp, embedding, active_app, active_window, description=description)
            return jsonify({"status": "ok", "message": "Entry stored"}), 200
        else:
            return jsonify({"status": "ok", "message": "No text or description, skipped"}), 200
            
    except Exception as e:
        logger.exception("Upload processing error")
        return jsonify({"status": "error", "message": str(e)}), 500


def _safe_analyze_image(image: Image.Image) -> str | None:
    """Safely run AI analysis with fault tolerance.
    
    If AI fails, logs the error and returns None instead of crashing.
    This ensures OCR data is still saved even if AI has issues.
    """
    try:
        ai_engine = get_ai_engine()
        return ai_engine.analyze_image(image)
    except Exception as e:
        logger.error(f"AI analysis failed: {e}")
        return None


def _build_fusion_text(description: str | None, ocr_text: str) -> str:
    """Build combined text for embedding using fusion strategy.
    
    Combines visual description (semantic context) with OCR text (precise content)
    to create a rich embedding input. Description comes first to establish context.
    
    Args:
        description: AI-generated visual description (may be None).
        ocr_text: OCR-extracted text content.
        
    Returns:
        Combined text suitable for embedding.
    """
    desc_part = description or ""
    text_part = ocr_text.strip()
    
    if desc_part and text_part:
        return f"Visual Summary: {desc_part}\n\nDetailed Content: {text_part}"
    elif desc_part:
        return f"Visual Summary: {desc_part}"
    else:
        return text_part
