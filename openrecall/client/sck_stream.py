"""Screen capture helpers and monitor sources.

This module provides:
- monitor discovery with stable monitor_id semantics
- raw frame profile/data types for FFmpeg stdin pipelines
- row-wise stride/padding removal for NV12/BGRA buffers
- smart frame buffer pooling with auto-growth safeguards
- optional ScreenCaptureKit source on macOS with mss fallback
"""

from __future__ import annotations

import ctypes
import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import mss

try:
    import ScreenCaptureKit  # type: ignore
    import CoreMedia  # type: ignore
    import Quartz  # type: ignore
    import objc  # type: ignore
    from Foundation import NSObject  # type: ignore
except Exception:  # pragma: no cover - platform dependent
    ScreenCaptureKit = None
    CoreMedia = None
    Quartz = None
    objc = None
    NSObject = object

try:
    import dispatch  # type: ignore
except Exception:  # pragma: no cover - optional
    dispatch = None


logger = logging.getLogger(__name__)

# CVPixelBuffer format constants (fourcc)
FOURCC_NV12_VIDEO_RANGE = 0x34323076  # '420v'
FOURCC_NV12_FULL_RANGE = 0x34323066  # '420f'
FOURCC_BGRA = 0x42475241  # 'BGRA'

# Structured ScreenCaptureKit startup error codes
SCK_ERR_PERMISSION_DENIED = "permission_denied"
SCK_ERR_NO_DISPLAYS = "no_displays"
SCK_ERR_DISPLAY_NOT_FOUND = "display_not_found"
SCK_ERR_START_TIMEOUT = "start_timeout"
SCK_ERR_STREAM_START_FAILED = "stream_start_failed"
SCK_ERR_UNKNOWN = "unknown"


class SCKStreamError(RuntimeError):
    """Structured startup error for SCK sources."""

    def __init__(self, code: str, detail: str, retryable: bool = True):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.retryable = retryable

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True)
class PixelFormatProfile:
    """Input profile for a rawvideo FFmpeg stdin pipeline."""

    pix_fmt: str
    width: int
    height: int
    fps: int
    color_range: str = "unknown"
    colorspace: str = "unknown"


@dataclass(frozen=True)
class RawFrame:
    """Raw frame bytes accompanied by its profile metadata."""

    data: bytes
    profile: PixelFormatProfile
    pts_ns: int


@dataclass(frozen=True)
class MonitorInfo:
    """Monitor descriptor used for monitor-id driven selection."""

    monitor_id: str
    name: str
    width: int
    height: int
    is_primary: bool
    backend: str
    fingerprint: str
    source_index: int


class FrameBufferPool:
    """Session-scoped reusable frame buffer with safe auto-growth."""

    def __init__(self, max_bytes: int):
        self.max_bytes = max(1, int(max_bytes))
        self._buffer = bytearray()
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        return len(self._buffer)

    def acquire(self, required_size: int) -> tuple[bytearray, bool]:
        """Return a writable buffer for required_size bytes.

        Returns (buffer, is_temporary). Temporary buffers are used only when
        required_size exceeds max_bytes to prevent persistent over-allocation.
        """
        if required_size <= 0:
            return bytearray(), True

        required = int(required_size)
        if required > self.max_bytes:
            logger.warning(
                "Frame size %s exceeds pool max %s, using temporary buffer",
                required,
                self.max_bytes,
            )
            return bytearray(required), True

        with self._lock:
            if len(self._buffer) < required:
                next_capacity = _next_power_of_two(required)
                self._buffer = bytearray(next_capacity)
            return self._buffer, False


