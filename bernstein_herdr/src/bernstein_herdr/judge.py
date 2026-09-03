"""Judge verdict parsing and archiving, shared by the `gate` judge path and the CLI."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from bernstein_herdr import ledger
from bernstein_herdr.plan import Plan, Step

#: The judge brief asks for these two lines verbatim, exactly once, in the file's last
#: three lines; counting the WORDS was unreliable in both directions and is gone.
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

    A malformed review also blocks, and that is safe where blocking on FINDINGS was
    not: a findings block punished the judge for doing its job, with no retry that
    could ever pass. A malformed block punishes a formatting failure that a fresh
    judge attempt fixes, and the alternative -- merging as `unclear` -- now dies one
    step later anyway at fix-N's refusal receipt, after a wasted spawn.

    The judge prompt requires the Certain /
    Plausible / Verdict block as the LAST three lines, exactly once each. The old
    parser split on the first word "Verdict" anywhere and fell back to counting
    the words `certain`/`plausible` in prose, so a duplicated or misplaced block
    merged as `unclear` and pushed the problem into fix-N's refusal path. Under
    an unattended run the right move is to refuse the judge merge so the engine
    retries the judge now (retro validation item 1/8, 2026-09-03).
    """
    if not review.exists():
        return {"review_present": False, "block": True, "verdict": "missing",
                "certain": 0, "plausible": 0, "counts_declared": False, "reason": "no blind-review.md"}
    raw = review.read_text()
    # Fenced code blocks are quoted material (a review may quote the required format or
    # a diff hunk containing `Certain:`); they never carry the review's own declaration.
    text = re.sub(r"```.*?```", "", raw, flags=re.S)
    tail_lines = [l.strip() for l in text.splitlines() if l.strip()][-3:]
    low = "\n".join(tail_lines).lower()
    verdict = next((v for v in VERDICTS if v in low), None)
    certain_all = DECLARED["certain"].findall(text)
    plausible_all = DECLARED["plausible"].findall(text)
    problems = []
    if verdict is None:
        problems.append("no legal Verdict line in the last three lines")
    if len(certain_all) != 1:
        problems.append(f"{len(certain_all)} `Certain:` lines (need exactly 1)")
    if len(plausible_all) != 1:
        problems.append(f"{len(plausible_all)} `Plausible:` lines (need exactly 1)")
    if problems:
        return {"review_present": True, "verdict": verdict or "unclear",
                "certain": int(certain_all[0]) if len(certain_all) == 1 else 0,
                "plausible": int(plausible_all[0]) if len(plausible_all) == 1 else 0,
                "counts_declared": False, "do_not_merge": False, "merge_as_is": False,
                "block": True, "reason": "malformed review: " + "; ".join(problems)}
    certain, plausible = int(certain_all[0]), int(plausible_all[0])
    return {"review_present": True, "verdict": verdict,
            "certain": certain, "plausible": plausible, "counts_declared": True,
            "do_not_merge": verdict == "do not merge", "merge_as_is": verdict == "merge as-is",
            "block": verdict == "do not merge"}
