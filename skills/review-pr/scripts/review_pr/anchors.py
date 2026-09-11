"""Anchor verification as code: GitHub rejects a whole review on one bad anchor."""

from __future__ import annotations

from typing import Any

from .diffindex import FileDiff


def violations(findings: list[dict[str, Any]], files: dict[str, FileDiff]) -> list[dict[str, Any]]:
    """Every anchor a review would post, checked against the PR's own hunks."""
    problems = []
    for finding in findings:
        if finding.get("scope", "diff") != "diff":
            continue
        path = finding["file"]
        diff = files.get(path)
        if diff is None:
            problems.append(
                {
                    "id": finding["id"],
                    "path": path,
                    "line": finding["line"],
                    "reason": "file is not in this pull request's diff",
                }
            )
            continue
        if diff.deleted:
            problems.append(
                {
                    "id": finding["id"],
                    "path": path,
                    "line": finding["line"],
                    "reason": "file is deleted by this pull request",
                }
            )
            continue
        for key in ("start_line", "line"):
            line = finding.get(key)
            if line is None:
                continue
            if not diff.anchorable(int(line)):
                problems.append(
                    {
                        "id": finding["id"],
                        "path": path,
                        "line": int(line),
                        "reason": f"{key} does not sit inside a diff hunk",
                    }
                )
    return problems


def anchored(findings: list[dict[str, Any]], files: dict[str, FileDiff]) -> list[dict[str, Any]]:
    """Findings that can carry an inline comment. The rest go in the review body."""
    bad = {problem["id"] for problem in violations(findings, files)}
    return [
        finding
        for finding in findings
        if finding["id"] not in bad and finding.get("scope", "diff") == "diff"
    ]
