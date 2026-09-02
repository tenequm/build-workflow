"""Bernstein adapters that run an executor inside a herdr pane.

Contract (see docs/2609-02-design.md in the repo root):
- one worktree per task is Bernstein's; this adapter opens one herdr pane with
  cwd at that worktree, starts the agent, reads the screen before the first
  Enter, prompts with a one-liner pointing at the brief;
- completion is the report file on disk followed by two idle reads 20 s apart,
  never the agent status alone;
- the returned SpawnResult carries a watcher subprocess as ``proc`` so the
  orchestrator's poll/is_alive path works unchanged;
- kill() sends ctrl+c to the agent and closes the pane;
- an optional shadow lane starts a second executor (agy by default) on the same
  brief in a sibling worktree and archives its diff and report; Bernstein never
  hears about it.

Everything herdr-specific is behind small helpers so the CLI calls can be
replaced by socket-API calls later without touching spawn().
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from bernstein.adapters.base import DEFAULT_TIMEOUT_SECONDS, CLIAdapter, SpawnResult

REPORT_RELPATH_ENV = "BUILD_REPORT_RELPATH"  # e.g. .agents/report.md, set per step by the plan
BRIEF_RELPATH_ENV = "BUILD_BRIEF_RELPATH"    # e.g. .agents/briefs/phase-1.md
SHADOW_KIND_ENV = "BUILD_SHADOW_KIND"        # e.g. agy; unset = no shadow lane
IDLE_READS = 2
IDLE_INTERVAL_S = 20


def _herdr(*args: str) -> dict[str, Any]:
    out = subprocess.run(["herdr", *args], capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise RuntimeError(f"herdr {' '.join(args)}: {out.stderr.strip()}")
    return json.loads(out.stdout) if out.stdout.strip().startswith("{") else {"raw": out.stdout}


def _agent_status(name: str) -> str:
    try:
        return _herdr("agent", "get", name)["result"]["agent"]["agent_status"]
    except Exception:
        return "gone"


class HerdrAdapter(CLIAdapter):
    kind: str = ""            # herdr agent kind: claude | codex | agy
    agent_args: list[str] = []  # native args after `--` on agent start

    def spawn(
        self,
        *,
        prompt: str,
        workdir: Path,
        model_config: Any,
        session_id: str,
        mcp_config: dict[str, Any] | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        task_scope: str = "medium",
        budget_multiplier: float = 1.0,
        system_addendum: str = "",
        multimodal_context: Any | None = None,
    ) -> SpawnResult:
        self.refuse_multimodal_if_needed(multimodal_context)
        report = os.environ.get(REPORT_RELPATH_ENV, ".agents/report.md")
        brief = os.environ.get(BRIEF_RELPATH_ENV, ".agents/briefs/brief.md")
        (workdir / brief).parent.mkdir(parents=True, exist_ok=True)
        (workdir / brief).write_text(prompt + ("\n\n" + system_addendum if system_addendum else ""))

        name = f"x-{session_id}"[:32].lower().replace("_", "-")
        pane = _herdr("pane", "split", "--direction", "down", "--cwd", str(workdir), "--no-focus")["result"]["pane"]["pane_id"]
        args = list(self.agent_args)
        if model_config.model and model_config.model != "default":
            args += ["--model", model_config.model]
        _herdr("agent", "start", name, "--kind", self.kind, "--pane", pane, "--timeout", "120000", "--", *args)
        _herdr("agent", "prompt", name, f"Read {brief} in this worktree and execute it fully. Reply DONE when the report is written.")

        log_path = workdir / ".sdd" / "runtime" / f"{session_id}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        watcher = subprocess.Popen(
            [sys.executable, "-m", "bernstein_herdr.watch", name, str(workdir / report), str(log_path)],
            cwd=workdir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        result = SpawnResult(pid=watcher.pid, log_path=log_path, proc=watcher)
        if timeout_seconds > 0:
            result.timeout_timer = self._start_timeout_watchdog(watcher.pid, timeout_seconds, session_id)
        shadow_kind = os.environ.get(SHADOW_KIND_ENV)
        if shadow_kind and shadow_kind != self.kind:
            _start_shadow(shadow_kind, workdir, brief, report, session_id)
        return result

    def kill(self, pid: int):  # type: ignore[override]
        # The pid is the watcher; the agent is found by name in the watcher's argv.
        name = _watcher_agent_name(pid)
        if name:
            subprocess.run(["herdr", "agent", "send-keys", name, "ctrl+c"], check=False, capture_output=True)
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
    agent_args = []  # settings toolPermission=always-proceed; worktree must be pre-trusted


def _watcher_agent_name(pid: int) -> str | None:
    try:
        cmd = subprocess.run(["ps", "-o", "args=", "-p", str(pid)], capture_output=True, text=True, check=False).stdout
        parts = shlex.split(cmd)
        return parts[parts.index("bernstein_herdr.watch") + 1] if "bernstein_herdr.watch" in parts else None
    except Exception:
        return None


def _start_shadow(kind: str, workdir: Path, brief: str, report: str, session_id: str) -> None:
    """Second executor on the same brief in a sibling worktree; archived, never merged."""
    shadow_dir = workdir.parent / f"{workdir.name}-shadow-{kind}"
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=workdir, capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(["git", "worktree", "add", "--detach", str(shadow_dir), base], cwd=workdir, check=True, capture_output=True)
    (shadow_dir / brief).parent.mkdir(parents=True, exist_ok=True)
    (shadow_dir / brief).write_text((workdir / brief).read_text())
    name = f"s-{session_id}"[:32].lower().replace("_", "-")
    pane = _herdr("pane", "split", "--direction", "down", "--cwd", str(shadow_dir), "--no-focus")["result"]["pane"]["pane_id"]
    _herdr("agent", "start", name, "--kind", kind, "--pane", pane, "--timeout", "120000")
    _herdr("agent", "prompt", name, f"Read {brief} in this worktree and execute it fully. Reply DONE when the report is written.")
    subprocess.Popen(
        [sys.executable, "-m", "bernstein_herdr.watch", name, str(shadow_dir / report), str(shadow_dir / ".shadow.log"), "--archive", base],
        cwd=shadow_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )
