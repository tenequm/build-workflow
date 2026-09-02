"""Judge verdict parsing and archiving, shared by the `gate` judge path and the CLI."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from bernstein_herdr import ledger
from bernstein_herdr.plan import Plan, Step

CERTAIN = re.compile(r"\bcertain\b", re.I)


def judged_step(plan: Plan, step: Step) -> Step:
    """The step under review: the one a judge step's `judges` names, else the step itself."""
    return plan.step(step.judges) if step.judges else step


def record_verdict(plan: Plan, step: Step, worktree: Path) -> dict:
    """Parse the blind review in `worktree`, archive it under <run>/judge/, write the gate row.

    Shared by the judge step's watcher and the `judge-verdict` CLI, which name the
    step from opposite ends: the CLI is given the phase under review, the watcher the
    judge step that reviews it.
    """
    judged = judged_step(plan, step)
    dest = plan.run_dir / "judge" / judged.slug
    dest.mkdir(parents=True, exist_ok=True)
    verdict = parse_verdict(worktree / ".agents" / "blind-review.md")
    for name in ("blind-review.md", "scorecard.md"):
        src = worktree / ".agents" / name
        if src.exists():
            shutil.copy(src, dest / name)
    ledger.row(plan.run_dir, {"run_id": f"{plan.slug}-{judged.slug}-judge", "step": judged.slug,
                              "gate": "judge_step", "evidence": "verified", **verdict})
    return verdict


def parse_verdict(review: Path) -> dict:
    """The judge's own three-way verdict decides; only `merge as-is` clears the gate.

    Counting the word "certain" across the whole review looked equivalent and is not:
    a review whose defect section reads "No defect, `certain` or `plausible`, is
    attributable to this diff" contains the word and means the opposite, and that
    blocked a `merge as-is` verdict. The count stays as recorded evidence, scoped to
    the verdict, but the verdict line is what decides -- and anything short of an
    explicit `merge as-is` (including `merge after listed fixes`) still blocks.
    """
    if not review.exists():
        return {"review_present": False, "block": True, "reason": "no blind-review.md"}
    text = review.read_text()
    verdict = text.split("Verdict", 1)[-1] if "Verdict" in text else text
    do_not_merge = "do not merge" in verdict.lower()
    merge_as_is = "merge as-is" in verdict.lower()
    return {"review_present": True, "certain_mentions": len(CERTAIN.findall(verdict)),
            "do_not_merge": do_not_merge, "merge_as_is": merge_as_is,
            "block": do_not_merge or not merge_as_is}
