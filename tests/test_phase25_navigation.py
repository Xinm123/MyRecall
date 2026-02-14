"""Phase 2.5 Navigation tests — nav links, icon highlighting, JS detection, regression.

Tests cover:
- Audio and Video nav links present in header
- Audio and Video icon macros rendered
- CSS highlighting rules for audio/video views
- JS currentPath detection includes audio/video
- Existing pages still return 200 (regression)
"""

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(flask_app):
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


# ===========================================================================
# Navigation Link Tests
# ===========================================================================

class TestNavLinks:

    def test_audio_link_in_header(self, client):
        resp = client.get("/")
        html = resp.data.decode()
        assert 'href="/audio"' in html

    def test_video_link_in_header(self, client):
        resp = client.get("/")
        html = resp.data.decode()
        assert 'href="/video"' in html

    def test_audio_icon_rendered(self, client):
        resp = client.get("/")
        html = resp.data.decode()
        # Audio icon: waveform SVG with title attribute
        assert 'title="Audio"' in html

    def test_video_icon_rendered(self, client):
        resp = client.get("/")
        html = resp.data.decode()
        assert 'title="Video"' in html


# ===========================================================================
# CSS Highlighting Tests
# ===========================================================================

class TestCSSHighlighting:

    def test_audio_css_rule_present(self, client):
        resp = client.get("/")
        html = resp.data.decode()
        assert 'html[data-current-view="audio"]' in html

    def test_video_css_rule_present(self, client):
        resp = client.get("/")
        html = resp.data.decode()
        assert 'html[data-current-view="video"]' in html


# ===========================================================================
# JS CurrentPath Detection
# ===========================================================================

class TestJSDetection:

    def test_audio_path_detection(self, client):
        resp = client.get("/audio")
        html = resp.data.decode()
        assert "'/audio'" in html

    def test_video_path_detection(self, client):
        resp = client.get("/video")
        html = resp.data.decode()
        assert "'/video'" in html


# ===========================================================================
# Regression Tests — Existing Pages Still Work
# ===========================================================================

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
