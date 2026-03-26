"""Flask web server for client-side Web UI."""

import logging
import threading
from flask import Flask, render_template, send_from_directory
from openrecall.client.chat.routes import chat_bp
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)

client_app = Flask(__name__, template_folder="templates")
client_app.register_blueprint(chat_bp)


@client_app.context_processor
def inject_template_vars():
    """Make EDGE_BASE_URL and settings available to all templates."""
    return {"EDGE_BASE_URL": settings.edge_base_url, "settings": settings}


@client_app.route("/")
def index():
    # Client doesn't have the database; templates fetch data via API from Edge
    return render_template("index.html", entries=[], stats={"completed": 0, "pending": 0, "processing": 0})


@client_app.route("/search")
def search():
    return render_template("search.html")


@client_app.route("/timeline")
def timeline():
    # Client doesn't have the database; templates fetch data via API from Edge
    return render_template("timeline.html", timeline_frames=[])


@client_app.route("/vendor/<path:filename>")
def vendor(filename):
    return send_from_directory("vendor", filename)


@client_app.route("/screenshots/<path:filename>")
def screenshots(filename):
    """Proxy screenshots requests to Edge server (served at /v1/frames/)."""
    import requests
    edge_url = f"{settings.edge_base_url}/v1/frames/{filename}"
    try:
        resp = requests.get(edge_url, timeout=5)
        from flask import Response
        return Response(resp.content, resp.status_code, {"Content-Type": resp.headers.get("Content-Type", "image/jpeg")})
    except requests.RequestException as e:
        from flask import abort
        logger.error(f"Failed to proxy screenshot {filename}: {e}")
        abort(502)


def start_web_server():
    """Start the web server in a daemon thread and return the thread."""
    t = threading.Thread(
        target=lambda: client_app.run(
            host="0.0.0.0",
            port=settings.client_web_port,
            debug=settings.debug,
            use_reloader=False,
        ),
        daemon=True,
        name="client-web-server",
    )
    t.start()
    logger.info(f"Web UI started: http://localhost:{settings.client_web_port}")
    return t
