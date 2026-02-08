"""Video chunk processing pipeline: extract frames, OCR, index."""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from openrecall.shared.config import settings
from openrecall.server.database import SQLStore
from openrecall.server.video.frame_extractor import FrameExtractor

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


class VideoChunkProcessor:
    """Processes a video chunk through the full pipeline.

    Pipeline per chunk:
    1. Extract frames via FrameExtractor (FFmpeg + MSSIM dedup)
    2. Insert frame records into database
    3. Rename temp frame PNGs to {frame_id}.png
    4. Run OCR on each frame
    5. Insert OCR text + FTS entries
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

            ocr_provider = self._get_ocr_provider()
            chunk_meta = self.sql_store.get_video_chunk_by_id(video_chunk_id) or {}
            chunk_app_name = str(chunk_meta.get("app_name") or "")
            chunk_window_name = str(chunk_meta.get("window_name") or "")

            for frame in extracted:
                if not frame.kept:
                    continue

                try:
                    # Step 2: Insert frame record
                    frame_id = self.sql_store.insert_frame(
                        video_chunk_id=video_chunk_id,
                        offset_index=frame.offset_index,
                        timestamp=frame.timestamp,
                        app_name=chunk_app_name,
                        window_name=chunk_window_name,
                    )
                    if frame_id is None:
                        logger.error(f"Failed to insert frame record for offset {frame.offset_index}")
                        continue

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
                        # Step 5: Insert OCR text + FTS
                        self.sql_store.insert_ocr_text(frame_id, text)
                        self.sql_store.insert_ocr_text_fts(
                            frame_id,
                            text,
                            app_name=chunk_app_name,
                            window_name=chunk_window_name,
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
    def extract_text(self, image_path: str) -> str:
        return ""
