"""Tests for row-wise stride/padding removal helpers."""

from openrecall.client.sck_stream import pack_bgra_plane, pack_nv12_planes


def test_pack_nv12_planes_removes_padding():
    # 4x2 NV12: Y plane has 2 rows, UV plane has 1 row.
    # Add two bytes of padding per row.
    y_stride = 6
    uv_stride = 6
    width = 4
    height = 2

    y_plane = bytes([
        1, 2, 3, 4, 99, 99,
        5, 6, 7, 8, 99, 99,
    ])
    uv_plane = bytes([
        10, 11, 12, 13, 77, 77,
    ])

    packed = pack_nv12_planes(
        y_plane=y_plane,
        uv_plane=uv_plane,
        width=width,
        height=height,
        y_stride=y_stride,
        uv_stride=uv_stride,
    )

    assert packed == bytes([1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13])


def test_pack_bgra_plane_removes_padding():
    width = 2
    height = 2
    row_bytes = width * 4
    stride = row_bytes + 4

    bgra_plane = bytes([
        1, 2, 3, 4, 5, 6, 7, 8, 99, 99, 99, 99,
        9, 10, 11, 12, 13, 14, 15, 16, 77, 77, 77, 77,
    ])

    packed = pack_bgra_plane(
        plane=bgra_plane,
        width=width,
        height=height,
        stride=stride,
    )

    assert packed == bytes([
        1, 2, 3, 4, 5, 6, 7, 8,
        9, 10, 11, 12, 13, 14, 15, 16,
    ])
