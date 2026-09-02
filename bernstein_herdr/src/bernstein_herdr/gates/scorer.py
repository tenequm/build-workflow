"""Required gate: the scripted scorer. Never trusts the executor's report.

From the task worktree, resolved through the plan sidecar by task title:
1. the project gate command (sidecar `gate_cmd`, default `just check`) on a clean lint cache
2. allowlist: changed files vs the step's `files` globs
3. new `nolint` directives without a reason line; non-ASCII in added authored lines
4. test files: none deleted without replacement (count of test files non-decreasing)
5. report accuracy: the report's claimed exit codes and issue counts vs the measured gate;
   a claim of clean with a red gate, or a missing lint mention, is `report_mismatch`
Details are one JSON line; the same line is appended to <run>/runs.jsonl as a gate row.
"""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
from pathlib import Path

from bernstein.core.quality.gate_plugins import GatePlugin
from bernstein.core.quality.gate_runner import GateResult

from bernstein_herdr import ledger
from bernstein_herdr.plan import load_plan, repo_root

LINT_RUN = re.compile(r"golangci|\bruff\b|eslint|clippy|\blint(ing|er)?\b", re.I)
NOLINT = re.compile(r"^\+.*//\s*nolint\b(?!.*\s//\s*\S)", re.M)
NON_ASCII = re.compile(r"^\+(?!\+\+).*[^\x00-\x7F]", re.M)
TEST_FILE = re.compile(r"_test\.go$|\.test\.ts$|\.spec\.ts$")
# Written into the tree by the orchestrator or by this adapter, never by the executor:
# Bernstein's per-task CLAUDE.md and .sdd state, and our own brief/report under .agents.
ORCHESTRATOR_PATHS = (".agents/", ".sdd/", ".claude/")
ORCHESTRATOR_FILES = ("CLAUDE.md",)


def _authored(path: str) -> bool:
    return not path.startswith(ORCHESTRATOR_PATHS) and path not in ORCHESTRATOR_FILES


def _sh(cmd: str, cwd: Path) -> tuple[int, str]:
    p = subprocess.run(["bash", "-lc", cmd], cwd=cwd, capture_output=True, text=True, check=False)
    return p.returncode, (p.stdout + p.stderr)[-6000:]


def score(worktree: Path, task_title: str, changed_files: list[str] | None = None) -> tuple[bool, dict]:
    plan = load_plan(root=repo_root(worktree))
    step = plan.step(task_title)
    gate_cmd = plan.sidecar.get("defaults", {}).get("gate_cmd", "just check")
    f: dict = {"step": step.slug, "gate_cmd": gate_cmd}

    lint_clean = "if [ -f go.mod ] && command -v golangci-lint >/dev/null 2>&1; then golangci-lint cache clean >/dev/null 2>&1 || true; fi"
    rc, out = _sh(f"{lint_clean}; {gate_cmd}", worktree)
    f["gate"] = {"rc": rc, "tail": out[-1200:]}
    lint_issues = re.findall(r"(\d+) issues?\.", out)
    f["lint_issues_measured"] = int(lint_issues[-1]) if lint_issues else None

    if changed_files is None:
        tracked = _sh(f"git diff --name-only {step.base} -- . ':!.agents'", worktree)[1].splitlines()
        untracked = _sh("git ls-files --others --exclude-standard -- . ':!.agents'", worktree)[1].splitlines()
        changed_files = sorted({l for l in tracked + untracked if l})
    f["allowlist_violations"] = [
        c for c in changed_files if step.files and _authored(c) and not any(fnmatch.fnmatch(c, g) for g in step.files)
    ]

    _, diff = _sh(f"git diff {step.base} -- . ':!.agents'", worktree)
    f["new_nolint_without_reason"] = len(NOLINT.findall(diff))
    f["non_ascii_added_lines"] = len(NON_ASCII.findall(diff))
    deleted = [l for l in _sh(f"git diff --diff-filter=D --name-only {step.base}", worktree)[1].splitlines() if TEST_FILE.search(l)]
    f["deleted_test_files"] = deleted

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

    blocked = rc != 0 or bool(f["allowlist_violations"]) or f["new_nolint_without_reason"] > 0 or bool(deleted)
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
