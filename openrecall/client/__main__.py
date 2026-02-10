"""OpenRecall Client entry point.

Launch with: python -m openrecall.client

The client handles:
- Screenshot capture (Producer)
- Local buffering when server is unavailable
- Uploading to server (Consumer)
"""

import signal
import sys
import threading
import time
from pathlib import Path

from openrecall.shared.config import settings
from openrecall.shared.logging_config import configure_logging

logger = configure_logging("openrecall.client")

from openrecall.client.recorder import get_recorder

STATUS_LOG_INTERVAL_SECONDS = 20


def main():
    """Start the OpenRecall client (recorder + uploader)."""
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
    logger.info(f"Capture interval: {settings.capture_interval}s")
    logger.info(f"Upload timeout: {settings.upload_timeout}s")
    logger.info(f"Primary monitor only: {settings.primary_monitor_only}")
    logger.info(
        "Video monitor IDs: %s",
        settings.video_monitor_id_list if settings.video_monitor_id_list else "auto",
    )
    logger.info(
        "Profile-change restart: %s | Pool max bytes: %s",
        settings.video_pipeline_restart_on_profile_change,
        settings.video_pool_max_bytes,
    )
    logger.info(
        "SCK retries: max=%s backoff=%ss perm_backoff=%ss auto_recover=%s",
        settings.sck_start_retry_max,
        settings.sck_retry_backoff_seconds,
        settings.sck_permission_backoff_seconds,
        settings.sck_auto_recover_from_legacy,
    )
    logger.info("=" * 50)

    # Get recorder (manages Producer + Consumer)
    recorder = get_recorder()

    # Start audio recording if enabled
    audio_recorder = None
    if settings.audio_enabled:
        try:
            from openrecall.client.audio_recorder import AudioRecorder

            audio_recorder = AudioRecorder()
            audio_recorder.start()
            if audio_recorder.is_running():
                logger.info("✅ Audio recording initialized")
            else:
                logger.info("Audio recording: no devices available")
                audio_recorder = None
        except Exception as e:
            logger.warning(f"Failed to start audio recorder: {e}")
            audio_recorder = None
    else:
        logger.info("Audio capture disabled by configuration")

    # Status logging thread
    status_stop_event = threading.Event()

    def log_periodic_status():
        """Log combined client status every 20 seconds."""
        last_log_at = 0.0
        while not status_stop_event.is_set():
            now = time.time()
            if now - last_log_at >= STATUS_LOG_INTERVAL_SECONDS:
                last_log_at = now

                # Get upload queue status
                pending_uploads = (
                    recorder.buffer.count() if hasattr(recorder, "buffer") else 0
                )

                # Build status components
                status_parts = []

                # Audio status with current chunk file and duration
                if audio_recorder and audio_recorder.is_running():
                    active_devices = sum(
                        1 for m in audio_recorder._managers if m.is_alive()
                    )
                    audio_duration = audio_recorder.get_total_recording_duration()
                    # Get current chunk file name from first active manager
                    current_file = "none"
                    for mgr in audio_recorder._managers:
                        if mgr.is_alive() and mgr._current_path:
                            current_file = mgr._current_path.name
                            break
                    status_parts.append(
                        f"🎤 [AUDIO] Recording | devices={active_devices}/{len(audio_recorder._managers)} | file={current_file} | duration={audio_duration:.0f}s"
                    )
                elif settings.audio_enabled:
                    status_parts.append("🎤 [AUDIO] Idle")

                # Video status with current chunk file and duration
                video_recorder = None
                for attr_name in dir(recorder):
                    if attr_name.startswith("_"):
                        continue
                    attr = getattr(recorder, attr_name, None)
                    if attr and hasattr(attr, "get_total_recording_duration"):
                        try:
                            video_recorder = attr
                            break
                        except Exception:
                            pass

                if video_recorder:
                    try:
                        video_duration = video_recorder.get_total_recording_duration()
                        # Get current chunk file name from legacy ffmpeg
                        current_file = "none"
                        if hasattr(video_recorder, "_legacy_ffmpeg"):
                            ff = video_recorder._legacy_ffmpeg
                            if ff._current_path:
                                current_file = Path(ff._current_path).name
                        if status_parts:
                            status_parts.append(
                                f"🎥 [VIDEO] Recording | file={current_file} | duration={video_duration:.0f}s | pending_uploads={pending_uploads}"
                            )
                        else:
                            status_parts.append(
                                f"🎥 [VIDEO] Recording | file={current_file} | duration={video_duration:.0f}s | pending_uploads={pending_uploads}"
                            )
                    except Exception:
                        pass
                elif status_parts:
                    status_parts.append(f"pending_uploads={pending_uploads}")

                if status_parts:
                    logger.info(" | ".join(status_parts))

            time.sleep(1)

    status_thread = threading.Thread(target=log_periodic_status, daemon=True)
    status_thread.start()

    # Flag to prevent duplicate signal handling
    _shutting_down = False

    def shutdown_handler(signum, frame):
        nonlocal _shutting_down
        if _shutting_down:
            return
        _shutting_down = True

        logger.info("")
        logger.info("Received shutdown signal, stopping client...")
        status_stop_event.set()
        if audio_recorder is not None:
            try:
                audio_recorder.stop()
            except Exception as e:
                logger.warning(f"Error stopping audio recorder: {e}")
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
        if not _shutting_down:
            status_stop_event.set()
            if audio_recorder is not None:
                try:
                    audio_recorder.stop()
                except Exception:
                    pass
            recorder.stop()
            logger.info("Client shutdown complete")
        sys.exit(0)


if __name__ == "__main__":
    main()
