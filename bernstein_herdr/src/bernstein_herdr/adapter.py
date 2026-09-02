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
  appends a runs.jsonl row with wall and diff stats, runs the step's gate, and on a
  pass calls `bernstein task complete` -- Bernstein drops a plan step's
  completion_signals, so the watcher owns the gate and the completion call;
- a judge step (sidecar `judges:`) gets its own worktree at the merge result, and its
  watcher parses the verdict instead of running the scorer;
- a per-step shadow lane (sidecar `shadow: agy`) runs a second executor on the
  same brief in a sibling worktree; archived under <run>/shadow/, never merged.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from bernstein.adapters._contract import (
    AdapterStrategy,
    DangerousModeStrategy,
    EventChannel,
    OutputMode,
    ResumeStrategy,
    SessionState,
)
from bernstein.adapters.base import DEFAULT_TIMEOUT_SECONDS, CLIAdapter, SpawnResult

from bernstein_herdr import herdr, judge, ledger, watch
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


#: Bernstein's prompt tells the agent to run `bernstein task complete` itself. An agent
#: that does completes its task before the gate has judged anything, and the gate's
#: verdict then arrives too late to hold the merge -- measured: a judge marked its own
#: task done and Bernstein verified it "by default", so no verdict was ever recorded.
#: The brief is the last word the agent reads, so the override goes there.
COMPLETION_OVERRIDE = """
## Completing this task -- overrides the contract above

Do NOT run `bernstein task complete`, and do not report completion any other way.
Write the report named above and stop; the orchestrator runs this step's gate and
completes the task for you. Completing it yourself skips the gate.
"""


def _refuse_root_workdir(plan, step: Step, task_id: str, workdir: Path, root: Path) -> None:
    """Refuse an executor step Bernstein placed at the repository root instead of a worktree.

    Two routes get here, both unmergeable. `validate_worktree_isolation` refuses a repo
    whose `CLAUDE.md` is a symlink -- a false positive: the target is inside the same
    worktree -- and `spawner_core.py:4489` then falls back SILENTLY to the main workdir,
    checking out `agent/<session>` in place (measured, gopost 1a replay). A warm-pool
    slot does the same thing without any refusal: it writes the task CLAUDE.md at the
    root and spawns there with no worktree at all (measured 2026-09-02 in the smoke
    repo, whose CLAUDE.md is a regular file). In both the merge target is
    `current_branch(worktree_root)` (spawner_merge.py:557) -- the agent branch itself --
    so the integration branch can never advance and there is no merge step: the executor
    works, the gate passes, nothing lands. Failing the spawn is the only signal, and
    Bernstein's retry then hands the step a real worktree. `bernstein-herdr ready`
    refuses the symlink shape up front; the warm-pool case costs one retry.
    """
    if workdir != root:
        return
    reason = (f"{step.slug}: Bernstein handed this executor step the repository root ({root}) "
              "instead of a worktree under .sdd/worktrees/, where the work can never merge back. "
              "Either a warm-pool slot spawned at the root (retry, which drops the slot, fixes it) "
              "or worktree isolation was refused, whose known cause is a symlinked CLAUDE.md or "
              "AGENTS.md at the root -- make it a real file and rerun `bernstein-herdr ready`.")
    ledger.note(plan.run_dir, f"refused step={step.slug} task={task_id} root_workdir={root}")
    if task_id:
        watch.fail_task(root, task_id, reason)
    raise RuntimeError(reason)


def _write_brief(wt: Path, step: Step, orchestrator_prompt: str) -> str:
    rel = f".agents/briefs/{step.slug}.md"
    body = step.brief.read_text() if step.brief.exists() else f"# {step.title}\n\n{step.raw.get('description', '')}\n"
    (wt / rel).parent.mkdir(parents=True, exist_ok=True)
    (wt / rel).write_text(body.rstrip() + "\n\n## Orchestrator instructions and completion contract\n\n"
                          + orchestrator_prompt.strip() + "\n" + COMPLETION_OVERRIDE)
    return rel


