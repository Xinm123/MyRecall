"""Mock MyRecall API server for skill evaluation.

Records all incoming requests to a log file for later analysis.
Run: python mock_server.py --port 8083 --log /tmp/skill_test.log
"""

import argparse
import json
import logging
import os
from datetime import datetime
from flask import Flask, jsonify, request

app = Flask(__name__)

# In-memory storage for frame data
FRAMES = {}
LOG_FILE = "/tmp/skill_test.log"


def log_request(method, path, args, body=None):
    """Append request details to log file."""
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "method": method,
        "path": path,
        "args": dict(args),
    }
    if body:
        entry["body"] = body
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def ensure_log_cleared():
    """Clear log file at startup."""
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)


@app.route("/v1/health", methods=["GET"])
def health():
    log_request("GET", "/v1/health", request.args)
    return jsonify({"status": "ok"})


@app.route("/v1/activity-summary", methods=["GET"])
def activity_summary():
    log_request("GET", "/v1/activity-summary", request.args)
    start_time = request.args.get("start_time", "")
    end_time = request.args.get("end_time", "")
    app_name = request.args.get("app_name", "")
    max_desc = request.args.get("max_descriptions")

    apps = [
        {"name": "Safari", "frame_count": 15, "minutes": 45.5,
         "first_seen": "2026-04-30T09:00:00", "last_seen": "2026-04-30T10:30:00"},
        {"name": "VSCode", "frame_count": 30, "minutes": 120.0,
         "first_seen": "2026-04-30T10:00:00", "last_seen": "2026-04-30T12:00:00"},
        {"name": "Chrome", "frame_count": 8, "minutes": 25.0,
         "first_seen": "2026-04-30T14:00:00", "last_seen": "2026-04-30T14:25:00"},
    ]
    if app_name:
        apps = [a for a in apps if a["name"].lower() == app_name.lower()]

    descriptions = [
        {"frame_id": 101, "timestamp": "2026-04-30T09:15:00",
         "summary": "Browsing GitHub issues", "tags": ["github", "browsing"]},
        {"frame_id": 102, "timestamp": "2026-04-30T10:30:00",
         "summary": "Reviewing PR #456 in VSCode", "tags": ["code_review", "vscode"]},
        {"frame_id": 103, "timestamp": "2026-04-30T11:45:00",
         "summary": "Writing Python tests", "tags": ["coding", "python"]},
    ]

    return jsonify({
        "apps": apps,
        "audio_summary": {"segment_count": 0, "speakers": []},
        "total_frames": 53,
        "time_range": {"start": start_time, "end": end_time},
        "descriptions": descriptions[: int(max_desc)] if max_desc else descriptions,
    })


@app.route("/v1/search", methods=["GET"])
def search():
    log_request("GET", "/v1/search", request.args)
    q = request.args.get("q", "")
    mode = request.args.get("mode", "hybrid")
    limit = int(request.args.get("limit", 20))
    app_name = request.args.get("app_name", "")
    window_name = request.args.get("window_name", "")
    include_text = request.args.get("include_text", "false").lower() == "true"

    results = [
        {
            "frame_id": 201,
            "timestamp": "2026-04-30T10:30:00",
            "text_source": "accessibility",
            "app_name": "VSCode",
            "window_name": "myrecall-search — pull_request.py",
            "browser_url": None,
            "focused": True,
            "device_name": "monitor_0",
            "frame_url": "/v1/frames/201",
            "embedding_status": "completed",
            "score": 0.95,
            "cosine_score": 0.95,
        },
        {
            "frame_id": 202,
            "timestamp": "2026-04-30T10:35:00",
            "text_source": "accessibility",
            "app_name": "VSCode",
            "window_name": "myrecall-search — test_runner.py",
            "browser_url": None,
            "focused": True,
            "device_name": "monitor_0",
            "frame_url": "/v1/frames/202",
            "embedding_status": "completed",
            "score": 0.88,
            "cosine_score": 0.88,
        },
    ]

    if app_name:
        results = [r for r in results if r["app_name"].lower() == app_name.lower()]
    if q:
        results = [r for r in results if q.lower() in str(r).lower() or True]

    data = []
    for r in results[:limit]:
        item = dict(r)
        if include_text:
            item["text"] = f"Sample text for frame {r['frame_id']}..."
        data.append(item)

    return jsonify({
        "data": data,
        "pagination": {"limit": limit, "offset": 0, "total": len(data)},
    })


@app.route("/v1/frames/<int:frame_id>", methods=["GET"])
def get_frame_image(frame_id):
    log_request("GET", f"/v1/frames/{frame_id}", request.args)
    # Return a tiny 1x1 JPEG
    return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9", 200, {"Content-Type": "image/jpeg"}


@app.route("/v1/frames/<int:frame_id>/context", methods=["GET"])
def get_frame_context(frame_id):
    log_request("GET", f"/v1/frames/{frame_id}/context", request.args)
    return jsonify({
        "frame_id": frame_id,
        "timestamp": "2026-04-30T10:30:00",
        "app_name": "VSCode",
        "window_name": "myrecall-search — pull_request.py",
        "description": {
            "narrative": f"The user is reviewing a pull request in VSCode, looking at code changes in frame {frame_id}.",
            "summary": "PR review in VSCode",
            "tags": ["code_review", "vscode"],
        },
        "text": "Reviewing pull request changes...\nModified files: mock_server.py, test_runner.py\n...",
        "text_source": "accessibility",
        "urls": ["https://github.com/user/repo/pull/456"],
        "browser_url": None,
        "status": "completed",
        "description_status": "completed",
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8083)
    parser.add_argument("--log", type=str, default="/tmp/skill_test.log")
    args = parser.parse_args()
    LOG_FILE = args.log
    ensure_log_cleared()
    print(f"Mock server starting on port {args.port}, logging to {LOG_FILE}")
    app.run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False, threaded=True)
