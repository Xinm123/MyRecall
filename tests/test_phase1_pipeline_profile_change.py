"""Tests for atomic restart behavior on pixel profile changes."""

import queue
import time
from unittest.mock import MagicMock

from openrecall.client.sck_stream import PixelFormatProfile, RawFrame
from openrecall.client.video_recorder import MonitorPipelineController


def test_profile_change_triggers_reconfigure_once():
    ffmpeg = MagicMock()
    ffmpeg.write_frame.return_value = None

    controller = MonitorPipelineController(
        monitor_id="monitor-1",
        ffmpeg_manager=ffmpeg,
        queue_maxsize=8,
    )

    p1 = PixelFormatProfile(
        pix_fmt="nv12",
        width=1920,
        height=1080,
        fps=30,
        color_range="tv",
    )
    p2 = PixelFormatProfile(
        pix_fmt="bgra",
        width=1920,
        height=1080,
        fps=30,
        color_range="tv",
    )

    controller.start(p1)
    assert ffmpeg.start_with_profile.call_count == 1

    controller.submit_frame(RawFrame(data=b"abc", profile=p1, pts_ns=1))
    controller.submit_frame(RawFrame(data=b"def", profile=p2, pts_ns=2))

    # Drain internal queue by manually pumping writer loop helper
    controller._drain_once_for_test()
    controller._drain_once_for_test()

    assert ffmpeg.reconfigure.call_count == 1
    ffmpeg.reconfigure.assert_called_with(p2)


def test_generation_mismatch_frame_is_dropped():
    ffmpeg = MagicMock()
    ffmpeg.write_frame.return_value = None

    controller = MonitorPipelineController(
        monitor_id="monitor-1",
        ffmpeg_manager=ffmpeg,
        queue_maxsize=2,
    )

    p1 = PixelFormatProfile("nv12", 1280, 720, 30, "tv")
    controller.start(p1)

    frame = RawFrame(data=b"frame", profile=p1, pts_ns=1)
    controller._enqueue_for_generation(frame, generation=99)
    controller._drain_once_for_test()

    assert controller.stats.dropped_generation_mismatch == 1
    ffmpeg.write_frame.assert_not_called()


def test_keepalive_writes_last_frame_when_source_quiet():
    ffmpeg = MagicMock()
    ffmpeg.write_frame.return_value = 0.001

    controller = MonitorPipelineController(
        monitor_id="monitor-1",
        ffmpeg_manager=ffmpeg,
        queue_maxsize=2,
    )

    profile = PixelFormatProfile("nv12", 1280, 720, 30, "tv")
    controller.start(profile)

    # Prime controller with one real frame.
    controller.submit_frame(RawFrame(data=b"frame-a", profile=profile, pts_ns=1))
    controller._drain_once_for_test()
    ffmpeg.write_frame.reset_mock()

    # Simulate source stall and ensure keepalive emits cached frame.
    controller._last_write_monotonic = time.monotonic() - 2.0
    controller._drain_once_for_test()

    ffmpeg.write_frame.assert_called_once_with(b"frame-a")


def test_keepalive_respects_interval():
    ffmpeg = MagicMock()
    ffmpeg.write_frame.return_value = 0.001

    controller = MonitorPipelineController(
        monitor_id="monitor-1",
        ffmpeg_manager=ffmpeg,
        queue_maxsize=2,
    )

    profile = PixelFormatProfile("nv12", 1280, 720, 30, "tv")
    controller.start(profile)
    controller.submit_frame(RawFrame(data=b"frame-a", profile=profile, pts_ns=1))
    controller._drain_once_for_test()
    ffmpeg.write_frame.reset_mock()

    controller._last_write_monotonic = time.monotonic()
    controller._drain_once_for_test()

    ffmpeg.write_frame.assert_not_called()
