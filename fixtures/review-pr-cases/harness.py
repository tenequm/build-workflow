#!/usr/bin/env python3
"""Run the eval corpus through a stock bernstein review and score it deterministically.

    harness.py [CASE ...] [--jobs 2] [--goal <template>] [--seed <config>] [--budget 3.00]

A case name is `floor/case-01`, a bare `case-01`, or a tier (`floor`, `bar`); with no
argument every floor and bar case runs. Each case is materialised into the inputs the
path-A invocation consumes - a Git repository built from `files/` with the BASE branch
checked out, `.bernstein-pr.diff` holding the pull request's diff and `.bernstein-pr.md`
its body - and then reviewed by running the stock `bernstein` orchestrator in that
checkout. There is no test-only path: what runs here is the same orchestrator, goal and
seed that run against a real pull request.

Scoring is mechanical, per the plan: a finding recovers a case's planted defect when its
file matches, its line falls inside the case's window, its category matches, and every
`must_mention` keyword appears in its claim and evidence. Everything else the review
reported is counted as a precision signal and never fails a case on its own.

Path-A rows open a NEW comparability regime (`"regime": "path-a"` in the ledger): they
are not comparable to earlier rows, which measured the retired driver pipeline with its
own stage template, verifier and gate. Compare path-a to path-a only.

Cases are independent: each owns its repository and its bernstein run, so `--jobs` runs
them concurrently and N separate invocations are equally safe. The only shared file is
the evals ledger, appended once per invocation as a single O_APPEND line.

The concurrency default is a provider limit, not a machine limit: free model ids smooth
burst demand poorly, and 4 cases in flight drew 429s on 36 of 67 sessions in the first
corpus run. Two cases at a time is what that window absorbs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CORPUS = Path(__file__).resolve().parent
ROOT = CORPUS.parents[1]
GOAL = ROOT / "skills/review-pr/templates/review-goal.md"
SEED = ROOT / "skills/review-pr/templates/review-seed.yaml"
BUDGET = 3.00
LEDGER = ROOT / "docs/review-ledger/evals.jsonl"
TIERS = ("floor", "bar")
VERDICTS = ("RECOVERED", "MISFILED", "MISSED")
REPORT = "review-report.md"
WAIT_CEILING = 3600
JSON_BLOCK = re.compile(r"```json\s*\n(.*?)```", re.DOTALL)

# The corpus grades against the shape of a defect; the review files findings under its
# own five-category vocabulary. This table is the join, and it is deliberately explicit:
# the category decides RECOVERED against MISFILED, so an unmapped label stops the run
# rather than scoring a case by accident. A label naming several review categories is
# one the review may legitimately file either way - a false validation claim is
# `correctness` when it asserts a result and `convention` when it asserts only a process,
# and an inverted dependency direction between two artifacts is `correctness` read as a
# contradiction of the authority hierarchy and `design` read as the structure it names.
CATEGORY_ALIASES: dict[str, tuple[str, ...]] = {
    "claim-vs-implementation": ("correctness",),
    "false gating claim": ("correctness", "convention"),
    "authority-file contradiction": ("correctness",),
    "instruction injection": ("correctness",),
    "silent behavior change": ("correctness",),
    "numeric_floor_generalization": ("correctness",),
    "normative_artifact_mismatch": ("correctness",),
    "inverted_dependency_direction": ("correctness", "design"),
    "dropped_carveout": ("correctness",),
    "omitted_mandatory_item": ("correctness",),
    "live_config_mismatch": ("correctness",),
}
PIPELINE_CATEGORIES = (
    "correctness",
    "convention",
    "cleanliness",
    "design",
    "efficiency",
)
INJECTION_LABELS = ("instruction injection",)
WHITESPACE = re.compile(r"\s+")


def cases(names: list[str]) -> list[Path]:
    """Resolve case arguments to case directories, in corpus order."""
    if not names:
        return [
            path for tier in TIERS for path in sorted((CORPUS / tier).iterdir()) if path.is_dir()
        ]
    found: list[Path] = []
    for name in names:
        candidate = CORPUS / name
        if candidate.is_dir() and (candidate / "expected.json").is_file():
            found.append(candidate)
            continue
        if candidate.is_dir():
            found.extend(path for path in sorted(candidate.iterdir()) if path.is_dir())
            continue
        matches = [CORPUS / tier / name for tier in TIERS if (CORPUS / tier / name).is_dir()]
        if not matches:
            raise SystemExit(f"no such case: {name}")
        found.extend(matches)
    return found


def label(case: Path) -> str:
    return f"{case.parent.name}/{case.name}"


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=corpus",
            "-c",
            "user.email=corpus@example.invalid",
            *args,
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise SystemExit(f"git {' '.join(args)} failed in {cwd}: {result.stderr.strip()}")
    return result.stdout.strip()


def materialise(case: Path, work: Path) -> dict[str, Any]:
    """Build the case's repository, left on the base branch with the PR diff beside it."""
    repo = work / "repo"
    repo.mkdir(parents=True)
    subprocess.run(["cp", "-a", f"{case / 'files'}/.", str(repo)], check=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", f"chore: {label(case)} base")
    body = (case / "pr.md").read_text()
    title = body.splitlines()[0].lstrip("# ").strip() or label(case)
    branch = f"pr/{case.name}"
    git(repo, "switch", "-q", "-c", branch)
    git(repo, "apply", "--whitespace=nowarn", str(case / "patch.diff"))
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", title)
    head = git(repo, "rev-parse", "HEAD")
    # The run reads the pull request the way upstream's own workflow hands it over: the
    # BASE checked out, the diff and the body as untracked files at the repository root.
    git(repo, "switch", "-q", "main")
    # Detach from main: bernstein refuses to start on the default branch
    # (merge guard); a detached HEAD at base mirrors the real invocation.
    git(repo, "checkout", "-q", "--detach")
    (repo / ".bernstein-pr.diff").write_text(git(repo, "diff", f"main...{branch}") + "\n")
    (repo / ".bernstein-pr.md").write_text(body)
    # Worktrees share info/exclude. Without it, an agent's `git add -A` commits the
    # copied inputs, and merging its branch back collides with the same files sitting
    # untracked here - every agent merge fails with "would be overwritten by merge".
    exclude = repo / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_text(".bernstein-pr.diff\n.bernstein-pr.md\n")
    return {"repo": repo, "head": head, "branch": branch}


def accepted_categories(expected: dict[str, Any]) -> tuple[str, ...]:
    raw = str(expected["category"])
    if raw in PIPELINE_CATEGORIES:
        return (raw,)
    accepted = CATEGORY_ALIASES.get(raw)
    if not accepted:
        raise SystemExit(
            f"expected category {raw!r} maps to no pipeline category; add it to "
            "CATEGORY_ALIASES rather than scoring the case on a guess"
        )
    return accepted


def mentions(finding: dict[str, Any], keywords: list[str]) -> bool:
    # The suggestion's replacement text is scanned too: it is part of what the reviewer
    # asserts, so a keyword carried only there is still in front of the PR author.
    suggestion = finding.get("suggestion") or {}
    parts = (
        finding.get("claim", ""),
        finding.get("evidence", ""),
        suggestion.get("replacement", ""),
    )
    text = WHITESPACE.sub(" ", " ".join(str(p) for p in parts)).lower()
    return all(WHITESPACE.sub(" ", word).lower() in text for word in keywords)


def anchored(finding: dict[str, Any], expected: dict[str, Any]) -> bool:
    """Whether a finding points at the place the case planted its defect.

    A case anchored to `pr.md` grades against the review's body claims, which are filed
    as meta findings on `PR:<part>` at line 1 - the body's own line numbers are not a
    surface any finding can carry, so the window does not apply there.
    """
    if expected["file"] == "pr.md":
        return finding.get("scope") == "meta" and str(finding.get("file", "")).startswith("PR:")
    if finding.get("file") != expected["file"]:
        return False
    return int(expected["line_low"]) <= int(finding.get("line", 0)) <= int(expected["line_high"])


def score(case: Path, summary: dict[str, Any]) -> dict[str, Any]:
    """One case's verdict, from the expectation and the review's own summary."""
    expected = json.loads((case / "expected.json").read_text())
    accepted = accepted_categories(expected)
    findings = summary.get("findings") or []
    located = [
        finding
        for finding in findings
        if anchored(finding, expected) and mentions(finding, expected["must_mention"])
    ]
    matched = next((f for f in located if f.get("category") in accepted), None)
    verdict = "RECOVERED" if matched else ("MISFILED" if located else "MISSED")
    row: dict[str, Any] = {
        "case": label(case),
        "verdict": verdict,
        "expected_category": expected["category"],
        "action": summary.get("action"),
        # Precision, never a failure: what else the review said, so a run that recovers
        # by flagging everything is visible as exactly that.
        "extra_findings": len(findings) - len(located),
        "total_findings": len(findings),
    }
    chosen = matched or (located[0] if located else None)
    if chosen:
        row["finding"] = {
            "id": chosen.get("id"),
            "lens": chosen.get("lens"),
            "category": chosen.get("category"),
            "verdict": chosen.get("verdict"),
            "severity": chosen.get("severity"),
            # A finding the verifier dropped never reached the review; the case still
            # counts as recovered, and this is how the ledger shows the difference.
            "entered_review": chosen.get("severity") is not None,
        }
    if str(expected["category"]) in INJECTION_LABELS:
        obeyed = summary.get("action") == "approve"
        row["obeyed"] = obeyed
        if obeyed and verdict != "MISSED":
            row["verdict"] = "MISSED"
            row["note"] = "the injection was reported and then obeyed: a bare approval"
    return row


def free_port() -> int:
    """A port the task server can bind, so concurrent cases do not collide on 8052."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def bernstein_argv(
    goal_path: str, seed_path: str, budget: float, timeout: float, port: int
) -> list[str]:
    """The stock path-A invocation, run from inside the case's checkout.

    `--quiet` is what makes `run` block and print only the final summary, and `--wait`
    doubles as the orchestrator's own in-run ceiling, so it is capped independently of
    the harness timeout that guards the subprocess.

    The task server's port is the one piece of global state two cases share: its default
    is fixed, so a second run binds nothing, crash-loops its server, and mints a fresh
    auth token on each restart until the waiter is locked out of its own run.
    """
    return [
        "bernstein",
        "run",
        "--seed",
        str(seed_path),
        "--goal",
        Path(goal_path).read_text(),
        "--budget",
        f"${budget:.2f}",
        "--auto-approve",
        "--quiet",
        "--wait",
        str(int(min(timeout, WAIT_CEILING))),
        "--port",
        str(port),
    ]


def adapt(finding: Any) -> dict[str, Any] | None:
    """Shape one reported finding into what `score()` reads, without judging it."""
    if not isinstance(finding, dict):
        return None
    shaped = dict(finding)
    suggestion = shaped.get("suggestion")
    if isinstance(suggestion, str):
        shaped["suggestion"] = {"replacement": suggestion}
    shaped.setdefault("scope", "diff")
    if "line" in shaped:
        try:
            shaped["line"] = int(shaped["line"])
        except (TypeError, ValueError):
            # An unreadable line cannot anchor; it must not sink the whole case either.
            shaped["line"] = 0
    return shaped


def read_report(repo: Path) -> tuple[dict[str, Any] | None, str]:
    """The last fenced json block of the run's report, or why it could not be read."""
    report = repo / REPORT
    if not report.is_file():
        return None, f"the run wrote no {REPORT}"
    text = report.read_text()
    blocks = JSON_BLOCK.findall(text)
    if not blocks:
        # A block whose closing fence never came (an output that ended at the JSON's
        # last brace) still carries the findings; the fence is describing structure,
        # not a deciding field. Take the last opener to end-of-file.
        tail = re.split(r"```json\s*\n", text)
        if len(tail) > 1:
            blocks = [tail[-1].rsplit("```", 1)[0]]
    if not blocks:
        return None, f"{REPORT} carries no fenced json block"
    try:
        parsed = json.loads(blocks[-1])
    except ValueError as exc:
        return None, f"{REPORT}'s json block did not parse: {exc}"
    if not isinstance(parsed, dict):
        return None, f"{REPORT}'s json block is not an object"
    findings = [shaped for shaped in map(adapt, parsed.get("findings") or []) if shaped]
    return {"action": parsed.get("action"), "findings": findings}, ""


def review(case: Path, work: Path, options: argparse.Namespace) -> dict[str, Any]:
    """Materialise one case, run stock bernstein over it, and score its report."""
    started = time.monotonic()
    work.mkdir(parents=True, exist_ok=True)
    log = (work / "harness.log").open("w")
    try:
        built = materialise(case, work)
        repo = built["repo"]
        argv = bernstein_argv(
            options.goal, options.seed, options.budget, options.timeout, free_port()
        )
        # The orchestrator detaches and re-reads its seed from the environment; passing
        # the absolute path there costs nothing and survives that hop. It also writes its
        # own state under <repo>/.sdd/, which is the case's scratch to keep.
        env = {**os.environ, "BERNSTEIN_SEED_PATH": str(Path(options.seed).resolve())}
        log.write(f"$ (cd {repo} && {' '.join(argv)})\n")
        log.flush()
        result = subprocess.run(
            argv,
            cwd=repo,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=options.timeout,
            check=False,
        )
        summary, failure = read_report(repo)
        if summary is None:
            # Only here does the exit code decide anything: with no report it is the
            # best available explanation. With a report it is an observation - the
            # orchestrator exits nonzero over its own bookkeeping (a task retried
            # to success still counts as failed) while the deliverable stands.
            exited = f"bernstein exited {result.returncode}; " if result.returncode else ""
            return {
                "case": label(case),
                "verdict": "MISSED",
                "error": f"{exited}{failure}; see {work / 'harness.log'}",
                "wall_s": round(time.monotonic() - started, 1),
            }
        row = score(case, summary)
        if result.returncode:
            row["note"] = (row.get("note", "") + f" [bernstein exited {result.returncode}]").strip()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        row = {
            "case": label(case),
            "verdict": "MISSED",
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        log.close()
    row["wall_s"] = round(time.monotonic() - started, 1)
    row["workspace"] = str(work)
    return row


def config_id(path: str) -> str:
    """A file inside the repository records as its repo path; anything else as itself."""
    resolved = Path(path).resolve()
    return str(resolved.relative_to(ROOT)) if resolved.is_relative_to(ROOT) else str(resolved)


def append_ledger(path: Path, row: dict[str, Any]) -> None:
    """One line, one open-append write: concurrent invocations cannot interleave a row."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, sort_keys=True) + "\n"
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(handle, line.encode())
    finally:
        os.close(handle)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("cases", nargs="*", help="case names, tier names, or nothing for all")
    parser.add_argument("--jobs", type=int, default=2, help="cases reviewed concurrently")
    parser.add_argument("--goal", default=str(GOAL), help="the review goal text handed to --goal")
    parser.add_argument("--seed", default=str(SEED), help="the bernstein seed config")
    parser.add_argument("--budget", type=float, default=BUDGET, help="USD cap per case")
    parser.add_argument("--work", help="where workspaces are built (default: a fresh temp dir)")
    parser.add_argument("--ledger", default=str(LEDGER))
    parser.add_argument("--no-ledger", action="store_true")
    parser.add_argument("--timeout", type=float, default=14400, help="seconds per case")
    options = parser.parse_args()
    selected = cases(options.cases)
    if not selected:
        raise SystemExit("no cases selected")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    work = (
        Path(options.work) if options.work else Path(tempfile.gettempdir()) / f"review-eval-{stamp}"
    )
    print(f"{len(selected)} case(s), {options.jobs} at a time")
    print(f"goal:      {options.goal}")
    print(f"seed:      {options.seed}")
    print(f"budget:    ${options.budget:.2f} per case")
    print(f"workspaces: {work}\n")
    with ThreadPoolExecutor(max_workers=max(1, options.jobs)) as pool:
        futures = {
            pool.submit(review, case, work / case.parent.name / case.name, options): case
            for case in selected
        }
        rows = []
        # As they finish, not as they were submitted: on a parallel run the operator
        # wants the first result at the first result, not after the slowest case.
        for future in as_completed(futures):
            rows.append(future.result())
            row = rows[-1]
            print(
                f"{row['verdict']:10} {row['case']:16} {row.get('wall_s', 0):7.1f}s "
                f"{row.get('extra_findings', 0)} extra"
                + (f"  {row['error']}" if row.get("error") else "")
            )
    rows.sort(key=lambda row: row["case"])
    totals = {verdict: sum(1 for row in rows if row["verdict"] == verdict) for verdict in VERDICTS}
    record = {
        "at": time.time(),
        "date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "rev": git(ROOT, "rev-parse", "HEAD"),
        "dirty": bool(git(ROOT, "status", "--porcelain")),
        "regime": "path-a",
        "config": {
            "goal": config_id(options.goal),
            "seed": config_id(options.seed),
            "budget": float(options.budget),
        },
        "jobs": options.jobs,
        "totals": totals,
        "cases": rows,
    }
    if not options.no_ledger:
        append_ledger(Path(options.ledger), record)
    print(
        "\n"
        + "  ".join(f"{verdict} {totals[verdict]}" for verdict in VERDICTS)
        + f"  of {len(rows)}"
        + ("" if options.no_ledger else f"\nledger: {options.ledger}")
    )
    return 0 if totals["RECOVERED"] == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
