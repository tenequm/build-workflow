"""Executing a finding's rubric, and the gold gate on a proof-of-concept.

Generic LLM judging of code runs at kappa 0.10-0.21 against execution truth; a
per-bug rubric reaches 0.75, and the rubric's author matters more than the judge
model. So the rubric runs HERE, in the driver, deterministically - a verifier model
is spent only on what execution cannot settle. Nothing in this module reads a model's
opinion; it reads exit codes.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from operator_driver.storage import Park

from . import sandbox
from .proc import git, git_bytes

HUNK_HEAD = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
GREP = ("rg", "--no-heading", "--line-number", "--color=never")


INTERPRETERS = ("sh", "bash", "zsh", "python", "python3", "node", "ruby", "perl")


def unrunnable(run: str, tree: Path) -> str | None:
    """Why a command rubric could not run at all, or None if it can be tried.

    One shape only, and it is the dangerous one: a rubric that hands an interpreter a
    script that is not there. The shell answers a missing file with a non-zero exit, and
    `expect: exit_nonzero` reads that as the check passing - a CONFIRMED verdict from a
    check that never executed. Measured 2026-09-11: a verifier wrote its repro to its
    own worktree and then named it in a rubric, and rubrics run against the shared tree.

    This deliberately does not police every path in a command line: `test -f gone.md`
    with `expect: exit_nonzero` is a legitimate absence proof, and refusing it would
    cost real findings.
    """
    words = run.split()
    target = None
    if words and words[0] in INTERPRETERS and len(words) > 1 and not words[1].startswith("-"):
        target = words[1]
    elif words and words[0].startswith("./"):
        target = words[0]
    if target is None or target.startswith("-"):
        return None
    path = Path(target)
    if path.is_absolute() or ".." in path.parts or (tree / path).exists():
        return None
    return f"the rubric runs {target!r}, which does not exist in the tree it executes against"


def _evaluate(expect: str, result: dict[str, Any], contains: str | None) -> bool:
    output = (result["stdout"] + result["stderr"]).strip()
    if expect == "exit_zero":
        return result["returncode"] == 0
    if expect == "exit_nonzero":
        return result["returncode"] != 0
    if expect == "empty":
        return output == ""
    if expect == "nonempty":
        return output != ""
    if expect == "contains":
        if not contains:
            raise Park("a contains expectation needs the literal it expects")
        return contains in output
    raise Park(f"unknown rubric expectation: {expect!r}")


def hunk_patch(repo: Path, base: str, head: str, path: str, start: int, end: int) -> bytes:
    """The subset of one file's diff whose new-side lines intersect [start, end]."""
    text = git_bytes(repo, "diff", "--no-color", "--no-renames", base, head, "--", path).decode(
        errors="replace"
    )
    lines = text.splitlines(keepends=True)
    header: list[str] = []
    blocks: list[tuple[int, int, list[str]]] = []
    current: list[str] | None = None
    span = (0, 0)
    for line in lines:
        match = HUNK_HEAD.match(line)
        if match:
            if current is not None:
                blocks.append((*span, current))
            new_start = int(match.group(3))
            new_count = int(match.group(4) or 1)
            span = (new_start, new_start + max(new_count, 1) - 1)
            current = [line]
        elif current is None:
            header.append(line)
        else:
            current.append(line)
    if current is not None:
        blocks.append((*span, current))
    selected = [block for low, high, block in blocks if not (high < start or low > end)]
    if not selected:
        raise Park(f"no hunk of {path} covers new-side lines {start}-{end}")
    return ("".join(header) + "".join("".join(block) for block in selected)).encode()


def _revert_worktree(sidecar: dict[str, Any], name: str, patch: bytes) -> Path:
    repo = Path(sidecar["repo_path"])
    scratch = Path(sidecar["scratch"]) / name
    if scratch.exists():
        shutil.rmtree(scratch, ignore_errors=True)
        git(repo, "worktree", "prune")
    git(repo, "worktree", "add", "--detach", "--quiet", str(scratch), sidecar["head"])
    patch_path = scratch / ".review-pr-revert.patch"
    patch_path.write_bytes(patch)
    git(scratch, "apply", "--reverse", str(patch_path))
    patch_path.unlink()
    return scratch


