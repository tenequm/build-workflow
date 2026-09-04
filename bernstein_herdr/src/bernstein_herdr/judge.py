"""Judge verdict parsing and archiving, shared by the `gate` judge path and the CLI."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from bernstein_herdr import ledger
from bernstein_herdr.plan import Plan, Step

#: The judge brief asks for these two lines verbatim, exactly once, in the file's last
#: three lines; counting the WORDS was unreliable in both directions and is gone.
DECLARED = {label: re.compile(rf"^\s*{label}\s*[:=]\s*(\d+)\b", re.I | re.M) for label in ("certain", "plausible")}

VERDICTS = ("do not merge", "merge after listed fixes", "merge as-is")

#: A file:line-shaped reference; a prose review that counts certain defects must carry
#: at least `certain` of these, or the counts are assertions with nothing behind them.
FILE_LINE = re.compile(r"\S+\.(go|py|ts|md|sql|yaml|yml):\d+")

#: The only files a judge step may change: its review, its scorecard, and the
#: structured verdict beside them.
JUDGE_ALLOWED = (".agents/blind-review.md", ".agents/scorecard.md", ".agents/verdict.json")


def judge_worktree_violations(worktree: Path, base: str) -> list[str]:
    """Tracked files the judge worktree changed vs `base`, beyond its review artifacts.

    The judge brief used to say "nothing mechanical stops you" editing code; this is
    the mechanical stop. An explicit diff, without the scorer's `:!.agents` exclusion,
    because the review files themselves live under `.agents/` and everything else
    there is exactly what a judge must not touch. Orchestrator writes (the per-task
    CLAUDE.md, `.sdd/`, `.claude/` runtime) stay out, as they do in the scorer.
    """
    from bernstein_herdr import ledger

    r = subprocess.run(["git", "diff", "--name-only", base], cwd=worktree,
                       capture_output=True, text=True, check=False)
    return sorted({
        l for l in r.stdout.splitlines()
        if l and l not in JUDGE_ALLOWED and l not in ledger.ORCHESTRATOR_FILES
        and not l.startswith((".sdd/", ".claude/"))
    })


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
        malformed = {"review_present": True, "verdict": verdict or "unclear",
                     "certain": int(certain_all[0]) if len(certain_all) == 1 else 0,
                     "plausible": int(plausible_all[0]) if len(plausible_all) == 1 else 0,
                     "counts_declared": False, "do_not_merge": False, "merge_as_is": False,
                     "block": True, "reason": "malformed review: " + "; ".join(problems)}
        vj = review.with_name("verdict.json")
        return _json_verdict(vj, malformed) if vj.exists() else malformed
    certain, plausible = int(certain_all[0]), int(plausible_all[0])
    prose = {"review_present": True, "verdict": verdict,
             "certain": certain, "plausible": plausible, "counts_declared": True,
             "do_not_merge": verdict == "do not merge", "merge_as_is": verdict == "merge as-is",
             "block": verdict == "do not merge"}
    vj = review.with_name("verdict.json")
    if vj.exists():
        return _json_verdict(vj, prose)
    # Prose-only back-compat path. A review that counts certain defects without a
    # single file:line reference per defect is a count with nothing behind it.
    if not prose["block"] and certain > 0 and len(FILE_LINE.findall(raw)) < certain:
        return {**prose, "block": True,
                "reason": f"counted defects without evidence: certain={certain} but fewer "
                          f"file:line references in the review"}
    return prose


def _schema_problems(data: object) -> list[str]:
    if not isinstance(data, dict):
        return ["top level is not an object"]
    problems = []
    if data.get("verdict") not in VERDICTS:
        problems.append(f"verdict {data.get('verdict')!r} is not one of the three legal strings")
    for key in ("certain", "plausible"):
        v = data.get(key)
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            problems.append(f"{key} is not a non-negative integer")
    ev = data.get("evidence")
    if not isinstance(ev, list):
        problems.append("evidence is not a list")
    else:
        for i, e in enumerate(ev):
            if (not isinstance(e, dict) or not isinstance(e.get("file"), str)
                    or not isinstance(e.get("line"), int) or isinstance(e.get("line"), bool)
                    or not isinstance(e.get("note"), str)):
                problems.append(f"evidence[{i}] is not {{file: str, line: int, note: str}}")
        if isinstance(data.get("certain"), int) and not isinstance(data.get("certain"), bool) \
                and len(ev) != data["certain"]:
            problems.append(f"{len(ev)} evidence entries for certain={data['certain']} (need exactly certain)")
    return problems


def _json_verdict(vj: Path, prose: dict) -> dict:
    """Reconcile the committed `.agents/verdict.json` with the prose tail block.

    Valid and consistent: the structured verdict stands, evidence attached (the
    schema itself guarantees one evidence entry per certain defect). Anything
    else -- unparseable, schema-invalid, or disagreeing with the prose block --
    blocks with the mismatch named, so a fresh judge attempt fixes it.
    """
    try:
        data = json.loads(vj.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return {**prose, "block": True, "verdict_json": False,
                "reason": f"invalid verdict.json: {exc}"}
    problems = _schema_problems(data)
    if problems:
        return {**prose, "block": True, "verdict_json": False,
                "reason": "invalid verdict.json: " + "; ".join(problems)}
    if not prose.get("counts_declared"):
        return {**prose, "block": True, "verdict_json": False,
                "reason": "verdict.json is valid but the prose verdict block is malformed: "
                          + str(prose.get("reason", ""))}
    mismatches = [f"{key}: json {data[key]!r} vs prose {prose[key]!r}"
                  for key in ("verdict", "certain", "plausible") if data[key] != prose[key]]
    if mismatches:
        return {**prose, "block": True, "verdict_json": False,
                "reason": "verdict.json disagrees with the prose block: " + "; ".join(mismatches)}
    return {**prose, "verdict_json": True, "evidence": data["evidence"]}
