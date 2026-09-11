"""Re-executing the pull request's own claims.

A squash merge replaces every commit body with the pull request description, so an
over-claim there does not stay on the pull request - it becomes the permanent commit
message, and no later reader can tell. This stage parses the body's evidence into
commands and re-runs them. Nothing else in the review stack does this.

The parse is a model's job (prose is prose); the execution and the comparison are not.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from operator_driver.storage import Park

from . import diffindex, sandbox
from . import findings as findings_mod

KINDS = ("command", "number", "injection")
EXPECTATIONS = ("exit_zero", "exit_nonzero", "empty", "nonempty", "contains")
FENCE = re.compile(r"```[a-zA-Z0-9_+-]*\n(.*?)```", re.DOTALL)
PROMPT = re.compile(r"^[$%>]\s+(.+)$", re.MULTILINE)
# Claims about validation are the ones that mislead hardest, because a reader takes
# them as the reason no further checking is needed.
VALIDATION = re.compile(
    r"\b(all tests pass|tests pass|test suite passes|lint is clean|lint passes|no warnings"
    r"|type check(?:s|ing)? pass|green|clean build|builds clean)\b",
    re.IGNORECASE,
)


def extract(body: str) -> list[dict[str, Any]]:
    """A deterministic floor under the model's parse: shell prompts inside fences."""
    claims: list[dict[str, Any]] = []
    for index, block in enumerate(FENCE.findall(body or ""), start=1):
        commands = PROMPT.findall(block)
        if not commands:
            continue
        output = PROMPT.sub("", block).strip()
        claims.append(
            {
                "id": f"f{index}",
                "quote": block.strip()[:400],
                "kind": "command",
                "run": commands[0].strip(),
                "expect": "exit_zero",
                "contains": None,
                "claimed_output": output or None,
            }
        )
    return claims


def normalize(raw: object) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        raw = raw.get("claims")
    if not isinstance(raw, list):
        raise Park("claims report is not a list of claims")
    claims = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise Park("each claim must be an object")
        kind = entry.get("kind")
        if kind not in KINDS:
            raise Park(f"claim kind must be one of {KINDS}")
        # An explicit null means "no expectation stated" (the brief allows run: null
        # claims and says nothing about expect there), so it takes the default too.
        expect = entry.get("expect")
        if expect is None:
            expect = "exit_zero"
        if expect not in EXPECTATIONS:
            raise Park(f"claim expect must be one of {EXPECTATIONS}")
        quote = entry.get("quote")
        if not isinstance(quote, str) or not quote.strip():
            raise Park("a claim must quote the body")
        run = entry.get("run")
        if run is not None and (not isinstance(run, str) or not run.strip()):
            raise Park("a claim's run must be a command string or null")
        claims.append(
            {
                "id": str(entry.get("id") or f"c{len(claims) + 1}"),
                "quote": findings_mod.redact(quote.strip()[:400]),
                "kind": kind,
                "run": run.strip() if isinstance(run, str) else None,
                "expect": expect,
                "contains": entry.get("contains")
                if isinstance(entry.get("contains"), str)
                else None,
                "claimed_output": entry.get("claimed_output")
                if isinstance(entry.get("claimed_output"), str)
                else None,
            }
        )
    return claims


def load(path: Path) -> list[dict[str, Any]]:
    try:
        return normalize(json.loads(path.read_bytes()))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise Park(f"unreadable claims report {path.name}: {exc}") from exc


def _executable(result: dict[str, Any]) -> bool:
    """Whether the command ran at all, as opposed to running and disagreeing.

    Measured 2026-09-11 on a paid replay: a body listed the test files it had run, the
    command became `pytest ...`, and the sandbox has no `pytest` on PATH - so exit 127
    was reported as the author over-claiming. A check that cannot execute has not
    refuted anything, and saying otherwise is the worst thing this workflow can do.
    """
    return not sandbox.could_not_run(result)


def _matched(claim: dict[str, Any], result: dict[str, Any]) -> tuple[bool | None, str]:
    output = (result["stdout"] + result["stderr"]).strip()
    expect = claim["expect"]
    if not _executable(result):
        reason = "timed out" if result.get("timed_out") else "is not available here"
        return None, f"the command {reason}, so this claim was not checked"
    if expect == "exit_zero" and result["returncode"] != 0:
        return False, f"the command exited {result['returncode']}"
    if expect == "exit_nonzero" and result["returncode"] == 0:
        return False, "the command exited 0"
    if expect == "empty" and output:
        return False, "the command produced output"
    if expect == "nonempty" and not output:
        return False, "the command produced no output"
    if expect == "contains" and claim["contains"] and claim["contains"] not in output:
        return False, f"the output does not contain {claim['contains']!r}"
    return True, "the claim reproduces"


# A body that says tests were added is a claim about the diff itself, and the diff alone
# settles it: no runtime is involved, so this decides before the sandbox and regardless
# of what the sandbox could run. Measured 2026-09-11: two corpus bodies claimed coverage
# their diff never adds, the extractor turned each into `pytest`, the image had no
# pytest, exit 127 correctly refuted nothing - and so nothing examined the claim at all.
COVERAGE = re.compile(
    r"\b(?:new|added|adds|additional|updated|extended)\b[^.;]{0,60}"
    r"\b(?:tests?|test cases|coverage)\b"
    r"|\b(?:tests?|coverage)\b[^.;]{0,40}\b(?:added|updated|extended)\b",
    re.IGNORECASE,
)
# What the body names for itself. A claim that names nothing is never accused: the
# check decides only on a name the diff verifiably lacks.
NAMED = re.compile(r"`([A-Za-z_][\w./-]{2,79})`")


