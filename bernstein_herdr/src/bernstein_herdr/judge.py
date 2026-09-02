"""Judge staging and verdict parsing, shared by the judge step, the judge gate and the CLI."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

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


def parse_verdict(review: Path) -> dict:
    if not review.exists():
        return {"review_present": False, "block": True, "reason": "no blind-review.md"}
    text = review.read_text()
    verdict = text.split("Verdict", 1)[-1] if "Verdict" in text else text
    certain = len(CERTAIN.findall(text))
    do_not_merge = "do not merge" in verdict.lower()
    return {"review_present": True, "certain_mentions": certain, "do_not_merge": do_not_merge, "block": do_not_merge or certain > 0,
            "merge_as_is": "merge as-is" in verdict.lower()}
