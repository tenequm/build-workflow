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
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from operator_driver.acp import claude_bridge, judge_argv, transcript
from operator_driver.processes import alive, cancel_acp, launch_once, owned_processes, terminate
from operator_driver.storage import Ledger, Park, atomic, canonical, digest, immutable

from .proc import git, removals

POLL_S = 0.25


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
        protocol = transcript(log, require_cost=claude_bridge(task.spec))
    except Park as exc:
        problems.append(f"ACP evidence: {exc}")
    if protocol["stop_reason"] != "end_turn" or protocol["errors"]:
        problems.append("ACP prompt did not finish successfully")
    cost = protocol["cost_usd"]
    if cost is not None and cost > task.spec["budget_usd"]:
        raise Park(f"review session exceeded its reserved spend: {operation}")
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
        # An unmetered transport reports no cost, so the bound charges the full
        # reservation rather than reading an absent number as zero.
        "cost_usd": cost,
        "charged_usd": cost if cost is not None else task.spec["budget_usd"],
        "metered": cost is not None,
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
        charged_usd=receipt["charged_usd"],
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
    spend_cap: float,
    wall_cap: float,
) -> dict[str, dict[str, Any]]:
    """Run every task concurrently; return one receipt per task, retrying a failed one.

    The batch returns only when every task has a receipt, which is what makes the
    next stage's inputs complete rather than merely available.
    """
    results: dict[str, dict[str, Any]] = {}
    charged = 0.0
    deadline = time.monotonic() + wall_cap
    for attempt in range(1, attempts + 1):
        outstanding = [task for task in tasks if task.operation not in results]
        if not outstanding:
            break
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
                    charged += receipt["charged_usd"]
                    if charged > spend_cap:
                        raise Park(
                            f"review stage exceeded its spend bound: {charged:.2f} > {spend_cap:.2f}"
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
