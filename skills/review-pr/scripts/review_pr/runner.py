"""One-shot ACP review sessions, launched as a driver-owned parallel batch.

A reviewer reads and writes one report. It never commits, never merges, never becomes
an engine task, and its worktree is checked afterwards to prove it touched nothing
else. So this workflow runs no task engine: the engine's value here would be its
retry-on-missing-work, and that is the report-witness law, which is implemented
directly below - a task whose declared report is absent or unwitnessed is a failed
attempt, retried once on a fresh session, then parked.

Keeping it driver-side also keeps the stage boundary sound. The engine releases a
dependent on worker-reported DONE, before any verification, so stage 3 could never
have been an in-DAG dependent of stage 2; each stage is its own batch here, and the
batch returns only after every receipt is written.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from operator_driver.acp import claude_bridge, judge_argv, transcript
from operator_driver.processes import alive, cancel_acp, launch_once, owned_processes, terminate
from operator_driver.storage import Ledger, Park, atomic, canonical, digest, immutable

from .proc import git, removals

POLL_S = 0.25
# The measured 429 is a burst limiter on a subscription window, not a hard quota, so a
# retry that relaunches immediately spends itself on the same exhausted window.
PROVIDER_BACKOFF_S = 60.0
PROVIDER_PROBLEM = "session stream ended in a provider error"
PROVIDER_ERROR = re.compile(
    r"model unreachable"
    r"|RESOURCE_EXHAUSTED"
    r"|RATE_LIMIT_EXCEEDED"
    r"|Agent execution terminated due to error"
    r"|request failed \(code [45]\d\d\)",
    re.IGNORECASE,
)


@dataclass
class Task:
    """One session's whole contract: what it reads, what it must write, and its bounds."""

    operation: str
    brief: str
    report: str
    witness: str
    spec: dict[str, Any]
    lens: str | None = None
    family: str = "claude"
    # Per-task input files, written under `<workspace>/inputs/<key>/`. The key is
    # stable across retries; the operation is not, and a brief that named the
    # operation's directory would break the moment a session was retried.
    key: str = ""
    reads: dict[str, str] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def inputs(self, workspace: Path) -> Path:
        return workspace / "inputs" / (self.key or self.operation)

    @property
    def signal(self) -> str:
        """The same shape as a plan's file_contains signal: `path :: literal`."""
        return f"{self.report} :: {self.witness}"


def session_argv(spec: dict[str, Any], worktree: Path, prompt: Path) -> list[str]:
    """The vendored judge command, plus the one knob a Codex one-shot needs."""
    argv = judge_argv(spec, worktree, prompt)
    effort = spec.get("effort")
    if effort and not claude_bridge(spec):
        # The Claude bridge has no effort knob; a Codex one-shot takes it on `exec`.
        index = argv.index("exec")
        argv = [
            *argv[: index + 1],
            "--config-option",
            f"reasoning_effort={effort}",
            *argv[index + 1 :],
        ]
    return argv


def provider_failure(log: bytes) -> str | None:
    """The provider error a turn ended on, if it ended on one.

    A 429 in the middle of a turn is not a failure: the first corpus run has sessions
    that hit one, recovered inside the same turn and wrote a full report. What is a
    failure is the turn ENDING on one - the agent's last word is the provider error,
    the stop reason is still `end_turn`, the adapter exits 0, and the receipt would
    otherwise read as a lens that ran and found nothing. A check that could not run
    refutes nothing, so that shape must never reach stage 3 as an empty findings list.
    """
    terminal = ""
    speaking = False
    for line in log.splitlines():
        try:
            message = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(message, dict) or message.get("method") != "session/update":
            continue
        update = (message.get("params") or {}).get("update") or {}
        kind = update.get("sessionUpdate")
        if kind == "agent_message_chunk":
            content = update.get("content")
            text = content.get("text") if isinstance(content, dict) else content
            terminal = terminal + str(text or "") if speaking else str(text or "")
            speaking = True
        elif kind in ("tool_call", "tool_call_update") and update.get("status") == "failed":
            terminal = str(update.get("rawOutput") or "")
            speaking = False
    found = PROVIDER_ERROR.search(terminal)
    return found.group(0) if found else None


