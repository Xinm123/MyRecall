import sqlite3
from unittest import mock

import numpy as np


def test_search_applies_rerank_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENRECALL_RERANK_ENABLED", "true")
    monkeypatch.setenv("OPENRECALL_RERANK_TOPK", "2")

    import importlib
    import openrecall.shared.config
    importlib.reload(openrecall.shared.config)

    import openrecall.server.database
    importlib.reload(openrecall.server.database)
    db = openrecall.server.database
    db.create_db()

    import openrecall.server.app
    importlib.reload(openrecall.server.app)

    from openrecall.shared.config import settings

    emb = np.zeros(settings.embedding_dim, dtype=np.float32)
    ts1 = 1710000201
    ts2 = 1710000202
    db.insert_entry("TypeError A", ts1, emb, "App", "Win", "d1")
    db.insert_entry("TypeError B", ts2, emb, "App", "Win", "d2")

    with sqlite3.connect(str(settings.db_path)) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM entries WHERE timestamp=?", (ts1,))
        id1 = int(cur.fetchone()[0])
        cur.execute("SELECT id FROM entries WHERE timestamp=?", (ts2,))
        id2 = int(cur.fetchone()[0])

    with sqlite3.connect(str(settings.db_path)) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, app, title, text, description FROM entries ORDER BY timestamp ASC")
        rows = cur.fetchall()
        for row in rows:
            db.fts_upsert_entry(conn, entry_id=row[0], app=row[1], title=row[2], text=row[3], description=row[4])

    class _StubReranker:
        def rerank(self, query: str, candidates: list[dict]) -> list[dict]:
            out = []
            for c in candidates:
                cid = int(c["id"])
                score = 1.0 if cid == id2 else 0.0
                d = dict(c)
                d["rerank_score"] = score
                out.append(d)
            out.sort(key=lambda x: float(x.get("rerank_score") or 0.0), reverse=True)
            return out

    with mock.patch("openrecall.server.ai.factory.get_reranker_provider", return_value=_StubReranker()):
        client = openrecall.server.app.app.test_client()
        resp = client.get("/search?q=TypeError")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        pos1 = html.find(f"/screenshots/{ts1}.png")
        pos2 = html.find(f"/screenshots/{ts2}.png")
        assert pos1 != -1 and pos2 != -1
        assert pos2 < pos1
