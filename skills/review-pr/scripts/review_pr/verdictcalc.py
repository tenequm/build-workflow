"""Polish's verdict table as code, computed from verified findings alone.

The skill it replaces eyeballed this. Here severity is a function of the finding's
category, its verifier verdict and its impact, so two runs over the same findings
cannot disagree, and no prose in a report can talk the verdict up or down.
"""

from __future__ import annotations

from typing import Any

from operator_driver.storage import Park

ACTIONS = ("request-changes", "comment-only", "approve-with-comments", "approve", "skip")
EVENTS = {
    "request-changes": "REQUEST_CHANGES",
    "comment-only": "COMMENT",
    "approve-with-comments": "APPROVE",
    "approve": "APPROVE",
}
RANK = ("SEVERE", "BLOCKING_FIX", "BLOCKING_QUESTION", "SUGGESTION")
BEFORE_MERGE = ("before merge", "before merging", "must fix", "blocker")


def state_gate(facts: dict[str, Any]) -> str | None:
    """Reached only from PR state, never from finding severity - polish's rule."""
    if facts.get("isDraft"):
        return "the pull request is a draft"
    state = str(facts.get("state", "")).upper()
    if state and state != "OPEN":
        return f"the pull request is {state.lower()}"
    if facts.get("withdrawn"):
        return "the review request was withdrawn"
    return None


def severity(finding: dict[str, Any]) -> str | None:
    """None means the finding does not enter the verdict (dropped or a follow-up)."""
    if finding["verdict"] == "DROPPED":
        return None
    if finding["follow_up"]:
        return None
    if finding["verdict"] == "UNVERIFIED":
        raise Park(f"finding {finding['id']} reached synthesis unverified")
    if finding["unverifiable"]:
        # No mechanical check could be stated, so the claim cannot block a merge.
        return "SUGGESTION"
    correctness = finding["category"] == "correctness" or finding["lens"] == "gating"
    if correctness:
        if finding["verdict"] == "CONFIRMED":
            return "BLOCKING_FIX" if finding["impact"] == "none" else "SEVERE"
        return "BLOCKING_QUESTION"
    if finding["category"] == "convention":
        # The house rules upstream machinery demonstrably blocks over: a commit is
        # required, but nothing here is security, data loss or a broken deploy.
        return "BLOCKING_FIX" if finding["verdict"] == "CONFIRMED" else "SUGGESTION"
    return "SUGGESTION"


def classify(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**finding, "severity": severity(finding)} for finding in findings]


def verdict(findings: list[dict[str, Any]], facts: dict[str, Any] | None = None) -> str:
    skip = state_gate(facts or {})
    if skip:
        return "skip"
    present = {finding["severity"] for finding in classify(findings)} - {None}
    for level, action in (
        ("SEVERE", "request-changes"),
        ("BLOCKING_FIX", "comment-only"),
        ("BLOCKING_QUESTION", "comment-only"),
        ("SUGGESTION", "approve-with-comments"),
    ):
        if level in present:
            return action
    return "approve"


def consistency(action: str, comments: list[dict[str, Any]]) -> list[str]:
    """An approve means every comment can be ignored; prove that before posting."""
    if not action.startswith("approve"):
        return []
    return [
        f"{comment.get('path')}:{comment.get('line')} asks for a change before merge"
        for comment in comments
        if any(phrase in str(comment.get("body", "")).lower() for phrase in BEFORE_MERGE)
    ]


def split(findings: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Pre-merge asks and follow-ups. Dropped findings belong to neither."""
    graded = [f for f in classify(findings) if f["verdict"] != "DROPPED"]
    asks = [f for f in graded if f["severity"] is not None]
    follow = [f for f in graded if f["severity"] is None]
    asks.sort(key=lambda f: (RANK.index(f["severity"]), f["file"], f["line"]))
    follow.sort(key=lambda f: (f["file"], f["line"]))
    return asks, follow
