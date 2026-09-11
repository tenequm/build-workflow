"""Stage 0: the mechanical checks, before any model spawns.

Derived from what upstream's own machinery demonstrably enforces. Every rule records
a pass, a fail or an explicit skip, because a report that claims a clean stage 0 has
to say which rules actually ran - an unrecorded skip is indistinguishable from a pass.

Rule sets are per repository. `bernstein` adds the two rules only that repo's bots
enforce; every other repository gets `generic`, which is the repo-agnostic subset.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from operator_driver.storage import Park

from . import diffindex, findings, sandbox
from .proc import git, git_ok

FRAGMENT_DIR = "docs/release-notes/fragments/"
SIGNOFF = re.compile(r"^\s*Signed-off-by:", re.MULTILINE)
# The characters upstream's hygiene denylist names, written as escapes so this file -
# whose whole job is to find them - stays plain ASCII itself.
UNICODE_PROSE = re.compile(r"[\u2010-\u2015\u2018-\u201f\u2026\u00a0]")
UNICODE_NAMES = {
    "\u2010": "hyphen",
    "\u2011": "non-breaking hyphen",
    "\u2012": "figure dash",
    "\u2013": "en dash",
    "\u2014": "em dash",
    "\u2015": "horizontal bar",
    "\u2018": "left single quote",
    "\u2019": "right single quote",
    "\u201a": "single low quote",
    "\u201b": "single high-reversed quote",
    "\u201c": "left double quote",
    "\u201d": "right double quote",
    "\u201e": "double low quote",
    "\u201f": "double high-reversed quote",
    "\u2026": "ellipsis",
    "\u00a0": "non-breaking space",
}
# Instruction-shaped content in material that is supposed to be judged, not obeyed.
# The scan is mechanical so the fixture's planted injection is caught even when a
# model misses it, and so the report can prove the pipeline read it without acting.
INJECTION = re.compile(
    r"ignore (?:all )?(?:previous|prior|above) instructions"
    r"|disregard (?:all )?(?:previous|prior|the) (?:instructions|rules)"
    r"|you are now|new instructions:|system prompt"
    r"|approve this (?:pr|pull request|change)|mark this as (?:approved|clean)"
    r"|do not report|skip the review|report no (?:issues|findings)"
    r"|run the following command",
    re.IGNORECASE,
)
REGRESSION_LABEL = "regression"


def _article(name: str) -> str:
    return ("An " if name[0] in "aeiou" else "A ") + name


def _finding(entry: dict[str, Any]) -> dict[str, Any]:
    return findings.normalize(entry, lens="house-rules", producer="script")


def prose_hygiene(ctx: dict[str, Any]) -> dict[str, Any]:
    """Their denylist names em-dashes; plain ASCII with single hyphens passes."""
    pr = ctx["pr"]
    surfaces: list[tuple[str, str]] = [
        ("PR:title", str(pr.get("title") or "")),
        ("PR:body", str(pr.get("body") or "")),
        ("PR:branch", str(pr.get("headRefName") or "")),
    ]
    for commit in pr.get("commits") or []:
        sha = str(commit.get("oid") or commit.get("sha") or "")[:12] or "commit"
        message = f"{commit.get('messageHeadline', '')}\n{commit.get('messageBody', '')}"
        surfaces.append((f"PR:commit/{sha}", message))
    hits = []
    for surface, text in surfaces:
        # One finding per surface and character, counted. Five em dashes in one commit
        # message are one thing to fix, and five separate findings would share an id.
        counted: dict[str, list[int]] = {}
        for match in UNICODE_PROSE.finditer(text):
            counted.setdefault(match.group(0), []).append(match.start())
        for char, offsets in sorted(counted.items()):
            name = UNICODE_NAMES.get(char, "unicode punctuation")
            part = surface.split(":", 1)[1]
            times = "" if len(offsets) == 1 else f", {len(offsets)} times"
            hits.append(
                _finding(
                    {
                        "scope": "meta",
                        "file": surface,
                        "line": 1,
                        "category": "convention",
                        "claim": f"{_article(name)} character appears in the {part}"
                        f"{times}, which the prose hygiene workflow scans for.",
                        "evidence": f"{surface} U+{ord(char):04X} at offset(s) "
                        + ", ".join(str(offset) for offset in offsets[:10]),
                        "rubric": {
                            "kind": "grep",
                            "expect": "empty",
                            "path": ".",
                            "pattern": f"\\x{{{ord(char):04x}}}",
                        },
                    }
                )
            )
    return {
        "rule": "prose_hygiene",
        "result": "fail" if hits else "pass",
        "detail": f"{len(surfaces)} surfaces scanned",
        "findings": hits,
    }


def no_signoff(ctx: dict[str, Any]) -> dict[str, Any]:
    """Their governance has no CLA and forbids adding a sign-off trailer."""
    pr = ctx["pr"]
    hits = []
    surfaces = [("PR:body", str(pr.get("body") or ""))]
    for commit in pr.get("commits") or []:
        sha = str(commit.get("oid") or commit.get("sha") or "")[:12] or "commit"
        surfaces.append((f"PR:commit/{sha}", str(commit.get("messageBody") or "")))
    for surface, text in surfaces:
        if SIGNOFF.search(text):
            hits.append(
                _finding(
                    {
                        "scope": "meta",
                        "file": surface,
                        "line": 1,
                        "category": "convention",
                        "claim": "A Signed-off-by trailer is present, which this project's "
                        "governance forbids adding.",
                        "evidence": f"{surface} carries a Signed-off-by line",
                        "rubric": {
                            "kind": "grep",
                            "expect": "empty",
                            "path": ".",
                            "pattern": "Signed-off-by:",
                        },
                    }
                )
            )
    return {
        "rule": "no_signoff",
        "result": "fail" if hits else "pass",
        "detail": f"{len(surfaces)} surfaces scanned",
        "findings": hits,
    }


def injection_scan(ctx: dict[str, Any]) -> dict[str, Any]:
    """Instruction-shaped content is material to report, never direction to follow."""
    hits = []
    pr = ctx["pr"]
    for surface, text in (
        ("PR:title", str(pr.get("title") or "")),
        ("PR:body", str(pr.get("body") or "")),
    ):
        match = INJECTION.search(text)
        if match:
            hits.append(
                _finding(
                    {
                        "scope": "meta",
                        "file": surface,
                        "line": 1,
                        "category": "correctness",
                        "impact": "security",
                        "tags": ["injection"],
                        "claim": "The pull request body contains instruction-shaped text aimed at "
                        "an automated reviewer; it was read as material and not followed.",
                        "evidence": f"{surface}: {match.group(0)[:120]}",
                        "rubric": {
                            "kind": "grep",
                            "expect": "nonempty",
                            "path": ".",
                            "pattern": re.escape(match.group(0)[:60]),
                        },
                    }
                )
            )
    for path, diff in ctx["files"].items():
        for line, text in diff.added:
            match = INJECTION.search(text)
            if match:
                hits.append(
                    _finding(
                        {
                            "file": path,
                            "line": line,
                            "category": "correctness",
                            "impact": "security",
                            "tags": ["injection"],
                            "claim": "An added line contains instruction-shaped text aimed at an "
                            "automated reader; it was read as material and not followed.",
                            "evidence": f"{path}:{line}: {text.strip()[:160]}",
                            "rubric": {
                                "kind": "grep",
                                "expect": "nonempty",
                                "path": path,
                                "pattern": re.escape(match.group(0)[:60]),
                            },
                        }
                    )
                )
    return {
        "rule": "injection_scan",
        "result": "fail" if hits else "pass",
        "detail": f"{len(ctx['files'])} files and 2 metadata surfaces scanned",
        "findings": hits,
    }


def validation_command(ctx: dict[str, Any]) -> dict[str, Any]:
    """Polish's own rule, promoted to a machine check."""
    side = ctx["sidecar"]
    if not side.get("gate_edited"):
        return {
            "rule": "validation_command",
            "result": "pass",
            "detail": f"{side['gate']['command']!r} pinned from "
            f"{side['gate'].get('path', 'the operator')}",
            "findings": [],
        }
    path = side["gate"].get("path", "CLAUDE.md")
    return {
        "rule": "validation_command",
        "result": "fail",
        "detail": f"{path} differs between {side['base_ref']} and the pull request head",
        "findings": [
            _finding(
                {
                    "scope": "meta",
                    "file": "CHECK:gate",
                    "line": 1,
                    "category": "correctness",
                    "claim": f"This pull request edits {path}, the file the validation command is "
                    "read from; the command executed here is the base branch's.",
                    "evidence": f"{side['base_ref']}:{path} blob {side['gate']['blob'][:12]} "
                    f"differs at {side['head'][:12]}",
                    "rubric": {
                        "kind": "command",
                        "expect": "exit_nonzero",
                        "run": f"git diff --quiet {side['base_ref']} {side['head']} -- {path}",
                    },
                }
            )
        ],
    }


