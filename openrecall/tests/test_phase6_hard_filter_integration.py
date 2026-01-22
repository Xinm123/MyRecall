import importlib
from datetime import datetime

import numpy as np


def test_hard_filter_time_window(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))

    import openrecall.shared.config
    importlib.reload(openrecall.shared.config)
    settings = openrecall.shared.config.settings

    import openrecall.server.database
    importlib.reload(openrecall.server.database)
    db = openrecall.server.database
    db.create_db()

    from openrecall.server.query_parsing import parse_time_range

    now = datetime(2026, 1, 22, 15, 30, 0)

    def ts_of(dt: datetime) -> int:
        return int(dt.timestamp())

    emb = np.zeros(settings.embedding_dim, dtype=np.float32)
    db.insert_entry("t1", ts_of(datetime(2026, 1, 21, 13, 0, 0)), emb, "App", "Win", "d1")
    db.insert_entry("t2", ts_of(datetime(2026, 1, 21, 19, 0, 0)), emb, "App", "Win", "d2")
    db.insert_entry("t3", ts_of(datetime(2026, 1, 22, 13, 0, 0)), emb, "App", "Win", "d3")

    start_ts, end_ts, _ = parse_time_range("昨天下午", now=now)
    entries = db.get_entries_by_time_range(start_ts, end_ts)
    assert len(entries) == 1
    assert entries[0].timestamp == ts_of(datetime(2026, 1, 21, 13, 0, 0))
