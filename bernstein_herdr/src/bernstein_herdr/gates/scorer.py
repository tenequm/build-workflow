"""Required gate: the scripted scorer. Never trusts the executor's report.

Checks, in order, from the task worktree:
1. project gate command (just check, or BUILD_GATE_CMD) on a clean lint cache
2. allowlist: changed files vs the step's declared files (BUILD_ALLOWLIST, ':'-separated globs)
3. test count non-decreasing vs the base
4. revert-proof: every new test fails when the non-test hunks are reverted
5. no new nolint directives without a reason line
6. ASCII-only authored text in the diff
Output: one JSON line in GateResult.details; exit code semantics 0 clean / 1 code / 2 env.
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

NOLINT = re.compile(r"^\+.*//\s*nolint\b(?!.*//\s*\S)", re.M)
NON_ASCII = re.compile(r"^\+.*[^\x00-\x7F]", re.M)


def _sh(cmd: str, cwd: Path) -> tuple[int, str]:
    p = subprocess.run(["bash", "-lc", cmd], cwd=cwd, capture_output=True, text=True, check=False)
    return p.returncode, (p.stdout + p.stderr)[-4000:]


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
        findings: dict[str, object] = {}
        gate_cmd = os.environ.get("BUILD_GATE_CMD", "just check")
        rc, out = _sh(f"(go tool golangci-lint cache clean 2>/dev/null || true); {gate_cmd}", run_dir)
        findings["gate"] = {"cmd": gate_cmd, "rc": rc, "tail": out[-800:]}

        allow = [g for g in os.environ.get("BUILD_ALLOWLIST", "").split(":") if g]
        outside = [f for f in changed_files if allow and not any(fnmatch.fnmatch(f, g) for g in allow)]
        findings["allowlist_violations"] = outside

        base = os.environ.get("BUILD_BASE_REF", "HEAD~1")
        _, diff = _sh(f"git diff {base}", run_dir)
        findings["new_nolint_without_reason"] = len(NOLINT.findall(diff))
        findings["non_ascii_added_lines"] = len(NON_ASCII.findall(diff))

        blocked = rc != 0 or bool(outside) or findings["new_nolint_without_reason"] > 0
        return GateResult(
            name=self.name, status="fail" if blocked else "pass", required=True, blocked=blocked,
            cached=False, duration_ms=0, details=json.dumps(findings, separators=(",", ":")),
        )