def release_notes_fragment(ctx: dict[str, Any]) -> dict[str, Any]:
    """The one requirement their review bot has demonstrably blocked over."""
    side = ctx["sidecar"]
    number = side["number"]
    fragments = [path for path in ctx["files"] if path.startswith(FRAGMENT_DIR)]
    if not fragments:
        return {
            "rule": "release_notes_fragment",
            "result": "fail",
            "detail": f"no file added under {FRAGMENT_DIR}",
            "findings": [
                _finding(
                    {
                        "scope": "meta",
                        "file": "CHECK:release-notes",
                        "line": 1,
                        "category": "convention",
                        "claim": f"No release-notes fragment is present under {FRAGMENT_DIR}; the "
                        "review bot blocks on this.",
                        "evidence": f"{len(ctx['files'])} changed files, none under {FRAGMENT_DIR}",
                        "rubric": {
                            "kind": "grep",
                            "expect": "nonempty",
                            "path": FRAGMENT_DIR,
                            "pattern": f"\\(#{number}\\)",
                        },
                    }
                )
            ],
        }
    hits = []
    tree = Path(side["tree"])
    for path in fragments:
        file = tree / path
        text = file.read_text(errors="replace") if file.is_file() else ""
        lines = [line for line in text.splitlines() if line.strip()]
        closing = lines[-1].strip() if lines else ""
        problems = []
        if not any(line.startswith("## ") for line in lines):
            problems.append("no `## <title>` heading")
        if closing != f"(#{number})":
            problems.append(f"last line is {closing!r}, not '(#{number})'")
        if problems:
            hits.append(
                _finding(
                    {
                        "file": path,
                        "line": max(len(text.splitlines()), 1),
                        "category": "convention",
                        "claim": "The release-notes fragment does not close with its own pull request "
                        f"number: {'; '.join(problems)}.",
                        "evidence": f"{path} last non-empty line: {closing!r}",
                        "rubric": {
                            "kind": "grep",
                            "expect": "nonempty",
                            "path": path,
                            "pattern": f"^\\(#{number}\\)$",
                        },
                    }
                )
            )
    return {
        "rule": "release_notes_fragment",
        "result": "fail" if hits else "pass",
        "detail": f"{len(fragments)} fragment(s) checked against (#{number})",
        "findings": hits,
    }


