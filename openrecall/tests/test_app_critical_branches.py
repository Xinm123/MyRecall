import numpy as np


def test_index_sorts_entries_desc(flask_client):
    from openrecall.server.database import insert_pending_entry, insert_entry
    from openrecall.shared.config import settings
    from PIL import Image

    Image.fromarray(np.zeros((8, 8, 3), dtype=np.uint8)).save(settings.screenshots_path / "1700000000.png")
    Image.fromarray(np.zeros((8, 8, 3), dtype=np.uint8)).save(settings.screenshots_path / "1700003600.png")

    insert_pending_entry(timestamp=1700000000, app="A", title="T", image_path="x")
    insert_entry(text="t", timestamp=1700003600, embedding=np.zeros((8,), dtype=np.float32), app="B", title="T")

    resp = flask_client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert html.find("1700003600") < html.find("1700000000")


def test_timeline_renders(flask_client):
    resp = flask_client.get("/timeline")
    assert resp.status_code == 200


def test_static_and_screenshots_routes_serve_files(flask_client):
    from openrecall.shared.config import settings
    from PIL import Image

    ts = 1700000000
    Image.new("RGB", (4, 4), (0, 0, 0)).save(settings.screenshots_path / f"{ts}.png")

    resp1 = flask_client.get(f"/static/{ts}.png")
    assert resp1.status_code == 200
    resp2 = flask_client.get(f"/screenshots/{ts}.png")
    assert resp2.status_code == 200


def test_init_background_worker_attaches_worker(flask_app, monkeypatch):
    import openrecall.server.app as app_mod

    class DummyWorker:
        daemon = False
        started = False

        def start(self):
            self.started = True

    monkeypatch.setattr(app_mod, "reset_stuck_tasks", lambda: 1)

    import openrecall.server.worker as worker_mod
    monkeypatch.setattr(worker_mod, "ProcessingWorker", DummyWorker)

    app_mod.init_background_worker(flask_app)
    assert hasattr(flask_app, "worker")
    assert flask_app.worker.started is True


def test_search_ignores_invalid_datetime(flask_client):
    resp = flask_client.get("/search", query_string={"start_time": "not-a-date"})
    assert resp.status_code == 200


def test_search_with_query_sorts_by_similarity(flask_client, monkeypatch):
    import openrecall.server.app as app_mod
    from openrecall.server.database import insert_entry

    emb_low = np.zeros((8,), dtype=np.float32)
    emb_high = np.ones((8,), dtype=np.float32)
    insert_entry(text="low", timestamp=1700000000, embedding=emb_low, app="AppA", title="T")
    insert_entry(text="high", timestamp=1700003600, embedding=emb_high, app="AppB", title="T")

    monkeypatch.setattr(app_mod, "get_embedding", lambda q: np.ones((8,), dtype=np.float32))

    def fake_cosine(q, e):
        return float(e[0])

    monkeypatch.setattr(app_mod, "cosine_similarity", fake_cosine)

    resp = flask_client.get("/search", query_string={"q": "x"})
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert html.find("/screenshots/1700003600.png") < html.find("/screenshots/1700000000.png")
