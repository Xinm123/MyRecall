import os


def main():
    try:
        import requests  # type: ignore
    except ImportError as e:
        raise SystemExit("requests 未安装，请先安装再运行该脚本") from e

    base_url = os.environ.get("OPENRECALL_BASE_URL", "http://localhost:8083")

    resp = requests.get(f"{base_url}/api/config", timeout=5)
    resp.raise_for_status()
    print("GET /api/config", resp.status_code, resp.json())


if __name__ == "__main__":
    main()

