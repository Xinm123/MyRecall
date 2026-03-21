#!/usr/bin/env python3
"""Manual verification script for Phase 6 query helpers.

Usage:
    python scripts/verify_phase6.py

Prerequisites:
    - Server running with some captured frames
    - Or run with --create-test-data to create test frames first
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openrecall.server.database.frames_store import FramesStore
from openrecall.server.database.migrations_runner import run_migrations
from openrecall.shared.config import settings


def create_test_data(store: FramesStore) -> None:
    """Create test frames with accessibility data."""
    print("\n📝 Creating test data...")

    # Create 3 Safari frames
    for i in range(3):
        elements = [
            {"role": "AXStaticText", "text": f"Safari content {i}", "depth": 0},
            {"role": "AXLink", "text": "https://example.com", "depth": 0},
            {"role": "AXButton", "text": "Click me", "depth": 0},  # Not text-like
        ]
        frame_id, _ = store.claim_frame(
            capture_id=f"test-safari-{i}",
            metadata={
                "timestamp": f"2026-03-21T10:0{i}:00Z",
                "app_name": "Safari",
                "window_name": "Safari Window",
                "browser_url": "https://example.com",
            },
        )
        store.complete_accessibility_frame(
            frame_id=frame_id,
            text=f"Safari content {i}",
            browser_url="https://example.com",
            content_hash=None,
            simhash=None,
            accessibility_tree_json=json.dumps(elements),
            accessibility_text_content=f"Safari content {i}",
            accessibility_node_count=len(elements),
            accessibility_truncated=False,
            elements=elements,
        )
        print(f"   Created Safari frame {frame_id}")

    # Create 5 Mail frames
    for i in range(5):
        elements = [
            {"role": "line", "text": f"Email line {i}", "depth": 0},
            {"role": "paragraph", "text": f"Email paragraph {i}", "depth": 0},
        ]
        frame_id, _ = store.claim_frame(
            capture_id=f"test-mail-{i}",
            metadata={
                "timestamp": f"2026-03-21T11:0{i}:00Z",
                "app_name": "Mail",
                "window_name": "Mail Window",
            },
        )
        store.complete_accessibility_frame(
            frame_id=frame_id,
            text=f"Email line {i} Email paragraph {i}",
            browser_url=None,
            content_hash=None,
            simhash=None,
            accessibility_tree_json=json.dumps(elements),
            accessibility_text_content=f"Email line {i} Email paragraph {i}",
            accessibility_node_count=len(elements),
            accessibility_truncated=False,
            elements=elements,
        )
        print(f"   Created Mail frame {frame_id}")

    # Create 1 pending frame (should not be counted)
    store.claim_frame(
        capture_id="test-pending",
        metadata={
            "timestamp": "2026-03-21T12:00:00Z",
            "app_name": "Notes",
        },
    )
    print("   Created pending frame (should not appear in queries)")

    print("✅ Test data created!\n")


def verify_activity_summary_apps(store: FramesStore) -> bool:
    """Verify get_activity_summary_apps."""
    print("1️⃣  Testing get_activity_summary_apps...")

    apps = store.get_activity_summary_apps(
        start_time="2026-03-21T00:00:00Z",
        end_time="2026-03-21T23:59:59Z",
    )

    print(f"   Result: {json.dumps(apps, indent=4)}")

    # Verify basic structure
    assert isinstance(apps, list), "Expected list"
    for app in apps:
        assert "name" in app, "Missing 'name' field"
        assert "frame_count" in app, "Missing 'frame_count' field"
        assert "minutes" in app, "Missing 'minutes' field"

    # Verify Mail has more frames than Safari (test data)
    mail_app = next((a for a in apps if a["name"] == "Mail"), None)
    safari_app = next((a for a in apps if a["name"] == "Safari"), None)

    if mail_app and safari_app:
        assert mail_app["frame_count"] >= safari_app["frame_count"], \
            "Expected Mail frames >= Safari frames"
        print(f"   ✅ Mail ({mail_app['frame_count']}) >= Safari ({safari_app['frame_count']})")

    # Test app_name filter
    safari_only = store.get_activity_summary_apps(
        start_time="2026-03-21T00:00:00Z",
        end_time="2026-03-21T23:59:59Z",
        app_name="Safari",
    )
    if safari_only:
        assert safari_only[0]["name"] == "Safari", "Expected Safari filter to work"
        print(f"   ✅ App name filter works (Safari: {safari_only[0]['frame_count']} frames)")

    print("   ✅ PASSED\n")
    return True


def verify_activity_summary_recent_texts(store: FramesStore) -> bool:
    """Verify get_activity_summary_recent_texts."""
    print("2️⃣  Testing get_activity_summary_recent_texts...")

    texts = store.get_activity_summary_recent_texts(
        start_time="2026-03-21T00:00:00Z",
        end_time="2026-03-21T23:59:59Z",
        limit=10,
    )

    print(f"   Result ({len(texts)} items):")
    for t in texts[:5]:
        print(f"      - [{t['role']}] {t['text'][:30]}... (frame_id={t['frame_id']})")

    # Verify only text-like roles (AXStaticText, line, paragraph)
    roles = {t["role"] for t in texts}
    print(f"   Roles found: {roles}")

    assert roles.issubset({"AXStaticText", "line", "paragraph"}), \
        f"Expected only text-like roles, got {roles}"

    # Verify ordering (timestamp DESC)
    timestamps = [t["timestamp"] for t in texts]
    assert timestamps == sorted(timestamps, reverse=True), \
        "Expected timestamps in descending order"

    # Test app_name filter
    safari_texts = store.get_activity_summary_recent_texts(
        start_time="2026-03-21T00:00:00Z",
        end_time="2026-03-21T23:59:59Z",
        app_name="Safari",
    )
    assert all(t["app_name"] == "Safari" for t in safari_texts), \
        "Expected only Safari texts"

    print("   ✅ PASSED\n")
    return True


def verify_activity_summary_total_frames(store: FramesStore) -> bool:
    """Verify get_activity_summary_total_frames."""
    print("3️⃣  Testing get_activity_summary_total_frames...")

    total = store.get_activity_summary_total_frames(
        start_time="2026-03-21T00:00:00Z",
        end_time="2026-03-21T23:59:59Z",
    )

    print(f"   Total completed frames: {total}")

    # Should have at least 8 test frames (3 Safari + 5 Mail)
    # May have more from existing data
    assert total >= 8, f"Expected at least 8 completed frames, got {total}"

    print("   ✅ PASSED\n")
    return True


def verify_activity_summary_time_range(store: FramesStore) -> bool:
    """Verify get_activity_summary_time_range."""
    print("4️⃣  Testing get_activity_summary_time_range...")

    time_range = store.get_activity_summary_time_range(
        start_time="2026-03-21T00:00:00Z",
        end_time="2026-03-21T23:59:59Z",
    )

    print(f"   Time range: {time_range}")

    assert time_range is not None, "Expected time_range to be non-None"
    assert "start" in time_range and "end" in time_range

    print("   ✅ PASSED\n")
    return True


def verify_get_frame_context(store: FramesStore) -> bool:
    """Verify get_frame_context."""
    print("5️⃣  Testing get_frame_context...")

    # Find a frame with accessibility data for meaningful test
    frames = store.get_recent_memories(limit=20)
    test_frame = None
    for f in frames:
        ctx = store.get_frame_context(f["frame_id"])
        if ctx and ctx.get("text_source") == "accessibility":
            test_frame = ctx
            break

    if not test_frame:
        print("   ⚠️  No frames with accessibility data found, skipping detailed test")
        # Still test that missing frame returns None
        missing = store.get_frame_context(999999)
        assert missing is None, "Expected None for missing frame"
        print("   ✅ PASSED (basic)\n")
        return True

    frame_id = test_frame["frame_id"]
    print(f"   Frame {frame_id} context:")
    print(f"      text_source: {test_frame.get('text_source')}")
    print(f"      nodes count: {len(test_frame.get('nodes', []))}")
    print(f"      urls: {test_frame.get('urls')}")
    print(f"      text preview: {(test_frame.get('text') or '')[:50]}...")

    # Verify basic structure
    assert test_frame["frame_id"] == frame_id
    assert "text" in test_frame
    assert "text_source" in test_frame
    assert "nodes" in test_frame
    assert "urls" in test_frame

    # Verify accessibility data is present
    assert test_frame["text_source"] == "accessibility", \
        f"Expected text_source='accessibility', got {test_frame['text_source']}"
    assert len(test_frame["nodes"]) > 0, \
        "Expected nodes to be non-empty for accessibility frame"

    # Test missing frame
    missing = store.get_frame_context(999999)
    assert missing is None, "Expected None for missing frame"
    print("   ✅ Missing frame returns None")

    # Test truncation (screenpipe-aligned)
    print()
    print("   Testing truncation parameters...")
    ctx_truncated = store.get_frame_context(frame_id, max_text_length=100, max_nodes=10)

    assert len(ctx_truncated["text"]) <= 103, "Expected truncated text"  # 100 + "..."
    assert len(ctx_truncated["nodes"]) <= 10, "Expected truncated nodes"

    if len(test_frame["nodes"]) > 10:
        assert "nodes_truncated" in ctx_truncated, "Expected nodes_truncated field"
        print(f"      ✅ Truncation works: text={len(ctx_truncated['text'])} chars, nodes={len(ctx_truncated['nodes'])}, truncated={ctx_truncated.get('nodes_truncated', 0)}")
    else:
        print(f"      ✅ Truncation params accepted (frame has only {len(test_frame['nodes'])} nodes)")

    print("   ✅ PASSED\n")
    return True


def main():
    parser = argparse.ArgumentParser(description="Verify Phase 6 query helpers")
    parser.add_argument(
        "--create-test-data",
        action="store_true",
        help="Create test data before verification",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Path to database (default: use settings)",
    )
    args = parser.parse_args()

    print("=" * 50)
    print("Phase 6 Query Helpers Verification")
    print("=" * 50)

    # Initialize store
    if args.db_path:
        db_path = Path(args.db_path)
    else:
        db_path = settings.db_path

    print(f"\n📊 Database: {db_path}")

    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        print("   Run the server first or use --create-test-data with a test DB")
        sys.exit(1)

    store = FramesStore(db_path)

    # Create test data if requested
    if args.create_test_data:
        create_test_data(store)

    # Run verification
    results = []
    results.append(verify_activity_summary_apps(store))
    results.append(verify_activity_summary_recent_texts(store))
    results.append(verify_activity_summary_total_frames(store))
    results.append(verify_activity_summary_time_range(store))
    results.append(verify_get_frame_context(store))

    # Summary
    print("=" * 50)
    if all(results):
        print("✅ All Phase 6 query helpers verified successfully!")
    else:
        print("❌ Some tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
