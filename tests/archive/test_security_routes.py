import pytest


pytestmark = pytest.mark.security


@pytest.mark.parametrize("path", ["/screenshots/../app.py", "/static/../app.py"])
def test_no_path_traversal(flask_client, path):
    resp = flask_client.get(path)
    assert resp.status_code in (400, 404)

