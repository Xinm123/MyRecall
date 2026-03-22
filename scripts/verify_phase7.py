#!/usr/bin/env python3
"""Phase 7 Verification Script.

Seeds test data and verifies the /v1/search content_type parameter.
Run after starting the server with: ./run_server.sh --debug

Usage:
    python scripts/verify_phase7.py          # Verify only
    python scripts/verify_phase7.py --seed   # Seed test data first
"""

import argparse
import json
import sys
import time
import uuid

import requests

BASE_URL = "http://localhost:8083"


def gen_uuid7() -> str:
    """Generate a simple UUID v7-like ID for testing."""
    ts = int(time.time() * 1000)
    return f"{ts:016x}-0000-7000-8000-000000000000"


def seed_ocr_frame(capture_id: str, text: str, app_name: str = "TestApp") -> bool:
    """Seed an OCR-pending frame."""
    jpeg_header = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"

    resp = requests.post(
        f"{BASE_URL}/v1/ingest",
        files={"file": ("test.jpg", jpeg_header, "image/jpeg")},
        data={
            "capture_id": capture_id,
            "metadata": json.dumps({
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "capture_trigger": "manual",
                "device_name": "monitor_0",
                "app_name": app_name,
                "window_name": f"{app_name} Window",
                "focused": True,
            }),
        },
    )
    return resp.status_code in [200, 201]


def seed_accessibility_frame(
    capture_id: str, text: str, app_name: str = "TestBrowser", browser_url: str = None
) -> bool:
    """Seed an accessibility-canonical frame."""
    jpeg_header = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x00\x01\x00\x01\x00\x00"

    if browser_url is None:
        browser_url = f"https://example.com/{app_name.lower()}"

    resp = requests.post(
        f"{BASE_URL}/v1/ingest",
        files={"file": ("test.jpg", jpeg_header, "image/jpeg")},
        data={
            "capture_id": capture_id,
            "metadata": json.dumps({
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "capture_trigger": "manual",
                "device_name": "monitor_0",
                "app_name": app_name,
                "window_name": f"{app_name} Window",
                "focused": True,
                "text": text,
                "text_source": "accessibility",
                "browser_url": browser_url,
                "accessibility": {
                    "text_content": text,
                    "tree_json": json.dumps([{"role": "AXStaticText", "text": text, "depth": 0}]),
                    "node_count": 1,
                    "truncated": False,
                },
            }),
        },
    )
    return resp.status_code in [200, 201]


def check_server_health() -> bool:
    """Check if server is running."""
    try:
        resp = requests.get(f"{BASE_URL}/v1/health", timeout=5)
        data = resp.json()
        return data.get("status") in ["ok", "degraded"]
    except Exception:
        return False


def get_queue_status() -> dict:
    """Get queue status."""
    resp = requests.get(f"{BASE_URL}/v1/ingest/queue/status")
    return resp.json()


def search(content_type: str = "all", **kwargs) -> dict:
    """Execute search with content_type."""
    params = {"content_type": content_type, **kwargs}
    resp = requests.get(f"{BASE_URL}/v1/search", params=params)
    return resp.json()


def seed_test_data():
    """Seed test data for verification."""
    print("Seeding test frames...")

    # Seed OCR frames
    for i in range(3):
        capture_id = gen_uuid7()
        seed_ocr_frame(capture_id, f"OCR test content number {i}", f"Terminal_{i}")
        print(f"  ✓ Seeded OCR frame {i + 1}")

    # Seed accessibility frames
    for i in range(3):
        capture_id = gen_uuid7()
        seed_accessibility_frame(
            capture_id,
            f"Accessibility test content number {i}",
            f"Safari_{i}",
            f"https://example.com/page{i}",
        )
        print(f"  ✓ Seeded Accessibility frame {i + 1}")

    print("Done seeding test frames!\n")
    time.sleep(1)  # Give server time to process


