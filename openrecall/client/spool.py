"""Spool queue for v3 capture pipeline (jpg+json, atomic, UUID v7)."""

import json
import logging
import os
import struct
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image

from openrecall.shared.config import settings

logger = logging.getLogger(__name__)

_SPOOL_METADATA_DEFAULTS = {
    "accessibility_text": "",
    "content_hash": None,
    "browser_url": None,
    "device_name": "monitor_0",
    "capture_trigger": "manual",
    "event_ts": None,
    "outcome": None,
    "capture_cycle_latency_ms": None,
    "host_pid": None,
    "runtime_started_at": None,
}


def _uuid_v7() -> str:
    """Generate a UUID v7 (time-ordered, RFC 9562) string.

    Bit layout (128 bits):
      [0..47]   unix_ts_ms  – 48-bit millisecond timestamp
      [48..51]  version     – 0x7
      [52..63]  rand_a      – 12 random bits
      [64..65]  variant     – 0b10
      [66..127] rand_b      – 62 random bits
    """
    ts_ms = int(time.time() * 1000) & 0xFFFF_FFFF_FFFF
    rand_bytes = os.urandom(10)
    rand_a, rand_b_raw = struct.unpack(">HQ", rand_bytes)
    rand_a &= 0x0FFF
    rand_b = (rand_b_raw & ~(0b11 << 62)) | (0b10 << 62)
    hi = (ts_ms << 16) | (0x7 << 12) | rand_a
    lo = rand_b
    h = f"{hi:016x}{lo:016x}"
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


@dataclass
class SpoolItem:
    capture_id: str
    jpg_path: Path
    metadata: Dict[str, Any]


class SpoolQueue:
    """File-system-backed queue writing .jpg + .json pairs atomically.

    Write: jpg -> json.tmp -> os.replace(json.tmp, json)  (atomic on POSIX/Win)
    Read:  glob *.json, skip entries missing paired .jpg
    Drain: removes legacy .webp files from LocalBuffer on init
    """

    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        self.storage_dir: Path = storage_dir or settings.spool_path
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._drain_legacy_webp()
        self._drain_orphan_jpg()

    def enqueue(self, image: Image.Image, metadata: Dict[str, Any]) -> str:
        capture_id = _uuid_v7()
        jpg_tmp = self.storage_dir / f"{capture_id}.jpg.tmp"
        jpg_path = self.storage_dir / f"{capture_id}.jpg"
        json_tmp = self.storage_dir / f"{capture_id}.json.tmp"
        json_path = self.storage_dir / f"{capture_id}.json"

        image.save(str(jpg_tmp), format="JPEG", quality=85)
        os.replace(jpg_tmp, jpg_path)

        meta = self._serialize_metadata(metadata)
        capture_cycle_started_at = meta.pop("_capture_cycle_started_at", None)
        for key, default in _SPOOL_METADATA_DEFAULTS.items():
            meta.setdefault(key, default)
        if isinstance(capture_cycle_started_at, (int, float)):
            meta["capture_cycle_latency_ms"] = int(
                (time.perf_counter() - float(capture_cycle_started_at)) * 1000
            )
        meta.setdefault("event_device_hint", meta.get("device_name"))
        meta["capture_id"] = capture_id
        meta.setdefault(
            "timestamp",
            datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
        )
        meta.setdefault("ingested_at", datetime.now(timezone.utc).isoformat())

        with open(json_tmp, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=2)
        os.replace(json_tmp, json_path)

        logger.info(
            "spool: enqueued capture_id=%s size=%d queue=%d",
            capture_id,
            jpg_path.stat().st_size,
            self.count(),
        )
        return capture_id

    def get_pending(self, limit: int = 50) -> List[SpoolItem]:
        items: List[SpoolItem] = []
        for json_path in sorted(self.storage_dir.glob("*.json")):
            if len(items) >= limit:
                break
            capture_id = json_path.stem
            jpg_path = self.storage_dir / f"{capture_id}.jpg"
            if not jpg_path.exists():
                logger.debug("spool: orphan json (no jpg), removing %s", json_path)
                self._safe_unlink(json_path)
                continue
            try:
                with open(json_path, "r", encoding="utf-8") as fh:
                    meta = json.load(fh)
            except (json.JSONDecodeError, OSError) as exc:
                logger.error("spool: corrupt metadata %s: %s", json_path, exc)
                continue
            items.append(
                SpoolItem(
                    capture_id=meta.get("capture_id", capture_id),
                    jpg_path=jpg_path,
                    metadata=meta,
                )
            )
        return items

    def commit(self, capture_id: str) -> None:
        self._safe_unlink(self.storage_dir / f"{capture_id}.jpg")
        self._safe_unlink(self.storage_dir / f"{capture_id}.json")
        logger.info(
            "spool: committed capture_id=%s remaining=%d", capture_id, self.count()
        )

    def update_metadata(self, capture_id: str, updates: Dict[str, Any]) -> None:
        json_path = self.storage_dir / f"{capture_id}.json"
        if not json_path.exists():
            return
        json_tmp = self.storage_dir / f"{capture_id}.json.tmp"
        try:
            with open(json_path, "r", encoding="utf-8") as fh:
                metadata = json.load(fh)
            metadata.update(self._serialize_metadata(updates))
            with open(json_tmp, "w", encoding="utf-8") as fh:
                json.dump(metadata, fh, ensure_ascii=False, indent=2)
            os.replace(json_tmp, json_path)
        except OSError as exc:
            logger.warning(
                "spool: failed to update metadata capture_id=%s: %s",
                capture_id,
                exc,
            )
        except json.JSONDecodeError as exc:
            logger.warning(
                "spool: failed to decode metadata capture_id=%s: %s",
                capture_id,
                exc,
            )

    def count(self) -> int:
        return sum(
            1
            for p in self.storage_dir.glob("*.json")
            if (self.storage_dir / f"{p.stem}.jpg").exists()
        )

    def _drain_legacy_webp(self) -> None:
        webp_files = list(self.storage_dir.glob("*.webp"))
        if not webp_files:
            return
        logger.info("spool: draining %d legacy .webp item(s)", len(webp_files))
        for webp_path in webp_files:
            stem = webp_path.stem
            self._safe_unlink(webp_path)
            self._safe_unlink(self.storage_dir / f"{stem}.json")

    def _drain_orphan_jpg(self) -> None:
        orphan_jpg_files = [
            jpg_path
            for jpg_path in self.storage_dir.glob("*.jpg")
            if not (self.storage_dir / f"{jpg_path.stem}.json").exists()
        ]
        if not orphan_jpg_files:
            return
        logger.info("spool: draining %d orphan .jpg item(s)", len(orphan_jpg_files))
        for jpg_path in orphan_jpg_files:
            self._safe_unlink(jpg_path)

    @staticmethod
    def _serialize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, value in metadata.items():
            if isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, Path):
                result[key] = str(value)
            else:
                result[key] = value
        return result

    @staticmethod
    def _safe_unlink(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("spool: failed to delete %s: %s", path, exc)


_spool: Optional[SpoolQueue] = None


def get_spool() -> SpoolQueue:
    global _spool
    if _spool is None:
        _spool = SpoolQueue()
    return _spool
