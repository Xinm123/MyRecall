"""REST API Blueprint for OpenRecall server.

Provides HTTP endpoints for client-server communication:
- Health check endpoint
- Screenshot upload endpoint
"""

import numpy as np
from flask import Blueprint, jsonify, request

from openrecall.server.database import insert_entry
from openrecall.server.nlp import get_embedding
from openrecall.server.ocr import extract_text_from_image

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
        
        # Process the image: OCR → Embedding → Database
        text: str = extract_text_from_image(image_array)
        
        # Only store if OCR extracts meaningful text
        if text.strip():
            embedding: np.ndarray = get_embedding(text)
            insert_entry(text, timestamp, embedding, active_app, active_window)
            return jsonify({"status": "ok", "message": "Entry stored"}), 200
        else:
            return jsonify({"status": "ok", "message": "No text extracted, skipped"}), 200
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
