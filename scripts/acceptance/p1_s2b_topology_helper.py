from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


@dataclass(frozen=True)
class TopologyEvidence:
    generated_at: str
    method: str
    notes: str | None
    scenarios: dict[str, dict[str, object]]


def _default_scenarios() -> dict[str, dict[str, object]]:
    return {
        "SC-T1": {"name": "monitor_add", "status": "pending"},
        "SC-T2": {"name": "monitor_remove", "status": "pending"},
        "SC-T3": {"name": "primary_switch", "status": "pending"},
        "SC-T4": {"name": "monitor_recovery", "status": "pending"},
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate S2b topology evidence scaffold"
    )
    parser.add_argument(
        "--method",
        choices=["injected", "manual"],
        default="injected",
        help="Topology-change evidence method",
    )
    parser.add_argument(
        "--notes-file",
        default="",
        help="Optional path to operator notes/steps",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output JSON file path",
    )
    parser.add_argument(
        "--all-pass",
        action="store_true",
        help="Mark all topology scenarios as pass",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scenarios = _default_scenarios()

    if args.all_pass:
        for key in scenarios:
            scenarios[key]["status"] = "pass"

    notes: str | None = None
    if args.notes_file:
        notes_path = Path(args.notes_file)
        if notes_path.exists():
            notes = notes_path.read_text(encoding="utf-8")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    evidence = TopologyEvidence(
        generated_at=_utc_now_iso(),
        method=args.method,
        notes=notes,
        scenarios=scenarios,
    )
    output_path.write_text(json.dumps(asdict(evidence), indent=2), encoding="utf-8")
    print(json.dumps(asdict(evidence), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
