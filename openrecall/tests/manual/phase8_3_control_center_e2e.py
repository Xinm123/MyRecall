import json
import subprocess
import sys
import time
from urllib import error, request


def _wait_until_ready(url: str, timeout_s: int = 30) -> None:
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            with request.urlopen(url, timeout=1):
                return
        except (error.URLError, Exception):
            time.sleep(1)
    raise TimeoutError(f"Server not ready: {url}")


def _get_json(url: str) -> dict:
    with request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read().decode())


def main():
    base_url = "http://localhost:8083"
    proc = subprocess.Popen([sys.executable, "-m", "openrecall.server"])
    try:
        _wait_until_ready(f"{base_url}/")
        print(_get_json(f"{base_url}/api/config"))
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == "__main__":
    main()

