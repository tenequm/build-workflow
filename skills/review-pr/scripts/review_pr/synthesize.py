"""Stage 4: the report and the payload, assembled by code.

Anchors are verified here rather than by GitHub's 422, the verdict comes from the
table rather than from prose, and the only thing a model contributes is one or two
sentences of judgment. The report keeps polish's shape: correctness first and always,
a substantiated zero, and everything dropped listed with its reason.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from operator_driver.storage import Park, atomic, canonical

from . import anchors, config, diffindex, verdictcalc

TITLES = {
    "correctness": "Correctness",
    "convention": "Convention",
    "cleanliness": "Cleanliness",
    "design": "Design",
    "efficiency": "Efficiency",
}
FRAMING = {
    "SEVERE": "Blocking fix",
    "BLOCKING_FIX": "Blocking fix",
    "BLOCKING_QUESTION": "Blocking question",
    "SUGGESTION": "Suggestion",
}


def comment_body(finding: dict[str, Any], proof: dict[str, Any] | None) -> str:
    """Review mode frames a finding as a question or a suggestion: it is someone else's code."""
    label = FRAMING.get(finding.get("severity") or "SUGGESTION", "Suggestion")
    lines = [f"[{TITLES[finding['category']]} / {label}] {finding['claim']}"]
    verify = finding.get("verify") or {}
    if finding["verdict"] == "CONFIRMED":
        lines.append(f"\nVerified: {verify.get('reason', 'a rubric decided it')}")
    elif finding["verdict"] == "PLAUSIBLE":
        lines.append(f"\nNot mechanically proven: {verify.get('reason', 'no rubric decided it')}")
    if finding.get("tags"):
        lines.append("\nTagged: " + ", ".join(f"`{tag}`" for tag in finding["tags"]))
    change = finding.get("suggestion")
    if change and proof and proof.get("proven"):
        lines.append(f"\n{proof['reason']}.\n")
        lines.append("```suggestion\n" + change["replacement"].rstrip("\n") + "\n```")
    elif change:
        reason = (proof or {}).get("reason", "not proven")
        lines.append(
            f"\nA possible fix, offered as prose because it was not proven ({reason}):\n\n"
            "```\n" + change["replacement"].rstrip("\n") + "\n```"
        )
    return "\n".join(lines)


