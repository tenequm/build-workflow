"""Bernstein adapters that run an executor inside a herdr pane.

Contract:
- Bernstein owns the worktree; this adapter resolves the plan step from the task
  title in the prompt, refuses to start if the pinned sources (spec, plan, brief)
  changed since readiness, writes the worktree brief (run-dir brief + the
  orchestrator's own instructions and completion contract), opens one tab in the
  run's herdr workspace, starts the agent, reads the screen before the first
  Enter, prompts with a one-liner;
- completion is the report file on disk followed by two idle reads 20 s apart
  (never the agent status alone); the watcher process is the SpawnResult.proc;
- on settle the watcher copies the report into <run>/reports/, archives the diff,
  appends a runs.jsonl row with wall and diff stats;
- a per-step shadow lane (sidecar `shadow: agy`) runs a second executor on the
  same brief in a sibling worktree; archived under <run>/shadow/, never merged.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from bernstein.adapters.base import DEFAULT_TIMEOUT_SECONDS, CLIAdapter, SpawnResult

from bernstein_herdr import herdr, ledger
from bernstein_herdr.plan import Step, load_plan, pinned_hashes, repo_root

PROMPT_LINE = "Read {brief} in this worktree and execute it fully. Reply DONE when the report is written."


def _check_pins(plan) -> None:
    ledger_md = plan.run_dir / "readiness" / "pins.json"
    if not ledger_md.exists():
        raise RuntimeError(f"no readiness pins at {ledger_md}; run `bernstein-herdr ready` first")
    pinned = json.loads(ledger_md.read_text())
    current = pinned_hashes(plan)
    changed = [k for k, v in pinned.items() if current.get(k) != v]
    if changed:
        raise RuntimeError(f"source changed since readiness: {', '.join(changed)}; rerun `bernstein-herdr ready`")


def _write_brief(wt: Path, step: Step, orchestrator_prompt: str) -> str:
    rel = f".agents/briefs/{step.slug}.md"
    body = step.brief.read_text() if step.brief.exists() else f"# {step.title}\n\n{step.raw.get('description', '')}\n"
    (wt / rel).parent.mkdir(parents=True, exist_ok=True)
    (wt / rel).write_text(body.rstrip() + "\n\n## Orchestrator instructions and completion contract\n\n" + orchestrator_prompt.strip() + "\n")
    return rel


class HerdrAdapter(CLIAdapter):
    kind: str = ""
    agent_args: list[str] = []

    def spawn(
        self, *, prompt: str, workdir: Path, model_config: Any, session_id: str,
        mcp_config: dict[str, Any] | None = None, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        task_scope: str = "medium", budget_multiplier: float = 1.0, system_addendum: str = "",
        multimodal_context: Any | None = None,
    ) -> SpawnResult:
        self.refuse_multimodal_if_needed(multimodal_context)
        root = repo_root(workdir)
        plan = load_plan(root=root)
        step = plan.step_from_prompt(prompt)
        _check_pins(plan)
        brief_rel = _write_brief(workdir, step, prompt + ("\n\n" + system_addendum if system_addendum else ""))
        base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=workdir, capture_output=True, text=True, check=True).stdout.strip()

        ws = herdr.workspace_for_run(plan.run_dir, f"build-{plan.slug}")
        name = f"x-{step.slug}"[:32]
        if self.kind == "agy":
            herdr.pretrust_agy(workdir)
        pane = herdr.open_tab(ws, workdir, step.slug)
        args = list(self.agent_args)
        model = getattr(model_config, "model", None)
        if model and model != "default":
            args += ["--model", model]
        herdr.start_agent(name, self.kind, pane, args)
        started = time.time()
        herdr.prompt(name, PROMPT_LINE.format(brief=brief_rel))
        ledger.note(plan.run_dir, f"spawn step={step.slug} kind={self.kind} model={model} worktree={workdir} base={base} agent={name}")

        log_path = workdir / ".sdd" / "runtime" / f"{session_id}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        watcher = subprocess.Popen(
            [sys.executable, "-m", "bernstein_herdr.watch", "--agent", name, "--worktree", str(workdir), "--report", step.report_rel,
             "--run-dir", str(plan.run_dir), "--step", step.slug, "--base", base, "--kind", self.kind, "--model", str(model), "--started", str(started), "--lane", "primary"],
            cwd=workdir, stdout=log_path.open("a"), stderr=subprocess.STDOUT, start_new_session=True,
        )
        result = SpawnResult(pid=watcher.pid, log_path=log_path, proc=watcher)
        if timeout_seconds > 0:
            result.timeout_timer = self._start_timeout_watchdog(watcher.pid, timeout_seconds, session_id)
        if step.shadow and step.shadow != self.kind:
            _start_shadow(step, plan, workdir, brief_rel, base, ws)
        return result

    def kill(self, pid: int):  # type: ignore[override]
        name = _watcher_agent(pid)
        if name:
            herdr.stop_agent(name)
        return super().kill(pid)

    def name(self) -> str:
        return f"herdr-{self.kind}"


class HerdrClaudeAdapter(HerdrAdapter):
    kind = "claude"
    agent_args = ["--permission-mode", "auto"]


class HerdrCodexAdapter(HerdrAdapter):
    kind = "codex"
    agent_args = ["--approve-for-me", "--no-alt-screen"]


class HerdrAgyAdapter(HerdrAdapter):
    kind = "agy"
    agent_args = []


def _watcher_agent(pid: int) -> str | None:
    out = subprocess.run(["ps", "-o", "args=", "-p", str(pid)], capture_output=True, text=True, check=False).stdout.split()
    return out[out.index("--agent") + 1] if "--agent" in out else None


def _start_shadow(step: Step, plan, workdir: Path, brief_rel: str, base: str, ws: str) -> None:
    shadow_wt = workdir.parent / f"{workdir.name}-shadow-{step.shadow}"
    if shadow_wt.exists():
        return
    subprocess.run(["git", "worktree", "add", "--detach", str(shadow_wt), base], cwd=workdir, check=True, capture_output=True)
    (shadow_wt / brief_rel).parent.mkdir(parents=True, exist_ok=True)
    (shadow_wt / brief_rel).write_text((workdir / brief_rel).read_text())
    if step.shadow == "agy":
        herdr.pretrust_agy(shadow_wt)
    name = f"s-{step.slug}"[:32]
    pane = herdr.open_tab(ws, shadow_wt, f"{step.slug}-shadow")
    herdr.start_agent(name, step.shadow, pane, [])
    started = time.time()
    herdr.prompt(name, PROMPT_LINE.format(brief=brief_rel))
    ledger.note(plan.run_dir, f"shadow step={step.slug} kind={step.shadow} worktree={shadow_wt}")
    subprocess.Popen(
        [sys.executable, "-m", "bernstein_herdr.watch", "--agent", name, "--worktree", str(shadow_wt), "--report", step.report_rel,
         "--run-dir", str(plan.run_dir), "--step", step.slug, "--base", base, "--kind", step.shadow, "--model", "default", "--started", str(started), "--lane", "shadow"],
        cwd=shadow_wt, stdout=(shadow_wt / ".shadow.log").open("a"), stderr=subprocess.STDOUT, start_new_session=True,
    )
