import json
import urllib.request


def _call_api(method: str, url: str, data: dict | None = None, timeout: int = 5):
    payload = None
    headers = {}
    if data is not None:
        payload = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=payload, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, json.loads(response.read().decode())


def main():
    base_url = "http://localhost:8083"
    tests: list[tuple[str, str, str, dict | None]] = [
        ("GET config", "GET", "/api/config", None),
        ("Disable AI", "POST", "/api/config", {"ai_processing_enabled": False}),
        ("Disable recording", "POST", "/api/config", {"recording_enabled": False}),
        ("Disable upload", "POST", "/api/config", {"upload_enabled": False}),
        ("Heartbeat", "POST", "/api/heartbeat", None),
        (
            "Re-enable all",
            "POST",
            "/api/config",
            {"ai_processing_enabled": True, "recording_enabled": True, "upload_enabled": True},
        ),
    ]
    for name, method, path, body in tests:
        status, data = _call_api(method, f"{base_url}{path}", data=body, timeout=5)
        print(name, status, data if isinstance(data, dict) else type(data))


if __name__ == "__main__":
    main()