class HerdrAdapter(CLIAdapter):
    """One CLI kind, with its model and effort locked at the class level.

    Bernstein's heuristic selector emits Claude tier names (opus/sonnet/haiku) for
    any step the role policy left unpinned, and the adapter used to forward them
    verbatim -- which launched `codex --model sonnet`. The lock below is the whole
    contract: the class decides the model and effort, and a caller-supplied model
    is honoured only when it names a model this class recognises for its own CLI.
    `default_model` also satisfies Bernstein's refusal to spawn a non-Claude
    adapter that declares none (core/agents/spawner_warm_pool.py:98).
    """

    kind: str = ""
    agent_args: list[str] = []
    model: str = ""
    effort: str = ""
    #: What these adapters actually do (docs/adapters/capability_contract.md). Every one
    #: launches a fresh CLI in a new pane, so there is no resume and no agent-side state;
    #: permissions come from a launch flag; completion is the commit on the agent branch;
    #: and nothing structured comes back on stdout -- the report file is the channel, so
    #: `text-signals` would promise a parse that never happens.
    strategy_override: AdapterStrategy = AdapterStrategy(
        resume=ResumeStrategy.UNSUPPORTED,
        dangerous_mode=DangerousModeStrategy.CLI_FLAG,
        event_channel=EventChannel.NONE,
        output_mode=OutputMode.GIT_DIFF,
        session_state=SessionState.STATELESS,
    )

    @property
    def default_model(self) -> str:
        return self.model

    def model_args(self, requested: object) -> tuple[list[str], str, str]:
        """The --model/effort argv for this launch, plus the model and effort it resolves to.

        A requested model is accepted only when it is this class's own locked model;
        anything else (a Claude tier name handed to codex, an empty value, "default")
        falls back to the lock rather than reaching the CLI.
        """
        model = str(requested) if requested and str(requested) == self.model else self.model
        return [*self._model_argv(model), *self._effort_argv()], model, self.effort

    def _model_argv(self, model: str) -> list[str]:
        return ["--model", model] if model else []

    def _effort_argv(self) -> list[str]:
        return ["--effort", self.effort] if self.effort else []

    def launch(self, *, name: str, pane: str, args: list[str], plan, step, root: Path, workdir: Path, brief_rel: str) -> tuple[float, str]:
        """Start this CLI in the pane and hand it the one-line prompt.

        Returns the start time and the target the watcher polls. The one seam
        `herdr-fake` overrides (fake.py): it runs a script in the pane instead of an
        agent, so its watcher polls the pane id -- and it pre-trusts nothing.
        """
        # codex trusts at the repository root, agy and claude at the worktree they open in.
        herdr.PRETRUST[self.kind](root if self.kind == "codex" else workdir)
        herdr.start_agent(name, self.kind, pane, args)
        started = time.time()
        herdr.prompt(name, PROMPT_LINE.format(brief=brief_rel))
        return started, name

    def spawn(
        self, *, prompt: str, workdir: Path, model_config: Any, session_id: str,
        mcp_config: dict[str, Any] | None = None, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        task_scope: str = "medium", budget_multiplier: float = 1.0, system_addendum: str = "",
        multimodal_context: Any | None = None,
    ) -> SpawnResult:
        self.refuse_multimodal_if_needed(multimodal_context)
        # Bernstein passes a relative workdir (".") for a step it gave no worktree.
        # herdr's `tab create --cwd` resolves that against the herdr SERVER's cwd, not
        # ours, so the agent opened in an unrelated repository. Resolve here, once.
        workdir = Path(workdir).resolve()
        root = repo_root(workdir)
        plan = load_plan(root=root)
        step = plan.step_from_prompt(prompt)
        task_id = plan.task_id_from_prompt(prompt)
        _check_pins(plan)
        # The sidecar's `cli` is the authoritative executor choice for a step: Bernstein's
        # plan schema has no `cli` key and only warns on one, so whichever herdr-* adapter
        # the seed routed to delegates here. The model and effort locks stay on the
        # concrete class, so a delegation cannot smuggle a model past them.
        runner = self._runner(step)
        lane = "judge" if step.judges else "primary"
        if step.judges:
            # A judge step owns no files, so Bernstein hands it the repo root. Review the
            # merge result in a worktree of its own; the diff under review is the judged
            # step's base..HEAD, which is also what its archived diff.patch should hold.
            workdir = judge.judge_worktree(plan, step, root)
            base = plan.step(step.judges).base
        else:
            _refuse_root_workdir(plan, step, task_id, workdir, root)
            base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=workdir, capture_output=True, text=True, check=True).stdout.strip()
        brief_rel = _write_brief(workdir, step, prompt + ("\n\n" + system_addendum if system_addendum else ""))

        ws = herdr.workspace_for_run(plan.run_dir, f"build-{plan.slug}", root)
        name = f"x-{step.slug}"[:32]
        pane = herdr.open_tab(ws, workdir, step.slug)
        model_argv, model, effort = runner.model_args(getattr(model_config, "model", None))
        args = [*runner.agent_args, *model_argv]
        started, target = runner.launch(name=name, pane=pane, args=args, plan=plan, step=step, root=root, workdir=workdir, brief_rel=brief_rel)
        ledger.note(plan.run_dir, f"spawn step={step.slug} lane={lane} task={task_id} kind={runner.kind} model={model} effort={effort} argv={' '.join(args)} worktree={workdir} base={base} agent={name}")

        log_path = workdir / ".sdd" / "runtime" / f"{session_id}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        watcher = subprocess.Popen(
            [sys.executable, "-m", "bernstein_herdr.watch", "--agent", target, "--worktree", str(workdir), "--report", step.report_rel,
             "--run-dir", str(plan.run_dir), "--step", step.slug, "--title", step.title, "--base", base, "--kind", runner.kind,
             "--model", model, "--effort", effort, "--started", str(started), "--lane", lane, "--task-id", task_id, "--root", str(root)],
            cwd=workdir, stdout=log_path.open("a"), stderr=subprocess.STDOUT, start_new_session=True,
        )
        result = SpawnResult(pid=watcher.pid, log_path=log_path, proc=watcher)
        if timeout_seconds > 0:
            result.timeout_timer = self._start_timeout_watchdog(watcher.pid, timeout_seconds, session_id)
        if step.shadow and step.shadow != self.kind:
            _start_shadow(step, plan, workdir, brief_rel, base, ws)
        return result

    def _runner(self, step: Step) -> "HerdrAdapter":
        """The adapter that actually launches this step: the sidecar's `cli`, else self."""
        cli = (step.cli or "").removeprefix("herdr-")
        if not cli or cli == self.kind:
            return self
        if cli in LAZY_KIND_MODULES and cli not in ADAPTER_BY_KIND:
            # `fake` registers itself on import and lives in its own module; when the seed
            # routed this run to a real CLI, nothing has imported it yet.
            importlib.import_module(LAZY_KIND_MODULES[cli])
        if cli not in ADAPTER_BY_KIND:
            raise RuntimeError(f"step {step.title!r}: sidecar cli={step.cli!r} is not one of {sorted(set(ADAPTER_BY_KIND) | set(LAZY_KIND_MODULES))}")
        return ADAPTER_BY_KIND[cli]()

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
    model = "claude-opus-5"
    effort = "high"


