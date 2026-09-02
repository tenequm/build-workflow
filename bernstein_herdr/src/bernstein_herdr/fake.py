"""`fake`: a plumbing executor with no model, registered as a native Bernstein adapter.

It exists to exercise the wiring -- spawn, worktree, commit, gate, merge, ledger row --
in seconds and for nothing, where a real executor costs minutes and tokens. It reads the
brief path out of the step's `description:` (the only channel that reaches a spawn), takes
the allowlist and the report path from the plan sidecar, writes a one-line placeholder into
each allowlisted file, writes the report, and commits. It never reads the brief's Items:
a fake executor that tried to do the work would be a bad model, not a plumbing test.

A sidecar `fake_write: {<path>: <literal content>}` on the step replaces the placeholder for
those paths. That is how the judge path is exercised without a model: a plumbing test of the
JUDGE needs a diff with a real, reviewable defect in it, and the fake cannot invent one.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from bernstein.adapters._contract import AdapterStrategy
from bernstein.adapters.base import DEFAULT_TIMEOUT_SECONDS, CLIAdapter, SpawnResult
from bernstein.adapters.env_isolation import build_filtered_env

#: Bernstein calls any clean exit under `_FAST_EXIT_THRESHOLD_S` = 60 s suspicious
#: (`core/agents/agent_lifecycle.py:1510,1561`); when the reap lands on the orphaned-task
#: path it reads a 0-token exit as a TRANSPORT FAILURE, refuses to auto-complete the task
#: and retries it to the cap -- measured 2026-09-02, four dead retries and a judge stuck on
#: `blocked_by_failed_dep`, on a step that had already committed and merged. Outliving the
#: threshold makes the same path auto-complete instead. It is a minute per fake step and it
#: is what makes a plumbing run deterministic.
LIVE_S = 70

SCRIPT = r'''
import subprocess, sys, time
from pathlib import Path
from bernstein_herdr.plan import load_plan, repo_root
wt, prompt = Path(sys.argv[1]), sys.argv[2]
plan = load_plan(root=repo_root(wt))
step = plan.step_from_prompt(prompt)
scripted = plan.sidecar.get("steps", {}).get(step.title, {}).get("fake_write") or {}
for g in step.files:
    p = wt / g
    p.parent.mkdir(parents=True, exist_ok=True)
    if g in scripted:
        p.write_text(scripted[g])
    else:
        p.write_text((p.read_text() if p.exists() else "") + f"# fake executor placeholder for {step.slug}\n")
r = wt / step.report_rel
r.parent.mkdir(parents=True, exist_ok=True)
r.write_text(f"# Report: {step.title}\n\n## Items\n\n1. SKIPPED - fake plumbing executor, no model ran.\n\n"
             f"## Validation\n\nNot run by the executor; the gate measures it.\n\n## Deviations\n\n"
             f"Every item skipped: this run exercises the plumbing, not the work.\n\n## Open\n\nnone\n")
subprocess.run(["git", "add", "-A"], cwd=wt, check=True)
subprocess.run(["git", "commit", "-m", f"chore: fake executor placeholder for {step.slug}"], cwd=wt, check=True)
time.sleep(float(sys.argv[3]))
'''


class FakeAdapter(CLIAdapter):
    """No API key, no network, no model. `default_model` only has to satisfy the model gate."""

    default_model = "fake"
    strategy_override = AdapterStrategy()

    def name(self) -> str:
        return "fake"

    def spawn(self, *, prompt: str, workdir: Path, model_config: Any, session_id: str,
              mcp_config: dict[str, Any] | None = None, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
              task_scope: str = "medium", budget_multiplier: float = 1.0, system_addendum: str = "",
              multimodal_context: Any | None = None, **_: Any) -> SpawnResult:
        self.refuse_multimodal_if_needed(multimodal_context)
        log = workdir / ".sdd" / "runtime" / f"agent-{session_id}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("w") as fh:
            proc = subprocess.Popen([sys.executable, "-c", SCRIPT, str(workdir), prompt, str(LIVE_S)], cwd=str(workdir),
                                    env=build_filtered_env([]), stdout=fh, stderr=subprocess.STDOUT)
        return SpawnResult(pid=proc.pid, log_path=log, proc=proc)
