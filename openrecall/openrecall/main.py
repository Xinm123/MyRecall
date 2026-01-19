"""OpenRecall main entry point.

Launch with: python -m openrecall.main
"""

from threading import Thread

from openrecall.shared.config import settings
from openrecall.server.database import create_db
from openrecall.server.app import app
from openrecall.client.recorder import record_screenshots_thread


def main():
    """Start OpenRecall: recorder thread + Flask server."""
    # Initialize database
    create_db()

    print(f"Data folder: {settings.base_path}")
    print(f"Starting OpenRecall on http://localhost:{settings.port}")

    # Start the recorder thread (Producer)
    recorder_thread = Thread(target=record_screenshots_thread, daemon=True)
    recorder_thread.start()

    # Start the Flask server (Consumer/UI) on main thread
    app.run(port=settings.port)


if __name__ == "__main__":
    main()
