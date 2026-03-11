#!/usr/bin/env python3
import sqlite3
import sys
import os
from datetime import datetime, timedelta, timezone


def _iso_now_minus(seconds: int) -> str:
    return (
        (datetime.now(timezone.utc) - timedelta(seconds=seconds))
        .isoformat()
        .replace("+00:00", "Z")
    )


def seed_trigger_samples(
    db_path: str,
    app_switch_count: int = 50,
    click_count: int = 100,
    manual_count: int = 20,
    idle_count: int = 20,
) -> None:
    print(f"Seeding trigger samples into {db_path}")
    print(f"  app_switch: {app_switch_count}")
    print(f"  click: {click_count}")
    print(f"  manual: {manual_count}")
    print(f"  idle: {idle_count}")

    if not os.path.exists(db_path):
        print(f"ERROR: Database not found at {db_path}")
        sys.exit(1)

    with sqlite3.connect(db_path) as conn:
        total = 0

        for i in range(app_switch_count):
            ts = _iso_now_minus(i + 1)
            conn.execute(
                """INSERT INTO frames 
                   (capture_id, timestamp, app_name, window_name, device_name,
                    snapshot_path, capture_trigger, event_ts, status, ingested_at, processed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f"trigger-app_switch-{i:04d}",
                    ts,
                    f"App_{i % 5}",
                    f"Window_{i}",
                    "monitor_0",
                    f"/tmp/trigger-app_switch-{i:04d}.jpg",
                    "app_switch",
                    ts,
                    "completed",
                    ts,
                    ts,
                ),
            )
        total += app_switch_count
        print(f"  Seeded {app_switch_count} app_switch triggers")

        for i in range(click_count):
            ts = _iso_now_minus(i + app_switch_count + 1)
            conn.execute(
                """INSERT INTO frames 
                   (capture_id, timestamp, app_name, window_name, device_name,
                    snapshot_path, capture_trigger, event_ts, status, ingested_at, processed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f"trigger-click-{i:04d}",
                    ts,
                    "Finder",
                    "Desktop",
                    "monitor_0",
                    f"/tmp/trigger-click-{i:04d}.jpg",
                    "click",
                    ts,
                    "completed",
                    ts,
                    ts,
                ),
            )
        total += click_count
        print(f"  Seeded {click_count} click triggers")

        for i in range(manual_count):
            ts = _iso_now_minus(i + app_switch_count + click_count + 1)
            conn.execute(
                """INSERT INTO frames 
                   (capture_id, timestamp, app_name, window_name, device_name,
                    snapshot_path, capture_trigger, event_ts, status, ingested_at, processed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f"trigger-manual-{i:04d}",
                    ts,
                    "Terminal",
                    "bash",
                    "monitor_0",
                    f"/tmp/trigger-manual-{i:04d}.jpg",
                    "manual",
                    ts,
                    "completed",
                    ts,
                    ts,
                ),
            )
        total += manual_count
        print(f"  Seeded {manual_count} manual triggers")

        for i in range(idle_count):
            ts = _iso_now_minus(i + app_switch_count + click_count + manual_count + 1)
            conn.execute(
                """INSERT INTO frames 
                   (capture_id, timestamp, app_name, window_name, device_name,
                    snapshot_path, capture_trigger, event_ts, status, ingested_at, processed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f"trigger-idle-{i:04d}",
                    ts,
                    "Finder",
                    "Desktop",
                    "monitor_0",
                    f"/tmp/trigger-idle-{i:04d}.jpg",
                    "idle",
                    ts,
                    "completed",
                    ts,
                    ts,
                ),
            )
        total += idle_count
        print(f"  Seeded {idle_count} idle triggers")

        conn.commit()

    print(f"\nTotal triggers seeded: {total}")
    print("\nVerification query:")
    print("  SELECT capture_trigger, COUNT(*) FROM frames GROUP BY capture_trigger;")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Seed trigger samples for P1-S2a acceptance"
    )
    parser.add_argument(
        "--db", default=os.path.expanduser("~/MRS/db/edge.db"), help="Path to edge.db"
    )
    parser.add_argument(
        "--app-switch", type=int, default=50, help="Number of app_switch triggers"
    )
    parser.add_argument(
        "--click", type=int, default=100, help="Number of click triggers"
    )
    parser.add_argument(
        "--manual", type=int, default=20, help="Number of manual triggers"
    )
    parser.add_argument("--idle", type=int, default=20, help="Number of idle triggers")

    args = parser.parse_args()

    seed_trigger_samples(
        args.db,
        app_switch_count=args.app_switch,
        click_count=args.click,
        manual_count=args.manual,
        idle_count=args.idle,
    )
