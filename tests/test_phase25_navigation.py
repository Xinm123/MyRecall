"""Phase 2.6 navigation tests — primary flow must not expose audio entrypoints."""

import pytest


@pytest.fixture
def client(flask_app):
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


class TestNavLinks:
    def test_audio_link_removed_from_header(self, client):
        resp = client.get("/")
        html = resp.data.decode()
        assert 'href="/audio"' not in html

    def test_video_link_in_header(self, client):
        resp = client.get("/")
        html = resp.data.decode()
        assert 'href="/video"' in html

    def test_audio_icon_not_rendered_in_header(self, client):
        resp = client.get("/")
        html = resp.data.decode()
        assert 'title="Audio"' not in html

    def test_video_icon_rendered(self, client):
        resp = client.get("/")
        html = resp.data.decode()
        assert 'title="Video"' in html


class TestCSSHighlighting:
    def test_audio_css_rule_removed(self, client):
        resp = client.get("/")
        html = resp.data.decode()
        assert 'html[data-current-view="audio"]' not in html

    def test_video_css_rule_present(self, client):
        resp = client.get("/")
        html = resp.data.decode()
        assert 'html[data-current-view="video"]' in html


class TestJSDetection:
    def test_audio_path_detection_removed(self, client):
        resp = client.get("/audio")
        html = resp.data.decode()
        assert "currentPath === '/audio'" not in html

    def test_video_path_detection(self, client):
        resp = client.get("/video")
        html = resp.data.decode()
        assert "'/video'" in html


class TestExistingPagesRegression:
    def test_index_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_timeline_returns_200(self, client):
        resp = client.get("/timeline")
        assert resp.status_code == 200

    def test_search_returns_200(self, client):
        resp = client.get("/search")
        assert resp.status_code == 200

    def test_audio_returns_200(self, client):
        resp = client.get("/audio")
        assert resp.status_code == 200

    def test_video_returns_200(self, client):
        resp = client.get("/video")
        assert resp.status_code == 200
