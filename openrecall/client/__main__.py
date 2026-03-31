"""OpenRecall Client entry point.

Launch with: python -m openrecall.client [--config=/path/to/client.toml]

The client handles:
- Screenshot capture (Producer)
- Local buffering when server is unavailable
- Uploading to server (Consumer)
"""

import argparse
import signal
import sys

_args = None
for arg in sys.argv[1:]:
    if arg == "--no-web":
        import os

        os.environ["OPENRECALL_CLIENT_WEB_ENABLED"] = "false"
        sys.argv.remove(arg)
        break

from openrecall.shared.logging_config import configure_logging

logger = None  # Set in main() after settings are initialized


def _parse_args():
    parser = argparse.ArgumentParser(prog="openrecall-client")
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to TOML config file (default: ~/.myrecall/client.toml)",
    )
    return parser.parse_known_args()[0]


def _load_settings(config_path):
    from openrecall.client.config_client import ClientSettings

    return ClientSettings.from_toml(config_path)


_args = _parse_args()
settings = _load_settings(_args.config)

# Make new settings the global singleton for client modules
import openrecall.shared.config

openrecall.shared.config.settings = settings


def main():
    """Start the OpenRecall client (recorder + uploader)."""
    # Import here (not module-level) so Flask's debug-reload subprocess
    # does not hit settings before openrecall.shared.config.settings is set.
    from openrecall.client.recorder import get_recorder

    global logger
    logger = configure_logging("openrecall.client")
    logger.info("=" * 50)
    logger.info("OpenRecall Client Starting")
    logger.info("=" * 50)
    logger.info(f"Debug mode: {'ON' if settings.debug else 'OFF'}")
    logger.info(f"Buffer path: {settings.buffer_path}")
    logger.info(
        f"Client screenshots: {settings.client_screenshots_path} (enabled={settings.client_save_local_screenshots})"
    )
    logger.info(f"Cache folder: {settings.cache_path}")
    logger.info(f"Server API: {settings.api_url}")
    logger.info(
        f"Debounce: click={settings.click_debounce_ms}ms, trigger={settings.trigger_debounce_ms}ms, capture={settings.capture_debounce_ms}ms"
    )
    logger.info(f"Idle capture interval: {settings.idle_capture_interval_ms}ms")
    logger.info(
        f"Simhash dedup: click={settings.simhash_enabled_for_click}, app_switch={settings.simhash_enabled_for_app_switch}"
    )
    logger.info(f"Trigger queue capacity: {settings.trigger_queue_capacity}")
    logger.info(f"Upload timeout: {settings.upload_timeout}s")
    logger.info(f"Primary monitor only: {settings.primary_monitor_only}")
    logger.info("=" * 50)

    # Start client web UI server (if enabled)
    web_server_thread = None
    if settings.client_web_enabled:
        from openrecall.client.web.app import start_web_server

        web_server_thread = start_web_server()

    # Get recorder (manages Producer + Consumer)
    recorder = get_recorder()

    # Flag to prevent duplicate signal handling
    _shutting_down = False

    def shutdown_handler(signum, frame):
        nonlocal _shutting_down
        if _shutting_down:
            return
        _shutting_down = True

        logger.info("")
        logger.info("Received shutdown signal, stopping client...")
        recorder.stop()
        logger.info("Client shutdown complete")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # Run the capture loop on main thread
    try:
        recorder.run_capture_loop()
    except KeyboardInterrupt:
        pass
    finally:
        recorder.stop()


if __name__ == "__main__":
    main()