class MonitorSourceBase:
    """Base class for monitor sources producing RawFrame callbacks."""

    def __init__(
        self,
        monitor: MonitorInfo,
        fps: int,
        on_frame: Callable[[RawFrame], None],
    ):
        self.monitor = monitor
        self.fps = max(1, int(fps))
        self.on_frame = on_frame

    def start(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def stop(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class MSSMonitorSource(MonitorSourceBase):
    """Cross-platform monitor source using mss BGRA frames."""

    def __init__(self, monitor: MonitorInfo, fps: int, on_frame: Callable[[RawFrame], None]):
        super().__init__(monitor, fps, on_frame)
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name=f"MSSSource-{self.monitor.monitor_id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._thread = None

    def _run_loop(self) -> None:
        frame_interval = 1.0 / float(self.fps)
        profile = PixelFormatProfile(
            pix_fmt="bgra",
            width=self.monitor.width,
            height=self.monitor.height,
            fps=self.fps,
            color_range="pc",
            colorspace="rgb",
        )

        with mss.mss() as sct:
            if self.monitor.source_index >= len(sct.monitors):
                logger.error(
                    "MSS source index out of bounds for monitor_id=%s",
                    self.monitor.monitor_id,
                )
                return

            target = sct.monitors[self.monitor.source_index]
            while not self._stop_event.is_set():
                loop_start = time.perf_counter()
                shot = sct.grab(target)
                frame = RawFrame(data=bytes(shot.bgra), profile=profile, pts_ns=time.time_ns())
                try:
                    self.on_frame(frame)
                except Exception:
                    logger.exception("MSS frame callback failed")

                elapsed = time.perf_counter() - loop_start
                sleep_s = frame_interval - elapsed
                if sleep_s > 0:
                    self._stop_event.wait(timeout=sleep_s)


if ScreenCaptureKit and Quartz and objc:  # pragma: no cover - macOS runtime only
    class _SCKOutputDelegate(NSObject):
        def initWithHandler_(self, handler):
            self = objc.super(_SCKOutputDelegate, self).init()
            if self is None:
                return None
            self._handler = handler
            return self

        def stream_didOutputSampleBuffer_ofType_(self, stream, sample_buffer, output_type):
            if output_type != ScreenCaptureKit.SCStreamOutputTypeScreen:
                return
            self._handler(sample_buffer)


class SCKMonitorSource(MonitorSourceBase):
    """macOS ScreenCaptureKit monitor source with CVPixelBuffer extraction."""

    def __init__(
        self,
        monitor: MonitorInfo,
        fps: int,
        on_frame: Callable[[RawFrame], None],
        pool_max_bytes: int,
        color_range_mode: str = "auto",
    ):
        super().__init__(monitor, fps, on_frame)
        self.color_range_mode = color_range_mode
        self.pool = FrameBufferPool(max_bytes=pool_max_bytes)
        self._stream = None
        self._delegate = None
        self._dispatch_queue = None
        self._running = False

    @property
    def available(self) -> bool:
        return ScreenCaptureKit is not None and Quartz is not None and objc is not None

    def start(self) -> None:
        if not self.available:
            raise SCKStreamError(
                code=SCK_ERR_UNKNOWN,
                detail="ScreenCaptureKit not available",
                retryable=False,
            )
        if self._running:
            return

        display, lookup_error = _get_sck_display_by_id(
            self.monitor.monitor_id,
            source_index=self.monitor.source_index,
        )
        if lookup_error is not None:
            raise lookup_error
        if display is None:
            raise SCKStreamError(
                code=SCK_ERR_DISPLAY_NOT_FOUND,
                detail=f"Display not found for monitor_id={self.monitor.monitor_id}",
                retryable=True,
            )

        config = ScreenCaptureKit.SCStreamConfiguration.alloc().init()
        config.setWidth_(int(self.monitor.width))
        config.setHeight_(int(self.monitor.height))
        min_interval = None
        if CoreMedia is not None and hasattr(CoreMedia, "CMTimeMake"):
            min_interval = CoreMedia.CMTimeMake(1, int(self.fps))
        elif hasattr(Quartz, "CMTimeMake"):
            min_interval = Quartz.CMTimeMake(1, int(self.fps))
        if min_interval is not None:
            config.setMinimumFrameInterval_(min_interval)
        config.setQueueDepth_(8)
        config.setPixelFormat_(FOURCC_NV12_VIDEO_RANGE)

        filter_obj = ScreenCaptureKit.SCContentFilter.alloc().initWithDisplay_excludingWindows_(display, [])
        stream = ScreenCaptureKit.SCStream.alloc().initWithFilter_configuration_delegate_(
            filter_obj,
            config,
            None,
        )

        self._dispatch_queue = None
        if dispatch is not None and hasattr(dispatch, "dispatch_queue_create"):
            queue_label = f"openrecall.sck.{self.monitor.monitor_id}".encode("utf-8")
            self._dispatch_queue = dispatch.dispatch_queue_create(queue_label, None)
        else:
            logger.warning(
                "dispatch_queue_create unavailable; sample handler queue is None "
                "(SCK start may timeout on this environment)"
            )
        self._delegate = _SCKOutputDelegate.alloc().initWithHandler_(self._handle_sample_buffer)

        ok, err = stream.addStreamOutput_type_sampleHandlerQueue_error_(
            self._delegate,
            ScreenCaptureKit.SCStreamOutputTypeScreen,
            self._dispatch_queue,
            None,
        )
        if not ok:
            error_detail = f"Failed to add SCK stream output: {err}"
            code, retryable = classify_sck_error(error_detail)
            if code not in {SCK_ERR_PERMISSION_DENIED, SCK_ERR_UNKNOWN}:
                code = SCK_ERR_STREAM_START_FAILED
            raise SCKStreamError(code=code, detail=error_detail, retryable=retryable)

        start_event = threading.Event()
        start_error: dict[str, object] = {"error": None}

        def _on_started(error):
            start_error["error"] = error
            start_event.set()

        stream.startCaptureWithCompletionHandler_(_on_started)
        if not start_event.wait(timeout=10.0):
            raise SCKStreamError(
                code=SCK_ERR_START_TIMEOUT,
                detail="Timed out starting SCK stream (no completion callback within 10s)",
                retryable=True,
            )
        if start_error["error"]:
            error_detail = f"SCK stream start failed: {start_error['error']}"
            code, retryable = classify_sck_error(error_detail)
            if code not in {SCK_ERR_PERMISSION_DENIED, SCK_ERR_START_TIMEOUT}:
                code = SCK_ERR_STREAM_START_FAILED
            raise SCKStreamError(code=code, detail=error_detail, retryable=retryable)

        self._stream = stream
        self._running = True

    def stop(self) -> None:
        if not self._running or self._stream is None:
            return

        stop_event = threading.Event()

        def _on_stopped(_error):
            stop_event.set()

        try:
            self._stream.stopCaptureWithCompletionHandler_(_on_stopped)
            stop_event.wait(timeout=5.0)
        except Exception:
            logger.exception("Failed to stop SCK stream")

        self._stream = None
        self._delegate = None
        self._dispatch_queue = None
        self._running = False

    def _handle_sample_buffer(self, sample_buffer) -> None:
        try:
            if CoreMedia is not None and hasattr(CoreMedia, "CMSampleBufferGetImageBuffer"):
                pixel_buffer = CoreMedia.CMSampleBufferGetImageBuffer(sample_buffer)
            elif hasattr(Quartz, "CMSampleBufferGetImageBuffer"):
                pixel_buffer = Quartz.CMSampleBufferGetImageBuffer(sample_buffer)
            else:
                raise RuntimeError("CMSampleBufferGetImageBuffer is unavailable")
            if pixel_buffer is None:
                return

            profile = pixel_profile_from_buffer(
                pixel_buffer,
                fps=self.fps,
                color_range_mode=self.color_range_mode,
            )
            frame_bytes = extract_packed_bytes(pixel_buffer, profile, self.pool)
            frame = RawFrame(data=frame_bytes, profile=profile, pts_ns=time.time_ns())
            self.on_frame(frame)
        except Exception:
            logger.exception("SCK frame extraction failed")


def _next_power_of_two(value: int) -> int:
    return 1 << (value - 1).bit_length()


def _copy_rows_tight(
    src: bytes | bytearray | memoryview,
    row_bytes: int,
    stride: int,
    rows: int,
    dst: bytearray,
    dst_offset: int,
) -> int:
    """Copy rows from a padded buffer into a tightly packed destination."""
    mv = memoryview(src)
    offset = dst_offset
    for row in range(rows):
        start = row * stride
        end = start + row_bytes
        dst[offset : offset + row_bytes] = mv[start:end]
        offset += row_bytes
    return offset


def pack_nv12_planes(
    y_plane: bytes | bytearray | memoryview,
    uv_plane: bytes | bytearray | memoryview,
    width: int,
    height: int,
    y_stride: int,
    uv_stride: int,
) -> bytes:
    """Pack NV12 plane data by removing per-row padding bytes."""
    y_rows = int(height)
    uv_rows = int(height) // 2
    packed_size = width * y_rows + width * uv_rows
    packed = bytearray(packed_size)

    offset = 0
    offset = _copy_rows_tight(y_plane, width, y_stride, y_rows, packed, offset)
    _copy_rows_tight(uv_plane, width, uv_stride, uv_rows, packed, offset)
    return bytes(packed)


def pack_bgra_plane(
    plane: bytes | bytearray | memoryview,
    width: int,
    height: int,
    stride: int,
) -> bytes:
    """Pack BGRA buffer by removing per-row padding bytes."""
    row_bytes = int(width) * 4
    packed = bytearray(row_bytes * int(height))
    _copy_rows_tight(plane, row_bytes, int(stride), int(height), packed, 0)
    return bytes(packed)


def pixel_profile_from_buffer(pixel_buffer, fps: int, color_range_mode: str = "auto") -> PixelFormatProfile:
    """Build PixelFormatProfile from a CVPixelBuffer."""
    if Quartz is None:
        raise RuntimeError("Quartz is required for CVPixelBuffer profile extraction")

    pixel_fmt = int(Quartz.CVPixelBufferGetPixelFormatType(pixel_buffer))
    width = int(Quartz.CVPixelBufferGetWidth(pixel_buffer))
    height = int(Quartz.CVPixelBufferGetHeight(pixel_buffer))

    if pixel_fmt in (FOURCC_NV12_VIDEO_RANGE, FOURCC_NV12_FULL_RANGE):
        pix_name = "nv12"
        default_range = "pc" if pixel_fmt == FOURCC_NV12_FULL_RANGE else "tv"
    elif pixel_fmt == FOURCC_BGRA:
        pix_name = "bgra"
        default_range = "pc"
    else:
        raise ValueError(f"Unsupported CVPixelBuffer format: {pixel_fmt}")

    color_range = default_range
    if color_range_mode in {"pc", "tv"}:
        color_range = color_range_mode

    colorspace = "unknown"
    attachments = Quartz.CVBufferGetAttachments(
        pixel_buffer,
        Quartz.kCVAttachmentMode_ShouldPropagate,
    )
    if attachments:
        matrix = attachments.get("CVImageBufferYCbCrMatrix")
        if matrix:
            colorspace = str(matrix)

    return PixelFormatProfile(
        pix_fmt=pix_name,
        width=width,
        height=height,
        fps=int(fps),
        color_range=color_range,
        colorspace=colorspace,
    )


def extract_packed_bytes(pixel_buffer, profile: PixelFormatProfile, pool: FrameBufferPool) -> bytes:
    """Extract tightly packed bytes from a CVPixelBuffer.

    Safety requirements:
    - Lock base address before any pointer access
    - Unlock in finally block for all code paths
    - Remove row padding explicitly
    """
    if Quartz is None:
        raise RuntimeError("Quartz is required for CVPixelBuffer extraction")

    Quartz.CVPixelBufferLockBaseAddress(pixel_buffer, 0)
    try:
        if profile.pix_fmt == "nv12":
            y_stride = int(Quartz.CVPixelBufferGetBytesPerRowOfPlane(pixel_buffer, 0))
            uv_stride = int(Quartz.CVPixelBufferGetBytesPerRowOfPlane(pixel_buffer, 1))
            y_height = int(Quartz.CVPixelBufferGetHeightOfPlane(pixel_buffer, 0))
            uv_height = int(Quartz.CVPixelBufferGetHeightOfPlane(pixel_buffer, 1))
            y_base = Quartz.CVPixelBufferGetBaseAddressOfPlane(pixel_buffer, 0)
            uv_base = Quartz.CVPixelBufferGetBaseAddressOfPlane(pixel_buffer, 1)

            y_plane = _pointer_to_bytes(y_base, y_stride * y_height)
            uv_plane = _pointer_to_bytes(uv_base, uv_stride * uv_height)
            packed = pack_nv12_planes(
                y_plane=y_plane,
                uv_plane=uv_plane,
                width=profile.width,
                height=profile.height,
                y_stride=y_stride,
                uv_stride=uv_stride,
            )
            pool.acquire(len(packed))
            return packed

        if profile.pix_fmt == "bgra":
            stride = int(Quartz.CVPixelBufferGetBytesPerRow(pixel_buffer))
            base = Quartz.CVPixelBufferGetBaseAddress(pixel_buffer)
            plane = _pointer_to_bytes(base, stride * profile.height)
            packed = pack_bgra_plane(
                plane=plane,
                width=profile.width,
                height=profile.height,
                stride=stride,
            )
            pool.acquire(len(packed))
            return packed

        raise ValueError(f"Unsupported extraction format: {profile.pix_fmt}")
    finally:
        Quartz.CVPixelBufferUnlockBaseAddress(pixel_buffer, 0)


def _pointer_to_bytes(ptr, size: int) -> bytes:
    if isinstance(ptr, (bytes, bytearray)):
        return bytes(ptr[:size])
    if isinstance(ptr, memoryview):
        return ptr[:size].tobytes()
    if hasattr(ptr, "as_buffer"):
        try:
            return bytes(ptr.as_buffer(size))
        except Exception:
            pass
    try:
        mv = memoryview(ptr)
        return mv[:size].tobytes()
    except Exception:
        pass
    try:
        return bytes(ptr[:size])
    except Exception:
        pass
    try:
        addr = int(ptr)
    except Exception as exc:  # pragma: no cover - defensive branch
        raise TypeError(f"Cannot convert pointer type {type(ptr)!r} to address") from exc
    return ctypes.string_at(addr, size)


def classify_sck_error(detail: str) -> tuple[str, bool]:
    """Classify an SCK error message into a normalized code and retryability."""
    lowered = (detail or "").lower()
    if any(token in lowered for token in ("permission", "not authorized", "denied", "screen recording")):
        return SCK_ERR_PERMISSION_DENIED, True
    if any(token in lowered for token in ("timeout", "timed out")):
        return SCK_ERR_START_TIMEOUT, True
    if any(token in lowered for token in ("no display", "no monitor", "empty content", "no displays")):
        return SCK_ERR_NO_DISPLAYS, True
    if "not found" in lowered:
        return SCK_ERR_DISPLAY_NOT_FOUND, True
    if "start failed" in lowered or "add sck stream output" in lowered:
        return SCK_ERR_STREAM_START_FAILED, True
    return SCK_ERR_UNKNOWN, True


def list_monitors_detailed() -> tuple[list[MonitorInfo], Optional[SCKStreamError]]:
    """Discover monitors with optional structured startup error context."""
    monitors, error = _list_monitors_sck_detailed()
    if monitors:
        return monitors, None
    if error and error.code != SCK_ERR_UNKNOWN:
        return [], error

    fallback = _list_monitors_mss()
    if fallback:
        return fallback, None
    return [], error or SCKStreamError(
        code=SCK_ERR_NO_DISPLAYS,
        detail="No monitors found from SCK or MSS discovery",
        retryable=True,
    )


def list_monitors() -> list[MonitorInfo]:
    """Discover monitors, preferring ScreenCaptureKit IDs on macOS."""
    monitors, _error = list_monitors_detailed()
    return monitors


def select_monitors(primary_only: bool, monitor_ids: list[str] | None) -> list[MonitorInfo]:
    available = list_monitors()
    if not available:
        return []

    selected = available
    normalized_ids = {m.strip() for m in (monitor_ids or []) if m.strip()}
    if normalized_ids:
        selected = [m for m in available if m.monitor_id in normalized_ids]

    if primary_only and selected:
        primary = [m for m in selected if m.is_primary]
        return primary[:1] if primary else selected[:1]

    return selected


def create_monitor_source(
    monitor: MonitorInfo,
    fps: int,
    on_frame: Callable[[RawFrame], None],
    pool_max_bytes: int,
    color_range_mode: str,
) -> MonitorSourceBase:
    """Build an active monitor source (SCK on macOS, otherwise MSS)."""
    if monitor.backend == "sck":
        source = SCKMonitorSource(
            monitor=monitor,
            fps=fps,
            on_frame=on_frame,
            pool_max_bytes=pool_max_bytes,
            color_range_mode=color_range_mode,
        )
        if source.available:
            return source
    return MSSMonitorSource(monitor=monitor, fps=fps, on_frame=on_frame)


def _list_monitors_mss() -> list[MonitorInfo]:
    monitors: list[MonitorInfo] = []
    try:
        with mss.mss() as sct:
            for index in range(1, len(sct.monitors)):
                mon = sct.monitors[index]
                width = int(mon.get("width", 0))
                height = int(mon.get("height", 0))
                left = int(mon.get("left", 0))
                top = int(mon.get("top", 0))
                is_primary = index == 1
                monitor_id = str(index)
                monitors.append(
                    MonitorInfo(
                        monitor_id=monitor_id,
                        name=f"monitor-{monitor_id}",
                        width=width,
                        height=height,
                        is_primary=is_primary,
                        backend="mss",
                        fingerprint=f"{width}x{height}:{left}:{top}:{int(is_primary)}",
                        source_index=index,
                    )
                )
    except Exception:
        logger.exception("Failed to enumerate monitors via mss")
    return monitors


def _list_monitors_sck_detailed(
    timeout: float = 3.0,
    attempts: int = 2,
) -> tuple[list[MonitorInfo], Optional[SCKStreamError]]:
    if ScreenCaptureKit is None:
        return [], None
    displays, error = _get_sck_displays_detailed(timeout=timeout, attempts=attempts)
    if not displays:
        return [], error

    monitors: list[MonitorInfo] = []
    for idx, display in enumerate(displays):
        display_id = int(display.displayID())
        width = int(display.width())
        height = int(display.height())
        is_primary = idx == 0
        monitors.append(
            MonitorInfo(
                monitor_id=str(display_id),
                name=f"display-{display_id}",
                width=width,
                height=height,
                is_primary=is_primary,
                backend="sck",
                fingerprint=f"{width}x{height}:{int(is_primary)}",
                source_index=idx + 1,
            )
        )
    return monitors, None


def _list_monitors_sck(timeout: float = 3.0) -> list[MonitorInfo]:
    monitors, _error = _list_monitors_sck_detailed(timeout=timeout)
    return monitors


def _get_sck_display_by_id(
    monitor_id: str,
    timeout: float = 3.0,
    source_index: int = 0,
):
    displays, error = _get_sck_displays_detailed(timeout=timeout)
    if not displays:
        return None, error

    wanted = str(monitor_id)
    for display in displays:
        if str(int(display.displayID())) == wanted:
            return display, None

    # Defensive fallback: ID lookup may occasionally drift between calls; use
    # source index discovered during monitor selection.
    if source_index > 0 and source_index <= len(displays):
        fallback = displays[source_index - 1]
        logger.warning(
            "SCK display id=%s not found; falling back to source_index=%s (display_id=%s)",
            monitor_id,
            source_index,
            int(fallback.displayID()),
        )
        return fallback, None

    return None, SCKStreamError(
        code=SCK_ERR_DISPLAY_NOT_FOUND,
        detail=f"Display not found for monitor_id={monitor_id}",
        retryable=True,
    )


def _get_sck_displays(timeout: float = 3.0, attempts: int = 2):
    displays, _error = _get_sck_displays_detailed(timeout=timeout, attempts=attempts)
    return displays


def _get_sck_displays_detailed(
    timeout: float = 3.0,
    attempts: int = 2,
) -> tuple[list[object], Optional[SCKStreamError]]:
    if ScreenCaptureKit is None:
        return [], None

    last_error: Optional[SCKStreamError] = None
    for attempt in range(1, max(1, attempts) + 1):
        content_holder: dict[str, object] = {"content": None, "error": None}
        done = threading.Event()

        def _on_content(content, error):
            content_holder["content"] = content
            content_holder["error"] = error
            done.set()

        try:
            ScreenCaptureKit.SCShareableContent.getShareableContentWithCompletionHandler_(_on_content)
        except Exception:
            logger.debug("SCK shareable content call failed (attempt %s)", attempt, exc_info=True)
            last_error = SCKStreamError(
                code=SCK_ERR_UNKNOWN,
                detail=f"SCK shareable content call failed on attempt {attempt}",
                retryable=True,
            )
            continue

        if not done.wait(timeout=timeout):
            logger.debug("SCK shareable content timeout (attempt %s)", attempt)
            last_error = SCKStreamError(
                code=SCK_ERR_START_TIMEOUT,
                detail=f"SCK shareable content timeout on attempt {attempt}",
                retryable=True,
            )
            continue

        if content_holder["error"]:
            detail = str(content_holder["error"])
            code, retryable = classify_sck_error(detail)
            if code == SCK_ERR_START_TIMEOUT:
                code = SCK_ERR_UNKNOWN
            logger.debug(
                "SCK monitor discovery failed (attempt=%s code=%s retryable=%s detail=%s)",
                attempt,
                code,
                retryable,
                detail,
            )
            last_error = SCKStreamError(code=code, detail=detail, retryable=retryable)
            continue

        content = content_holder["content"]
        if not content:
            logger.debug("SCK monitor discovery returned empty content (attempt %s)", attempt)
            last_error = SCKStreamError(
                code=SCK_ERR_NO_DISPLAYS,
                detail=f"SCK monitor discovery returned empty content on attempt {attempt}",
                retryable=True,
            )
            continue

        try:
            displays = list(content.displays())
        except Exception:
            logger.debug("SCK displays() failed (attempt %s)", attempt, exc_info=True)
            last_error = SCKStreamError(
                code=SCK_ERR_UNKNOWN,
                detail=f"SCK displays() failed on attempt {attempt}",
                retryable=True,
            )
            continue

        if displays:
            return displays, None

        last_error = SCKStreamError(
            code=SCK_ERR_NO_DISPLAYS,
            detail=f"SCK monitor discovery returned 0 displays on attempt {attempt}",
            retryable=True,
        )

    return [], last_error or SCKStreamError(
        code=SCK_ERR_NO_DISPLAYS,
        detail="SCK monitor discovery returned no displays",
        retryable=True,
    )