def validate_tree(worktree: Path, head: str, allowed: set[str]) -> None:
    """Prove the session wrote only what it was allowed to write."""
    if git(worktree, "rev-parse", "HEAD") != head:
        raise Park(f"review session moved its detached HEAD in {worktree}")
    changed = git(worktree, "diff", "--name-only", "--no-renames", head).splitlines()
    changed += git(worktree, "diff", "--cached", "--name-only", "--no-renames", head).splitlines()
    changed += git(worktree, "ls-files", "--others", "--exclude-standard").splitlines()
    violations = sorted({path for path in changed if path and path not in allowed})
    if violations:
        raise Park(f"review session wrote outside its allowlist: {violations}")


def _worktree(sidecar: dict[str, Any], directory: Path, fresh: bool) -> Path:
    repo = Path(sidecar["repo_path"])
    worktree = directory / "worktree"
    if worktree.exists():
        if not fresh:
            return worktree
        git(repo, "worktree", "remove", "--force", str(worktree))
    git(repo, "worktree", "add", "--detach", "--quiet", str(worktree), sidecar["head"])
    return worktree


def _attempt(
    task: Task,
    sidecar: dict[str, Any],
    ledger: Ledger,
    *,
    operation: str,
) -> dict[str, Any]:
    """Launch one session and return its receipt. Never raises on the model's failure."""
    directory = ledger.directory / "sessions" / operation
    receipt_path = directory / "receipt.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        recorded = ledger.last("session_receipt", operation=operation)
        if recorded and recorded["receipt_hash"] != digest(canonical(receipt)):
            raise Park(f"session receipt differs from its journal binding: {operation}")
        return receipt
    directory.mkdir(parents=True, exist_ok=True)
    launched = ledger.last("launch_intent", operation=operation)
    worktree = _worktree(sidecar, directory, fresh=launched is None)
    prompt = directory / "prompt.md"
    immutable(prompt, task.brief.encode())
    inputs = task.inputs(ledger.directory)
    for name, body in task.reads.items():
        atomic(inputs / name, body.encode(), mode=0o644)
    report = worktree / task.report
    if launched is None:
        # A report inherited from an interrupted attempt must never become this
        # attempt's output; preserve it, then clear the declared path.
        if report.is_file():
            immutable(directory / "inherited-report.json", report.read_bytes())
            report.unlink()
        ledger.append(
            "session_intent",
            operation=operation,
            lens=task.lens,
            family=task.family,
            model=task.spec["model"],
            signal=task.signal,
            prompt_hash=digest(task.brief.encode()),
            reserved_usd=task.spec["budget_usd"],
        )
    argv = session_argv(task.spec, worktree, prompt)
    process = launch_once(
        ledger,
        operation,
        argv,
        worktree,
        {**removals(), "ACPX_CLAUDE_INCLUDE_USER_SETTINGS": "0"},
    )
    return {
        "pending": True,
        "operation": operation,
        "process": process,
        "worktree": str(worktree),
        "directory": str(directory),
    }


