"""v3 spool uploader: multipart POST /v1/ingest with retry and resume."""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional

import requests

from openrecall.client.spool import SpoolItem, SpoolQueue, get_spool
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)

_INGEST_TIMEOUT = 30
_BACKOFF_BASE = 1
_BACKOFF_MAX = 60


def _ingest_url() -> str:
    base = settings.api_url.rstrip("/")
    if base.endswith("/api"):
        base = base[: -len("/api")]
    return f"{base}/v1/ingest"


def upload_capture(item: SpoolItem, spool: Optional[SpoolQueue] = None) -> bool:
    """Upload one spool item to POST /v1/ingest.

    Handles:
    - 201 Created       → new frame, deletes spool entry
    - 200 already_exists → idempotent success, deletes spool entry
    - 503 QUEUE_FULL    → respects retry_after, returns False (caller retries)
    - network errors    → logs warning, returns False (caller backs off)
    - other 4xx/5xx     → logs error, returns False

    Args:
        item: The SpoolItem to upload.
        spool: SpoolQueue for cleanup on success. Defaults to global singleton.

    Returns:
        True when the item was successfully ingested (and removed from spool).
    """
    if spool is None:
        spool = get_spool()

    url = _ingest_url()
    try:
        with open(item.jpg_path, "rb") as jpg_fh:
            files = {"file": (f"{item.capture_id}.jpg", jpg_fh, "image/jpeg")}
            data = {
                "capture_id": item.capture_id,
                "metadata": json.dumps(item.metadata),
            }
            response = requests.post(url, files=files, data=data, timeout=_INGEST_TIMEOUT)
    except requests.RequestException as exc:
        logger.warning("v3_uploader: network error capture_id=%s: %s", item.capture_id, exc)
        return False

    if response.status_code in (200, 201):
        body = {}
        try:
            body = response.json()
        except Exception:
            pass
        status_str = body.get("status", "queued")
        logger.info(
            "v3_uploader: %d %s capture_id=%s frame_id=%s",
            response.status_code,
            status_str,
            item.capture_id,
            body.get("frame_id"),
        )
        spool.commit(item.capture_id)
        return True

    if response.status_code == 503:
        retry_after = 5
        try:
            retry_after = int(response.json().get("retry_after", 5))
        except Exception:
            pass
        logger.warning(
            "v3_uploader: 503 QUEUE_FULL capture_id=%s retry_after=%ds",
            item.capture_id,
            retry_after,
        )
        time.sleep(retry_after)
        return False

    logger.error(
        "v3_uploader: unexpected %d capture_id=%s body=%r",
        response.status_code,
        item.capture_id,
        response.text[:200],
    )
    return False


class SpoolUploader(threading.Thread):
    """Background thread that drains the spool via POST /v1/ingest.

    On start it immediately scans the spool directory for any residual
    .jpg + .json pairs from previous runs (auto-resume after restart).

    Retry policy:
      - 503 QUEUE_FULL: honour retry_after from response
      - network failure: exponential backoff 1s -> 2s -> 4s ... capped at 60s
      - success: reset backoff counter
    """

    def __init__(
        self,
        spool: Optional[SpoolQueue] = None,
        stop_event: Optional[threading.Event] = None,
        name: str = "SpoolUploader",
    ) -> None:
        super().__init__(name=name, daemon=True)
        self.spool = spool or get_spool()
        self._stop_event = stop_event or threading.Event()
        self._retry_count = 0

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        residual = self.spool.count()
        logger.info("v3_uploader: SpoolUploader started | residual=%d", residual)

        while not self._stop_event.is_set():
            items = self.spool.get_pending(limit=1)

            if not items:
                self._stop_event.wait(timeout=1.0)
                continue

            item = items[0]
            success = upload_capture(item, spool=self.spool)

            if success:
                self._retry_count = 0
            else:
                self._retry_count += 1
                wait = min(_BACKOFF_BASE * (2 ** (self._retry_count - 1)), _BACKOFF_MAX)
                logger.debug(
                    "v3_uploader: backing off %ds (attempt #%d)",
                    wait,
                    self._retry_count,
                )
                self._stop_event.wait(timeout=float(wait))

        remaining = self.spool.count()
        logger.info("v3_uploader: SpoolUploader stopped | remaining=%d", remaining)


_uploader: Optional[SpoolUploader] = None


def get_v3_uploader() -> SpoolUploader:
    """Return the global SpoolUploader singleton (not yet started)."""
    global _uploader
    if _uploader is None:
        _uploader = SpoolUploader()
    return _uploader
