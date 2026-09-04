"""Required gate: the scripted scorer. Never trusts the executor's report.

From the task worktree, resolved through the plan sidecar by task title:
1. the project gate command (sidecar per-step `gate_cmd`, else `defaults.gate_cmd`,
   else `just check`) with a per-run lint cache
2. allowlist: changed files vs the step's `files` globs
3. new `nolint` directives without a reason line; non-ASCII in added authored lines
4. the step committed something at all, and no test file was deleted without replacement
   (count of test files non-decreasing)
5. report accuracy: the report's claimed exit codes and issue counts vs the measured gate;
   a claim of clean with a red gate, or a missing lint mention, is `report_mismatch`
Details are one JSON line; the same line is appended to <run>/runs.jsonl as a gate row.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
from pathlib import Path

from bernstein.core.quality.gate_plugins import GatePlugin
from bernstein.core.quality.gate_runner import GateResult

from bernstein_herdr import ledger
from bernstein_herdr.plan import frozen_plan, load_plan, repo_root

LINT_RUN = re.compile(r"golangci|\bruff\b|eslint|clippy|\blint(ing|er)?\b", re.I)
NOLINT = re.compile(r"^\+.*//\s*nolint\b(?!.*\s//\s*\S)", re.M)
NON_ASCII = re.compile(r"^\+(?!\+\+).*[^\x00-\x7F]", re.M)
TEST_FILE = re.compile(r"_test\.go$|\.test\.ts$|\.spec\.ts$")
# Written into the tree by the orchestrator or by this adapter, never by the executor:
# Bernstein's per-task CLAUDE.md and .sdd state, and our own brief/report under .agents.
ORCHESTRATOR_PATHS = (".agents/", ".sdd/", ".claude/")


def _authored(path: str) -> bool:
    return not path.startswith(ORCHESTRATOR_PATHS) and path not in ledger.ORCHESTRATOR_FILES


def _sh(cmd: str, cwd: Path, env: dict[str, str] | None = None) -> tuple[int, str]:
    # `bash -c`, not `-lc`: the login profile can reorder PATH under the gate and buys
    # nothing the adapters' environment does not already carry.
    p = subprocess.run(["bash", "-c", cmd], cwd=cwd, capture_output=True, text=True, check=False,
                       env={**os.environ, **env} if env else None)
    return p.returncode, (p.stdout + p.stderr)[-6000:]


def lint_env(worktree: Path, run_dir: Path) -> dict[str, str]:
    """A lint cache private to this run, shared by its worktrees.

    golangci-lint's shared default cache is what let a report claim a clean run over
    files that had issues, so the gate never uses it. A cache per WORKTREE was the first
    fix, but it is cold for every step's first gate: measured 2026-09-03, 11.2s cold
    against 1.4s warm, about five minutes over a thirty-worktree run. The cache is
    content-addressed with atomic renames, so one cache per run is safe under concurrent
    gates and warm after the first; it keeps other repos and other runs out, which was
    the point.
    """
    cache = run_dir / "lintcache"
    cache.mkdir(parents=True, exist_ok=True)
    return {"GOLANGCI_LINT_CACHE": str(cache)}


def score(worktree: Path, task_title: str, changed_files: list[str] | None = None) -> tuple[bool, dict]:
    plan = load_plan(root=repo_root(worktree))
    # Once run-config froze refs/build/base/<slug>, gate_cmd, allowlist and base come
    # from the FROZEN plan files, not the working copies an executor (or an earlier
    # step's merge) can rewrite. Pre-run and in tests the ref is absent and the
    # working copies stand.
    frozen = frozen_plan(plan, worktree)
    if frozen is not None:
        plan = frozen
    step = plan.step(task_title)
    f: dict = {"step": step.slug, "gate_cmd": step.gate_cmd,
               "plan_source": "frozen_base" if frozen is not None else "worktree"}

    rc, out = _sh(step.gate_cmd, worktree, lint_env(worktree, step.run_dir))
    f["gate"] = {"rc": rc, "tail": out[-1200:]}
    lint_issues = re.findall(r"(\d+) issues?\.", out)
    f["lint_issues_measured"] = int(lint_issues[-1]) if lint_issues else None

    if changed_files is None:
        tracked = _sh(f"git diff --name-only {step.base} -- . ':!.agents'", worktree)[1].splitlines()
        untracked = _sh("git ls-files --others --exclude-standard -- . ':!.agents'", worktree)[1].splitlines()
        changed_files = sorted({l for l in tracked + untracked if l})
    f["allowlist_violations"] = [
        c for c in changed_files
        if step.files and _authored(c) and not any(fnmatch.fnmatch(c, g) for g in step.files)
    ]

    # The plan files are the gate's own configuration. `.agents` is excluded from every
    # diff above, so a step that rewrites `.agents/build/plans/` (allowlist, gate_cmd,
    # briefs) merges that edit invisibly and every LATER step is gated by it. Tracked
    # edits there vs the step base are an automatic block.
    f["plans_dir_edit"] = [l for l in _sh(f"git diff --name-only {step.base} -- .agents/build/plans", worktree)[1].splitlines() if l]

    _, diff = _sh(f"git diff {step.base} -- . ':!.agents'", worktree)
    f["new_nolint_without_reason"] = len(NOLINT.findall(diff))
    f["non_ascii_added_lines"] = len(NON_ASCII.findall(diff))
    deleted = [l for l in _sh(f"git diff --diff-filter=D --name-only {step.base}", worktree)[1].splitlines() if TEST_FILE.search(l)]
    f["deleted_test_files"] = deleted

    # An executor reaped before its first commit leaves a worktree at its base. Every other
    # signal here is clean for it -- the tree is the base, so the gate command is green, the
    # allowlist is empty and nothing was deleted -- and a run once merged two such steps as
    # successes (2026-09-03). Zero commits is the block. It is COMMITS, not changed files:
    # the fix-N no-op path legitimately commits only its report under `.agents/`, which is
    # excluded from every diff above, and must still pass.
    commits = _sh(f"git rev-list --count {step.base}..HEAD", worktree)[1].strip()
    f["commits"] = int(commits) if commits.isdigit() else -1

    f["lint_expected"] = (worktree / "go.mod").exists() or bool(LINT_RUN.search(out))
    claims = ledger.report_claims(worktree / step.report_rel)
    mismatch = []
    if claims.get("present"):
        if rc != 0 and claims.get("claimed_exit_codes") and all(c == 0 for c in claims["claimed_exit_codes"]):
            mismatch.append("report claims all commands exit 0; measured gate is red")
        if f["lint_issues_measured"] and claims.get("claimed_issue_counts") and all(c == 0 for c in claims["claimed_issue_counts"]):
            mismatch.append(f"report claims 0 issues; measured {f['lint_issues_measured']}")
        # Only a repo that actually lints can have a missing lint result. Asking every
        # report for one made "no lint result at all" fire on every non-Go project.
        if f["lint_expected"] and not claims.get("mentions_lint"):
            mismatch.append("report has no lint result at all")
    else:
        mismatch.append("no report file")
    f["report_mismatch"] = mismatch

    # A refusal receipt in the report parks the step as failed instead of merging it as a
    # silent success: a refused step used to pass (gate green on an untouched tree, report
    # committed) and the missing work surfaced only at branch validation (retro item 8).
    f["refusal"] = claims.get("refusal")
    # A report that contradicts the measured gate is a false receipt and blocks. The
    # SOLE entry "no report file" stays a non-blocking note: Codex skips the report on
    # about half of otherwise-good steps (measured 2026-09-02), and the gate measures
    # everything the report would have claimed anyway.
    lying_report = bool(mismatch) and mismatch != ["no report file"]
    blocked = (rc != 0 or bool(f["allowlist_violations"]) or f["new_nolint_without_reason"] > 0
               or bool(deleted) or f["commits"] == 0 or bool(f["refusal"]) or bool(f["plans_dir_edit"])
               or lying_report)
    f["blocked"] = blocked
    ledger.row(plan.run_dir, {"run_id": f"{plan.slug}-{step.slug}-scorer", "step": step.slug, "gate": "scorer", "evidence": "verified", **{k: v for k, v in f.items() if k != "gate"}, "gate_rc": rc})
    return blocked, f


class ScorerGate(GatePlugin):
    @property
    def name(self) -> str:
        return "scorer"

    @property
    def required(self) -> bool:
        return True

    @property
    def condition(self) -> str:
        return "any_changed"

    def run(self, changed_files: list[str], run_dir: Path, task_title: str, task_description: str) -> GateResult:
        blocked, f = score(run_dir, task_title, changed_files)
        return GateResult(name=self.name, status="fail" if blocked else "pass", required=True, blocked=blocked,
                          cached=False, duration_ms=0, details=json.dumps(f, separators=(",", ":")))