def payload(
    action: str,
    body: str,
    asks: list[dict[str, Any]],
    files: dict[str, diffindex.FileDiff],
    proofs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """The exact JSON `gh api ... /reviews` takes, with every anchor already checked."""
    if action == "skip":
        raise Park("a skipped review has no payload")
    comments = []
    for finding in anchors.anchored(asks, files):
        comment: dict[str, Any] = {
            "path": finding["file"],
            "line": int(finding["line"]),
            "side": "RIGHT",
            "body": comment_body(finding, proofs.get(finding["id"])),
        }
        start = finding.get("start_line")
        if start is not None and int(start) < int(finding["line"]):
            comment["start_line"] = int(start)
            comment["start_side"] = "RIGHT"
        comments.append(comment)
    problems = verdictcalc.consistency(action, comments)
    if problems:
        raise Park("verdict is an approve but its comments ask for changes: " + "; ".join(problems))
    return {"event": verdictcalc.EVENTS[action], "body": body, "comments": comments}


def _section(title: str, rows: list[dict[str, Any]]) -> list[str]:
    lines = [f"### {title} ({len(rows)} issue{'' if len(rows) == 1 else 's'})"]
    if not rows:
        lines.append("")
        return lines
    for index, finding in enumerate(rows, start=1):
        where = (
            finding["file"]
            if finding["scope"] == "meta"
            else f"`{finding['file']}:{finding['line']}`"
        )
        tags = "".join(f" ({tag})" for tag in finding.get("tags", []))
        lines.append(f"{index}. {where} - {finding['claim']}{tags} [{finding['verdict']}]")
    lines.append("")
    return lines


def correctness_zero(evidence: dict[str, Any]) -> str:
    """A zero here is a real signal, so it has to say what was traced to earn it."""
    lint = evidence.get("lint", {})
    decided = ("pass", "fail")
    ran = [check["rule"] for check in lint.get("checks", []) if check["result"] in decided]
    skipped = [
        f"{check['rule']} ({check['detail']})"
        for check in lint.get("checks", [])
        if check["result"] not in decided
    ]
    gate = evidence.get("gate", {})
    verify = evidence.get("verify", {})
    parts = [
        f"House rules run: {', '.join(ran) or 'none'}.",
        f"Undecided: {'; '.join(skipped)}." if skipped else "No rule went undecided.",
        (
            f"Pinned validation `{gate.get('command', 'not run')}` exited "
            f"{gate.get('returncode', 'n/a')} in the {gate.get('tier', 'unsandboxed')} sandbox."
        ),
        (
            f"The side-effect gating lens returned {evidence.get('gating_findings', 0)} claim(s); "
            f"{verify.get('sessions', 0)} verifier session(s) ran and "
            f"{verify.get('settled_by_rubric', 0)} claim(s) settled on an executed rubric."
        ),
        (
            f"Claims in the body re-executed: {evidence.get('claims_reproduced', 0)} reproduced, "
            f"{evidence.get('claims_mismatched', 0)} did not, "
            f"{evidence.get('claims_unchecked', 0)} could not be run here."
        ),
    ]
    return " ".join(parts)


def report(
    sidecar: dict[str, Any],
    asks: list[dict[str, Any]],
    follow: list[dict[str, Any]],
    dropped: list[dict[str, Any]],
    action: str,
    body: str,
    evidence: dict[str, Any],
    skip_reason: str | None,
) -> str:
    header = f"# {sidecar.get('url') or sidecar['repo']} - {sidecar.get('title', '')}".rstrip(" -")
    lines = [header, "", "## Review Findings", ""]
    by_category = {name: [] for name in config.REPORT_CATEGORY_ORDER}
    for finding in asks:
        by_category[finding["category"]].append(finding)
    for name in config.REPORT_CATEGORY_ORDER:
        rows = by_category[name]
        if name == "correctness" or rows:
            lines += _section(TITLES[name], rows)
            if name == "correctness" and not rows:
                lines += [correctness_zero(evidence), ""]
    if follow:
        lines += ["### Follow-ups (not part of the verdict)", ""]
        for index, finding in enumerate(follow, start=1):
            where = (
                finding["file"]
                if finding["scope"] == "meta"
                else f"`{finding['file']}:{finding['line']}`"
            )
            tags = "".join(f" ({tag})" for tag in finding.get("tags", []))
            lines.append(f"{index}. {where} - {finding['claim']}{tags}")
        lines.append("")
    if dropped:
        lines += ["### Dropped after validation", ""]
        for index, finding in enumerate(dropped, start=1):
            where = (
                finding["file"]
                if finding["scope"] == "meta"
                else f"`{finding['file']}:{finding['line']}`"
            )
            reason = (finding.get("verify") or {}).get("reason", "did not survive verification")
            lines.append(f"{index}. {where} - {finding['claim']} - {reason}")
        lines.append("")
    categories = sum(1 for rows in by_category.values() if rows)
    lines += [f"**Total: {len(asks)} issues across {categories} categories**", ""]
    if skip_reason:
        lines += [
            (
                f"**Recommended: skip** - {skip_reason}; every finding above is reported so the "
                "work is not lost."
            ),
            "Post it? (y = post as recommended / another action by name / n = don't post)",
        ]
        return "\n".join(lines) + "\n"
    top = asks[0]["claim"] if asks else "nothing blocks this change"
    lines += [
        body.strip(),
        "",
        f"**Recommended: {action}** - {top}",
        "Post it? (y = post as recommended / another action by name / n = don't post)",
    ]
    return "\n".join(lines) + "\n"


def synthesize(
    workspace: Path,
    sidecar: dict[str, Any],
    verified: list[dict[str, Any]],
    *,
    body: str,
    evidence: dict[str, Any],
    proofs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    files = diffindex.reviewable(
        diffindex.parse((workspace / sidecar["diff"]).read_text(errors="replace"))
    )
    action = verdictcalc.verdict(verified, sidecar)
    skip_reason = verdictcalc.state_gate(sidecar)
    asks, follow = verdictcalc.split(verified)
    dropped = [f for f in verified if f["verdict"] == "DROPPED"]
    # Graded, not raw: `severity` is the field the ledger, the payload and the report
    # all read, so a consumer of summary.json never has to re-derive the table.
    graded = verdictcalc.classify(verified)
    bad = anchors.violations(asks + follow, files)
    summary = {
        "repo": sidecar["repo"],
        "number": sidecar["number"],
        "url": sidecar.get("url"),
        "head": sidecar["head"],
        "action": action,
        "skip_reason": skip_reason,
        "counts": {
            "asks": len(asks),
            "follow_ups": len(follow),
            "dropped": len(dropped),
            "confirmed": sum(1 for f in asks if f["verdict"] == "CONFIRMED"),
            "plausible": sum(1 for f in asks if f["verdict"] == "PLAUSIBLE"),
        },
        "anchor_violations": bad,
        "evidence": evidence,
        "findings": graded,
    }
    atomic(workspace / "summary.json", canonical(summary), mode=0o644)
    text = report(sidecar, asks, follow, dropped, action, body, evidence, skip_reason)
    atomic(workspace / "report.md", text.encode(), mode=0o644)
    if action != "skip":
        review = payload(action, body.strip(), asks, files, proofs)
        atomic(
            workspace / "pr-review.json",
            json.dumps(review, indent=2).encode() + b"\n",
            mode=0o644,
        )
        summary["payload_comments"] = len(review["comments"])
    return summary
