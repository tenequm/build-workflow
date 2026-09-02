"""Judge verdict parsing and archiving, shared by the `gate` judge path and the CLI."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from bernstein_herdr import ledger
from bernstein_herdr.plan import Plan, Step

CERTAIN = re.compile(r"\bcertain\b", re.I)
PLAUSIBLE = re.compile(r"\bplausible\b", re.I)
#: The judge brief asks for these two lines verbatim, because counting the WORDS is
#: unreliable in both directions: "No defect, `certain` or `plausible`, is attributable
#: to this diff" contains both and means zero, and a review that discusses one defect
#: over four paragraphs mentions `certain` four times. A declared count is the number;
#: the word count is the fallback and is marked as such in the row.
DECLARED = {label: re.compile(rf"^\s*{label}\s*[:=]\s*(\d+)\b", re.I | re.M) for label in ("certain", "plausible")}

VERDICTS = ("do not merge", "merge after listed fixes", "merge as-is")


def judged_step(plan: Plan, step: Step) -> Step:
    """The step under review: the one a judge step's `judges` names, else the step itself."""
    return plan.step(step.judges) if step.judges else step


def record_verdict(plan: Plan, step: Step, worktree: Path) -> dict:
    """Parse the blind review in `worktree`, archive it under <run>/judge/, write the gate row.

    Shared by the judge step's watcher and the `judge-verdict` CLI, which name the
    step from opposite ends: the CLI is given the phase under review, the watcher the
    judge step that reviews it.

    `verdict.json` beside the copied review is what `fix-N` reads: the fix brief needs
    the counts and the verdict without re-parsing prose, and a `certain` of 0 is what
    turns that step into a no-op.
    """
    judged = judged_step(plan, step)
    dest = plan.run_dir / "judge" / judged.slug
    dest.mkdir(parents=True, exist_ok=True)
    verdict = parse_verdict(worktree / ".agents" / "blind-review.md")
    for name in ("blind-review.md", "scorecard.md"):
        src = worktree / ".agents" / name
        if src.exists():
            shutil.copy(src, dest / name)
    (dest / "verdict.json").write_text(json.dumps({"ts": ledger.now(), "judge_step": step.slug, **verdict}, indent=2))
    ledger.row(plan.run_dir, {"run_id": f"{plan.slug}-{judged.slug}-judge", "step": judged.slug,
                              "gate": "judge_step", "evidence": "verified", **verdict})
    return verdict


def _declared(text: str, label: str) -> int | None:
    m = DECLARED[label].search(text)
    return int(m.group(1)) if m else None


def parse_verdict(review: Path) -> dict:
    """The judge's verdict ROUTES the run; only `do not merge` blocks the merge.

    A judge that finds defects has done its job, and its own diff is a review file: it
    must merge so that `fix-N`, which depends on the judge step, can run at all. Blocking
    on `merge after listed fixes` or on a `certain` count made criteria "the judge finds
    the defects" and "fix-N fixes them" jointly unsatisfiable -- a blocked required gate
    fails the judge TASK (`task_lifecycle.py:3149`) and every dependent goes
    `blocked_by_failed_dep` (measured 2026-09-02). The counts and the verdict are recorded
    for the fix step to route on; they never decide the exit code.

    `do not merge` is the one verdict that still blocks: it says the reviewed work should
    not be in the branch, and a review that says so is a driver decision, not a fix item.
    """
    if not review.exists():
        return {"review_present": False, "block": True, "verdict": "missing",
                "certain": 0, "plausible": 0, "counts_declared": False, "reason": "no blind-review.md"}
    text = review.read_text()
    tail = text.split("Verdict", 1)[-1] if "Verdict" in text else text
    low = tail.lower()
    verdict = next((v for v in VERDICTS if v in low), "unclear")
    certain, plausible = _declared(text, "certain"), _declared(text, "plausible")
    declared = certain is not None and plausible is not None
    return {"review_present": True, "verdict": verdict,
            "certain": certain if certain is not None else len(CERTAIN.findall(tail)),
            "plausible": plausible if plausible is not None else len(PLAUSIBLE.findall(tail)),
            "counts_declared": declared,
            "do_not_merge": verdict == "do not merge", "merge_as_is": verdict == "merge as-is",
            "block": verdict == "do not merge"}
