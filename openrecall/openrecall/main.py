"""OpenRecall main entry point.

Launch with: python -m openrecall.main

Architecture:
- Client (recorder thread): Captures screenshots, sends via HTTP to server
- Server (Flask main thread): Receives uploads, processes OCR/embeddings, stores data
"""

from threading import Thread

from openrecall.shared.config import settings
from openrecall.server.database import create_db
from openrecall.server.app import app
from openrecall.client.recorder import record_screenshots_thread


def main():
    """Start OpenRecall: Flask server + recorder client.
    
    The server starts first to ensure API is available when the client
    recorder thread begins uploading screenshots.
    """
    # Initialize database
    create_db()

    print(f"Data folder: {settings.base_path}")
    print(f"API URL: {settings.api_url}")
    print(f"Starting OpenRecall on http://localhost:{settings.port}")

    # Start the recorder thread (Client - Producer)
    # The recorder will wait for server health check before processing
    recorder_thread = Thread(target=record_screenshots_thread, daemon=True)
    recorder_thread.start()

    # Start the Flask server (Server - Consumer/UI) on main thread
    app.run(port=settings.port)


if __name__ == "__main__":
    main()