class HerdrCodexAdapter(HerdrAdapter):
    kind = "codex"
    agent_args = ["--approve-for-me", "--no-alt-screen"]
    model = "gpt-5.6-sol"
    effort = "high"

    def _effort_argv(self) -> list[str]:
        """codex has no --effort flag; reasoning effort is a config override."""
        return ["-c", f'model_reasoning_effort="{self.effort}"'] if self.effort else []


class HerdrAgyAdapter(HerdrAdapter):
    kind = "agy"
    agent_args = []
    model = "gemini-3.7-flash-high"
    effort = "high"
    #: agy takes no permission flag; approval is `toolPermission: always-proceed` in its
    #: settings file, which is on for the whole install.
    strategy_override = replace(HerdrAdapter.strategy_override, dangerous_mode=DangerousModeStrategy.ALWAYS_ON)


ADAPTER_BY_KIND = {"claude": HerdrClaudeAdapter, "codex": HerdrCodexAdapter, "agy": HerdrAgyAdapter}
#: Kinds whose adapter lives in a module nothing else imports; `_runner` pulls one in on
#: demand and it registers itself in ADAPTER_BY_KIND.
LAZY_KIND_MODULES = {"fake": "bernstein_herdr.fake"}


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
    herdr.PRETRUST[step.shadow](shadow_wt)
    name = f"s-{step.slug}"[:32]
    shadow_adapter = ADAPTER_BY_KIND[step.shadow]()
    shadow_argv, shadow_model, shadow_effort = shadow_adapter.model_args(None)
    pane = herdr.open_tab(ws, shadow_wt, f"{step.slug}-shadow")
    herdr.start_agent(name, step.shadow, pane, [*shadow_adapter.agent_args, *shadow_argv])
    started = time.time()
    herdr.prompt(name, PROMPT_LINE.format(brief=brief_rel))
    ledger.note(plan.run_dir, f"shadow step={step.slug} kind={step.shadow} worktree={shadow_wt}")
    subprocess.Popen(
        [sys.executable, "-m", "bernstein_herdr.watch", "--agent", name, "--worktree", str(shadow_wt), "--report", step.report_rel,
         "--run-dir", str(plan.run_dir), "--step", step.slug, "--title", step.title, "--base", base, "--kind", step.shadow,
         "--model", shadow_model, "--effort", shadow_effort, "--started", str(started), "--lane", "shadow", "--task-id", "", "--root", str(plan.root)],
        cwd=shadow_wt, stdout=(shadow_wt / ".shadow.log").open("a"), stderr=subprocess.STDOUT, start_new_session=True,
    )
