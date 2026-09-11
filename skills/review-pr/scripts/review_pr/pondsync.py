"""Executor sessions land in pond, so a review's provenance survives the workspace.

Every session this workflow spawns is a claude, codex, agy, opencode or pi CLI session -
the formats pond ingests losslessly. Capture is a verified stage against a fresh per-run
store, not a best-effort sync into whatever the host has: the run provisions its own
store inside the workspace, ingests only its own session sources, requires every receipt to
resolve to a stored transcript, and then folds the store into the operator's corpus
with pond's row-verified copy. The per-run store is also the run's provenance artifact:
`pond copy --from <store> --to provenance.pond` exports it whole.

The binary is pinned like the bernstein dependency: the operator venv carries its own
pond at PINNED (installed by `just install-pond`), so a drifting host pond never
changes what a review does. Transcripts are stored and queried; they are never fed
back into a brief - they are a prompt-injection surface and the corpus provably
carries credentials. Evidence, not instructions.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .proc import command, env_overlay

PINNED = (0, 17, 2)
# family (stages.yaml) -> the pond adapter that ingests that harness's sessions. A
# family whose name is not one of these declares `pond_adapter` in the template and is
# captured without a line of Python: a new lane is usually a new model on a harness
# pond already reads. A family that is neither is captured as nothing, which `resolve`
# then reports as a missing session rather than hiding.
ADAPTERS = {
    "claude": "claude-code",
    "codex": "codex-cli",
    "gemini": "agy",
    "opencode": "opencode",
    "pi": "pi-coding-agent",
}


def _redirect(directory: Path, name: str) -> Path:
    """Where a session's redirected `name` landed - the value proc.env_overlay gave it."""
    return Path(env_overlay([name], directory)[name])


def binary() -> str:
    """The workflow's own pond, never the host's by accident.

    POND_BIN overrides for tests and unusual layouts; the operator venv's copy is the
    pinned install; bare PATH is the last resort and version() still gates it.
    """
    override = os.environ.get("POND_BIN")
    if override:
        return override
    venv = Path(sys.executable).resolve().parent / "pond"
    if venv.is_file():
        return str(venv)
    return "pond"


def _pond(args: list[str], *, store: Path | None = None, timeout: float = 300) -> tuple[int, str]:
    scoped = ["--storage-path", str(store)] if store else []
    code, out, err = command([binary(), *scoped, *args], Path.cwd(), timeout=timeout)
    return code, (out + err).decode(errors="replace")


def version() -> tuple[tuple[int, ...] | None, str]:
    code, text = _pond(["--version"], timeout=30)
    text = text.strip()
    if code:
        return None, text or "pond is not installed"
    for token in text.split():
        bits = token.split(".")
        if len(bits) >= 3 and all(bit.isdigit() for bit in bits[:3]):
            return tuple(int(bit) for bit in bits[:3]), text
    return None, text


def current(pinned: tuple[int, ...] = PINNED) -> dict[str, Any]:
    """Exact pin, not a floor: a host pond ahead of the pin is as much drift as one
    behind it, and the workflow's store operations must not depend on host state."""
    found, text = version()
    return {
        "binary": binary(),
        "version": ".".join(str(part) for part in found) if found else None,
        "pinned": ".".join(str(part) for part in pinned),
        "raw": text,
        "ok": bool(found and found == pinned),
    }


def adapters() -> dict[str, Any]:
    code, text = _pond(["adapters", "list"], timeout=60)
    return {"ok": code == 0, "agy": "agy" in text, "output": text.strip()[-2000:]}


def _claude_project_dir(worktree: str) -> Path:
    """The directory Claude Code writes a session's JSONL under, derived from its cwd."""
    munged = "".join(char if char.isalnum() else "-" for char in worktree)
    return Path.home() / ".claude" / "projects" / munged


def stage_agy_root(worktrees: set[str], destination: Path) -> Path | None:
    """A gemini-root-shaped directory holding only this run's agy conversations.

    pond's agy adapter discovers sessions from the `~/.gemini` root and walks down to
    `antigravity-acp/conversations` itself, so a sync scoped at the conversations
    directory matches nothing and ingests zero sessions (measured 2026-09-11). Pointing
    it at the real root instead would ingest the operator's entire Antigravity history
    into a store that is meant to hold one run, so the run stages its own root: the same
    layout, carrying only the conversation files whose `.meta` names one of this run's
    session worktrees. Returns None when this run produced no agy conversation.
    """
    # GEMINI_HOME relocates the whole agy tree (the metered API-key lane runs under one);
    # honouring it here keeps capture pointed at the lane the sessions actually used.
    gemini_home = os.environ.get("GEMINI_HOME")
    root = Path(gemini_home) if gemini_home else Path.home() / ".gemini"
    source = root / "antigravity-acp" / "conversations"
    if not source.is_dir():
        return None
    staged = destination / "antigravity-acp" / "conversations"
    staged.mkdir(parents=True, exist_ok=True)
    found = False
    for meta in sorted(source.glob("*.meta")):
        try:
            cwd = json.loads(meta.read_text()).get("cwd")
        except (OSError, ValueError):
            continue
        if cwd not in worktrees:
            continue
        # The sqlite database plus its -wal and -shm siblings: a database copied without
        # them loses whatever the adapter had not checkpointed.
        for part in sorted(source.glob(f"{meta.stem}.*")):
            if part.is_file():
                shutil.copy2(part, staged / part.name)
        found = True
    return destination if found else None


def _sources(receipts: dict[str, dict[str, Any]], ledger_dir: Path) -> dict[str, set[Path]]:
    """Per adapter, the narrowest source directories that cover this run's sessions."""
    sources: dict[str, set[Path]] = {}
    agy_worktrees: set[str] = set()
    for operation, receipt in receipts.items():
        family = receipt.get("family")
        adapter = receipt.get("pond_adapter") or ADAPTERS.get(str(family))
        if adapter is None:
            continue
        directory = ledger_dir / "sessions" / receipt.get("operation", operation)
        worktree = str(directory / "worktree")
        if adapter == "claude-code":
            sources.setdefault(adapter, set()).add(_claude_project_dir(worktree))
        elif adapter == "codex-cli":
            for stamp in (receipt.get("started"), receipt.get("finished")):
                if stamp:
                    day = datetime.fromtimestamp(stamp, UTC)
                    sources.setdefault(adapter, set()).add(
                        Path.home() / ".codex" / "sessions" / day.strftime("%Y/%m/%d")
                    )
        elif adapter == "opencode":
            # opencode writes every session it has ever run into one store, so the
            # narrow source is manufactured rather than found: the family redirects
            # XDG_DATA_HOME per session (proc.env_overlay), which leaves a store holding
            # that session and nothing else. Naming it here is what keeps the operator's
            # whole opencode history out of a store that is meant to hold one run.
            sources.setdefault(adapter, set()).add(
                _redirect(directory, "XDG_DATA_HOME") / "opencode"
            )
        elif adapter == "pi-coding-agent":
            # Same manufactured scope, one directory shallower: pi writes every session
            # under one root keyed by cwd, the family redirects
            # PI_CODING_AGENT_SESSION_DIR per session, and pond's adapter reads that
            # root directly - its configured default, `~/.pi/agent/sessions`, is the
            # same shape.
            sources.setdefault(adapter, set()).add(
                _redirect(directory, "PI_CODING_AGENT_SESSION_DIR")
            )
        elif adapter == "agy":
            agy_worktrees.add(worktree)
    if agy_worktrees:
        staged = stage_agy_root(agy_worktrees, ledger_dir / "agy-root")
        if staged:
            sources.setdefault("agy", set()).add(staged)
    found = {
        adapter: {path for path in paths if path.is_dir()} for adapter, paths in sources.items()
    }
    # An adapter whose every candidate is absent is dropped rather than carried as an
    # empty set: "this run produced no source for that family" is the thing capture
    # needs to be able to say.
    return {adapter: paths for adapter, paths in found.items() if paths}


def sync_run_store(
    store: Path, receipts: dict[str, dict[str, Any]], ledger_dir: Path
) -> list[dict[str, Any]]:
    """Ingest exactly this run's session sources into the fresh per-run store."""
    store.mkdir(parents=True, exist_ok=True)
    results = []
    for adapter, paths in sorted(_sources(receipts, ledger_dir).items()):
        for path in sorted(paths):
            code, output = _pond(["sync", adapter, "--path", str(path)], store=store, timeout=900)
            results.append(
                {"adapter": adapter, "path": str(path), "ok": code == 0, "tail": output[-1500:]}
            )
    return results


def fold(store: Path) -> dict[str, Any]:
    """Merge the run store into the operator's corpus, row-verified by pond itself.

    pond copy is an idempotent union merge that exits 6 when any row failed to land.
    Best-effort and recorded, never fatal: a box whose configured store is remote may
    hold read-only credentials (measured 2026-09-11, a 403 on the copy path), and the
    host's own scheduled sync ingests the same session sources regardless.
    """
    code, output = _pond(["copy", "--from", str(store), "--to", "@"], timeout=900)
    return {"ok": code == 0, "returncode": code, "tail": output[-2000:]}


def archive(store: Path, target: Path) -> dict[str, Any]:
    """Export the run store as a compact restorable `.pond` archive - the provenance
    artifact that travels with the run even where the corpus fold cannot land."""
    code, output = _pond(["copy", "--from", str(store), "--to", str(target)], timeout=900)
    return {"ok": code == 0, "path": str(target), "tail": output[-1000:]}


def _stamp(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def resolve(
    receipts: dict[str, dict[str, Any]], ledger_dir: Path, *, store: Path | None = None
) -> dict[str, Any]:
    """Link each session's worktree and time window to the stored transcript.

    A session's `--cwd` is its own throwaway worktree, which makes `project` a unique
    key; the ACP session id is the adapter's, not the stored one, so it is recorded
    alongside rather than used as the join.
    """
    resolved: dict[str, Any] = {}
    for operation, receipt in receipts.items():
        directory = ledger_dir / "sessions" / receipt.get("operation", operation)
        worktree = str(directory / "worktree")
        started = receipt.get("started")
        finished = receipt.get("finished")
        window = {
            "project": worktree,
            "from": _stamp(started) if started else None,
            "to": _stamp(finished) if finished else None,
            "acp_session": (receipt.get("acp") or {}).get("session_id"),
            "model": receipt.get("model"),
            "family": receipt.get("family"),
        }
        rows: list[dict[str, Any]] = []
        if started and finished:
            sql = (
                "SELECT session_id, source_agent, created_at FROM sessions "
                f"WHERE project = '{worktree}' "
                f"AND created_at >= '{window['from']}' AND created_at <= '{window['to']}'"
            )
            code, output = _pond(["sql", "--format", "ndjson", sql], store=store, timeout=120)
            if code == 0:
                for line in output.splitlines():
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        resolved[operation] = {**window, "sessions": rows, "resolved": bool(rows)}
    return resolved
