"""Proven suggestions: speculation, but only the kind with a rollback and a receipt.

A `suggestion` block on a GitHub review is a one-click commit for the author, so
posting one that does not compile is worse than posting prose. Each is applied to a
throwaway worktree, the pinned validation command runs, and only a suggestion that
survives keeps its block; the rest are downgraded to prose with the reason attached.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from operator_driver.storage import Park

from . import sandbox
from .proc import git


def apply(finding: dict[str, Any], worktree: Path) -> str:
    """Replace the finding's line span with the suggested text. Returns the old span."""
    change = finding.get("suggestion")
    if not change:
        raise Park(f"finding {finding['id']} carries no suggestion")
    target = worktree / finding["file"]
    if not target.is_file():
        raise Park(f"suggestion targets a file that is not in the tree: {finding['file']}")
    lines = target.read_text().splitlines(keepends=True)
    start = int(change.get("start_line", change["line"]))
    end = int(change["line"])
    if not 1 <= start <= end <= len(lines):
        raise Park(f"suggestion span {start}-{end} is outside {finding['file']}")
    replaced = "".join(lines[start - 1 : end])
    replacement = change["replacement"]
    if not replacement.endswith("\n"):
        replacement += "\n"
    target.write_text("".join(lines[: start - 1]) + replacement + "".join(lines[end:]))
    return replaced


def prove(
    finding: dict[str, Any],
    sidecar: dict[str, Any],
    *,
    tier: str,
    timeout: float = 1800,
) -> dict[str, Any]:
    """Apply, gate, and report. The worktree is disposable; the verdict is not."""
    repo = Path(sidecar["repo_path"])
    scratch = Path(sidecar["scratch"]) / f"suggest-{finding['id']}"
    if scratch.exists():
        shutil.rmtree(scratch, ignore_errors=True)
        git(repo, "worktree", "prune")
    git(repo, "worktree", "add", "--detach", "--quiet", str(scratch), sidecar["head"])
    try:
        try:
            replaced = apply(finding, scratch)
        except Park as exc:
            return {"id": finding["id"], "applied": False, "proven": False, "reason": str(exc)}
        result = sandbox.run(
            sidecar["gate"]["command"],
            scratch,
            tier_name=tier,
            image=sidecar.get("sandbox_image"),
            timeout=timeout,
        )
        proven = result["returncode"] == 0
        return {
            "id": finding["id"],
            "applied": True,
            "proven": proven,
            "replaced": replaced,
            "command": sidecar["gate"]["command"],
            "returncode": result["returncode"],
            "reason": "the pinned validation command passes with this suggestion applied"
            if proven
            else f"the pinned validation command exited {result['returncode']} with it applied",
            "output_tail": (result["stdout"] + result["stderr"]).strip()[-2000:],
        }
    finally:
        git(repo, "worktree", "remove", "--force", str(scratch))


def prove_all(
    findings: list[dict[str, Any]],
    sidecar: dict[str, Any],
    *,
    tier: str,
    cap: int,
) -> dict[str, dict[str, Any]]:
    # Each proof is a full run of the pinned validation command, the most expensive
    # thing this workflow executes. Only a correctness suggestion earns one; anything
    # else posts as prose, which is what an unproven suggestion becomes anyway.
    candidates = [
        f
        for f in findings
        if f.get("suggestion") and f["verdict"] != "DROPPED" and f["category"] == "correctness"
    ]
    skipped = [
        f
        for f in findings
        if f.get("suggestion") and f["verdict"] != "DROPPED" and f["category"] != "correctness"
    ]
    candidates.sort(key=lambda f: (f["file"], f["line"]))
    proofs = {}
    for finding in candidates[:cap]:
        proofs[finding["id"]] = prove(finding, sidecar, tier=tier)
    for finding in candidates[cap:]:
        proofs[finding["id"]] = {
            "id": finding["id"],
            "applied": False,
            "proven": False,
            "reason": f"past the {cap}-suggestion proof budget for this review",
        }
    for finding in skipped:
        proofs[finding["id"]] = {
            "id": finding["id"],
            "applied": False,
            "proven": False,
            "reason": "only correctness suggestions are proven; offered as prose",
        }
    return proofs
