import os
from pathlib import Path

import pytest
from PIL import Image

from openrecall.client import spool


@pytest.mark.unit
def test_spool_enqueue_commits_jpg_and_json_with_replace(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(spool, "_uuid_v7", lambda: "capture-001")

    calls: list[tuple[Path, Path]] = []
    original_replace = os.replace

    def tracking_replace(
        src: str | os.PathLike[str], dst: str | os.PathLike[str]
    ) -> None:
        src_path = Path(src)
        dst_path = Path(dst)
        calls.append((src_path, dst_path))
        original_replace(src_path, dst_path)

    monkeypatch.setattr(spool.os, "replace", tracking_replace)

    queue = spool.SpoolQueue(storage_dir=tmp_path)
    image = Image.new("RGB", (2, 2), color=(120, 45, 90))

    capture_id = queue.enqueue(image, {"app": "TestApp"})

    assert capture_id == "capture-001"
    assert (tmp_path / "capture-001.jpg").exists()
    assert (tmp_path / "capture-001.json").exists()
    assert not list(tmp_path.glob("*.tmp"))

    assert len(calls) == 2
    assert calls[0] == (tmp_path / "capture-001.jpg.tmp", tmp_path / "capture-001.jpg")
    assert calls[1] == (
        tmp_path / "capture-001.json.tmp",
        tmp_path / "capture-001.json",
    )


@pytest.mark.unit
def test_spool_init_removes_orphan_jpg_without_json(tmp_path: Path) -> None:
    orphan_jpg = tmp_path / "orphan.jpg"
    orphan_jpg.write_bytes(b"jpeg")

    paired_jpg = tmp_path / "paired.jpg"
    paired_json = tmp_path / "paired.json"
    paired_jpg.write_bytes(b"jpeg")
    paired_json.write_text("{}", encoding="utf-8")

    spool.SpoolQueue(storage_dir=tmp_path)

    assert not orphan_jpg.exists()
    assert paired_jpg.exists()
    assert paired_json.exists()
