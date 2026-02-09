"""Frame extraction from video chunks with MSSIM-based deduplication."""

import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import numpy as np
from PIL import Image

from openrecall.shared.config import settings
from openrecall.shared.image_utils import compute_similarity

logger = logging.getLogger(__name__)


@dataclass
class ExtractedFrame:
    """Represents a frame extracted from a video chunk."""
    path: Path
    offset_index: int
    timestamp: float
    kept: bool = True
    metadata: Optional[dict] = None


class FrameExtractor:
    """Extracts frames from video chunks and deduplicates via MSSIM.

    Uses FFmpeg to extract frames at a configurable interval, then
    compares consecutive frames using MSSIM to remove near-duplicates.
    """

    def __init__(
        self,
        extraction_interval: Optional[float] = None,
        dedup_threshold: Optional[float] = None,
        frames_dir: Optional[Path] = None,
    ):
        self.extraction_interval = extraction_interval or settings.frame_extraction_interval
        self.dedup_threshold = dedup_threshold or settings.frame_dedup_threshold
        self.frames_dir = frames_dir or settings.frames_path
        self.frames_dir.mkdir(parents=True, exist_ok=True)

    def extract_frames(
        self,
        chunk_path: str,
        video_chunk_id: int,
        chunk_start_time: float,
    ) -> List[ExtractedFrame]:
        """Extract and deduplicate frames from a video chunk.

        Args:
            chunk_path: Path to the .mp4 video chunk file.
            video_chunk_id: Database ID of the video chunk.
            chunk_start_time: Unix timestamp of the chunk's start.

        Returns:
            List of ExtractedFrame objects (only kept=True frames are useful).
        """
        with tempfile.TemporaryDirectory(prefix="openrecall_frames_") as tmpdir:
            raw_frames = self._run_ffmpeg_extraction(chunk_path, tmpdir)

            if not raw_frames:
                logger.warning(f"No frames extracted from {chunk_path}")
                return []

            frames: List[ExtractedFrame] = []
            last_kept_array: Optional[np.ndarray] = None

            for idx, frame_path in enumerate(raw_frames):
                timestamp = chunk_start_time + (idx * self.extraction_interval)
                try:
                    img = Image.open(frame_path).convert("RGB")
                    img_array = np.array(img)
                except Exception as e:
                    logger.error(f"Failed to load frame {frame_path}: {e}")
                    continue

                kept = True
                if last_kept_array is not None:
                    similarity = compute_similarity(img_array, last_kept_array)
                    if similarity >= self.dedup_threshold:
                        kept = False

                if kept:
                    last_kept_array = img_array
                    # Copy to persistent location (will be renamed to {frame_id}.png later)
                    persist_path = self.frames_dir / f"tmp_{video_chunk_id}_{idx}.png"
                    img.save(str(persist_path), format="PNG")
                    frames.append(ExtractedFrame(
                        path=persist_path,
                        offset_index=idx,
                        timestamp=timestamp,
                        kept=True,
                    ))

            total = len(raw_frames)
            kept_count = len(frames)
            logger.info(
                f"Extracted {total} raw frames, kept {kept_count} after dedup "
                f"(threshold={self.dedup_threshold}) from chunk {video_chunk_id}"
            )
            return frames

    def extract_single_frame(
        self, chunk_path: str, offset_seconds: float,
    ) -> Optional[Path]:
        """Extract a single frame from a video at a given offset.

        Used for on-demand frame serving when the pre-extracted PNG is missing.

        Args:
            chunk_path: Path to the video chunk file.
            offset_seconds: Time offset in seconds from the start of the chunk.

        Returns:
            Path to the extracted frame PNG, or None on failure.
        """
        with tempfile.TemporaryDirectory(prefix="openrecall_single_") as tmpdir:
            output_path = Path(tmpdir) / "frame.png"
            cmd = [
                "ffmpeg", "-nostdin",
                "-ss", str(offset_seconds),
                "-i", chunk_path,
                "-frames:v", "1",
                "-q:v", "2",
                "-y",
                str(output_path),
            ]
            try:
                subprocess.run(
                    cmd, capture_output=True, check=True, timeout=30,
                )
                if output_path.exists():
                    # Move to frames dir with a temp name
                    dest = self.frames_dir / f"ondemand_{Path(chunk_path).stem}_{offset_seconds:.1f}.png"
                    output_path.rename(dest)
                    return dest
            except subprocess.CalledProcessError as e:
                logger.error(f"FFmpeg single frame extraction failed: {e.stderr.decode()[:200]}")
            except subprocess.TimeoutExpired:
                logger.error("FFmpeg single frame extraction timed out")
            except Exception as e:
                logger.error(f"Single frame extraction error: {e}")
        return None

    def _run_ffmpeg_extraction(self, chunk_path: str, output_dir: str) -> List[Path]:
        """Run FFmpeg to extract frames at the configured interval.

        Args:
            chunk_path: Path to the video file.
            output_dir: Directory to write extracted frames.

        Returns:
            Sorted list of frame file paths.
        """
        output_pattern = str(Path(output_dir) / "frame_%04d.png")
        cmd = [
            "ffmpeg", "-nostdin",
            "-i", chunk_path,
            "-vf", f"fps=1/{self.extraction_interval}",
            "-q:v", "2",
            "-y",
            output_pattern,
        ]
        try:
            subprocess.run(
                cmd, capture_output=True, check=True, timeout=300,
            )
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode()[:500] if e.stderr else ""
            logger.error(f"FFmpeg frame extraction failed: {stderr}")
            return []
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg frame extraction timed out (300s)")
            return []
        except Exception as e:
            logger.error(f"FFmpeg extraction error: {e}")
            return []

        frames = sorted(Path(output_dir).glob("frame_*.png"))
        return frames
