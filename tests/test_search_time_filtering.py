from datetime import datetime

import numpy as np


def _to_datetime_local(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H:%M")


def test_search_filters_by_start_time(flask_client):
    from openrecall.server.database import insert_entry

    emb = np.zeros((8,), dtype=np.float32)
    base = 1700000000
    stamps = [base, base + 3600, base + 7200]
    for ts in stamps:
        insert_entry(text="t", timestamp=ts, embedding=emb, app="App", title="Title")

    resp = flask_client.get("/search", query_string={"start_time": _to_datetime_local(stamps[1])})
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert f"/screenshots/{stamps[2]}.png" in html
    assert f"/screenshots/{stamps[1]}.png" in html
    assert f"/screenshots/{stamps[0]}.png" not in html


def test_search_filters_by_end_time_inclusive_minute(flask_client):
    from openrecall.server.database import insert_entry

    emb = np.zeros((8,), dtype=np.float32)
    base = 1700000000
    stamps = [base, base + 3600, base + 7200]
    for ts in stamps:
        insert_entry(text="t", timestamp=ts, embedding=emb, app="App", title="Title")

    resp = flask_client.get("/search", query_string={"end_time": _to_datetime_local(stamps[1])})
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert f"/screenshots/{stamps[0]}.png" in html
    assert f"/screenshots/{stamps[1]}.png" in html
    assert f"/screenshots/{stamps[2]}.png" not in html


def test_search_swaps_start_end_when_reversed(flask_client):
    from openrecall.server.database import insert_entry

    emb = np.zeros((8,), dtype=np.float32)
    base = 1700000000
    stamps = [base, base + 3600, base + 7200]
    for ts in stamps:
        insert_entry(text="t", timestamp=ts, embedding=emb, app="App", title="Title")

    resp = flask_client.get(
        "/search",
        query_string={"start_time": _to_datetime_local(stamps[2]), "end_time": _to_datetime_local(stamps[0])},
    )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    for ts in stamps:
        assert f"/screenshots/{ts}.png" in html


def test_search_without_query_shows_no_match_score(flask_client):
    from openrecall.server.database import insert_entry

    emb = np.zeros((8,), dtype=np.float32)
    ts = 1700000000
    insert_entry(text="t", timestamp=ts, embedding=emb, app="App", title="Title")

    resp = flask_client.get("/search", query_string={"start_time": _to_datetime_local(ts)})
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Match:" in html
    assert "—" in html

