"""Settle watcher for one pane: settle, gate, complete the task.

Bernstein 3.19.0 drops a plan step's `completion_signals` when it posts the task to
its task server (core/planning/planner.py), and its seed parser refuses a
`bernstein.gates` plugin name in the pipeline (core/config/seed_parser.py:1916), so
neither the scorer nor the judge verdict can be driven from the plan. The watcher runs
the step's gate itself instead, and reports completion through the same front door an
agent would use.

Settle is the report file on disk plus two idle reads 20 s apart, never the agent
status alone. Then: archive the diff, write the wall row, run the gate (scorer for an
implementation step, verdict parsing for a judge step -- decided by the sidecar
`judges` field, not by the title), and on a pass complete the task.

Exiting on the POST alone is not enough. Bernstein reaps a spawned process whose
`proc.poll()` returns, and resolves the orphan question against the task snapshot taken
at the START of that tick (agent_lifecycle.py:2183-2229), so a process that dies in the
same tick as its own completion is still judged an orphan -- and with the agent running
outside the worktree, that lands on the "clean exit, no changes" branch and the task is
failed. So the watcher waits until the completion is observed, which arrives either as
`closed` on the task or as the SIGTERM Bernstein sends to reap it before merging.

Exit 0 on a completed task, 2 on a blocked gate or blocked agent, 1 if the agent
vanished without a report or the completion was never observed. Every block also fails
the task on the server, so the run advances instead of waiting for the reaper.
"""

from __future__ import annotations

import argparse
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from bernstein_herdr import herdr, ledger
from bernstein_herdr.herdr import IDLE

ARGS = ("agent", "worktree", "report", "run_dir", "step", "title", "base", "kind",
        "model", "effort", "started", "lane", "task_id", "root")
#: How long to wait for Bernstein to observe the completion. Well under the 30 min
#: `max_agent_runtime_s` reaper (core/defaults.py:168).
CONFIRM_TIMEOUT_S = 600
CONFIRM_POLL_S = 2
#: `closed` is set only after the janitor, the gates and the merge-back all passed
#: (task_lifecycle.py:4092). `done` alone is the completion the server recorded.
CLOSED = "closed"
DONE = "done"
#: Consecutive `done` polls accepted instead of `closed`, for runs whose approval gate
#: skips the merge. Three polls span more than two 3 s orchestrator ticks, so the
#: orchestrator's tick-start task snapshot cannot still be the pre-completion one --
#: the stale snapshot is what sends a dead process down the orphan path
#: (agent_lifecycle.py:2183-2229).
DONE_POLLS = 3


def run_gate(root: Path, worktree: Path, title: str) -> tuple[bool, dict]:
    """The step's own gate. Writes its runs.jsonl row itself, as the CLI forms do."""
    from bernstein_herdr.plan import load_plan

    plan = load_plan(root=root)
    step = plan.step(title)
    if step.judges:
        from bernstein_herdr.judge import record_verdict

        verdict = record_verdict(plan, step, worktree)
        return bool(verdict["block"]), verdict
    from bernstein_herdr.gates.scorer import score

    return score(worktree, title)


def complete_task(root: Path, task_id: str, summary: str) -> bool:
    """Report completion, then wait until the server says the task is done.

    Exiting on the POST alone is not enough: Bernstein reaps the spawned process on a
    poll tick, and a process that dies while its task is still open takes the orphan
    path ("git commits detected, no signals"). Waiting for the status the server
    actually holds keeps the completion genuine.
    """
    posted = subprocess.run(["bernstein", "task", "complete", task_id, "--summary", summary[:2000]],
                            cwd=root, capture_output=True, text=True, check=False)
    print(f"{ledger.now()} task complete rc={posted.returncode} {(posted.stdout + posted.stderr).strip()[-300:]}", flush=True)
    if posted.returncode != 0:
        return False
    deadline = time.time() + CONFIRM_TIMEOUT_S
    seen = 0
    while time.time() < deadline:
        status = task_status(root, task_id)
        if status == CLOSED:
            print(f"{ledger.now()} observed closed (merged)", flush=True)
            return True
        seen = seen + 1 if status == DONE else 0
        if seen >= DONE_POLLS:
            print(f"{ledger.now()} observed done x{seen}", flush=True)
            return True
        time.sleep(CONFIRM_POLL_S)
    return False


def fail_task(root: Path, task_id: str, reason: str) -> bool:
    """Mark the task failed so a block ends the step instead of stalling the run.

    `bernstein task` has no `fail` verb (only complete/suspend/resume/list-suspended),
    so this posts to the same task-server front door the CLI uses, `/tasks/<id>/fail`
    (core/routes/task_crud.py:1673). Upstream that is not a dead end: the orchestrator's
    tick loop offers a failed task to `maybe_retry_task`, which requeues it with effort
    then model escalation up to the task's retry budget, and on exhaustion records the
    title in the cross-run quarantine store (task_lifecycle.py:550-625) so later runs
    skip it. Leaving the task open instead left the run waiting for the 30 min reaper.
    """
    data = _server(root, "post", f"/tasks/{task_id}/fail", {"reason": reason[:2000]})
    print(f"{ledger.now()} task fail -> {data.get('status') if data else 'no response'}", flush=True)
    return bool(data)


def task_status(root: Path, task_id: str) -> str:
    """Task status straight from the run's own task server, via Bernstein's helper."""
    data = _server(root, "get", f"/tasks/{task_id}")
    return str(data.get("status", "")) if data else ""


