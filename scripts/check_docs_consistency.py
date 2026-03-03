#!/usr/bin/env python3
"""Consistency checks for MyRecall v3 docs SSOT split."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS_V3 = ROOT / "docs" / "v3"

REQUIRED_FILES = [
    DOCS_V3 / "spec.md",
    DOCS_V3 / "architecture.md",
    DOCS_V3 / "data_model.md",
    DOCS_V3 / "api_contract.md",
    DOCS_V3 / "decisions.md",
    DOCS_V3 / "document_governance.md",
    DOCS_V3 / "roadmap.md",
    DOCS_V3 / "open_questions.md",
    DOCS_V3 / "gate_baseline.md",
]

ACCEPTANCE_FILES = sorted((DOCS_V3 / "acceptance").rglob("*.md"))

NON_SSOT_DOCS = [
    DOCS_V3 / "spec.md",
    DOCS_V3 / "roadmap.md",
    DOCS_V3 / "open_questions.md",
    *ACCEPTANCE_FILES,
]

FORBIDDEN_DDL_PATTERNS = [
    re.compile(r"\bCREATE\s+TABLE\b", flags=re.IGNORECASE),
    re.compile(r"\bCREATE\s+TRIGGER\b", flags=re.IGNORECASE),
    re.compile(r"\bCREATE\s+VIRTUAL\s+TABLE\b", flags=re.IGNORECASE),
]

MARKDOWN_LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
SCHEME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def has_all_decisions(table_ids: list[str]) -> bool:
    expected = [f"DEC-{i:03d}A" for i in range(1, 26)]
    return all(item in table_ids for item in expected)


def parse_relative_link_target(raw_target: str) -> str | None:
    target = raw_target.strip()
    if not target:
        return None

    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")].strip()
    else:
        target = target.split(maxsplit=1)[0]

    if target.startswith(("#", "/", "//")):
        return None

    if SCHEME_PATTERN.match(target):
        return None

    target = target.split("#", maxsplit=1)[0].split("?", maxsplit=1)[0]
    if not target:
        return None

    return target


def main() -> int:
    errors: list[str] = []

    for path in REQUIRED_FILES:
        if not path.exists():
            errors.append(f"Missing required file: {path}")

    if errors:
        for err in errors:
            print(f"ERROR: {err}")
        return 1

    spec = read_text(DOCS_V3 / "spec.md")
    roadmap = read_text(DOCS_V3 / "roadmap.md")
    open_questions = read_text(DOCS_V3 / "open_questions.md")
    decisions = read_text(DOCS_V3 / "decisions.md")

    spec_lines = spec.count("\n") + 1
    if spec_lines > 220:
        errors.append(f"spec.md must be <= 220 lines, got {spec_lines}")

    for needle in ["architecture.md", "data_model.md", "api_contract.md", "decisions.md"]:
        if needle not in spec:
            errors.append(f"spec.md must link to {needle}")

    for path in NON_SSOT_DOCS:
        text = read_text(path)
        for marker in FORBIDDEN_DDL_PATTERNS:
            if marker.search(text):
                errors.append(f"{path} must not contain DDL marker: {marker.pattern}")

    if "## 8. 已拍板基线" in spec:
        errors.append("spec.md must not keep full decided baseline section")

    if re.search(r"^\s*\d+\.\s*`?DEC-\d{3}[A-Z]`?\b", roadmap, flags=re.M):
        errors.append("roadmap.md must not keep full DEC-xxx decision list")

    if "已拍板结论" in open_questions:
        errors.append("open_questions.md must only contain unresolved items")

    table_ids = re.findall(r"^\| (DEC-\d{3}[A-Z]) \|", decisions, flags=re.M)

    if not has_all_decisions(table_ids):
        errors.append("decisions.md must include DEC-001A .. DEC-025A entries")

    if len(table_ids) != len(set(table_ids)):
        errors.append("decisions.md contains duplicate DEC IDs in decision table")

    for path in ACCEPTANCE_FILES:
        text = read_text(path)
        if "## 0. 规范引用 IDs" not in text:
            errors.append(f"{path} missing '## 0. 规范引用 IDs' section")

    p1s3 = read_text(DOCS_V3 / "acceptance" / "phase1" / "p1-s3.md")
    p1s4 = read_text(DOCS_V3 / "acceptance" / "phase1" / "p1-s4.md")
    if "AX 成功帧写入 `accessibility`" not in p1s3:
        errors.append("p1-s3.md must validate Scheme C accessibility path")

    forbidden_conflicts = [
        "frames WHERE status='completed') - (SELECT COUNT(*) FROM ocr_text)",
        "主路径始终 `frames INNER JOIN ocr_text`",
    ]
    for conflict in forbidden_conflicts:
        if conflict in p1s4:
            errors.append(f"p1-s4.md still contains old conflicting rule: {conflict}")

    # Simple relative markdown link validation inside docs/v3
    for path in (DOCS_V3.rglob("*.md")):
        text = read_text(path)
        for raw_target in MARKDOWN_LINK_PATTERN.findall(text):
            rel = parse_relative_link_target(raw_target)
            if rel is None:
                continue
            target = (path.parent / rel).resolve()
            if not target.exists():
                errors.append(f"Broken relative link in {path}: {rel}")

    if errors:
        for err in errors:
            print(f"ERROR: {err}")
        return 1

    print("Docs consistency check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