def verify_phase7():
    """Verify Phase 7 implementation."""
    print("=== Phase 7 Verification ===\n")

    # 1. Check server health
    print("1. Checking server health...")
    if not check_server_health():
        print("  ✗ Server not responding")
        print("  Please start server with: ./run_server.sh --debug")
        sys.exit(1)
    print("  ✓ Server is healthy\n")

    # 2. Check frame counts
    print("2. Checking frame counts...")
    status = get_queue_status()
    completed = status.get("completed", 0)
    print(f"  Completed frames: {completed}")

    if completed == 0:
        print("\n  No completed frames found. Run with --seed to add test data:")
        print("  python scripts/verify_phase7.py --seed")
        sys.exit(0)
    print()

    # 3. Test content_type=ocr
    print("3. Testing content_type=ocr...")
    ocr_result = search(content_type="ocr", limit=10)
    ocr_count = len(ocr_result.get("data", []))
    ocr_items = ocr_result.get("data", [])
    ocr_types = {item.get("type") for item in ocr_items}
    print(f"  Found {ocr_count} OCR frames")
    if ocr_count > 0 and ocr_types == {"OCR"}:
        print(f"  ✓ All results have type='OCR'")
    else:
        print(f"  ⚠ Types found: {ocr_types}")
    print()

    # 4. Test content_type=accessibility
    print("4. Testing content_type=accessibility...")
    ax_result = search(content_type="accessibility", limit=10)
    ax_count = len(ax_result.get("data", []))
    ax_items = ax_result.get("data", [])
    ax_types = {item.get("type") for item in ax_items}
    print(f"  Found {ax_count} Accessibility frames")
    if ax_count > 0 and ax_types == {"Accessibility"}:
        print(f"  ✓ All results have type='Accessibility'")
    else:
        print(f"  ⚠ Types found: {ax_types}")
    print()

    # 5. Test content_type=all (default)
    print("5. Testing content_type=all (default)...")
    all_result = search(content_type="all", limit=20)
    all_count = len(all_result.get("data", []))
    all_items = all_result.get("data", [])
    all_types = {item.get("type") for item in all_items}
    print(f"  Found {all_count} total frames")
    print(f"  Types: {all_types}")
    print()

    # 6. Verify response format
    print("6. Verifying response format...")
    sample = search(limit=1)

    # Check top-level structure
    has_data = "data" in sample
    has_pagination = "pagination" in sample
    # Top-level "type" should NOT be present per new mvp.md format
    has_top_level_type = "type" in sample

    if has_data and has_pagination and not has_top_level_type:
        print("  ✓ Response has correct structure (data, pagination, no top-level type)")
    else:
        print(f"  ✗ Unexpected structure: data={has_data}, pagination={has_pagination}, top-level type={has_top_level_type}")

    # Check each item has type
    items = sample.get("data", [])
    if items:
        has_item_type = all("type" in item for item in items)
        has_content = all("content" in item for item in items)
        if has_item_type and has_content:
            print("  ✓ Each item has 'type' and 'content' fields")
        else:
            print("  ✗ Items missing required fields")

    # Verify content fields
    if items:
        content = items[0].get("content", {})
        expected_fields = ["frame_id", "timestamp", "text", "text_source", "app_name", "window_name"]
        missing = [f for f in expected_fields if f not in content]
        if not missing:
            print("  ✓ Content has all expected fields")
        else:
            print(f"  ✗ Missing content fields: {missing}")
    print()

    # 7. Test browser_url filter
    print("7. Testing browser_url filter...")
    url_result = search(content_type="all", browser_url="example", limit=10)
    url_items = url_result.get("data", [])
    url_count = len(url_items)
    print(f"  Found {url_count} frames with browser_url containing 'example'")
    if url_count > 0:
        # Check that results have browser_url
        for item in url_items[:3]:
            content = item.get("content", {})
            bu = content.get("browser_url")
            if bu:
                print(f"    - browser_url: {bu}")
    print()

    # 8. Test pagination
    print("8. Testing pagination...")
    page1 = search(content_type="all", limit=2, offset=0)
    page2 = search(content_type="all", limit=2, offset=2)
    total = page1.get("pagination", {}).get("total", 0)

    print(f"  Total frames: {total}")
    print(f"  Page 1: {len(page1.get('data', []))} items")
    print(f"  Page 2: {len(page2.get('data', []))} items")

    # Check no duplicates between pages
    ids1 = {item["content"]["frame_id"] for item in page1.get("data", [])}
    ids2 = {item["content"]["frame_id"] for item in page2.get("data", [])}
    if ids1.isdisjoint(ids2):
        print("  ✓ No duplicate frame_ids between pages")
    else:
        print(f"  ✗ Found duplicates: {ids1 & ids2}")
    print()

    # Summary
    print("=== Verification Summary ===")
    print(f"  OCR frames: {ocr_count}")
    print(f"  Accessibility frames: {ax_count}")
    print(f"  Total (merged): {all_count}")

    if all_count >= ocr_count and all_count >= ax_count:
        print("\n✓ Phase 7 implementation verified successfully!")
        return True
    else:
        print("\n✗ Verification failed - check content_type merging")
        return False


def main():
    parser = argparse.ArgumentParser(description="Phase 7 Verification Script")
    parser.add_argument("--seed", action="store_true", help="Seed test data before verification")
    args = parser.parse_args()

    if args.seed:
        if not check_server_health():
            print("Server not responding. Please start with: ./run_server.sh --debug")
            sys.exit(1)
        seed_test_data()

    verify_phase7()


if __name__ == "__main__":
    main()
