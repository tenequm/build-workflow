"""Judge staging and verdict parsing, shared by the judge step, the judge gate and the CLI."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from bernstein_herdr import ledger
from bernstein_herdr.plan import Plan, Step

TEMPLATES = Path(__file__).resolve().parents[3] / "templates"
CERTAIN = re.compile(r"\bcertain\b", re.I)


def stage_judge(plan: Plan, step: Step, worktree: Path) -> Path:
    """<run>/judge/<step>/ with W/ = base + the step's diff applied and staged, brief, reports, prompt."""
    jd = plan.run_dir / "judge" / step.slug
    jd.mkdir(parents=True, exist_ok=True)
    wt = jd / "W"
    if wt.exists():
        subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=worktree, capture_output=True, check=False)
    subprocess.run(["git", "worktree", "add", "--detach", str(wt), step.base], cwd=worktree, check=True, capture_output=True)
    patch = subprocess.run(["git", "diff", step.base, "--", ".", ":!.agents"], cwd=worktree, capture_output=True, text=True, check=True).stdout
    (jd / "W.patch").write_text(patch)
    if patch.strip():
        subprocess.run(["git", "apply", "--index", "../W.patch"], cwd=wt, check=True, capture_output=True)
    if step.brief.exists():
        shutil.copy(step.brief, jd / "brief.md")
    reports = plan.run_dir / "reports"
    if reports.exists():
        (jd / "reports").mkdir(exist_ok=True)
        for r in reports.glob("*/report.md"):
            shutil.copy(r, jd / "reports" / f"{r.parent.name}.md")
    prompt = (TEMPLATES / "judge-prompt.md").read_text().replace("<judge dir>", str(jd))
    (jd / "judge-prompt.md").write_text(prompt)
    return jd


def judged_step(plan: Plan, step: Step) -> Step:
    """The step under review: the one a judge step's `judges` names, else the step itself."""
    return plan.step(step.judges) if step.judges else step


def judge_worktree(plan: Plan, step: Step, root: Path) -> Path:
    """The reviewed change on its own: `<run>/judge/<phase>/W` at the phase's base with
    the phase's archived diff applied and staged.

    Two reasons not to hand the judge the repo root. Bernstein gives a step with no
    owned files no worktree, so the judge would read -- and could edit -- the live
    checkout. And it starts a dependent as soon as its dependency is `done`, while the
    merge-back happens later during the reap (spawner_merge.py:735), so the root is
    still pre-merge when the judge starts: measured at 7 s ahead of the merge. The
    archived patch is the change under review whatever the merge has done, and this is
    the layout templates/judge-prompt.md already documents.
    """
    judged = judged_step(plan, step)
    wt = plan.run_dir / "judge" / judged.slug / "W"
    if wt.exists():
        subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=root, capture_output=True, check=False)
    wt.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "worktree", "add", "--detach", str(wt), judged.base], cwd=root, check=True, capture_output=True)
    patch = plan.run_dir / "reports" / judged.slug / "diff.patch"
    if patch.exists() and patch.read_text().strip():
        subprocess.run(["git", "apply", "--index", str(patch)], cwd=wt, check=True, capture_output=True)
    return wt


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
