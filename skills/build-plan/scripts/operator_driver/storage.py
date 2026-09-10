"""Durable intents and immutable receipts; uncertain effects remain explicit."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


class Park(RuntimeError):
    """An obligation remains unresolved; do not release another phase."""


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def atomic(path: Path, data: bytes, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        Path(name).unlink(missing_ok=True)


def immutable(path: Path, data: bytes) -> None:
    if path.exists():
        if path.read_bytes() != data:
            raise Park(f"immutable receipt differs: {path}")
        return
    atomic(path, data)


def contained(root: Path, rel: str) -> Path:
    path = Path(rel)
    if not path.parts or path.is_absolute() or ".." in path.parts:
        raise Park(f"unsafe relative path: {rel!r}")
    result = root / path
    if not result.resolve().is_relative_to(root.resolve()):
        raise Park(f"path escapes root: {rel!r}")
    return result


@contextmanager
def driver_lock(root: Path):
    path = root / ".sdd/runtime/operator.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Park("another driver owns this workspace") from exc
        # Ordinary native bootstrap checks this marker before Git hygiene. Hold
        # it through the detached ceremony as well as every native mini-run.
        from bernstein.core.orchestration.bootstrap import _acquire_pid_lock, _release_pid_lock

        try:
            _acquire_pid_lock(root)
        except RuntimeError as exc:
            raise Park(str(exc)) from exc
        try:
            yield
        finally:
            _release_pid_lock(root)


class Ledger:
    """One writer; a torn/corrupt journal parks rather than forgetting an intent."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.path = directory / "workflow.jsonl"
        self.events: list[dict] = []
        previous = "0" * 64
        if self.path.exists():
            raw = self.path.read_bytes()
            if raw and not raw.endswith(b"\n"):
                raise Park("workflow journal has a torn tail; preserve it for recovery")
            for line in raw.splitlines():
                record = json.loads(line)
                seal = record.pop("hash")
                if (
                    record["seq"] != len(self.events)
                    or record["previous"] != previous
                    or digest(canonical(record)) != seal
                ):
                    raise Park("workflow journal chain is invalid")
                record["hash"] = seal
                self.events.append(record)
                previous = seal

    def append(self, event: str, **data) -> dict:
        record = {
            "seq": len(self.events),
            "previous": self.events[-1]["hash"] if self.events else "0" * 64,
            "event": event,
            "time": time.time(),
            **data,
        }
        record["hash"] = digest(canonical(record))
        self.directory.mkdir(parents=True, exist_ok=True)
        with os.fdopen(
            os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600), "ab"
        ) as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(canonical(record) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        self.events.append(record)
        # Compatibility projections are evidence indexes, never recovery authority.
        projection = {key: value for key, value in record.items() if key != "token"}
        with (self.directory / "runs.jsonl").open("ab") as stream:
            stream.write(canonical(projection) + b"\n")
        directory_fd = os.open(self.directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        with (self.directory / "ledger.md").open("a") as stream:
            stream.write(
                f"- {record['seq']}: {event} ({data.get('operation', data.get('run_id', 'build'))})\n"
            )
        return record

    def last(self, event: str, **match) -> dict | None:
        return next(
            (
                row
                for row in reversed(self.events)
                if row["event"] == event
                and all(row.get(key) == value for key, value in match.items())
            ),
            None,
        )


def post_once(ledger: Ledger, client, payload: dict, operation: str) -> str:
    """Bind server-generated IDs to intent. Never retry an ambiguous absent POST."""
    if "id" in payload:
        raise Park("explicit task IDs are forbidden")
    body = {**payload, "metadata": {**payload.get("metadata", {}), "operator_operation": operation}}
    request_hash = digest(canonical(body))
    intent = ledger.last("post_intent", operation=operation)
    if intent and intent["payload_hash"] != request_hash:
        raise Park("POST intent payload drift")
    tasks = client.tasks()
    found = [
        task
        for task in tasks
        if task.get("metadata", {}).get("operator_operation") == operation
        and not task.get("metadata", {}).get("retry_of")
    ]
    if len(found) > 1:
        raise Park("duplicate tasks for one POST intent")
    if found:
        client.verify_task(found[0], body)
        if not ledger.last("post_receipt", operation=operation):
            ledger.append(
                "post_receipt",
                operation=operation,
                task_id=found[0]["id"],
                payload_hash=request_hash,
            )
        return found[0]["id"]
    if intent:
        raise Park("POST outcome is uncertain or its task was lost; do not repost")
    ledger.append("post_intent", operation=operation, payload_hash=request_hash, payload=body)
    created = client.post_task(body)
    task_id = created["id"]
    stored = next((task for task in client.tasks() if task["id"] == task_id), None)
    if stored is None:
        raise Park("POST returned an ID absent from the task inventory")
    client.verify_task(stored, body)
    ledger.append("post_receipt", operation=operation, task_id=task_id, payload_hash=request_hash)
    return task_id