def execute(
    finding: dict[str, Any],
    sidecar: dict[str, Any],
    *,
    tier: str,
    timeout: float = 600,
) -> dict[str, Any]:
    """Run one finding's rubric. Returns the observation; it never raises on a failure."""
    check = finding.get("rubric")
    if check is None:
        return {"ran": False, "passed": False, "reason": "the finding states no rubric"}
    image = sidecar.get("sandbox_image")
    head = Path(sidecar["tree"])
    legs: list[dict[str, Any]] = []
    if check["kind"] == "command":
        blocked = unrunnable(check["run"], head)
        if blocked:
            return {"ran": False, "passed": False, "reason": blocked}
        result = sandbox.run(check["run"], head, tier_name=tier, image=image, timeout=timeout)
        legs.append({"leg": "head", **result})
        passed = _evaluate(check["expect"], result, check.get("contains"))
    elif check["kind"] == "grep":
        target = check["path"]
        if Path(target).is_absolute() or ".." in Path(target).parts:
            return {"ran": False, "passed": False, "reason": f"unsafe grep path {target!r}"}
        script = " ".join([*GREP, "--", _quote(check["pattern"]), _quote(target)])
        result = sandbox.run(script, head, tier_name=tier, image=image, timeout=timeout)
        legs.append({"leg": "head", **result})
        # rg exits 1 on no match, which is the signal here rather than a failure.
        passed = _evaluate(check["expect"], result, check.get("contains"))
    elif check["kind"] == "revert_test":
        path, span = check["hunk"].rsplit(":", 1)
        start, end = (int(value) for value in span.split("-"))
        at_head = sandbox.run(check["test"], head, tier_name=tier, image=image, timeout=timeout)
        legs.append({"leg": "head", **at_head})
        if at_head["returncode"] != 0:
            return {
                "ran": True,
                "passed": False,
                "reason": "the test does not pass at the pull request head, so it cannot flip",
                "kind": check["kind"],
                "legs": legs,
            }
        try:
            reverted = _revert_worktree(
                sidecar,
                f"revert-{finding['id']}",
                hunk_patch(
                    Path(sidecar["repo_path"]), sidecar["base"], sidecar["head"], path, start, end
                ),
            )
        except Park as exc:
            return {"ran": False, "passed": False, "reason": str(exc), "legs": legs}
        try:
            result = sandbox.run(
                check["test"], reverted, tier_name=tier, image=image, timeout=timeout
            )
        finally:
            # The reverted worktree registers a ref in the reviewed repo's .git; leaving
            # it accumulates locks across findings and across runs (suggestions.prove
            # already removes its own).
            git(Path(sidecar["repo_path"]), "worktree", "remove", "--force", str(reverted))
        legs.append({"leg": "reverted", **result})
        passed = _evaluate(check["expect"], result, check.get("contains"))
    else:
        raise Park(f"unknown rubric kind: {check['kind']!r}")
    return {
        "ran": True,
        "passed": passed,
        "kind": check["kind"],
        "expect": check["expect"],
        "legs": legs,
    }


def _quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def gold_gate(
    script: str,
    sidecar: dict[str, Any],
    *,
    tier: str,
    timeout: float = 600,
) -> dict[str, Any]:
    """A repro proves the pull request's defect only if it fails on head and passes on base.

    61.9% of decisive generated tests fail on the gold patch too, so a repro that fails
    both ways is evidence of nothing and demotes its finding.
    """
    head = sandbox.run(
        script,
        Path(sidecar["tree"]),
        tier_name=tier,
        image=sidecar.get("sandbox_image"),
        timeout=timeout,
    )
    base = sandbox.run(
        script,
        Path(sidecar["base_tree"]),
        tier_name=tier,
        image=sidecar.get("sandbox_image"),
        timeout=timeout,
    )
    fails_on_head = head["returncode"] != 0
    passes_on_base = base["returncode"] == 0
    if fails_on_head and passes_on_base:
        reason = "the repro fails on the pull request head and passes on base"
    elif not fails_on_head:
        reason = "the repro passes on the pull request head, so it demonstrates nothing"
    else:
        reason = "the repro fails on base as well, so it does not implicate this change"
    return {
        "passed": fails_on_head and passes_on_base,
        "fails_on_head": fails_on_head,
        "passes_on_base": passes_on_base,
        "reason": reason,
        "head": head,
        "base": base,
    }
