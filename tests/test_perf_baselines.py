import pytest


pytestmark = pytest.mark.perf

pytest.importorskip("pytest_benchmark")


def test_health_endpoint_baseline(benchmark, flask_client):
    benchmark(lambda: flask_client.get("/api/health"))


def test_config_endpoint_baseline(benchmark, flask_client):
    benchmark(lambda: flask_client.get("/api/config"))