def _settle(
    task: Task,
    sidecar: dict[str, Any],
    ledger: Ledger,
    pending: dict[str, Any],
) -> dict[str, Any]:
    """Reap, validate and archive one finished session."""
    operation = pending["operation"]
    directory = Path(pending["directory"])
    worktree = Path(pending["worktree"])
    exit_path = ledger.directory / "processes" / f"{operation}.exit.json"
    problems: list[str] = []
    if not exit_path.is_file():
        problems.append("session exited without a completion receipt")
        exit_record: dict[str, Any] = {"returncode": None}
    else:
        exit_record = json.loads(exit_path.read_text())
        if exit_record["returncode"]:
            problems.append(f"session command exited {exit_record['returncode']}")
    # acpx keeps a queue owner alive for its idle TTL after a one-shot turn, so a
    # survivor is routine; the reaping still has to have worked.
    survivors = owned_processes(worktree, all_commands=True)
    for survivor in survivors:
        terminate(survivor)
    if owned_processes(worktree, all_commands=True):
        raise Park(f"review session left surviving children: {operation}")
    validate_tree(worktree, sidecar["head"], {task.report})
    report = worktree / task.report
    body = b""
    if not report.is_file():
        problems.append(f"declared report is missing: {task.report}")
    else:
        body = report.read_bytes()
        if task.witness.encode() not in body:
            problems.append(f"report does not witness {task.witness!r}")
    log_path = ledger.directory / "processes" / f"{operation}.log"
    log = log_path.read_bytes() if log_path.is_file() else b""
    protocol: dict[str, Any] = {
        "cost_usd": None,
        "session_id": None,
        "stop_reason": None,
        "errors": [],
    }
    try:
        # Cost is observability here, never control flow: the Claude bridge enforces
        # its own maxBudgetUsd inside the session, and these lanes are
        # subscription-backed, so a missing or malformed figure records as None.
        protocol = transcript(log, require_cost=False)
    except Park as exc:
        problems.append(f"ACP evidence: {exc}")
    if protocol["stop_reason"] != "end_turn" or protocol["errors"]:
        problems.append("ACP prompt did not finish successfully")
    stalled = provider_failure(log)
    if stalled:
        problems.append(f"{PROVIDER_PROBLEM}: {stalled}")
    cost = protocol["cost_usd"]
    if body:
        immutable(directory / Path(task.report).name, body)
    immutable(directory / "process.log", log)
    receipt = {
        "operation": operation,
        "lens": task.lens,
        "family": task.family,
        "model": task.spec["model"],
        "signal": task.signal,
        "ok": not problems,
        "problems": problems,
        "report": task.report if body else None,
        "report_digest": digest(body) if body else None,
        # Informative only - an adapter's list-price estimate on a subscription lane.
        # The real figure comes from pond after the run.
        "cost_usd": cost,
        "acp": protocol,
        "reaped": sorted(survivor["command"] for survivor in survivors),
        "returncode": exit_record["returncode"],
        "meta": task.meta,
        "started": (ledger.last("launch_intent", operation=operation) or {}).get("time"),
        "finished": time.time(),
    }
    immutable(directory / "receipt.json", canonical(receipt))
    ledger.append(
        "session_receipt",
        operation=operation,
        receipt_hash=digest(canonical(receipt)),
        ok=receipt["ok"],
        cost_usd=cost,
        session_id=protocol["session_id"],
    )
    git(Path(sidecar["repo_path"]), "worktree", "remove", "--force", str(worktree))
    return receipt


def run_batch(
    tasks: list[Task],
    sidecar: dict[str, Any],
    ledger: Ledger,
    *,
    attempts: int = 2,
    wall_cap: float,
) -> dict[str, dict[str, Any]]:
    """Run every task concurrently; return one receipt per task, retrying a failed one.

    The batch returns only when every task has a receipt, which is what makes the
    next stage's inputs complete rather than merely available.
    """
    results: dict[str, dict[str, Any]] = {}
    deadline = time.monotonic() + wall_cap
    throttled = False
    for attempt in range(1, attempts + 1):
        outstanding = [task for task in tasks if task.operation not in results]
        if not outstanding:
            break
        if throttled:
            time.sleep(max(0.0, min(PROVIDER_BACKOFF_S, deadline - time.monotonic())))
            throttled = False
        live: list[tuple[Task, dict[str, Any]]] = []
        for task in outstanding:
            operation = task.operation if attempt == 1 else f"{task.operation}#{attempt}"
            record = _attempt(task, sidecar, ledger, operation=operation)
            if record.get("pending"):
                live.append((task, record))
            else:
                results[task.operation] = record
        try:
            while live:
                if time.monotonic() > deadline:
                    raise Park("review stage exceeded its wall-clock bound")
                remaining = []
                for task, record in live:
                    started = ledger.last("launch_intent", operation=record["operation"]) or {}
                    if alive(record["process"]):
                        if time.time() - started.get("time", time.time()) > task.spec["timeout_s"]:
                            cancel_acp(record["process"])
                        remaining.append((task, record))
                        continue
                    receipt = _settle(task, sidecar, ledger, record)
                    stalled = next(
                        (row for row in receipt["problems"] if row.startswith(PROVIDER_PROBLEM)),
                        None,
                    )
                    if stalled:
                        throttled = True
                        if attempt == attempts:
                            raise Park(
                                f"{record['operation']} spent every attempt on a provider "
                                f"error: a lens that could not run is not a lens with no "
                                f"findings ({stalled})"
                            )
                    if receipt["ok"] or attempt == attempts:
                        results[task.operation] = receipt
                live = remaining
                if live:
                    time.sleep(POLL_S)
        except BaseException:
            for _, record in live:
                cancel_acp(record["process"])
            raise
    missing = [task.operation for task in tasks if task.operation not in results]
    if missing:
        raise Park(f"review stage produced no receipt for: {missing}")
    return results