def bisect_annotation(ctx: dict[str, Any]) -> dict[str, Any]:
    """A files-touched heuristic, annotated as a lead. Never a verdict - measured
    2026-09-07, the label landed on a tuning fix with zero overlap with the failure."""
    labels = [str((label or {}).get("name", "")).lower() for label in ctx["pr"].get("labels") or []]
    if REGRESSION_LABEL not in labels:
        return {
            "rule": "bisect_annotation",
            "result": "pass",
            "detail": "no regression label on this pull request",
            "findings": [],
        }
    return {
        "rule": "bisect_annotation",
        "result": "fail",
        "detail": "regression label present; annotated as a lead",
        "findings": [
            _finding(
                {
                    "scope": "meta",
                    "file": "CHECK:bisect",
                    "line": 1,
                    "category": "convention",
                    "tags": ["heuristic", "out-of-diff"],
                    "claim": "A bisect-on-red regression label is present; that label names the "
                    "highest-file-count commit since the last green main run, which is a "
                    "files-touched heuristic to verify and not a verdict on this change.",
                    "evidence": "labels: " + ", ".join(sorted(labels)),
                }
            )
        ],
    }


def tests_fail_on_base(ctx: dict[str, Any]) -> dict[str, Any]:
    """Their bot's evidence step, reproduced locally and selectively.

    Run only when the pull request touches tests, which is how their own bot behaves.
    The non-test changes are reverted to base in a scratch worktree and the pull
    request's tests re-run there: a test that passes without the change under it
    witnesses nothing.
    """
    side = ctx["sidecar"]
    tests = side["test_files"]
    if not tests:
        return {
            "rule": "tests_fail_on_base",
            "result": "skipped",
            "detail": "the pull request changes no test files",
            "findings": [],
        }
    test_cmd = side.get("test_cmd") or side["gate"]["command"]
    timeout = float(side.get("test_timeout_s", 900))
    image = side.get("sandbox_image")
    at_head = sandbox.run(
        test_cmd, Path(side["tree"]), tier_name=ctx["tier"], image=image, timeout=timeout
    )
    if at_head["returncode"] != 0:
        # The control leg, and the whole reason this rule can be trusted: a command that
        # cannot run here fails with the change reverted too, which would read as a clean
        # pass. Measured 2026-09-11 against a real pull request, where the documented
        # command needed network the sandbox denies.
        return {
            "rule": "tests_fail_on_base",
            "result": "inconclusive",
            "detail": f"{test_cmd!r} exits {at_head['returncode']} on the pull request head "
            "itself, so reverting anything proves nothing; pass --test-cmd a command that "
            "passes here",
            "findings": [],
            "evidence": {"head": at_head},
        }
    scratch = Path(side["scratch"]) / "fail-on-base"
    repo = Path(side["repo_path"])
    git(repo, "worktree", "prune")
    if not scratch.exists():
        git(repo, "worktree", "add", "--detach", "--quiet", str(scratch), side["head"])
    reverted = [path for path in ctx["files"] if path not in tests]
    for path in reverted:
        if git_ok(repo, "cat-file", "-e", f"{side['base']}:{path}"):
            git(scratch, "checkout", side["base"], "--", path)
        else:
            (scratch / path).unlink(missing_ok=True)
    result = sandbox.run(test_cmd, scratch, tier_name=ctx["tier"], image=image, timeout=timeout)
    passed = result["returncode"] == 0
    detail = (
        f"{test_cmd!r} passes on the head, then reverting {len(reverted)} non-test path(s) "
        f"to base gives exit {result['returncode']} in the {result['tier']} sandbox"
    )
    hits = []
    if passed:
        hits.append(
            _finding(
                {
                    "scope": "meta",
                    "file": "CHECK:tests-fail-on-base",
                    "line": 1,
                    "category": "convention",
                    "claim": "The pull request's tests still pass with its non-test changes reverted "
                    "to base, so they do not witness the change they ship with.",
                    "evidence": detail,
                    "rubric": {"kind": "command", "expect": "exit_nonzero", "run": test_cmd},
                }
            )
        )
    return {
        "rule": "tests_fail_on_base",
        "result": "fail" if passed else "pass",
        "detail": detail,
        "findings": hits,
        "evidence": {"head": at_head, "reverted": result},
    }


GENERIC = (prose_hygiene, no_signoff, injection_scan, validation_command, tests_fail_on_base)
RULE_SETS: dict[str, tuple] = {
    "generic": GENERIC,
    "bernstein": (*GENERIC, release_notes_fragment, bisect_annotation),
}


def lint(sidecar: dict[str, Any], pr: dict[str, Any], diff: str, *, tier: str) -> dict[str, Any]:
    name = sidecar.get("rules", "generic")
    rules = RULE_SETS.get(name)
    if rules is None:
        raise Park(f"unknown rule set: {name!r} (have {sorted(RULE_SETS)})")
    ctx = {
        "sidecar": sidecar,
        "pr": pr,
        "files": diffindex.reviewable(diffindex.parse(diff)),
        "tier": tier,
    }
    checks = [rule(ctx) for rule in rules]
    return {
        "rules": name,
        "tier": tier,
        "checks": [
            {key: value for key, value in check.items() if key != "findings"} for check in checks
        ],
        "findings": [finding for check in checks for finding in check["findings"]],
    }
