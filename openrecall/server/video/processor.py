"""Video chunk processing pipeline: extract frames, OCR, index."""

import datetime
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from openrecall.shared.config import settings
from openrecall.server.database import SQLStore
from openrecall.server.video.frame_extractor import FrameExtractor
from openrecall.server.video.metadata_resolver import resolve_frame_metadata

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Result of processing a single video chunk."""
    video_chunk_id: int
    total_frames_extracted: int = 0
    frames_after_dedup: int = 0
    frames_with_ocr: int = 0
    elapsed_seconds: float = 0.0
    error: Optional[str] = None


def _validate_frame_offset(
    frame, video_chunk_id, chunk_path,
    chunk_start_time, chunk_end_time, prev_offset,
) -> Optional[str]:
    """Return rejection reason string, or None if valid.

    Phase 1.5 offset guard: validates frame-to-chunk alignment.
    """
    source_key = str(getattr(frame, "path", "") or "").strip()
    if (
        video_chunk_id is None
        or frame.offset_index is None
        or chunk_path is None
        or not str(chunk_path).strip()
        or not source_key
    ):
        return "missing_required_fields"
    if frame.offset_index < 0:
        return "negative_offset"
    if frame.timestamp < chunk_start_time:
        return "timestamp_before_chunk_start"
    if chunk_end_time is not None and frame.timestamp > chunk_end_time:
        return "timestamp_after_chunk_end"
    if frame.offset_index < prev_offset:
        return "non_monotonic_offset"
    return None


class VideoChunkProcessor:
    """Processes a video chunk through the full pipeline.

    Pipeline per chunk:
    1. Extract frames via FrameExtractor (FFmpeg + MSSIM dedup)
    2. Validate frame offset alignment (Phase 1.5 offset guard)
    3. Resolve frame metadata via priority chain (Phase 1.5 resolver)
    4. Insert frame records into database (with focused/browser_url)
    5. Rename temp frame PNGs to {frame_id}.png
    6. Run OCR on each frame
    7. Insert OCR text (with real engine name) + FTS entries
    """

    def __init__(
        self,
        frame_extractor: Optional[FrameExtractor] = None,
        ocr_provider=None,
        sql_store: Optional[SQLStore] = None,
    ):
        self.frame_extractor = frame_extractor or FrameExtractor()
        self.sql_store = sql_store or SQLStore()
        self._ocr_provider = ocr_provider
        self._ocr_initialized = ocr_provider is not None

    def _get_ocr_provider(self):
        """Lazy-initialize OCR provider."""
        if not self._ocr_initialized:
            try:
                from openrecall.server.ai.factory import get_ocr_provider
                self._ocr_provider = get_ocr_provider()
            except Exception as e:
                logger.error(f"Failed to initialize OCR provider: {e}")
                self._ocr_provider = _FallbackOCRProvider()
            self._ocr_initialized = True
        return self._ocr_provider

    def process_chunk(
        self, video_chunk_id: int, chunk_path: str, chunk_start_time: float,
    ) -> ProcessingResult:
        """Process a single video chunk through the full pipeline.

        Args:
            video_chunk_id: Database ID of the video chunk.
            chunk_path: Path to the .mp4 file.
            chunk_start_time: Unix timestamp of the chunk's start.

        Returns:
            ProcessingResult with counts and timing.
        """
        result = ProcessingResult(video_chunk_id=video_chunk_id)
        t0 = time.perf_counter()

        try:
            # Step 1: Extract and deduplicate frames
            extracted = self.frame_extractor.extract_frames(
                chunk_path, video_chunk_id, chunk_start_time,
            )
            result.total_frames_extracted = len(extracted)
            result.frames_after_dedup = sum(1 for f in extracted if f.kept)

            # Phase 1.5: Get OCR provider and its engine name
            ocr_provider = self._get_ocr_provider()
            ocr_engine_name = getattr(ocr_provider, "engine_name", "unknown")

            # Phase 1.5: Get chunk metadata for resolver
            chunk_meta = self.sql_store.get_video_chunk_by_id(video_chunk_id) or {}

            # Phase 1.5: Determine chunk end time for offset guard
            chunk_end_time = chunk_meta.get("end_time")
            if chunk_end_time is None:
                chunk_end_time = chunk_start_time + settings.video_chunk_duration + 5.0

            prev_offset = -1

            for frame in extracted:
                if not frame.kept:
                    continue

                try:
                    # Phase 1.5: Offset guard validation
                    reject_reason = _validate_frame_offset(
                        frame, video_chunk_id, chunk_path,
                        chunk_start_time, chunk_end_time, prev_offset,
                    )
                    if reject_reason:
                        logger.warning(
                            "event=offset_guard_reject chunk_id=%d frame_id=%s "
                            "frame_offset=%d offset=%d source=frame_extractor "
                            "source_key=%s reason=%s chunk_start_ts=%.3f "
                            "chunk_end_ts=%s frame_ts=%.3f previous_offset=%d "
                            "timestamp_utc=%s",
                            video_chunk_id,
                            "unassigned",
                            frame.offset_index,
                            frame.offset_index,
                            str(frame.path),
                            reject_reason,
                            chunk_start_time,
                            f"{chunk_end_time:.3f}" if chunk_end_time is not None else "none",
                            frame.timestamp,
                            prev_offset,
                            datetime.datetime.now(datetime.timezone.utc).strftime(
                                "%Y-%m-%dT%H:%M:%SZ"
                            ),
                        )
                        continue

                    # Phase 1.5: Resolve metadata with frame > chunk > null priority
                    frame_meta = getattr(frame, "metadata", None)
                    resolved = resolve_frame_metadata(frame_meta, chunk_meta)
                    logger.debug(
                        "Frame %d metadata resolved: source=%s app=%s window=%s",
                        frame.offset_index, resolved.source,
                        resolved.app_name, resolved.window_name,
                    )

                    # Step 2: Insert frame record (Phase 1.5: with focused + browser_url)
                    frame_id = self.sql_store.insert_frame(
                        video_chunk_id=video_chunk_id,
                        offset_index=frame.offset_index,
                        timestamp=frame.timestamp,
                        app_name=resolved.app_name,
                        window_name=resolved.window_name,
                        focused=resolved.focused,
                        browser_url=resolved.browser_url,
                    )
                    if frame_id is None:
                        logger.error(f"Failed to insert frame record for offset {frame.offset_index}")
                        continue

                    prev_offset = frame.offset_index

                    # Step 3: Rename temp file to {frame_id}.png
                    final_path = settings.frames_path / f"{frame_id}.png"
                    try:
                        frame.path.rename(final_path)
                    except OSError:
                        # Cross-device: copy then delete
                        import shutil
                        shutil.copy2(str(frame.path), str(final_path))
                        frame.path.unlink(missing_ok=True)

                    # Step 4: Run OCR
                    text = ""
                    try:
                        text = ocr_provider.extract_text(str(final_path))
                    except Exception as e:
                        logger.warning(f"OCR failed for frame {frame_id}: {e}")

                    if text:
                        # Step 5: Insert OCR text (Phase 1.5: real engine name) + FTS
                        self.sql_store.insert_ocr_text(
                            frame_id, text, ocr_engine=ocr_engine_name,
                        )
                        self.sql_store.insert_ocr_text_fts(
                            frame_id,
                            text,
                            app_name=resolved.app_name or "",
                            window_name=resolved.window_name or "",
                        )
                        result.frames_with_ocr += 1

                except Exception as e:
                    logger.error(f"Failed processing frame offset {frame.offset_index}: {e}")
                    continue

        except Exception as e:
            result.error = str(e)
            logger.exception(f"Video chunk processing failed for chunk {video_chunk_id}")

        result.elapsed_seconds = time.perf_counter() - t0
        logger.info(
            f"Chunk {video_chunk_id} processed: "
            f"{result.frames_after_dedup} frames kept, "
            f"{result.frames_with_ocr} OCR'd in {result.elapsed_seconds:.1f}s"
        )
        return result


class _FallbackOCRProvider:
    """Fallback OCR that returns empty text."""
    engine_name = "fallback"

    def extract_text(self, image_path: str) -> str:
        return ""
