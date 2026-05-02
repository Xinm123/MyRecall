"""Evaluate skill test results against expected behavior.

Usage:
    python evaluate.py --results /tmp/skill_eval_results.json --output /tmp/eval_report.md

Reads a results file produced by test execution and generates a scoring report.
"""

import argparse
import json
import sys
from pathlib import Path


def load_results(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def load_test_cases(path: str) -> list:
    with open(path) as f:
        return json.load(f)["cases"]


def evaluate_case(case: dict, requests: list) -> dict:
    """Score a single test case based on API requests made.

    Returns a dict with score breakdown and notes.
    """
    expected = case["expected"]
    score = {"total": 0, "endpoint": 0, "params": 0, "no_redundant": 0, "notes": []}

    if not requests:
        score["notes"].append("No API requests made")
        return score

    endpoints = [r["path"] for r in requests]

    # 1. Endpoint correctness (40 points)
    primary = expected.get("primary_endpoint")
    primaries = expected.get("primary_endpoints", [primary] if primary else [])
    acceptable = expected.get("acceptable_endpoints", [])

    if primary:
        if any(primary in ep for ep in endpoints):
            score["endpoint"] = 40
            score["notes"].append(f"Correct primary endpoint called: {primary}")
        elif acceptable and any(any(a in ep for ep in endpoints) for a in acceptable):
            score["endpoint"] = 30
            score["notes"].append(f"Acceptable endpoint called instead of {primary}")
        else:
            score["endpoint"] = 0
            score["notes"].append(f"Expected {primary}, got {endpoints}")
    elif primaries:
        if any(any(p in ep for ep in endpoints) for p in primaries):
            score["endpoint"] = 40
            score["notes"].append(f"One of expected endpoints called: {primaries}")
        else:
            score["endpoint"] = 0
            score["notes"].append(f"Expected one of {primaries}, got {endpoints}")
    elif acceptable:
        if any(any(a in ep for ep in endpoints) for a in acceptable):
            score["endpoint"] = 40
            score["notes"].append(f"Acceptable endpoint called: {acceptable}")
        else:
            score["endpoint"] = 0
            score["notes"].append(f"Expected one of {acceptable}, got {endpoints}")

    # 2. Parameters (30 points)
    required = expected.get("required_params", [])
    if required and requests:
        # Check first request (or all requests for composite)
        all_args = {}
        for r in requests:
            all_args.update(r.get("args", {}))
        missing = [p for p in required if p not in all_args]
        if not missing:
            score["params"] = 30
            score["notes"].append(f"All required params present: {required}")
        else:
            score["params"] = max(0, 30 - len(missing) * 10)
            score["notes"].append(f"Missing params: {missing}")
    else:
        score["params"] = 30
        score["notes"].append("No required params to check")

    # 3. No redundant calls (30 points)
    forbidden = expected.get("forbidden_endpoints", [])
    violations = [ep for ep in endpoints if any(f in ep for f in forbidden)]
    if not violations:
        score["no_redundant"] = 30
        score["notes"].append("No forbidden endpoints called")
    else:
        score["no_redundant"] = 0
        score["notes"].append(f"Forbidden endpoints called: {violations}")

    score["total"] = score["endpoint"] + score["params"] + score["no_redundant"]
    return score


def generate_report(results: dict, test_cases: list, skill_version: str) -> str:
    lines = [
        f"# Skill Evaluation Report: {skill_version}",
        "",
        f"Total cases: {len(test_cases)}",
        "",
        "| ID | Prompt | Score | Endpoint | Params | No Redundant | Notes |",
        "|---|--------|-------|----------|--------|-------------|-------|",
    ]

    total_score = 0
    for case in test_cases:
        case_id = case["id"]
        case_results = results.get("results", {}).get(case_id, {})
        requests = case_results.get("requests", [])
        score = evaluate_case(case, requests)
        total_score += score["total"]

        notes = "; ".join(score["notes"])
        lines.append(
            f"| {case_id} | {case['prompt'][:40]}... | "
            f"{score['total']}/100 | {score['endpoint']} | {score['params']} | "
            f"{score['no_redundant']} | {notes[:80]}... |"
        )

    avg = total_score / len(test_cases) if test_cases else 0
    lines.extend([
        "",
        f"## Summary",
        f"",
        f"- Total Score: {total_score}/{len(test_cases) * 100}",
        f"- Average: {avg:.1f}/100",
        "",
    ])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True, help="Path to results JSON")
    parser.add_argument("--cases", default="test_cases.json", help="Path to test cases JSON")
    parser.add_argument("--output", required=True, help="Path to output markdown report")
    args = parser.parse_args()

    results = load_results(args.results)
    test_cases = load_test_cases(args.cases)
    skill_version = results.get("skill_version", "unknown")

    report = generate_report(results, test_cases, skill_version)

    with open(args.output, "w") as f:
        f.write(report)

    print(f"Report written to {args.output}")
    print(report)


if __name__ == "__main__":
    main()
