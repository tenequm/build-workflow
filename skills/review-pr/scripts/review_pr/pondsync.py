"""Executor sessions land in pond, so a review's provenance survives the workspace.

Every session this workflow spawns is a claude, codex or agy CLI session - the formats
pond ingests losslessly. The driver syncs them at stage teardown and records each
session id against the finding ids it produced. A failed stage then becomes a query
rather than a crawl through runtime logs, and every posted finding can name the
transcript that produced it and the one that verified it.

Transcripts are stored and queried; they are never fed back into a brief. They are a
prompt-injection surface and the corpus provably carries credentials - evidence, not
instructions.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .proc import command

MINIMUM = (0, 17, 2)
AGY_ADAPTER = "agy"


def version() -> tuple[tuple[int, ...] | None, str]:
    code, out, err = command(["pond", "--version"], Path.cwd(), timeout=30)
    text = (out + err).decode(errors="replace").strip()
    if code:
        return None, text or "pond is not installed"
    parts = text.split()
    for token in parts:
        bits = token.split(".")
        if len(bits) >= 3 and all(bit.isdigit() for bit in bits[:3]):
            return tuple(int(bit) for bit in bits[:3]), text
    return None, text


def current(minimum: tuple[int, ...] = MINIMUM) -> dict[str, Any]:
    """agy sessions are ingested from pond 0.17.2; before that a whole lane is invisible."""
    found, text = version()
    return {
        "version": ".".join(str(part) for part in found) if found else None,
        "raw": text,
        "minimum": ".".join(str(part) for part in minimum),
        "ok": bool(found and found >= minimum),
    }


def adapters() -> dict[str, Any]:
    code, out, err = command(["pond", "adapters", "list"], Path.cwd(), timeout=60)
    text = (out + err).decode(errors="replace")
    return {"ok": code == 0, "agy": AGY_ADAPTER in text, "output": text.strip()[-2000:]}


def sync(timeout: float = 900) -> dict[str, Any]:
    code, out, err = command(["pond", "sync"], Path.cwd(), timeout=timeout)
    return {
        "ok": code == 0,
        "returncode": code,
        "output": (out + err).decode(errors="replace").strip()[-4000:],
    }


def _stamp(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def resolve(receipts: dict[str, dict[str, Any]], ledger_dir: Path) -> dict[str, Any]:
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
        }
        rows: list[dict[str, Any]] = []
        if started and finished:
            sql = (
                "SELECT session_id, source_agent, created_at FROM sessions "
                f"WHERE project = '{worktree}' "
                f"AND created_at >= '{window['from']}' AND created_at <= '{window['to']}'"
            )
            code, out, _ = command(
                ["pond", "sql", "--format", "ndjson", sql], Path.cwd(), timeout=120
            )
            if code == 0:
                for line in out.decode(errors="replace").splitlines():
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        resolved[operation] = {**window, "sessions": rows, "resolved": bool(rows)}
    return resolved