def _server(root: Path, verb: str, path: str, payload: dict | None = None) -> dict:
    import os

    cwd = os.getcwd()
    try:
        os.chdir(root)  # resolve_server_url()/auth_headers() read .sdd/runtime under the cwd
        from bernstein.cli.helpers import server_get, server_post

        data = server_post(path, payload or {}) if verb == "post" else server_get(path)
        return data or {}
    except Exception as exc:  # the server is gone, or never came up
        print(f"{ledger.now()} {verb} {path} failed: {exc}", flush=True)
        return {}
    finally:
        os.chdir(cwd)


#: Set once this watcher has resolved its own task (completed or failed), so a reap can
#: be told apart from a kill that arrived before the gate ever ran.
_completed = False


def _reaped(_signum: int, _frame: object) -> None:
    """Bernstein terminates the spawned process as the first step of merging the work
    (spawner_merge.py:1107 reap_subprocess), so a reap AFTER this watcher resolved the
    task is the success case, not a kill. A reap BEFORE it is the opposite: the task was
    resolved without this step's gate, and saying nothing would hide that."""
    print(f"{ledger.now()} reaped by the orchestrator; resolved_by_watcher={_completed}", flush=True)
    sys.exit(0 if _completed else 1)


def block(root: Path, run_dir: Path, task_id: str, step: str, lane: str, reason: str) -> int:
    """Record the block, fail the task so the run moves on, exit 2.

    A block used to be a bare `return 2`: the task stayed open with no live agent and
    nothing reopened it, so the run sat until the 30 min reaper. Failing it hands the
    step back to Bernstein's own retry-then-quarantine path with the reasons attached.
    After the retry budget the title is quarantined across runs; `bernstein quarantine
    list` shows it and `bernstein quarantine clear --task "<title>"` releases it, so a
    re-run needs neither a new run directory nor `rm -rf .sdd`.
    """
    global _completed
    ledger.note(run_dir, f"blocked step={step} lane={lane} {reason}")
    if task_id:
        _completed = fail_task(root, task_id, f"{step}: {reason}")
    return 2


def _reasons(detail: dict) -> str:
    """The blocking findings, short enough for a task fail reason and a ledger line."""
    keep = ("gate_rc", "allowlist_violations", "new_nolint_without_reason", "deleted_test_files",
            "report_mismatch", "do_not_merge", "merge_as_is", "review_present", "reason")
    named = {k: v for k, v in detail.items() if k in keep and v not in (None, [], 0, False)}
    tail = (detail.get("gate") or {}).get("tail", "")
    return ", ".join(f"{k}={v}" for k, v in named.items()) + (f"; tail: {tail[-400:]}" if tail else "")


def main() -> int:
    signal.signal(signal.SIGTERM, _reaped)
    ap = argparse.ArgumentParser()
    for k in ARGS:
        ap.add_argument(f"--{k.replace('_', '-')}", required=True)
    a = ap.parse_args()
    wt, run_dir, root = Path(a.worktree), Path(a.run_dir), Path(a.root)
    report = wt / a.report
    idle = 0
    blocks = 0
    while True:
        st = herdr.status(a.agent)
        print(f"{ledger.now()} {st} report={'yes' if report.exists() else 'no'}", flush=True)
        if st == "blocked":
            blocks += 1
            return block(root, run_dir, a.task_id, a.step, a.lane, f"agent {a.agent} is blocked")
        if st == "gone" and not report.exists():
            block(root, run_dir, a.task_id, a.step, a.lane, f"agent {a.agent} gone without a report")
            return 1
        idle = idle + 1 if (report.exists() and st in IDLE) else 0
        if idle >= 2:
            break
        time.sleep(20)
    wall = int(time.time() - float(a.started))
    dest = run_dir / ("shadow" if a.lane == "shadow" else "reports") / a.step
    stats = ledger.archive(wt, a.base, dest)
    if report.exists():
        shutil.copy(report, dest / "report.md")
    ledger.row(run_dir, {
        "run_id": f"{run_dir.name}-{a.step}-{a.lane}-{a.kind}", "step": a.step, "lane": a.lane, "base": a.base,
        "arm": {"agent": a.kind, "model": a.model, "effort": a.effort}, "wall_s": wall, "blocks": blocks, "diff": stats,
        "report": ledger.report_claims(report), "worktree": str(wt), "evidence": "reported",
    })
    ledger.note(run_dir, f"settled step={a.step} lane={a.lane} wall_s={wall} files={stats['files']}")
    if a.lane == "shadow":
        return 0  # archived for later blind judging, never in the chain, never completed

    blocked, detail = run_gate(root, wt, a.title)
    if blocked:
        return block(root, run_dir, a.task_id, a.step, a.lane, f"gate blocked: {_reasons(detail)}")
    if not a.task_id:
        ledger.note(run_dir, f"gate passed step={a.step} lane={a.lane} but no task id in the prompt; not completing")
        return 0
    global _completed
    _completed = True
    if not complete_task(root, a.task_id, f"{a.step}: gate passed, report at {dest}"):
        _completed = False
        ledger.note(run_dir, f"completion not confirmed step={a.step} task={a.task_id}")
        return 1
    ledger.note(run_dir, f"completed step={a.step} lane={a.lane} task={a.task_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
