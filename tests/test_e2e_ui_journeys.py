import threading
from datetime import datetime

import pytest


pytestmark = pytest.mark.e2e

sync_api = pytest.importorskip("playwright.sync_api")


def _to_datetime_local(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H:%M")


@pytest.fixture
def e2e_base_url(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))

    import importlib
    import openrecall.shared.config
    importlib.reload(openrecall.shared.config)

    import openrecall.server.database
    importlib.reload(openrecall.server.database)
    openrecall.server.database.create_db()

    from openrecall.shared.config import settings

    from PIL import Image
    import numpy as np

    ts1 = 1700000000
    ts2 = 1700003600
    for ts, app, title in [(ts1, "AppA", "TitleA"), (ts2, "AppB", "TitleB")]:
        img = Image.fromarray(np.zeros((32, 32, 3), dtype=np.uint8))
        img.save(settings.screenshots_path / f"{ts}.png")
        openrecall.server.database.insert_entry(
            text="t",
            timestamp=ts,
            embedding=np.zeros((8,), dtype=np.float32),
            app=app,
            title=title,
        )

    import openrecall.server.app
    importlib.reload(openrecall.server.app)
    app = openrecall.server.app.app
    app.config["TESTING"] = True

    from werkzeug.serving import make_server

    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        yield base_url
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_grid_modal_navigation_and_meta(e2e_base_url):
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{e2e_base_url}/", wait_until="networkidle")

        page.locator(".js-open-modal").first.click()
        modal = page.locator("#imageModal")
        modal.wait_for(state="visible")

        count = modal.locator('[data-role="modal-count"]').inner_text()
        assert count.startswith("第 ")

        app_text = modal.locator('[data-role="modal-app"]').inner_text()
        assert app_text in ("AppA", "AppB")

        page.locator("#imageModal .modal-nav.next").click()
        count2 = modal.locator('[data-role="modal-count"]').inner_text()
        assert count2 != count

        page.keyboard.press("Escape")
        assert not modal.evaluate("el => el.classList.contains('active')")
        browser.close()


def test_search_time_filtering_smoke(e2e_base_url):
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{e2e_base_url}/search?start_time={_to_datetime_local(1700003600)}", wait_until="networkidle")
        assert page.locator(".card").count() >= 1
        browser.close()

