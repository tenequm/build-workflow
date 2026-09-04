"""Event watcher for a live run: replaces the driver's manual polling loop.

`bernstein-herdr watch` blocks, printing ONE line per event, and exits when the
run is over (no Bernstein process owns this root and no activity arrives for a
grace period). Run it in the background and read its output on completion or on
a stall line; the seven-command 30-60s manual poll in build-run step 5 is what
this replaces.

Events, one line each, `<HH:MM:SS> <TAG> <detail>`:
  ROW      a new runs.jsonl attempt row (the tail of the row)
  SPAWNER  a spawner.log line matching the known trouble patterns (each one is
           also appended to <run>/runs.jsonl as a `spawner_event` row, so kills
           and refusals land in the causal ledger)
  LEDGER   a new ledger.md line
  STALL    no activity for --stall minutes while a Bernstein process is alive
           (apply build-run's stall rule: check the agent log mtime, kill if stale)
  ORCH-DEAD  bernstein processes are alive but the recorded task-server port has
           refused connections for 10+ minutes (said again at most every 30m)
  DISK     free space on the workspace volume fell below 10 GB (once per crossing)
  DISK-CRITICAL  below 2 GB free; kill the run before commits start failing
  END      no Bernstein process owns this root and the grace period passed
  NOSTART  no Bernstein process was EVER seen and nothing happened for 5 minutes;
           the run likely failed to launch -- check the launch wrapper's log

Exit code: 0 on END, 3 on --until-stall with a STALL seen, 4 on NOSTART.
"""

from __future__ import annotations

import os
import re
import socket
import time
from datetime import datetime
from pathlib import Path

TROUBLE = re.compile(r"liveness_judgment|SIGTERM|Timeout after|Refusing to merge|409|ownership conflict|retry_or_fail_task|permanent_fail|max_retries_exceeded|renamed refs/heads")

WARN_BYTES = 10 * 1024**3
CRITICAL_BYTES = 2 * 1024**3
ORCH_DEAD_AFTER_S = 600.0
ORCH_DEAD_REPEAT_S = 1800.0


def disk_events(free_bytes: int, state: dict) -> list[tuple[str, str]]:
    """Threshold crossings for the current free-space reading; `state` carries
    {'warned', 'critical'} across ticks so each threshold speaks once per crossing."""
    events: list[tuple[str, str]] = []
    gb = free_bytes / 1024**3
    if free_bytes < CRITICAL_BYTES and not state.get("critical"):
        state["critical"] = state["warned"] = True
        events.append(("DISK-CRITICAL", f"{gb:.1f} GB free on the workspace volume; executor and salvage "
                                        f"commits will start failing -- kill the run (kill -TERM -<wrapper_pid>) "
                                        f"and free space before losing work"))
    elif free_bytes < WARN_BYTES and not state.get("warned"):
        state["warned"] = True
        events.append(("DISK", f"{gb:.1f} GB free on the workspace volume (warn threshold 10 GB); "
                               f"an unattended run that hits 0 loses whatever was mid-commit"))
    if free_bytes >= WARN_BYTES:
        state["warned"] = state["critical"] = False
    return events


def orch_dead_due(failing_since: float | None, now: float, last_said: float | None) -> bool:
    """Say ORCH-DEAD after 10 consecutive failing minutes, then at most every 30."""
    if failing_since is None or now - failing_since < ORCH_DEAD_AFTER_S:
        return False
    return last_said is None or now - last_said >= ORCH_DEAD_REPEAT_S


def record_spawner_event(run_dir: Path, line: str) -> None:
    """A spawner trouble line as a runs.jsonl row, so kills and refusals sit in the
    same causal ledger as the gate rows they explain."""
    from bernstein_herdr import ledger

    ledger.row(run_dir, {"source": "watch", "kind": "spawner_event", "line": line[:400]})