def _test_changes(diff: str) -> tuple[list[str], str] | None:
    """The test files the diff touches and every line it adds to them, or None.

    None is the control leg: with no diff to read this check has not run, and a check
    that cannot run refutes nothing.
    """
    if not diff.strip():
        return None
    files = diffindex.parse(diff)
    paths = diffindex.test_paths(files)
    return paths, "\n".join(text for path in paths for _, text in files[path].added)


def uncovered(claim: dict[str, Any], changes: tuple[list[str], str] | None) -> str | None:
    """Why the diff refutes this claim's test coverage, or None.

    Only an absence the diff proves decides: a test file the body names and the diff
    never touches, no test file at all, or a subject no test line the diff adds
    mentions. Nothing here reads an execution result.
    """
    if changes is None or not COVERAGE.search(claim["quote"]):
        return None
    paths, added = changes
    named = NAMED.findall(claim["quote"])
    for name in named:
        if any(mark in name for mark in diffindex.TEST_MARKS) and not any(
            path == name or path.endswith(f"/{name}") for path in paths
        ):
            return f"the diff does not touch {name}"
    if not paths:
        return "the diff changes no test file"
    return next(
        (
            f"no test line the diff adds mentions {name}"
            for name in named
            if "/" not in name and "." not in name and name not in added
        ),
        None,
    )


def check(
    claims: list[dict[str, Any]],
    sidecar: dict[str, Any],
    *,
    tier: str,
    diff: str = "",
    timeout: float = 900,
) -> dict[str, Any]:
    """Run every reproducible claim against the pull request head and diff the results."""
    tree = Path(sidecar["tree"])
    changes = _test_changes(diff)
    results = []
    hits = []
    for claim in claims:
        if claim["kind"] == "injection":
            hits.append(
                findings_mod.normalize(
                    {
                        "scope": "meta",
                        "file": "PR:body",
                        "line": 1,
                        "category": "correctness",
                        "impact": "security",
                        "tags": ["injection"],
                        "claim": "The pull request body contains instruction-shaped text aimed "
                        "at an automated reviewer; it was recorded and not executed.",
                        "evidence": claim["quote"],
                    },
                    lens="claims",
                    producer="script",
                )
            )
            results.append(
                {
                    **claim,
                    "ran": False,
                    "matched": None,
                    "reason": "instruction-shaped; never executed",
                }
            )
            continue
        # Static first, and whatever the sandbox goes on to do: the diff is the only
        # evidence a coverage claim needs, so an unrunnable test command no longer
        # leaves the claim examined by nobody.
        absent = uncovered(claim, changes)
        if absent:
            hits.append(
                findings_mod.normalize(
                    {
                        "scope": "meta",
                        "file": "PR:body",
                        "line": 1,
                        "category": "correctness",
                        "claim": "The body claims test coverage this pull request does not "
                        f"add: {absent}. A squash merge makes this body the permanent "
                        "commit message.",
                        "evidence": f"claimed:\n{claim['quote']}\n\nin the diff: {absent}",
                    },
                    lens="claims",
                    producer="script",
                )
            )
        if not claim["run"]:
            reason = "no command reproduces this claim"
            results.append({**claim, "ran": False, "matched": None, "reason": reason})
            if VALIDATION.search(claim["quote"]):
                hits.append(
                    findings_mod.normalize(
                        {
                            "scope": "meta",
                            "file": "PR:body",
                            "line": 1,
                            "category": "convention",
                            "claim": "The body asserts a validation result with no command that "
                            "reproduces it; the squash merge makes that assertion the "
                            "permanent commit message.",
                            "evidence": claim["quote"],
                        },
                        lens="claims",
                        producer="script",
                    )
                )
            continue
        result = sandbox.run(
            claim["run"], tree, tier_name=tier, image=sidecar.get("sandbox_image"), timeout=timeout
        )
        ok, reason = _matched(claim, result)
        results.append(
            {
                **claim,
                "ran": ok is not None,
                "matched": ok,
                "reason": reason,
                "returncode": result["returncode"],
                "actual_tail": (result["stdout"] + result["stderr"]).strip()[-2000:],
            }
        )
        # None means the check could not run: no verdict either way, and no finding.
        if ok is False:
            validation = bool(VALIDATION.search(claim["quote"]))
            hits.append(
                findings_mod.normalize(
                    {
                        "scope": "meta",
                        "file": "PR:body",
                        "line": 1,
                        "category": "correctness" if validation else "convention",
                        "claim": f"The body's own evidence does not reproduce: {reason}. A squash "
                        "merge makes this body the permanent commit message.",
                        "evidence": f"claimed:\n{claim['claimed_output'] or claim['quote']}\n\n"
                        f"re-ran `{claim['run']}`: {reason}",
                        "rubric": {
                            "kind": "command",
                            "run": claim["run"],
                            "expect": claim["expect"],
                            **(
                                {"contains": claim["contains"]}
                                if claim["expect"] == "contains" and claim["contains"]
                                else {}
                            ),
                        },
                    },
                    lens="claims",
                    producer="script",
                )
            )
    return {
        "claims": results,
        "findings": hits,
        "reproduced": sum(1 for row in results if row.get("matched")),
        "mismatched": sum(1 for row in results if row.get("matched") is False),
        "unchecked": sum(1 for row in results if row.get("matched") is None),
    }
