"""Blocking-mode judge gate for steps whose sidecar says `judge: required`.

The normal path is a judge *step* in the plan (see templates/build.yaml) that runs
after merge while dependents proceed; this gate is the pre-merge form for seam
steps that must not merge unjudged. It stages a detached worktree at the step's
base with the diff applied, spawns the judge through the herdr adapter, waits for
blind-review.md, and blocks on a "do not merge" verdict or any defect labelled
certain. Judge family rule: never weaker than the executor.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from bernstein.core.quality.gate_plugins import GatePlugin
from bernstein.core.quality.gate_runner import GateResult

from bernstein_herdr import ledger
from bernstein_herdr.judge import parse_verdict, stage_judge
from bernstein_herdr.plan import load_plan, repo_root


class BlindJudgeGate(GatePlugin):
    @property
    def name(self) -> str:
        return "blind_judge"

    @property
    def required(self) -> bool:
        return True

    @property
    def condition(self) -> str:
        return "any_changed"

    def run(self, changed_files: list[str], run_dir: Path, task_title: str, task_description: str) -> GateResult:
        plan = load_plan(root=repo_root(run_dir))
        step = plan.step(task_title)
        if step.judge != "required":
            return GateResult(name=self.name, status="pass", required=False, blocked=False, cached=False, duration_ms=0, details='{"skipped":"judge not required for this step"}')
        judge_dir = stage_judge(plan, step, run_dir)
        from bernstein_herdr.adapter import HerdrClaudeAdapter

        class _Model:
            model = os.environ.get("BUILD_JUDGE_MODEL", "claude-opus-5")

        prompt = (judge_dir / "judge-prompt.md").read_text()
        res = HerdrClaudeAdapter().spawn(prompt=f"### Task 1: {step.title} (id=judge)\n\n{prompt}", workdir=judge_dir / "W", model_config=_Model(), session_id=f"judge-{step.slug}")
        res.proc.wait()
        verdict = parse_verdict(judge_dir / "W" / ".agents" / "blind-review.md")
        blocked = verdict["block"]
        ledger.row(plan.run_dir, {"run_id": f"{plan.slug}-{step.slug}-judge-gate", "step": step.slug, "gate": "blind_judge", "evidence": "verified", **verdict})
        return GateResult(name=self.name, status="fail" if blocked else "pass", required=True, blocked=blocked, cached=False, duration_ms=0, details=json.dumps(verdict))
