import sqlite3

import numpy as np


def test_search_renders_tags_and_snippet(flask_client):
    from openrecall.shared.config import settings
    from openrecall.server import database as db

    emb = np.zeros(settings.embedding_dim, dtype=np.float32)
    ts = 1710000300
    db.insert_entry("TypeError: boom", ts, emb, "App", "Win", "desc")

    with sqlite3.connect(str(settings.db_path)) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, app, title, text, description FROM entries WHERE timestamp=?", (ts,))
        row = cur.fetchone()
        db.fts_upsert_entry(conn, entry_id=row[0], app=row[1], title=row[2], text=row[3], description=row[4])

    resp = flask_client.get("/search?q=TypeError")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "关键词" in html
    assert "<mark>TypeError</mark>" in html
