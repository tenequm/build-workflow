"""Assembling a session's prompt from this skill's own templates.

Every brief carries the same three things before its lens-specific part: the review
rules, the injection fence, and a completion signal that names the report file. The
fence is not decoration - the diff, the tree and the pull request body are all author
controlled, and the only structural defence is to say so in every prompt and to check
the worktree afterwards.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from operator_driver.storage import Park

from . import config

LENS_TEMPLATE = {
    "cleanliness": "lens-cleanliness.md",
    "design": "lens-design.md",
    "efficiency": "lens-efficiency.md",
    "gating": "lens-gating.md",
    "implementation": "lens-implementation.md",
}
BRIEF_CAP = 16000


def guard(brief: str, sidecar: dict[str, Any]) -> str:
    """No brief may name the shared reviewed tree.

    Each session gets its own worktree and is validated against it, so a brief that
    hands the model an absolute path to the shared tree gets exactly what it asked
    for: a report written where nothing collects it, and a session that exits clean
    having produced nothing. Measured 2026-09-11 on the first paid run, where all
    seven stage-2 sessions did precisely that.
    """
    shared = str(sidecar.get("tree") or "")
    if shared and shared in brief:
        raise Park(
            f"brief names the shared reviewed tree {shared!r}; write targets are "
            "resolved against each session's own working directory"
        )
    return brief


def render(template: str, values: dict[str, str]) -> str:
    text = config.template(template)
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    missing = [token for token in ("{{",) if token in text]
    if missing:
        unresolved = text[text.index("{{") : text.index("{{") + 40]
        raise Park(f"brief template {template} has an unresolved placeholder: {unresolved!r}")
    if len(text) > BRIEF_CAP:
        raise Park(f"brief from {template} exceeds {BRIEF_CAP} characters: {len(text)}")
    return text


def inputs(workspace: Path, sidecar: dict[str, Any], diff: str, body: str) -> dict[str, Path]:
    """The per-pull-request inputs every stage-2 session reads, written once."""
    directory = workspace / "inputs"
    directory.mkdir(parents=True, exist_ok=True)
    files = {
        "diff": directory / "diff.patch",
        "body": directory / "pr-body.md",
        "files": directory / "changed-files.txt",
    }
    files["diff"].write_text(diff)
    files["body"].write_text(body or "(this pull request has an empty body)\n")
    files["files"].write_text("\n".join(sidecar["reviewable_files"]) + "\n")
    return files


def reviewer(lens: str, sidecar: dict[str, Any], paths: dict[str, Path]) -> tuple[str, str, str]:
    """Returns (brief, report path, witness literal) for one lens."""
    if lens not in LENS_TEMPLATE:
        raise Park(f"unknown lens: {lens!r}")
    report = f"reports/findings-{lens}.json"
    witness = f'"lens": "{lens}"'
    listed = sidecar["reviewable_files"]
    shown = listed[:200]
    changed = "\n".join(f"- `{path}`" for path in shown)
    if len(listed) > len(shown):
        changed += f"\n- ... and {len(listed) - len(shown)} more (read `{paths['files']}`)"
    brief = render(
        "reviewer-brief.md",
        {
            "NUMBER": str(sidecar["number"]),
            "DIFF_PATH": str(paths["diff"]),
            "BASE_TREE": sidecar["base_tree"],
            "BODY_PATH": str(paths["body"]),
            "CHANGED_FILES": changed,
            "RULES": config.template("rules.md").split("-->", 1)[-1].strip(),
            "LENS": config.template(LENS_TEMPLATE[lens]).split("-->", 1)[-1].strip(),
            "LENS_NAME": lens,
            "REPORT_PATH": report,
        },
    )
    return guard(brief, sidecar), report, witness


def verifier(
    finding: dict[str, Any], sidecar: dict[str, Any], paths: dict[str, Path]
) -> tuple[str, str, str]:
    """A blinded brief: no pull request body, no lens, no producer identity.

    A "correct code" note swings verdicts by more than twenty points and a judge
    passes its own family's output over half the time, so the verifier is told the
    claim and nothing about where it came from.
    """
    report = f"reports/verify-{finding['id']}.json"
    witness = f'"verification": "{finding["id"]}"'
    check = finding.get("rubric")
    if check:
        stated = "\n".join(f"- {key}: `{value}`" for key, value in sorted(check.items()))
        rubric_section = (
            "## The offered rubric\n\nRun this. It is the claim's own proposed proof:\n\n"
            f"{stated}\n\nIf it decides the question, your verdict follows from it. If it does\n"
            "not decide the question, say why and replace it."
        )
    else:
        rubric_section = (
            "## No rubric was offered\n\nNo mechanical check came with this claim. Decide whether "
            "one exists. If it does,\nstate it; if it does not, the claim cannot rise above a "
            "suggestion and your verdict\nshould say so."
        )
    if finding["category"] == "correctness" or finding["lens"] == "gating":
        poc_section = (
            "**A proof of concept, or a demotion.** For a claim in this class a verdict of\n"
            "CONFIRMED requires a failing demonstration on this tree: a test or a script that\n"
            "exits non-zero here. Put it in `repro`. It is then run against the unchanged tree\n"
            "too, and it only counts if it passes there - a repro that fails both ways proves\n"
            "nothing about this change. Without a repro that survives both legs, the strongest\n"
            "honest verdict is PLAUSIBLE."
        )
    else:
        poc_section = (
            "A repro is welcome but not required for this class of claim; the rubric decides it."
        )
    brief = render(
        "verifier-brief.md",
        {
            "BASE_TREE": sidecar["base_tree"],
            "DIFF_PATH": str(paths["diff"]),
            "FILE": finding["file"],
            "LINE": str(finding["line"]),
            "CATEGORY": finding["category"],
            "CLAIM": finding["claim"],
            "EVIDENCE": finding["evidence"],
            "RUBRIC_SECTION": rubric_section,
            "POC_SECTION": poc_section,
            "REPORT_PATH": report,
            "FINDING_ID": finding["id"],
        },
    )
    return guard(brief, sidecar), report, witness


def claims(sidecar: dict[str, Any], paths: dict[str, Path]) -> tuple[str, str, str]:
    report = "reports/claims.json"
    brief = render(
        "claims-brief.md",
        {
            "BODY_PATH": str(paths["body"]),
            "REPORT_PATH": report,
        },
    )
    return guard(brief, sidecar), report, '"claims"'


def body(summary: Path, sidecar: dict[str, Any]) -> tuple[str, str, str]:
    report = "reports/body.json"
    brief = render(
        "body-brief.md",
        {"SUMMARY_PATH": str(summary), "REPORT_PATH": report},
    )
    return guard(brief, sidecar), report, '"body"'