def _say(tag: str, detail: str) -> None:
    print(f"{datetime.now().strftime('%H:%M:%S')} {tag:8} {detail[:400]}", flush=True)


class _Tail:
    def __init__(self, path: Path):
        self.path = path
        self.pos = path.stat().st_size if path.exists() else 0

    def new_lines(self) -> list[str]:
        if not self.path.exists():
            return []
        size = self.path.stat().st_size
        if size < self.pos:  # rotated or truncated
            self.pos = 0
        if size == self.pos:
            return []
        with self.path.open("r", errors="replace") as f:
            f.seek(self.pos)
            chunk = f.read()
            self.pos = f.tell()
        return [l for l in chunk.splitlines() if l.strip()]


def watch(root: Path, run_dir: Path, interval: float = 10.0, stall_minutes: float = 25.0,
          end_grace: float = 60.0, nostart_grace: float = 300.0, until_stall: bool = False) -> int:
    from bernstein_herdr.proc import stale_bernstein_pids

    tails = {"ROW": _Tail(run_dir / "runs.jsonl"),
             "LEDGER": _Tail(run_dir / "ledger.md"),
             "SPAWNER": _Tail(root / ".sdd" / "runtime" / "spawner.log")}
    started = time.monotonic()
    last_activity = time.monotonic()
    dead_since: float | None = None
    stalled = False
    seen_alive = False
    cwd_memo: dict[tuple[int, str], bool] = {}
    disk_state: dict = {}
    conn_fail_since: float | None = None
    orch_dead_last: float | None = None
    _say("WATCH", f"root={root} run={run_dir} interval={interval}s stall={stall_minutes}m")
    while True:
        active = False
        for tag, tail in tails.items():
            for line in tail.new_lines():
                if tag == "SPAWNER":
                    if not TROUBLE.search(line):
                        continue
                    record_spawner_event(run_dir, line)
                _say(tag, line)
                active = True
        try:
            st = os.statvfs(root)
            for tag, detail in disk_events(st.f_bavail * st.f_frsize, disk_state):
                _say(tag, detail)
        except OSError:
            pass
        if active:
            last_activity = time.monotonic()
            stalled = False
        alive = bool(stale_bernstein_pids(root, cwd_memo))
        if alive:
            seen_alive = True
            dead_since = None
            port_file = root / ".sdd" / "runtime" / "server.port"
            port = 0
            if port_file.exists():
                try:
                    port = int(port_file.read_text().strip())
                except ValueError:
                    port = 0
            if port:
                with socket.socket() as sock:
                    sock.settimeout(2.0)
                    reachable = sock.connect_ex(("127.0.0.1", port)) == 0
                if reachable:
                    conn_fail_since = None
                else:
                    conn_fail_since = conn_fail_since or time.monotonic()
                    if orch_dead_due(conn_fail_since, time.monotonic(), orch_dead_last):
                        orch_dead_last = time.monotonic()
                        _say("ORCH-DEAD", f"bernstein processes are alive but 127.0.0.1:{port} has refused "
                                          f"connections for {(time.monotonic() - conn_fail_since)/60:.0f}m; "
                                          f"agents cannot report -- inspect the orchestrator and consider "
                                          f"killing the run")
            idle = time.monotonic() - last_activity
            if idle > stall_minutes * 60 and not stalled:
                stalled = True
                _say("STALL", f"no run activity for {idle/60:.0f}m with a live bernstein process; "
                              f"check the newest agent log mtime under .sdd/ and kill the session if stale")
                if until_stall:
                    return 3
        elif seen_alive:
            dead_since = dead_since or time.monotonic()
            if time.monotonic() - dead_since > end_grace:
                _say("END", "no bernstein process owns this root; run is over")
                return 0
        elif time.monotonic() - started > nostart_grace and time.monotonic() - last_activity > nostart_grace:
            _say("NOSTART", "no bernstein process ever seen and no activity; the run likely failed to launch")
            return 4
        time.sleep(interval)
